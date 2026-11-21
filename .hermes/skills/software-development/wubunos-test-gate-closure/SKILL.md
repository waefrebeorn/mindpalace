# WuBu Test-Gate Closure — closing the `make test` gate the right way

Class-level skill for closing WuBu (wubunos) `make test` gate failures, from optimizer-sensitive segfaults to
link errors, with verified results — not claims. Scope spans BOTH the `wubunos` test tier (tgemm/amoeba gates)
and the `wubuos` kernel test tier (`src/kernel/test/` via `mk/tests.mk`). The kernel tier is governed by the
per-section init/shutdown isolation model in `references/kernel-test-suite.md`.

## Standing rules (always apply)
- Run each test target DIRECTLY, not piped, to see the true exit code:
  `./test_tgemm 24 24 24; echo exit=$?`.
- Verify with BOTH `-O0 -g` (reference-correct) and `-O3` (the gate). If they disagree, treat the build flags as the
  suspected root cause and prove it with gdb, not by guessing.
- Make recipe edits MUST preserve TABs (recipe lines start with `\t`). Prefer Python splice via `execute_code` and
  verify with `cat -A` (recipe command lines must show `^I`, not spaces) and `make -n <target>` first.
- A GREEN `make test` gate does NOT mean `src/apps/*` or `src/tools/*` compile. After any app/tools source change,
  run `make <app-target>` / `make tools` explicitly.
- Don't trust stale handoff diagnoses — read the ACTUAL FAIL/segfault lines, then reproduce.

## Procedure — close a gate, verify with a real number

### Step 1 — Reproduce, read real output
1. `cd /home/wubu/wubunos && make clean >/dev/null 2>&1`
   `timeout 300 make test_tgemm 2>&1 | tail -5` — capture FAIL/segfault text.
2. Rebuild, then RUN the binary directly (no pipe):
   `timeout 60 ./test_tgemm 24 24 24; echo exit=${PIPESTATUS[0]}`.
3. If it segfaults, get a real backtrace BEFORE touching anything:
   `timeout 60 gdb -batch -ex run -ex "bt 25" --args ./test_tgemm 24 24 24`
   - If gdb is unavailable, note that as a blocker; do NOT guess a root cause.

### Step 2 — Isolate the true root cause
- Build the same sources at `-O0 -g` as the reference-correct binary and run it.
- Build at `-O3` (the gate's flags) and run it. If `-O0` passes and `-O3` crashes, an OPTIMIZER MISCOMPILE is the prime suspect.
- Common -O3 crash signatures: `clock_gettime()` / high-precision timing corrupting `main()` (stack layout via
  `-march=native -frename-registers -funroll-loops`). gdb points inside `clock_gettime()` -> `main()`.
- Do NOT claim "GPU/mem/cuda" or "softfloat" bugs from a theory alone. Verify with gdb + a minimal probe first.

### Step 3 — Fix the flag, not the code
When the root cause is an -O3 optimizer miscompile, fix the BUILD, not the source:
1. In the Makefile, give that target a local flag scrub that drops the aggressive flags:
   ```make
   $(eval CFG_TGEMM := $(filter-out -march=native -mavx2 -mfma -frename-registers -funroll-loops -O3,$(CFLAGS)))
   $(CC) $(CFG_TGEMM) -I. -I$(OS_ROOT) -o $@ $^ -lm
   ```
2. Re-run `make clean && make test_tgemm`. Exit must be 0.
3. Re-run `make test` for the live per-target tally; every target must read ✅ PASS.

### Step 4 — Close out cleanly
- Verify with explicit numbers: `=== TEST NUM run ===`, then the per-target results, then exit code.
- Clean diagnostic files (`rm -f /tmp/*.c /tmp/t*.c /tmp/test_tgemm*`) and re-check `git status --short` to see only intended changes.
- Record the verified result in the session report, not a handwave like "it works now".

## Pitfalls (generalizable rules)

### Kernel test-suite isolation (wubunos `mk/tests.mk`)
- **New kernel tests inherit a DEAD allocator+tasker.** Every `src/kernel/test/` section ends with
  `tasking_shutdown(); mem_shutdown();` (heap freed, task list drained, idle gone). A new section inserted
  anywhere MUST open with `mem_init(4*1024*1024); tasking_init();` in that order — `tasking_init` creates the
  idle task via `mem_alloc`, so `mem_init` must precede it. Without it `tasking_init` returns -1, every
  `task_create` returns NULL (count=0, cur=nil), and the failure looks like "the feature is broken" until
  you check init's return code. See `references/kernel-test-suite.md` for the full recipe contract.
- **Standalone probes without the recipe's defines miscompile.** Dropping `-DWUBU_NO_LIBM` from a
  `memory.c`/`tasking.c` probe leaves the malloc-backed allocator unseeded -> `mem_alloc` returns NULL ->
  false "create failed". Reproduce in-suite, never in a flag-stripped probe.
- **Host-only headers must NOT nest under `#ifndef WUBU_BAREMETAL`.** Recipes build the hosted variant with
  `-DWUBU_BAREMETAL=0` (defined-but-zero still satisfies `#ifndef` being false), so includes tucked inside
  that block are silently skipped and `mmap`/`PROT_*`/`MAP_*` are undeclared. At file scope only.
- **No `<unistd.h>` in a kernel TU that also includes `libc.h`.** glibc `pause()` conflicts with the
  kernel `libc.h` declaration (`conflicting types for 'pause'`); pull only `<sys/mman.h>` and use a 4 KiB
  page constant instead of `sysconf(_SC_PAGESIZE)`.

### Existing (wubunos tier)
- **patch mangles TABs in Makefile recipes** — when a patch touches recipe lines it can silently convert leading TABs
  to spaces (or drop the line), making `make` mis-handle the rule. Verify with `cat -A` (expect `^I`) before running.
  Prefer a Python splice (`content.split("\n")`, edit the exact line, "\n".join(...)) which preserves tabs reliably.
- **GREEN make test does NOT cover app/tools** — the gate compiles only the tier test binaries. `src/apps/*` and
  `src/tools/*` test binaries are NOT built by the gate. After editing an app/tools source, run the specific app/target
  manually to prove it still links and runs.
- **-O3 flag combos miscompile timing calls** — `-march=native` + `-frename-registers` + `-funroll-loops` on a fast CPU
  can corrupt `main()`'s stack layout so `clock_gettime()` segfaults. Confirm with `-O0 -g` reference + gdb before
  trusting the -O3 build.
- **Missing object in a link line -> undefined reference** — when a newly-real symbol appears, diff the failing recipe's
  `$(CC)` line against a neighboring successful target and add the missing `.o`. SWEEP: every recipe that links the
  changed `.c` must get the new module's `.o`, not just the target you touched.
- **spliced AM01 gate recipes in wubuwizard** — the `test_amoeba_shrink` gate failed at link with `silu`/`silu_deriv`
  undefined because the recipe linked `src/wubu_train.o` (which defines `wubu_bp_forward`/`wubu_bp_backward`/`wubu_bp_muon_step`
  and references `silu` from `src/wubu_ops.c`) without `src/wubu_ops.o`. Rule: after any object-level edit, diff the
  failing target's `$(CC)` line against a neighboring WORKING target, then `ls src/*.c` and `grep -rln "<symbol>" src/`
  to confirm the module exists before touching the link line. Verified by `make clean && make tools/test_amoeba_shrink`
  to a live exit code — never by a handoff's "it should link now".
- **Never add an `.o` to a Makefile by name without checking the source file exists first** — the wubuwizard
  `test_amoeba_shrink` gate failed at link because `wubu_calibration.o` was guessed into the recipe, but
  `src/wubu_calibration.c` does not exist in the tree, so `make` aborted before linking. Always `ls src/*.c` and
  `grep -rln "<symbol>" src/` to confirm the object's module exists before touching the link line.
- **Stale test binary masks a fix** — after any source edit, `rm` the specific binary, rebuild, then rerun. A stale
  object linked from an old compile is a classic bin that says "fails" right after your fix.
- **Don't trust a handoff's "environmental" label** — a handoff/paraphrase naming a root cause is a HYPOTHESIS, not
  ground truth. Re-derive the red from the actual FAIL lines before acting.

## References
- `references/kernel-test-suite.md` — WuBuOS kernel test-suite isolation model: per-section `mem_init+tasking_init`
  preambles, `mem_shutdown+tasking_shutdown` section endings, the `mk/tests.mk` CFLAGS family
  (`-DWUBU_NO_LIBM`/`-DWUBU_HOSTED`/`-DWUBU_BAREMETAL=0`), and host-header/flag-nesting traps for adding
  multi-variant kernel test recipes.
