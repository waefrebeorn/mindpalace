# Making a green test run mean something

A `make test` that exits 0 proves only that the harness exited 0. Several
independent mechanisms in this repo turn real defects into green runs. Audit
for them whenever a suite is suspiciously clean or a family of targets is
never invoked. Check them in this order — Gate 0 invalidates every measurement
that follows, so settle provenance before you audit anything else.

## Gate 0: is the result you are reading even yours?

Audits here are worthless against a misattributed log. A background job's
completion notification reports the exit code of ONE invocation, while the log
file it names may hold a DIFFERENT one — your own foreground re-run overwrites
the file and the notification still reports the background job's code. Repeated
`/tmp` names across a sweep, a re-run, and a background job make this constant.

- **Unique log name per invocation.** Never reuse a name across a sweep, a
  re-run, and a background job. Write the exit code from the same subshell that
  writes the log so the pair is provably consistent.
- **Check log mtime against the clock before believing it.** A log older than
  the fix you just committed is a different build.
- **When a notification contradicts your own output, re-run with a fresh name —
  do not re-read the shared log.** Three sequential runs in one command is the
  cheapest disambiguation:
  ```sh
  for i in 1 2 3; do timeout 300 make test_battery > /tmp/bat_run_$i.log 2>&1; echo "run$i EXIT=$?"; done
  ```
- A repeated notification for a target you already re-verified carries no new
  information. Absorb it silently and move to the next finding.

**Two different misattributions look identical from the exit code alone; only
mtime separates them.** A filename collision gives you a log whose CONTENT is
green next to a reported `EXIT=2` — self-evidently inconsistent, so re-run.
A genuinely stale snapshot gives a coherent log from an OLDER BUILD that is
legitimately failing. Tell them apart by what it names:

    stat -c '%y' /tmp/x.log && date '+now: %H:%M:%S'

If the failures it lists are bugs you already fixed, it is a pre-fix frame. A
sequence of stale logs will often show the suite mid-repair — result-set counts
and failure lists stepping monotonically toward the present — which confirms
provenance faster than any single log can. Do not act on either without a fresh
run under a unique name.

Beware a grep that finds nothing: it is not evidence of absence. A healthy test
may use a different success marker than the one you searched for (one target
prints `RESULT: PASS` rather than a `Results: N/N passed` line), and a suite-wide
`grep -c FAIL` matches `FAIL` inside source code and in PASS/FAIL banner macros.
Match on the harness's own failure line — `grep -cE '^make.*Error [0-9]'` — and
read any remaining hit before calling something broken.

## Verify a guard macro is defined on the path you are testing

Any fix hinging on an `#ifdef HOSTED`-style guard must confirm the macro is
actually passed by the rule that compiles that file. A correct guard compiled
out behaves exactly like a wrong one, and the diagnosis then spirals into
re-debugging code that never ran.

**The tell: a temporary diagnostic placed inside the guarded region prints
nothing at all.** Silence of a diagnostic means the code did not run — suspect
the build, not the logic. This is what finally located the cause after two
plausible-but-wrong libc theories.

Check the flag is on the rule owning the file, not a neighbour with a similar
name. Here the cached `build/testobj/%.o` rule passed `-DWUBU_HOSTED`, but the
test recipes that compile sources *directly* mostly did not — 242 of 292
omitted it, so guards in those files compiled to nothing. Count before trusting:

```sh
grep -c 'DWUBU_HOSTED' mk/tests.mk   # compare against recipes compiling from source
```

Corollary for this repo: a recipe whose link line lists source files DIRECTLY
(never `build/testobj/*.o`) has its own compiler flags. Adding `-I` or a
feature macro to the cached-object rule does nothing for it.

## Gate 1: is the target reachable at all?

A `test_*` target nothing depends on is a target nobody maintains. Its link
line rots, its assertions go stale, and `make test` stays green because it
never runs.

Compute reachability from the prerequisite graph, not by grepping the
aggregate line — tier aggregates delegate, so the aggregate's direct
prerequisites are a small fraction of what actually runs. Walk `test:`'s
transitive prerequisites, resolving `$(VAR)` expansions, and report every
`test_*` rule that is defined but not reached.

Wire that walk into the build as a gate with a checked-in baseline of the
known orphans, so new orphans fail the build and the list can only shrink.
The baseline is an adoption list, not a cleanup mandate: refusing to build on
300 existing orphans guarantees nobody ever adds the check.

Negatively test the gate before trusting it: add a fake unwired target and
confirm the build stops and names it.

Corollary: after fixing a target's link rot, WIRE IT INTO THE AGGREGATE in
the same change. Fixing an unwired target leaves the rot one recompile away.

## Gate 2: does the test report anything?

Exit code without output is not a pass. A test whose every `printf` is
swallowed will exit 0 no matter what it asserts.

Measure, don't assume:

    for b in build/testbin/test_hw_*; do
      o=$(timeout 20 "$b" 2>/dev/null | wc -c); [ "$o" -lt 200 ] && echo "$b silent"
    done

Debug the shape "prints a header then exits nonzero with no diagnostic" by
proving the code ran and the output vanished:

- gdb `break` near the end of `main`; if it is HIT while stdout holds only a
  few bytes, the logic is fine and the output path is broken.
- gdb `break printf` and read the reported source file. If it resolves to an
  in-repo libc rather than glibc, you have found it.

Compare a passing sibling against a failing one. Identical link lines apart
from each test's own source file prove the passing one is equally broken
rather than the failing one being special — that single comparison is what
turns "three flaky failures" into "the whole family is silent".

### The shadowing is not only stdio — check the allocator too

When an in-repo libc is linked into a userspace test binary it shadows glibc for
every symbol it defines, not just the output functions. Here `libc.c` also
overrode `malloc` onto the kernel allocator, which returns NULL outside the
kernel, so **glibc's own `fopen` failed**: it allocates a FILE buffer, gets
NULL, and returns NULL. Every hosted test reading `/proc` or `/sys` was reading
nothing, and hardware probes reported every field as zero on a 12-core host.

Generalize: once you find one glibc symbol shadowed, enumerate ALL symbols the
in-repo libc defines and reason about which glibc internals call back into them.
Fixing only stdio leaves glibc itself broken.

### A self-defined libc function can compile into a call to ITSELF

Shadowing has a second, quieter form that has nothing to do with glibc. GCC's
`loop-distribute-pattern` pass recognises a canonical byte loop and rewrites it
into a call to the library function of that name. Inside a function that IS
that name, the rewrite links the function to itself:

```c
void *memset(void *s, int c, size_t n) {      /* correct byte loop */
    uint8_t *p = (uint8_t *)s;
    while (n--) *p++ = (uint8_t)c;             /* -> call memset (itself) */
}
```

Symptom: infinite recursion with a backtrace of the SAME address repeated
until the stack dies, crashing on the first allocation of any program:

```
#0  memset ()   #1  memset ()   #2  memset ()   ... (12+ identical frames)
```

It looks like a stack overflow or a bad pointer; it is neither. Audit the
source and you will find nothing wrong with it, which is the tell. Fix by
keeping the loop as written:

```c
__attribute__((optimize("no-tree-loop-distribute-patterns")))
void *memset(void *s, int c, size_t n) { ... }
```

Applies to any self-named libc function with a recognisable loop (`memset`,
`memcpy`, `strlen`, `strcmp`). It hides in plain sight when few recipes link
the file — count the linkers before concluding the bug is rare:

```sh
grep -c 'libc\.c' mk/tests.mk
```

After the fix, confirm the freestanding build still EXPORTS its own copies
rather than silently dropping them: `nm src/kernel/kernel.elf | grep -E ' [Tt] (memset|memcpy|strlen)$'`.

- An override that delegates to a kernel-only allocator must fall back to
  something usable in hosted builds, or be guarded by the same hosted macro.
  A constructor is the reliable bring-up point — it runs before `main`, so it
  also covers glibc internals that allocate before any test code runs.
- `free()` must not hand pointers from a bump arena to the kernel allocator;
  that corrupts its bookkeeping even when allocation appears to work.
- Verify with a MINIMAL probe linked against the same objects rather than by
  reading the source:
  ```c
  FILE *f = fopen("/proc/cpuinfo","r");
  printf("fopen = %p\n", (void*)f);   // (nil) = the real defect, in one line
  ```

Beware the recovery heuristic: "printed under 200 bytes" flags concise tests
too. Check actual content before calling a binary silent — legitimate
summary-style tests print `=== BCACHE TESTS: 13 passed, 0 failed ===` and are
fine. Confirm with a real pass count, not a byte threshold. After a fix, re-run
the silence check and read every remaining hit.

## Gate 3: is the code under test actually reachable?

A helper that exists but has zero callers is a missing dispatch arm, and the
missing arm compiles to nothing silently. `emit_sbc()` sat fully written in
`wubu_isa_6502.c` while `MIR_SUB` had no `case`, so every subtraction
evaluated to 0 and three tests failed. Whenever an arithmetic/logic result is
uniformly zero, look for the helper that is implemented but never dispatched
before suspecting the arithmetic.

## Measuring a family cheaply

Building 200+ targets one at a time costs an afternoon. Run them in a
detached shell with a per-target log, then count outcomes:

    (setsid sh -c 'for t in $(cat targets); do make $t > /tmp/hw_$t.log 2>&1 \
      && echo "OK $t" || echo "FAIL $t"; done > /tmp/hwall.log' </dev/null &)

`||` not `-&&` on the make line: a target that fails to LINK must still be
recorded, and `make` reporting success while the binary then fails at runtime
is exactly the case you are hunting.

Put the loop in a SCRIPT FILE rather than a nested `sh -c` one-liner. Quoting
`$0`/`$(basename ...)` through two levels of shell mangles the argument and you
burn a cycle on `unexpected EOF` before anything runs. Parallelize with
`xargs -P 6 -n 1` to cut wall time roughly sixfold:

```sh
xargs -a /tmp/hwlist.txt -P 6 -n 1 sh -c '
  t="$0"; b=$(basename "$t")
  if timeout 400 make "$t" > "/tmp/hwrun/$b.log" 2>&1; then echo OK > "/tmp/hwrun/$b.rc"
  else echo FAIL > "/tmp/hwrun/$b.rc"; fi
'
```

## Triage a sweep before fixing anything

With per-target logs, CLASSIFY first and fix in category order — fixing one at a
time in alphabetical order re-derives the same root cause repeatedly:

```python
for t in failed:
    lg = open(f"/tmp/{t}.log", errors="replace").read()
    if "No rule to make target" in lg:         norecipe.append(t)
    elif "undefined reference" in lg:         link.append(t)
    elif re.search(r"error:", lg):            compile.append(t)
    elif re.search(r"[1-9][0-9]* failed", lg): assert_.append(t)
    else:                                      runtime.append(t)
```

An all-link/all-compile sweep means the family rotted at the BUILD layer and
nothing was ever really testing. Zero entries in the assertion bucket is the
tell — you are looking at wiring debt, not logic bugs.

For the link bucket, diff a failing recipe against a WORKING sibling that needs
the same objects; the set difference is the missing list, ready to apply. Note
that a recipe may reference make variables that are never defined anywhere —
they expand to nothing, so the recipe silently links none of the sources it
appears to name and fails with a wall of undefined references. Check for that
before adding flags, and do not paper over it with a link-flag patch when the
recipe is structurally wrong.

When a remaining failure is CORRECT rather than a defect — a backend that
reports "cannot compile on this host" on an x86-64 box — read the source to
confirm before chasing it, and report the real ceiling instead of manufacturing
a fix.

## Cost

Removing the silently-swallowed output made a 216-target family rebuild from
scratch and roughly doubled full-suite wall time. Budget for it, and do it in
its own change so the regression signal stays readable.