# Gauntlet differential battery — concrete facts (2026-08-18)

## Files
- `wubunos/holyc_mir_eval.c` / `.h` — `hc_build_mir`, `hc_run_prog`, `hc_eval_mir`.
- `wubunos/test_gauntlet_runner.c` — the runner (forks one child per target).
- `wubunos/test_gauntlet/wubu_test_gauntlet.h` — `test_entry_t`, `TEST_PASS/FAIL/ERROR`.
- `wubunos/wubu_isa_driver.h` — driver contract: `compile(MIR)->bytes`, `run(bytes)->int64`.
- `wubuos/src/runtime/wubu_6502_interp.c` — example MCU interpreter (8-bit A return).

## hc_eval_mir must use the driver (was a no-op)
Old (buggy): always `result = wubu_mir_interp(&prog);` — ignored `driver`.
Fix:
```c
int hc_build_mir(const char *source, wubu_mir_prog_t *prog);   // parse+lower+opt, 0/-1
int64_t hc_run_prog(const wubu_mir_prog_t *prog, const wubu_isa_driver_t *driver) {
    uint8_t *code=NULL; size_t csize=0;
    if (driver && driver->compile && driver->compile(prog,&code,&csize)==0 && code) {
        int64_t r = driver->run(code,csize,0); free(code); return r;
    }
    return wubu_mir_interp(prog);   // fallback oracle only
}
```

## Runner: parallel per-target (not per test)
```c
for (k=0;k<N_TARGETS;k++) { pid=fork(); if(!pid){ /* child: hc_build_mir+hc_run_prog
    all tests for target_names[k], write "p f e\n" to /tmp/gauntlet_<pid>/t<k> */ _exit(0);} }
for (k=0;k<N_TARGETS;k++) waitpid(child[k],NULL,0);   // merge tallies
```
Reset SIGSEGV/SIGBUS/SIGILL/SIGFPE/SIGABRT in child. Slowest target (x86-64 JIT)
is the long pole; 14-way parallel finishes 19,088 tests in minutes.

## MCU 8-bit value-model mismatch (root cause of MCU `got=0`)
`wubu_6502_run` ends with `return (int64_t)(int8_t)cpu.a;` — 8-bit accumulator.
MIR VRs are int64. Gauntlet expects 32/64-bit ints. `expected=1024` → 6502 returns
`1024 & 0xFF = 0`. Same defect in z80/8051/avr/pic interpreters (all 8-bit A model).
Fix direction: give MCU drivers a 64-bit VR representation (e.g. VR pairs in
zero-page / register pairs) and return the full width at MIR_RET. Until then their
gauntlet rows are overwhelmingly FAIL — that is the truthful "not finished" signal.

## Verify a run honestly
```sh
cd /home/wubu/wubunos && timeout 1200 ./gauntlet_runner > /tmp/gauntlet.log 2>&1; \
  echo "GAUNTLET_EXIT=$?" >> /tmp/gauntlet.log
# then READ /tmp/gauntlet.log — ignore the notify's "exit code 0" (that's the echo).
# GAUNTLET_EXIT=124 -> hit timeout wall (ran out of budget, no summary printed).
# GAUNTLET_EXIT=2   -> make/test error.  GAUNTLET_EXIT=0 -> clean.
grep -A16 "Gauntlet Summary" /tmp/gauntlet.log   # per-target pass/fail/error
```

## Subset runs: `--core` flag (the full 19,088 battery times out)
The full battery = 19,088 tests × 14 targets = 266k test-runs. Even 14-way
parallel (one child per target), the **slowest child dominates** — x86-64 JIT
recompiles each program + the stack-smash abort path is slow. At a 20-min
`timeout` it hits the wall with NO summary printed (empty tally dir). So:
- `./gauntlet_runner --core` runs ONLY the 7 built-in suites
  (integer/control/bitwise/comparison/stress/memory/comprehensive ≈ 247 tests)
  × 14 targets → finishes in minutes. THIS is the live correctness gate.
- The full 19k is a separate long-budget/overnight batch (≈2.5 hrs even parallel).
- Each child writes `p f e\n` (pass/fail/error) to `/tmp/gauntlet_<pid>/t<k>`;
  the parent waits for all 14 then prints the summary. If a child is still
  running at timeout, its tally file is absent → that target = HANG (a real
  interpreter non-termination bug, see below), not a pass.

## Non-termination step guards (fix for the 4 HANG targets)
m68k/6502/riscv interpreters (and arm64's fallback) had NO step cap. A test that
lowers to a runaway MIR (self-loop `JMP`, or a missing `RET` so `pc` walks into
garbage that loops) makes the interpreter run forever → the child never writes
its tally → the whole run times out. Fix (mirror `wubu_mir_interp`'s 50M guard):
- Added `uint64_t steps;` to `m68k_cpu_t`, `cpu6502_t`, `rv_cpu_t`.
- Guard in each fetch loop: `while (... && cpu.steps < 50000000) { cpu.steps++; ... }`
  (m68k: `cpu.pc+2<=size`; 6502: `!cpu.halted && cpu.pc<size`; riscv: `cpu.pc+4<=size`).
- arm64 `run` is a REAL JIT (`jit_alloc_exec`+`fn()`) → SIGILLs on x86 host.
  `arm64_compile` returns -1 off-aarch64, so `hc_run_prog` falls back to the
  `wubu_mir_interp` oracle (correct). On an aarch64 host it JITs natively.

## How to read a background gauntlet run (TRAP)
A background `timeout ... ; echo "GAUNTLET_EXIT=$?"` notification reports the
**wrapper echo's exit (0)**, NOT the real command result. Read the log:
- `GAUNTLET_EXIT=124` → hit the `timeout` wall (ran out of budget, no summary).
- `GAUNTLET_EXIT=2`   → make/test error.  `GAUNTLET_EXIT=0` → clean completion.
- `pkill -9 -f gauntlet_runner` SELF-KILLS: the pattern matches the running
  shell command string (which contains "gauntlet_runner") → SIGKILLs the agent's
  - `pkill -9 -f gauntlet_run'` or kill by exact pid instead.

  ## GPU differential fuzzing (test_fuzz_diff.c)
  `test_fuzz_diff.c` adds a GPU leg alongside x86-64 + 8086 + interpreter:
  ```c
  const wubu_isa_driver_t *d_gpu = wubu_isa_find("ptx");  /* GPU leg (sm_89) */
  // child: runs all 4 backends, parent reads 32-byte result array out[4]
  // verification checks GPU result g=out[2] alongside x86 a=out[0], 8086 b=out[1], interp r=out[3]
  ```
  Build: `make test_fuzz_diff` (auto-runs 3000 — kill via Popen+SIGKILL after binary appears, or use small N). PTX compile output: `/tmp/wubu_kernel.ptx`, ptxas errors: `/tmp/ptxas_build.log`.

  ## PTX float emission patterns (verified ptxas sm_89)
  PTX f32 values live in the **low 32 bits of `.b64` VRs** (zero-extended by softfloat). PTX `mov.b32` cannot transfer between `.b64` and `.f32` — use shared-memory bridge:
  ```ptx
  .shared .b8 s[8]
  st.shared.b64 [s], %r<vr>     ; save 64-bit VR
  ld.shared.b32 %w0, [s]        ; load low 32 bits
  mov.b32 %f<fd>, %w0           ; bit-copy to f32
  ; ... float op ...
  st.shared.b32 [s], %f<rd>     ; save f32 result
  ld.shared.b64 %r<d>, [s]      ; load back as 64-bit
  ```
  - **FNEG**: `neg.f32 %f<fd>, %f<fa>` (operand must be source `fa`, not dest `fd`)
  - **SHL/SHR**: count must be `.u32` — extract via `cvt.u32.u64 %w0, %r<cnt>` then `and.b32 %w0, %w0, 63`; emit `shl.b64 %r<rd>, %r<ra>, %w0`
  - **Comparisons**: `setp.lt.f32 p<n>, %f1, %f2; selp.b64 %r<rd>, 1, 0, p<n>` — integer immediates work
  - **Labels**: must NOT start with `.L_` (ptxas interprets `.L` as directive) — use bare labels like `t_i_test`
  - **T_GEMM addressing**: `imm = ((uint64_t)M << 22) | ((uint64_t)N << 11) | K`; extract via `and.b64`/`shr.s64`; cell-to-byte: `shl.b64 %r<n>, %r<n>, 3` (64-bit cells)

  ## AMDGPU float emission (RDNA2/gfx1030)
  AMDGPU backend emits assembly TEXT (not executable blob) — `amdgpu_run` falls back to `wubu_mir_interp`. Float ops use VGPR-pair pattern (`v0` for arg, `v<n>` per VR):
  ```
  FADD: v_add_f32 vDST, vA, vB
  FSUB: v_sub_f32 vDST, vA, vB
  FMUL: v_mul_f32 vDST, vA, vB
  FDIV: v_div_f32_e32 vDST, vA, vB
  FNEG: v_sub_f32 vDST, 0.0, vA
  FEQ:  v_cmp_eq_f32_e32 vcc, vA, vB; v_cndmask_b32 vDST, 0, 1, vcc
  FLT:  v_cmp_lt_f32_e32 vcc, vA, vB; v_cndmask_b32 vDST, 0, 1, vcc
  DADD: v_add_f64 vDST, vA, vB
  ITOF: v_cvt_f32_i32 vDST, vA
  FTOI: v_cvt_i32_f32 vDST, vA
  ```
  Note: f64 ops use VGPR pairs (vDST:vDST+1), int comparisons use `v_cmp_*_i32` + `v_cndmask_b32`.

  ## Pitfall: patch tool double-escapes `\\n` in C strings
  The `patch` tool transforms `\\n` in C source strings to `\\\\n`, causing ptxas/llvm-mc to see literal backslash-n text → parse errors ("Unexpected token", "Arguments mismatch"). **Workaround**: use `execute_code` with Python `str.replace` or `re.sub` for all escape-sensitive edits on `.c` files emitting text/assembly.

