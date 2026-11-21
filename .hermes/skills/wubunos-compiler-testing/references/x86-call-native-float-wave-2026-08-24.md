# Native x86-64 enablement + CALL wave (2026-08-24)

Full transcript of the wave that took test_isa_driver from 179 → 195/195 with the
REAL x86-64 JIT driver linked in the standalone build, plus MIR_CALL on 9 backends
and native SSE floats. Commits f1dbe56..6d70879 on wubunos main.

## What was done (chronological)
1. **MIR_CALL architecture** — one pattern replicated across retro backends:
   entry trampoline JMPs over callee bodies; func start offsets recorded during
   emission; abs targets patched in a second pass; interp hostcall fns
   27 CALL (push pc) / 28 FUNC_RET (write vr0 slot, pop or halt).
   - 6502: dst=0 skips write-back; zp_slot layout.
   - z80: vr0 slot = addr 0 (vr*2 layout); LE targets.
   - 8051: LJMP target is BIG-ENDIAN → used EXT_JMP 0x26 / EXT_CALL 0x24 instead.
   - avr/pic: MEMOP-style opcode family; pic FUNC_RET reads via PIC_VR_BASE.
   - m68k: trampoline must come AFTER the global LINK prologue (shared A6 frame);
     FUNC_RET writes slot_disp(0) = -4 LSB lane.
   - 8086: dos_emu decodes undefined opcode 0xF1 as hostcall; slots are
     SS-relative → phys(e, ss, off); BE abs16 targets (double-swap bug found).
   - riscv: JAL trampoline placed AFTER the fp/sp prologue (skipping it left
     x8=0); JAL offsets are PC-relative; FUNC_RET writes the vr0 frame slot.
   - mips: custom hostcall fns 27/28, word-addressed func offsets like labels.

2. **riscv x0 hardwiring bug (deep)**: the interp's JAL handler wrote
   `cpu.x[rd]` unconditionally — the trampoline's JAL x0 set x0=16, breaking the
   zero register invariant; every `addi rd, x0, imm` then computed garbage+imm
   (consts came back as value+16). Fix: `if (rd != 0)` guard + `cpu.x[0]=0`
   enforced at the top of every fetch loop iteration.

3. **x86-64 native floats** (all verified bit-exact vs softfloat oracle):
   FADD/FSUB/FMUL/FDIV (F3-prefix opss), FNEG (xorps sign mask),
   FEQ/FNE/FLT/FLE (ucomiss + setcc; NaN-safe equality = sete AND setnp;
   SETNP = 0F 9B — first attempt used 0F 9A = SETP, inverted results),
   ITOF/FTOI (cvtsi2ss/cvttss2si), DADD-family (movq + F2 SD ops),
   DITOF/DTOI (cvtsi2sd / cvttsd2si REX.W — 32-bit form truncated negatives),
   F32_TO_F64/F64_TO_F32 (cvtss2sd/cvtsd2ss, self-targeting ModRM C0 not C1),
   BF16 widen exact (shl 16) + narrow RNE ((x + 0x7FFF + ((x>>16)&1)) >> 16).

## The two root causes behind the [rbp+0] saved-RBP corruption

Symptom: JIT'd code segfaulted; disassembly showed stores to `[rbp+0x0]`.

1. **regalloc op_has_dst enum gaps** (`wubu_mir_regalloc.c`): any dst-producing op
   absent from `op_has_dst()` gets no live interval → assign[vr] stays at init
   values reg=-1/stack=0 → emitter stores through offset 0 = saved RBP.
   Found TWICE: float ops first, then ULT/ULE/UGT/UGE. A full programmatic audit
   (every enum member vs the case list, minus known no-dst ops) now shows NONE
   missing. Rule: adding ANY new MIR op requires updating op_has_dst.

2. **Driver-side defense**: `spare_off` emergency slot below the frame +
   `spill_off()` helper that falls back to it when VR_SPILL returns 0.
   Kept as defense-in-depth even after the root fix.

## Enabling the REAL driver in the standalone build

- Makefile: filter `wubu_isa_jit_stubs.c` out of ISA for test_isa_driver, link
  `wubu_isa_x86_64.c` + new `jit_stubs_arm64.c` (arm64-only stub split) +
  `jit_stub.c`. Needed a no-op `wubu_clear_cache` shim (jit_stub_x86.c for
  minimal links; wubu_isa_driver.c provides it in the full link).
- **JMP rel32 off-by-one**: patch pass computed `rel = t - (pos+4)` but E9 rel32
  is a 5-byte instruction — every jump landed ONE instruction past its target,
  skipping leave/ret. Fix: `rel = t - (pos + 5)`.
- Result: 195/195 (was 160 at wave start), T_GEMM 576/576 natively.

## T_GEMM AVX2 fast path

`wubu_tgemm.c`: 4-lane __m256i accumulation with emulated 64-bit multiply
(vpmullq needs AVX512DQ — emulate via lo/hi epu32 splits + shifts). Runtime
`__builtin_cpu_supports("avx2")` dispatch; scalar fallback intact. Measured
256^3 int64 GEMM: 26.0ms scalar → 7.3ms AVX2 (3.6x). Guard with
`#if defined(__x86_64__)` only (NOT `&& defined(__AVX2__)` — the function-level
`target("avx2")` attribute handles codegen; the macro isn't defined at -O0).

## Debugging playbook that cracked it

- Disassemble the EMITTED bytes (`objdump -D -b binary -m i386:x86-64 -M intel`)
  — wrong values that survive compile are almost always visible there.
- gdb on the harness binary; when the crash is inside JIT'd code, the faulting
  frame is x86_run calling fn() — dump the code buffer from the test instead.
- Stale object files lie: after editing an ISA file, `make clean` before trusting
  a "still failing" result (cost one false dead-end this wave).
- Per-pc fprintf tracing in the interpreter (inserted before the OP switch)
  pinpoints exactly which word desyncs execution — used for riscv/mips/z80/8051.
- Hex-transcribing dumps by hand into python `bytes.fromhex` produced THREE
  misreadings; always re-extract the byte string programmatically from the
  failing binary's own output.
