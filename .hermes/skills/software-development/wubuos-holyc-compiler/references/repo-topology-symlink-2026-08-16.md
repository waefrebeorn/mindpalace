# Repository Topology — wubuos (OS) vs wubunos (compiler)

> **CORRECTED 2026-08-16.** Authoritative, single-source layout lives in
> `wubuwizard/docs/TOPOLOGY.md` (§3). This note is a compressed reminder.

## The truth (user-corrected)

- `/home/wubu/wubuos/`  = **WuBuOS**  = THE BODY (OS, kernel, GUI).  Branch `wubu-integration`.
- `/home/wubu/wubunos/` = **WuBuNOS** = THE COMPILER (HolyC/MIR/14 ISAs). Branch `main`. **Real repo — not a symlink.**
- `/home/wubu/wubuwizard/` = THE BRAIN.

Linkage: `wubuos/src/compiler` is a **symlink → wubunos**. The OS Makefile reaches compiler sources via `$(COMP) = src/compiler`. There is **no compiler submodule** (the old `.gitmodules` entry is removed). `wubuos/src/brain` is the real gitlink submodule → wubuwizard.

## The bug this note fixes

Earlier docs claimed `wubunos` was a symlink to `wubuos` (FALSE) and that
`src/compiler` was a gitlink submodule (FALSE). Those claims caused:
- duplicate-stray compiler files in `wubuos/tools/` (`holyc.c`,
  `test_gauntlet_runner.c`, `isa-test/`, `peephole_superopt/`,
  `dev/compiler_diff.c`),
- a stale `.gitmodules` entry,
- the `tools/...` vs `$(COMP)/...` path confusion in `mk/tests.mk`.

All resolved: compiler sources now live **only** in `wubunos`; the OS
build reaches them through the `src/compiler` symlink.

## Edit rule

Edit compiler files **ONLY in `/home/wubu/wubunos/`**. They appear at
`wubuos/src/compiler/` for the Makefile via the symlink. Running
`git submodule update --init src/compiler` is a no-op / will fail — it is
not a submodule.

## Compiler bug recipes (unchanged from 2026-08-16 — real fixes, still valid)

These are compiler *bugs*, not org issues — their fixes apply whether you
build in wubunos or via the OS symlink:

- **Gauntlet runner double-execution**: `tools/test_gauntlet_runner.c`
  called `run_test_x86_64()` in the loop AND again after — doubled every
  JIT execution → segfault at test ~132. Fix: save `x86_result`/`x86_actual`
  from the loop, reuse for display. (Now `wubunos/test_gauntlet_runner.c`.)
- **32-bit signed overflow**: JIT uses 64-bit regs but HolyC `int` is
  32-bit. Emit `cdqe` after integer ADD/SUB (skip for pointer arithmetic,
  `pointer_elem_scale > 1`; don't emit before epilogue).
- **POST_INC/DEC on non-IDENT lvalues**: `a[1]++` crashed. Use the
  sized load/store sequence (`mov eax,[rdi]` not `mov rax,[rdi]`).
- **Braced array initializers**: handle `HC_AST_BRACE_INIT` +
  `case HC_TOK_LBRACE` in `parse_primary`.
