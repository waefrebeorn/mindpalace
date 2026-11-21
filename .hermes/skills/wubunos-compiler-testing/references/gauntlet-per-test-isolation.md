# Gauntlet per-test crash isolation (2026-08-19 fix → updated 2026-09-16)

## The bug it fixed

`test_gauntlet_runner.c` forks ONE child per target. That child loops over ALL
tests and writes its `p f e\n` tally to `/tmp/gauntlet_<pid>/t<k>` ONLY AFTER
the full loop (the original tail of the child). On the x86-64 native-JIT path,
some gcc-torture cases (e.g. `pr91137`) stack-smash → SIGABRT → the child dies
BEFORE writing the tally file. The parent's `fopen(t<k>)` then fails → it sets
`te[k] = g.n_tests` (all 19088 ERROR). So the full battery reported
`x86-64 0 / 0 / 19088` — a total false collapse, not real signal.

The 2026-08-18 "fork isolation" (per-target child + parent watchdog) handled a
child that NEVER returns, but NOT a child that dies mid-loop. That is the gap.

## The fix pattern (now in the runner)

Inside the per-target child, wrap EACH test in its own grandchild:

```c
int pfd[2]; pipe(pfd);
pid_t cpid = fork();
if (cpid == 0) {                 /* grandchild: THIS test only */
    close(pfd[0]);
    uint8_t buf[9];
    buf[0] = (uint8_t)TEST_ERROR;
    int64_t val = 0;
    wubu_mir_prog_t prog;
    if (hd_build_mir(t->source, &prog) == 0) {
        val = drv ? hd_run_prog(&prog, drv) : wubu_mir_interp(&prog);
        buf[0] = (val == t->expected) ? TEST_PASS : TEST_FAIL;
        wubu_mir_free(&prog);
    }
    memcpy(buf + 1, &val, sizeof(val));
    write(pfd[1], buf, sizeof(buf));
    close(pfd[1]);
    _exit(0);
}
close(pfd[1]);
/* reap grandchild with a PER-TEST 20s watchdog */
time_t t0 = time(NULL);
while (1) {
    pid_t r = waitpid(cpid, &st, WNOHANG);
    if (r == cpid) break;
    if (r == 0) {
        if (difftime(time(NULL), t0) > 20) {
            kill(cpid, SIGKILL); waitpid(cpid, &st, 0); break;
        }
        usleep(5000); continue;
    }
    if (r < 0) break;            /* ECHILD */
}
/* read 9-byte result, tally, then REWRITE tally file incrementally */
```

**Two key points:**
1. The tally file is rewritten (`fprintf(fn,"%u %u %u\n",p,f,e)`) AFTER EVERY
   TEST, not just at the end. So a crash loses only that one test (marked
   ERROR), and a watchdog-kill of the target child loses only the not-yet-run
   tail — never the work already done.
2. Per-test 20s watchdog, not just the per-target budget. A single hostile test
   cannot sink the whole target.

## Verified result

Full `./gauntlet_runner --dump-asm x86-64` went from `0/0/19088` to
`**247/247**` on `--core`. Full gauntlet: **390 FAIL, 0 ERROR, 18,698 PASS**.

The per-test isolation fix (2026-08-18) ensures crashes are isolated to individual tests,
not entire targets. A SIGABRT or stack-smash on one test does NOT corrupt the tally
for subsequent tests. This is verified working.

## Gauntlet-Only Regression Pattern (2026-09-16)

**PITFALL:** A test can pass when run individually (`gauntlet_runner --dump-asm x86-64 'source'`)
but FAIL in the full gauntlet run (`gauntlet_v3`). This is NOT a flaky test or timing issue —
it is a deterministic regression caused by running many tests in parallel workers.

**Observed case (2026-09-16):** Forward declaration resolution change (skipping forward decls
without body when resolving function calls) caused 5 `wcc_chapter_18_valid_no_structure_parameters_*`
tests to fail in gauntlet but pass individually. Net score change: 1,252 → 1,234 (-18).

**Root cause hypothesis:** The gauntlet_v3 runner uses multiple worker processes, each running
a subset of tests sequentially with fork-per-test grandchildren. The parallel workers share
the same filesystem (writing to `/tmp/gauntlet_*`) and possibly the same `prog.mem` layout.
A change that affects global state (function table ordering, memory layout, static variable
initialization) can cause different behavior when tests run in different orders or groupings.

**Diagnostic approach:**
1. Confirm the test passes individually: `gauntlet_runner --dump-asm x86-64 'exact source'`
2. Run gauntlet with `--only-target x86-64` to isolate from other targets
3. Run gauntlet single-worker to test if parallelism is the cause
4. Check if the failing tests share a common pattern (e.g., all use structs, all use forward decls)
5. Use `WUBU_DEBUG_MIR_BEFORE=1` to compare MIR output between individual and gauntlet runs

**Key insight:** When a change causes gauntlet-only regressions, the issue is often in
`mir_collect_funcs` or global state that depends on the order functions are parsed/compiled.
The individual runner compiles one test at a time; the gauntlet compiles many tests in sequence
within each worker, potentially accumulating state.

**CRITICAL:** Always verify changes with the FULL gauntlet, not just individual tests.
Individual passage is necessary but NOT sufficient — gauntlet-wide interaction effects are real.

## Extracting Individual Tests for Debugging (2026-09-21)

To debug a failing gauntlet test, extract its source from the test suite file and run individually:

```python
import ast
with open('test_gauntlet/suites/gauntlet_writing_c_compiler_full.c') as f:
    content = f.read()
idx = content.find('"wcc_chapter_XX_test_name"')
start = content.rfind('{', 0, idx)
depth = 0
for i in range(start, len(content)):
    if content[i] == '{': depth += 1
    elif content[i] == '}':
        depth -= 1
        if depth == 0: break
entry = content[start:i+1]
# Parse the source string (second field)
src_start = entry.index('"', entry.index('"', entry.index('"')+1)+1) + 1
# Find end of source string (handle escaped quotes)
i = src_start
while i < len(entry):
    if entry[i] == '\\': i += 2; continue
    if entry[i] == '"': break
    i += 1
source = ast.literal_eval('"' + entry[src_start:i] + '"')
with open('/tmp/test_extract.c', 'w') as f:
    f.write(source)
```

Then run: `./gauntlet_runner --dump-asm x86-64 "$(cat /tmp/test_extract.c)"`

**ALWAYS confirm a fix with the full gauntlet** (`timeout 300 ./gauntlet_v3 | grep '"pass"'`),
not just the individual test. Build with `rm -f gauntlet_v3 && make gauntlet_v3` to avoid stale binaries.