# test_hw_* bulk regeneration + cached-object build recovery (2026-08-12)

Context: `mk/tests.mk`'s ~215 generated `test_hw_<mod>` targets were corrupted
(by earlier dedupe scripts) AND each recompiled 283 kernel `.c` inline per run
(~30s each). Recovered by regenerating + converting to a shared cached-object pool.

## Verified working recovery path
- `tools/find_core_modules.py` — iteratively links the full kernel `.c` set with a
  probe selftest + `wubu_test_stubs.c`, removes files that cause undefined/multiple
  refs, writes the surviving ~283-file list to `/tmp/core_modules.txt`. It excludes
  arch/boot files (crt0, boot, isr_stubs, tasking, wubu_self_test, metal_main) and
  `_test.c`/`_selftest.c` files.
- `tools/gen_stubs.py` — builds `wubu_test_stubs.c` for symbols the selftests call but
  no compiled module defines. MUST use `nm` on compiled `.o` to find defined symbols,
  and only stub function-shaped calls (`wubu_\w+_\w+`, not bare `wubu_\w+` module names).
- `tools/regenerate_tests_mk.py` — writes `mk/tests.mk` (preamble + `CACHE := build/testobj`
  pattern rule + 215 targets). Classifies each module Type A (selftest doesn't call
  `wubu_hw_detect()`) vs Type B (does).

## Link-error traps (each bit this session, committed)
1. **CACHE dir must not be under `$(KERNEL)/`.** `mk/pattern-rules.mk` has
   `$(KERNEL)/%.o: $(KERNEL)/%.c`. A cache pattern rule `$(CACHE)/%.o` with
   `CACHE = $(KERNEL)/.testobj` fails to match ANY target ("No rule to make target
   src/kernel/.testobj/ahci.o") — even in an isolated 5-line Makefile. Fix: sibling dir,
   `CACHE := build/testobj`. Then the rule matches and objects cache correctly.
2. **Python list into Makefile deps via f-string emits `['a','b']` literal.** Always
   `deps_str = ' '.join(dep_files)` before embedding in the target.
3. **Module compiled fresh + its own cached `.o` linked = `multiple definition`.** For
   `test_hw_<mod>`, exclude `wubu_<mod>.o` from the cached objs list for that target.
4. **`wubu_test_stubs.c` must not stub symbols the real modules define.** If it does,
   `multiple definition` against the fresh-compiled module.c. nm-verified gen_stubs avoids
   this; if you hand-add a stub, check it's not already in a compiled module first.
5. **`git checkout mk/tests.mk` reverts to a 1-target committed file.** The 215-target
   version was working-tree state, never committed. Commit the regenerator + the .mk as you
   go; the scripts + `/tmp/core_modules.txt` are the recovery path after a wipe.

## Segfault triage on WSL2 (Type B tests)
Type B tests call `wubu_hw_detect()` which walks sysfs/PCI and SEGFAULTS on WSL2 — expected
(CRASH 139), not a build regression. Two real code bugs surfaced while triaging:
- `libc.c` `snprintf`/`__snprintf_chk` used `char buf[512]` + `vsprintf` → format string
  >512B (e.g. `wubu_audio_pipewire_config()`'s ~811B PipeWire config) overflowed the stack →
  `__stack_chk_fail` at `snprintf`. Fix: delegate to `vsnprintf` (writes straight into the
  caller's buffer, no intermediate). Symptom: `__stack_chk_fail` in the backtrace.
- selftests fed a NULL from a string-returning stub into `strcmp`/`strstr` with no guard →
  segfault. Guard (`chain != NULL && ...`) and make string-returning stubs return a plausible
  constant (not NULL) when the selftest `strcmp`s them.

## Verification
- `make kernel` clean.
- `make test_hw_audio` cold = ~8s (compiles 283 cached objs once); warm = ~0.48s.
- Full `tools/run_hw_tests.sh` = 211 pass / 3 fail (stub-string mismatch in hid, hw_detect,
  rtc) / 1 crash (kvfs: needs `mem_init()` for kernel heap in test env).
