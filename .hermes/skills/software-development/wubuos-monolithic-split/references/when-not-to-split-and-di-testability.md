# When NOT to Split + DI Testability for New Modules

Two hard-won lessons from the 2026-07-13 monolith-bust campaign, where the
genuine multi-concern monoliths (`vsl_nt_proc.c`, `wubu_bottles.c`,
`wubu_metal.c`) were split but the *remaining* large files turned out to be
cohesive cores or tightly-coupled residuals that MUST NOT be force-split.

=====================================================================
1. WHEN NOT TO SPLIT (the "simplify before extending" guard)
=====================================================================
The rule "no monolithic files" is SATISFIED once a file is a single concern.
Forcing further splits on the wrong shape creates WORSE code:

- **Cohesive single-concern core.** A file whose functions all share one
  subsystem (e.g. `fat32.c` = FS driver, `vsl_syscall_net.c` = network
  syscalls, `interrupt.c` = 71 ISR stubs + APIC glue, `wubucontainer.c` =
  container-engine driver) is ONE concern. Splitting it is cosmetic, not a
  real decomposition.
- **Tightly-coupled residual of an already-split module.** After extracting
  siblings (`explorer_*` has 10, `wubu_editor_*` has 3), the residual
  `explorer.c` / `wubu_editor.c` is the legitimate window/editor
  controller. Its functions call each other cyclically (e.g. everything calls
  `wubu_ed_current_tab`; undo records buffer ops). Splitting -> circular module
  deps + a GOD HEADER exporting nearly every symbol. That violates the
  "no god headers / self-contained modules" rule -- strictly worse than before.
- **Large-by-repetition, not by mixed concerns.** `interrupt.c` (71 boilerplate
  ISR stubs) is big but uniform. Splitting stubs into a module is fragmentation.

DETECTION RECIPE (run before splitting):
1. Group functions by name prefix / subsystem (grep `^(int|void|...)` + prefix).
2. Build the call graph: for each function, does it call a DIFFERENT concern's
   function? If concern-A funcs call concern-B funcs AND vice-versa -> circular
   -> DO NOT split (or only extract a leaf concern that is called but calls
   nothing back).
3. Check if siblings already exist (`ls src/.../<name>_*.c`). If 8-10 siblings
   exist, the residual is the core -- stop.

VERDICT LANGUAGE to report honestly (don't fabricate splits to "do work"):
  "The monolith frontier is exhausted for clean splits; remaining large files
  are cohesive cores or circular-coupled residuals. Forcing splits would
  require god-headers/circular-deps -- worse than current state."

=====================================================================
2. NEW MODULE + DEPENDENCY INJECTION (testable without shelling out)
=====================================================================
When you DO add a new module (feature work, not a split), make it REAL and
UNIT-TESTABLE even when its backend can't run in CI. Pattern proven by
`wubu_ns_bridge.c` / `wubu_ns_bridge_test.c` (29/29 green):

PROBLEM: a control module dispatches to backend APIs that shell out to
external tools (`arch-chroot`/`systemctl`/`wine`) which fail or HANG in CI.

PATTERN -- inject an ops table:
```c
typedef struct wubu_ns_svc_ops {
    int (*svc_start)(WubuArchd*, const char*, const char*);
    int (*svc_stop)(WubuArchd*, const char*, const char*);
    /* ... one fn ptr per backend op ... */
} wubu_ns_svc_ops_t;

/* production wires the real backend */
const wubu_ns_svc_ops_t wubu_ns_svc_ops_real = { real_svc_start, ... };
/* test injects mocks that record which op was called */
static int mock_start(...) { g_last_op = START; return 0; }
```

- The module's PURE dispatcher (`wubu_ns_svc_ctl(d,root,svc,cmd,ops)`) routes
  the verb to the right op. The test asserts ROUTING (correct op invoked) with
  mocks -- no backend execution.
- The test must NOT trigger a real exec that hangs. Trick used: for an action
  that would fork `wine`, construct a fixture that makes the backend FAIL FAST
  (e.g. a PROTON bottle with a bogus `prefix_path` -> `access()` on the launcher
  fails -> returns -1, no fork). Verifies routing without hanging.
- ANGEL-CODER GOTCHA surfaced here: `wubu_bottle_run` blindly `fork()`+`execl`
  +`waitpid` on `wine` -> HUNG in CI (wine present but no prefix). FIX: resolve
  the real launcher (`<prefix>/proton` absolute, or `wine` via /usr/bin//bin)
  and refuse to fork a missing binary (return -1 fast). A run that launches a
  missing binary must ERROR, not BLOCK.

MAKE INTEGRATION for a new module:
- Add `<name>.o` to `RT_OBJS` (near a sibling) -- edit Makefile ONLY via
  `patch` or a `terminal` Python `open()` script (NEVER hermes_tools
  read/write_file on Makefile -- it truncates to 500 lines; see
  wubuos-build-recovery).
- Add a `test_<name>:` target modeled on an existing one. If the module links
  a TU that defines `main()` (e.g. `wubu_archd_daemon.c`), add `-DWUBD_TEST_MAIN`
  to the COMPILE line (not the link line) so its `main` is renamed and doesn't
  collide with the test's `main`.
- Wire the test into `test_medium_other` (or the relevant tier) so it runs in
  `make test`.
- Every new module ships with a `*_test.c` asserting file<->API routing, like
  the ns_bridge (29/29). No stubs.
