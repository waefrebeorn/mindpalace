# Compiler Gauntlet (test_gauntlet_runner) — debugging notes

The `make test` gate (WuBuOS) and the **compiler gauntlet** (`src/compiler/test_gauntlet_runner.c`)
are SEPARATE harnesses. The gauntlet forks one child per ISA target (14: x86-64, 8086, m68k,
6502, riscv, z80, arm64, mips, 8051, avr, pic, amdgpu, ptx, wasm) and runs the canonical MIR
battery (`--core` = 247 built-in tests; full = 19088 per target) through each backend. It is the
oracle that proved the x86-64 JIT sign-extension bug and the ptx hang.

## Build the runner (hosted, C11, matches mk/tests.mk)
```bash
cd /home/wubu/wubuos
COMP=src/compiler JIT=src/jit RT=src/runtime
gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_HOSTED -include wubu_gnu_compat.h \
  -I$COMP -I$COMP/test_gauntlet -I$JIT -I$RT \
  $JIT/jit.c $JIT/jit_encode.c $JIT/wubu_x86.c $JIT/wubu_disasm.c \
  $JIT/jit_minic.c $JIT/jit_minic_expr.c $JIT/jit_minic_token.c $JIT/jit_minic_type.c \
  $JIT/jit_minic_loop.c $JIT/jit_minic_cg.c $JIT/jit_branch_profile.c $JIT/x86_regalloc.c \
  $JIT/jit_codegen_x86.c $JIT/jit_codegen_arm64.c $JIT/jit_codegen_rv64.c $JIT/jit_codegen_wasm.c \
  $JIT/wubu_wasm.c $JIT/wubu_rv64.c $RT/wubu_spawn.c \
  $COMP/holyc_lexer.c $COMP/holyc_parse.c $COMP/holyc_parse_ast.c $COMP/holyc_codegen.c \
  $COMP/holyc_codegen_emit.c $COMP/holyc_codegen_expr.c $COMP/holyc_codegen_stmt.c \
  $COMP/holyc_codegen_api.c $COMP/holyc_mir_eval.c $COMP/wubu_preproc.c $COMP/holyc_runtime.c \
  $COMP/wubu_mir.c $COMP/wubu_mir_opt.c $COMP/wubu_mir_lower.c $COMP/wubu_mir_regalloc.c \
  $COMP/wubu_mir_interp.c $COMP/x86_peephole.c $COMP/wubu_isa_driver.c $COMP/wubu_isa_x86_64.c \
  $JIT/wubu_arm64.c $COMP/wubu_isa_arm64.c $COMP/wubu_isa_mips.c $RT/wubu_mips_interp.c \
  $COMP/wubu_isa_m68k.c $COMP/wubu_m68k_interp.c $COMP/wubu_isa_8086.c $COMP/wubu_isa_riscv.c \
  $RT/wubu_dos_emu.c $COMP/wubu_isa_6502.c $RT/wubu_6502_interp.c $RT/wubu_riscv_interp.c \
  $RT/wubu_dos_emu_mem.c $RT/wubu_dos_emu_regs.c $RT/wubu_dos_emu_alu.c $RT/wubu_dos_emu_int.c \
  $RT/wubu_dos_emu_decode.c $COMP/wubu_isa_z80.c $COMP/wubu_z80_interp.c $COMP/wubu_isa_8051.c \
  $COMP/wubu_8051_interp.c $COMP/wubu_isa_avr.c $COMP/wubu_avr_interp.c $COMP/wubu_isa_pic.c \
  $COMP/wubu_pic_interp.c $COMP/wubu_isa_amdgpu.c $COMP/wubu_isa_ptx.c $COMP/wubu_lang_router.c \
  $COMP/test_gauntlet/wubu_test_gauntlet.c \
  $COMP/test_gauntlet/suites/*.c $COMP/test_gauntlet_runner.c -lm -ldl -o $COMP/gauntlet_runner
```
NOTE: `gauntlet_stress.c` does NOT exist — the stress suite is `gauntlet_stress_test_count` inside
`wubu_test_gauntlet.c`. Do not add it to the link line (undefined ref). Present suite files:
comprehensive, gcc_torture, gcc_dg, gcc_compile, fujitsu, extern_gcc, compcert, c_testsuite,
llvm, lacc, tinycc, chibicc, writing_c_compiler, slimcc, integer, control, bitwise, comparison,
memory, float, string.

## CRITICAL: a hung gauntlet produces ZERO output and looks like "still passing"
The runner streams a `  FAIL <name> <target> expected=X got=Y` line ONLY when a test returns a
wrong *value*. It does NOT detect infinite loops. A JIT codegen bug that emits a loop with a
wrong back-edge or a loop variable that never updates makes the backend child **spin forever**
with NO new FAIL lines. This is invisible from the log alone.

**Diagnostic — distinguish "slow but progressing" from "hung":**
```bash
PID=$(pgrep -f "gauntlet_runner --core")
# children (each ISA target is a forked child):
for c in $(pgrep -P $PID); do ps -o pid,etime,time,stat,cmd -p $c; done
```
- A *progressing* child: `time` (CPU seconds) grows slowly and the FAIL-line count in the log
  increases.
- A *hung* child (JIT infinite loop): `time` keeps growing (observed 32 min of CPU) while the
  FAIL-line count is frozen at 0. That means the backend emits code that never terminates — e.g.
  `ctrl_while`/`ctrl_for` with a broken loop-back branch or a loop var that stays 0.

**This happened on x86-64:** integer-suite FAILs (constant sign-extension, see below) printed
early, then the child hung on control-flow/loop tests. The constant fix removed the 25 value-FAILs
but the *loop hang* is a SEPARATE bug in the branch/loop emission — still open.

**Kill hung runs by EXACT PID** (never `pkill -f gauntlet_runner` — the pattern also matches your
own shell command line and SIGKILLs the launcher; see the pkill-self-match note in SKILL.md):
```bash
kill -9 362974 362975 364073 364074   # use the real PIDs from ps
```

## `--target X` does NOT skip the other 13 targets
The runner forks all 14 children regardless; only the named one's results matter. So
`--target x86-64 --core` still launches the slow native-JIT siblings. Don't expect a fast
single-target run. The native x86-64 JIT on 247 tests is genuinely slow on this host (~10-20 min).

## ptx: fails fast by design (no GPU in this env)
`wubu_isa_ptx.c` `ptx_run` launches a CUDA host stub that blocks forever when no CUDA device
exists. Fix: a one-shot GPU probe — the first call arms `alarm(8)` in the forked child; if the
stub dies by SIGALRM, a `static ptx_gpu_unavailable=1` disables ptx for all remaining tests
(returning 0). The gauntlet parent also has a watchdog: any target exceeding its budget is
SIGKILLed and reported as `SKIPPED` (honest "not runnable here", not FAIL/ERROR). ptx cannot
produce real results without a CUDA device — that is an environment limit, not a code bug. The
first ~15 ptx evals may still read a stale garbage result file before the probe disables it; that
is cosmetic.

## x86-64 native JIT sign-extension class bug (FIXED, keep as a guard)
`wubu_isa_x86_64.c` `MIR_CONST` emitted `mov r32, imm32` (no REX.W). On x86-64, writing a 32-bit
register ZERO-extends to 64 bits, so negative constants were corrupted: `-2 → 0x00000000FFFFFFFE
(4294967294)`, `-2147483648 → 2147483648`. Fix: emit `REX.W` so `mov r64, imm32` SIGN-extends
(both register-dst and spilled-dst CONST paths). Lesson: on x86-64, 32-bit ops zero-extend —
ALWAYS use REX.W for 64-bit values. After the fix the gauntlet showed 25 x86-64 FAILs → 0
streamed FAILs (the remaining open issue is the loop *hang* above, not value corruption).

## Do NOT build a hand-rolled x86-64 harness that calls `drv->compile`/`drv->run` directly
A standalone main that does `drv = wubu_isa_find("x86-64"); drv->compile(...); drv->run(...)`
crashed (backtrace: `x86_run(code=stack-addr, size=1, arg=15)` — the function-pointer call lands
wrong through the struct). The gauntlet's `hc_run_prog` path works (it is the proven oracle).
Reproduce backend behavior through the gauntlet runner, not a bespoke harness — or call
`hc_build_mir` + `hc_run_prog(&prog, drv)` which uses the same vetted call path.

## THE inspection path that WORKS: `--dump-asm <target> <src>` (use this instead of a harness)
The gauntlet runner has a built-in single-source inspection mode (see `main()` in
`test_gauntlet_runner.c`, the `--dump-asm` loop). It uses the proven `hc_build_mir` +
`drv->compile` + `drv->run` path internally (the same code the `--core` battery runs), so it
never hits the isolated-harness ABI crash. Build via `make test_gauntlet`, then:
```bash
cd /home/wubu/wubuos
./src/compiler/gauntlet_runner --dump-asm x86-64 'I64 i=0; I64 s=0; while(i<10){s=s+i; i=i+1;} return s;'
# prints: "=== x86-64 asm for: ... ===", then "+<off>: 0x<hex>" per byte pair, then "result=<N>"
```
This is the fast, authoritative way to:
- **Inspect emitted bytes** for ONE source through ONE backend (compare against the x86-64
  manual for branch/loop opcodes: `E9 rel32` = JMP, `0F 84 rel32` = JZ, `85 C0` = test rax,rax,
  `48 B8 ..` = mov r64,imm, `48 01 F8` = add rax,rdi, `48 29 F8` = sub rax,rdi).
- **Reproduce a loop/branch hang** in isolation WITHOUT running the 10-20 min full `--core`.
  If `--dump-asm` spins forever, you have reproduced the infinite-loop codegen bug (run it
  under `timeout 15` so it returns instead of hanging your terminal).

### Loop-hang triage recipe (x86-64, still OPEN as of 2026-08-21)
The constant sign-extension fix removed 25 value-FAILs, but the x86-64 native JIT *still
hangs* on control-flow/loop tests (`ctrl_while`, `ctrl_for`, `ctrl_while_10`, ...). Symptom:
the gauntlet child `time` (CPU) grows unbounded (observed 32 min) while the FAIL-line count is
frozen — an emitted loop never terminates. The MIR for `while` is correct (`top:` cond;
`JZ done`; body; `JMP top`; `done:`), the interpreters execute it fine, and the emitter handles
`MIR_JZ`/`MIR_JMP`/`MIR_LABEL`/`MIR_RET` — so the bug is emission-specific (wrong back-edge
displacement, or a vreg that is clobbered across the loop back-edge so the loop variable never
updates). To localize, `--dump-asm` a minimal `while` and hand-check the JMP rel32 math:
- prologue starts at offset 0; `MIR_LABEL top` records `label_off = e.n` (byte offset in emitted code).
- `MIR_JMP top` pushes `PATCH_PUSH(e.n, top)` at the position of the rel32 (right after `0xE9`),
  then the patch loop does `rel = t - (pos + 4)`. That is correct IF `e.n` at push time points
  at the rel32's first byte. Verify the back-edge jumps *into* the loop body, not past it.
- Also eyeball the loop variable update: if `i = i + 1` is spilled, confirm the store/load use
  the SAME `VR_SPILL` slot and that the result of the ADD is actually written back (the
  NEXT_IS_RET lookahead skips the store when the next instr is RET — make sure a loop-body
  update is never mis-identified as RET-feeding).
Reference: the register allocator (`wubu_mir_regalloc.c`) is linear-scan SSA; a loop var reused
across the back-edge has a live range spanning the JMP, so it must stay in a register (or a
consistent spill slot) across iterations.
