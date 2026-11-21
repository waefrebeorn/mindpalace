# x86-64 native enablement wave (2026-08-24) — commits f1dbe56..4ea41a2

Session that took the standalone test_isa_driver from "real x86-64 driver unlinked,
179/179 with 16 COMPILE FAILs" to "REAL JIT driver runs every test natively, 195/195".

## Bugs found by disassembling emitted machine code (objdump -D -b binary)

1. **JMP rel32 off-by-one** (`wubu_isa_x86_64.c` patch pass):
   `rel = target - (pos + 4)` — but E9 rel32 is FIVE bytes. Every jump landed one
   instruction past its label; a jump to l_done skipped `leave/ret` → SEGV in x86_run.
   Fix: `rel = t - (pos + 5)`.

2. **regalloc op_has_dst omission** (`wubu_mir_regalloc.c`): `op_has_dst()` did not
   list float ops (FADD/FNEG/ITOF/FTOI/DADD/...). A float dst got no live interval →
   `assign[v].reg=-1, stack=0` → emitter stored through `[rbp+0]` = **saved RBP** →
   leave/ret jumped into garbage. Symptom signature: crash at
   `x86_run ... int64_t r = fn();` with "Cannot access memory at 0xffffffffffffffd8".
   Fix: register EVERY dst-producing op. Rule: **any new MIR op with a dst must be
   added to op_has_dst or the frame corrupts.** Now covers all float/double/bf16 cvts.

3. **SETNP vs SETP**: NaN-guard used `0F 9A` (SETP) instead of `0F 9B` (SETNP) —
   inverted FEQ/FNE results. setcc opcode table: sete 94, setne 95, setb 92, setbe 96,
   seta 97, setae 93, setp 9A, **setnp 9B**.

4. **Spill-slot loss on regalloc splits**: a vr that was register-assigned then split
   to memory kept `stack = 0` from its register days → same [rbp+0] smash.
   Fix: emitter gained `spare_off` (an extra slot below the frame, frame size +8) and
   all `VR_SPILL(in->x)` sites route through `spill_off(assign, count, &e, vr)` which
   returns `spare_off` when the computed offset is 0. This is robust regardless of
   future regalloc edge cases.

## Native instruction encodings added (all verified bit-exact)

- f32 arithmetic: stage operands in eax/edi → `66 0F 6E C0` movd xmm0,eax;
  `66 0F 6E CF` movd xmm1,edi; `F3 0F 58|5C|59|5E C1` addss/subss/mulss/divss;
  `66 0F 7E C0` movd eax,xmm0. (F2 prefix = scalar DOUBLE — wrong for f32.)
- compares: `0F 2E C1` ucomiss xmm0,xmm1 then setcc al (+ setnp-and for EQ/NE),
  `0F B6 C0` movzx eax,al.
- FNEG: mov edi,0x80000000 (BF imm32); movd xmm1,edi; movd xmm0,eax; `0F 57 C1`
  xorps; movd back.
- conversions: `F3 0F 2A C0` cvtsi2ss xmm0,eax; `F3 0F 2C C0` cvttss2si eax,xmm0.
- doubles: 64-bit staging `66 48 0F 6E/7E` movq, ops use F2 prefix (addsd 58 etc.);
  DNEG masks 0x8000000000000000 via movabs rdi (48 BF imm64).
- MIR_FRET aliased to MIR_RET (f32 bits returned in rax).

## Makefile wiring

```
test_isa_driver: $(MIR) $(filter-out wubu_isa_jit_stubs.c,$(ISA)) wubu_isa_x86_64.c \
    $(INTERP) $(OS_INTERP) test_isa_driver.c jit_stub.c jit_stubs_arm64.c
```
- `jit_stubs_arm64.c`: arm64-only stub (arm64 cannot JIT on x86 host — legitimate).
- `jit_stub_x86.c`: standalone `wubu_clear_cache` shim (x86 has coherent I-cache);
  do NOT also link `wubu_isa_driver.c` without it or you get duplicate/missing symbols.
- Always `make clean` before judging — stale `.o` files silently linked old emitters
  and cost a full false-debugging cycle.

## Verification pattern

Minimal per-op harness (seconds): build MIR directly via wubu_mir_const/binop/unop +
ret/fret, compile with the real driver, run, compare against host-computed value.
Float host oracle must force true f32 (volatile float) — see
softfloat-and-float-differential-testing.md.
