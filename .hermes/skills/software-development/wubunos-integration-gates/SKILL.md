---
name: wubunos-integration-gates
description: "Use when building or testing wubunos from the OS repo."
---
# wubunos ↔ wubuos Integration & Test Gates

Load when compiling the compiler through the OS build (`make compiler` in
/home/wubu/wubunos), when a wubunos test fails to link against compiler sources,
or after any frontend rename in /home/wubu/wubunos.

## Layout facts (verified 2026-08-23)
- `/home/wubu/wubunos` = THE COMPILER repo, branch `main`. Canonical checkout:
  edit files HERE only.
- `/home/wubu/wubunos/src/compiler` is a plain SYMLINK → /home/wubu/wubunos
  (NOT a git submodule; brain + container are submodules, compiler is not).
- wubunos reaches compiler sources via `COMP = src/compiler` (mk/vars.mk);
  object lists in `mk/objects.mk` (`COMP_OBJS`); test recipes in `mk/tests.mk`.
- Frontend was renamed `holyc_*` → `holyd_*` (git R100 history proves it).
  Any remaining `HC*`/`hc_*`/`holyc_*.c` reference anywhere in either repo is
  stale and will fail at compile or link time.

## Directory disambiguation (byte-exact)
The compiler and OS body repos differ by a single `n`:
- **Compiler** = `/home/wubu/wubunos` (7 chars w-u-b-u-n-o-s, WITH `n`) — `isa-test/`, `holyd_*.c`, branch `main`.
- **OS body**  = `/home/wubu/wubuos`  (6 chars w-u-b-u-o-s, NO `n`) — `mk/` + `src/kernel/`, branch `master`, remote `waefrebeorn/WuBuOS`.
Both lowercase, so never read the path by eye. Registry `module` is repo-relative (`wubunos/...` = compiler, `wubuos/...` = OS): a `wubunos/` prefix on a `src/kernel/` module is a typo for `wubuos/` and must be corrected in the same commit that closes it.
When typing paths in shell/terminal, use Python auto-detection
(`os.listdir` + property check: compiler has `isa-test/`, OS has `mk/`+`src/`)
rather than typing the name — a single wrong character silently targets the
wrong repo. Verify symlink targets with `os.path.realpath()`.

## Rename-migration sweep (do all layers, not just one)
1. mk files: objects.mk COMP_OBJS, tests.mk source lists (use a single
   `HOLYD_SRC` var in vars.mk instead of repeating 10-file lists), pattern rules.
2. C includes: `"../compiler/holyc.h"` style paths across src/runtime, src/gui,
   tools/probe.
3. Type names: HCCompiler→HDCompiler, HCParser→HDParser, HCGen→HDGen,
   HCASTNode→HDASTNode, HC_AST_*→HD_AST_*, HC_TOK_*→HD_TOK_*.
4. Function names: hc_lex_init/hc_parse_init/hc_gen_init/hc_ast_free/
   hc_eval/hc_compile → hd_* equivalents. zealos_parity.h maps old ZealOS
   names onto these — update its RHS too.
5. Known-good sweep command shape: grep -rl --include='*.c' --include='*.h'
   (never grep binaries; use errors='replace' when rewriting in Python).

## JIT W^X trap: -DWUBU_HOSTED is load-bearing
`jit_alloc_exec` has two branches: WUBU_HOSTED → mmap RWX page (tracked in
g_jit_map, later mprotecd RX by jit_lock_exec); WITHOUT the flag → plain
malloc → executing the heap → SEGV si_code=SEGV_ACCERR at the first
instruction of the JIT'd code (gdb shows rip=code-buffer address, valid rsp,
bytes disassemble cleanly). Symptom pair "test segfaults but code bytes are a
perfect prologue" = missing -DWUBU_HOSTED, not a codegen bug.
Fix: every tests.mk target that JITs must carry -DWUBU_HOSTED. When editing
mk/tests.mk NEVER blanket-replace across all compile lines — multi-line
recipes (trailing `\\`) break; patch specific targets (test_holyd,
test_holyc_agi, test_jit family) or exact unique strings.

## Session-eval correctness requirements (wubu_holyd_exec.c)
Three things the standalone hd_eval path does that the REPL/session path MUST
also do, or evals crash or call garbage:
1. `hd_register_holyd_runtime(&gen)` before emit_prologue (else builtin calls
   emit `call 0`).
2. Patch n_call_patches rel32s into the exec copy AFTER memcpy (session-
   declared functions + personality builtins).
3. Call patches need the exec pointer AFTER any mprotect flip; keep writing
   through the RW pointer, lock only flips prot (same mapping).

## Test gates and their meaning
- wubunos `make test`: isa_driver (117/117 now) + softfloat (906/906) +
  peephole (4/4) + elf_cubin (3/3) + fuzz_diff (differential oracle).
- isa_driver float gate: `./test_isa_driver` prints
  `<isa>: fadd -> 40700000` (3.75 = 1.5+2.25) for every MCU interpreter.
  **All 8 green as of 2026-08-23** — each backend routes MIR_FADD/FRET through
  `wubu_softfloat.c` via a backend-specific escape opcode (6502=0x02,
  RISC-V=0x3F, Z80/M68K=0x0B00, 8051/AVR/PIC=EXT 0x20-0x21). Float is now a
  default gate. See `references/interp_float_hostcall_pattern.md`.
- wubunos `make compiler` then targeted `make test_holyd` (33 checks),
  `make test_jit`, `make test_battery` (selfhost battery; 149/155 as of
  2026-08-23 — known failures: globals-in-func ×3, pointer arith, ptr++/--×2,
  all real holyd-codegen bugs, next fix target).
- `make test_mir_battery` runs `tools/test_mir_battery.c` through `hd_eval_mir()` (HolyD → MIR → interpreter oracle). **Current: 69/69 passing.**
  Float path: fixed by storing float literals as IEEE-754 f32 bit patterns and routing float arithmetic through `MIR_FADD`/`MIR_FSUB`/`MIR_FMUL`/`MIR_FDIV` in `holyd_mir_eval.c`. All failures closed as of 2026-09-01. Do not regress the float fix.
  Parser fix: void parameter lists `f()` required a `fn_params_void_consumed` flag in `holyd_parse.c` so the `done_params` label doesn't double-consume the closing `)`. See `references/parser_void_params_fix.md`.
- Pre-existing dead target test_holyc_ptx references a nonexistent .c —
  disabled with a SKIPPED echo; PTX coverage lives in isa_driver/fuzz_diff.
- GDPR gate: EDR agent-action logging requires consent state at
  $WUBU_GDPR_STATE (format `A <age> <uuid7> <ts_ms>`). If /tmp/wubu exists as
  a FILE (stray binary), the state dir can't exist → silent event drop →
  mysterious test_holyc_agi audit failures. Move the stray file aside.
- `test_tgemm` target in mk/tests.mk builds tools/test_tgemm.c (576 correctness
  checks via the generic wubu_mir_interp). Ensure wubu_tgemm.c, wubu_mir_interp.c,
  wubu_softfloat.c are linked — add to any new test rule that includes ISA drivers.

## Soft-float hostcall wiring discipline (added 2026-08-23)
When a new MCU interpreter returns 0 for a float computation, it is NOT a
softfloat bug — the escape hatch is mis-wired. Check before touching
`wubu_softfloat.c`:
1. **pc double-advance.** fetch helpers already bump `cpu.pc`; the hostcall
   must NOT add a second manual advance after reading inline data words.
2. **const cell population.** MIR_CONST on 8-bit ISAs only stored byte 0;
   float operands need all 4 bytes → MIR_CONST must quad-store to the float
   cell.
3. **hostcall arg order.** MIR_FRET must emit the result SLOT as BOTH `dst`
   and `sa` — the interpreter reads `fa` from `sa` then writes `r` to `dst`;
   if they differ the result cell stays empty.
4. **frame base is an absolute address.** Subtract RAM size only once (at
   init); index slots as `mem[fp + disp]`, not `mem[fp-RAM+ disp]`.
5. **unified-memory ISAs** (Z80 copies `code[]` into `cpu.mem`) fetch the
   hostcall operands via `cpu.mem[pc]`, never a separate buffer.

## Debugging discipline that paid off repeatedly
- After ANY edit: rm the specific binary, rebuild, rerun — stale binaries
  produced three identical "failures" this session.
- Never diagnose from grep-piped output alone (pipes mask exit codes and
  truncate); run the failing binary directly.
- A JIT segfault whose bytes disassemble to a perfect prologue is an
  environment/flag problem (see W^X above), not a codegen bug — verify with a
  minimal mmap+memcpy+call probe BEFORE touching codegen.
- Two source trees for interpreters: driver-side files live in the wubunos
  repo ROOT (m68k/z80/8051/avr/pic interp + their isa_ drivers); runtime-side
  files live in wubunos/src/runtime (6502/riscv/mips interp + dos_emu). The
  Makefile OS_ROOT?=/home/wubu/wubunos/src symlink resolves both; edit the
  file that `make -n` actually compiles.
