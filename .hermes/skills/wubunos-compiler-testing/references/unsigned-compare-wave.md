# Unsigned compares (MIR_ULT/ULE/UGT/UGE) across all 14 drivers — done 2026-08-23, commit 8273252

Result: test_isa_driver **160/160 ALL TESTS PASSED** standalone. New test
`test_unsigned_compare` in test_isa_driver.c uses `a = -1` (0xFFFFFFFF as u32)
vs `b = 1` for all four ops — a signed backend returns wrong answers, so this is a
real differential, not a smoke test.

## Per-driver encodings (verified)

| driver | ULT | ULE | UGT | UGE |
|---|---|---|---|---|
| x86_64 | SETb 0x92 | SETbe 0x96 | SETa 0x97 | SETae 0x93 |
| arm64 | W64CC_CC (LO) | W64CC_LS | W64CC_HI | W64CC_CS (HS) |
| riscv | `sltu t0,a,b` (FN7_SLTU=0x00, FN3_SLTU=0x03) | sltu(b,a); xori 1 | sltu(b,a) | sltu(a,b); xori 1 |
| mips | `sltu` funct 0x2B; negate = `addui(0,T2,1); sub(rs=T2, rt=T0, rd=T0)` | | | |
| m68k | BCS cc=0x5 | BLS 0x3 | BHI 0x2 | BCC 0x4 |
| 8086 | JB 0x72 | JBE 0x76 | JA 0x77 | JAE 0x73 |
| z80 | JP C | JP C + JP Z | JP Z→set0 then JP NC→set1 | JP NC |
| 6502 | BCC | BEQ+BCC (two fwd branches, both patched) | BEQ +2 skip, then BCS | BCS |
| 8051 | EXT_ULT 0x10 | EXT_ULE 0x12 | EXT_UGT 0x0F | EXT_UGE 0x11 (new ops in BOTH compiler+interp) |
| avr | AVR_ULT 0x17 | AVR_ULE 0x19 | AVR_UGT 0x16 | AVR_UGE 0x18 (both sides) |
| pic | PIC_LTU 0x15 (existing) | PIC_ULEQ 0x1F (new) | PIC_GTU 0x14 (existing) | PIC_GEU 0x1D (new) |
| ptx | setp.lt.u64 | le.u64 | gt.u64 | ge.u64 (GPU-verified on RTX 4050 via WSL) |

## Traps hit and fixed (each cost a debug cycle — don't repeat them)

1. **Inner-switch-only insert does nothing (riscv).** The compare block is
   `case MIR_EQ..GE: { switch(in->op){...} }`. Adding `case MIR_ULT:` inside the
   INNER switch but not adding MIR_ULT to the OUTER case-label list means control
   never reaches it → op falls to outer `default:` → nothing emitted → result reads
   as stale slot value. Symptom: all four unsigned ops return garbage/0 while build
   succeeds. Fix: extend BOTH the outer label list and the inner switch.
2. **Negate idiom operand order (mips).** Their working signed GE uses
   `mips_sub(T2, T0, T0)` meaning `rd=T0 = rs=T2 - rt=T0` = `1 - t0`.
   Writing `mips_sub(T0, T2, T0)` computes `t0 - 1` instead. Copy the WORKING
   call's argument order verbatim when cloning an idiom.
3. **ULE/UGE formula swap.** Correct: `ULE = NOT(a>b) = 1 - sltu(b,a)`;
   `UGE = NOT(a<b) = 1 - sltu(a,b)`. Getting these backwards passes some tests and
   fails others (mips passed ULT/UGT, failed ULE/UGE) — always probe with the
   asymmetric pair (-1, 1) AND an equal pair (3,3).
4. **Compiler/interp opcode-table divergence (pic).** The compiler's local
   `#define PIC_*` numbering had drifted from the interp's dispatch table
   (interp: GTS=0x16/EQ=0x18 where compiler thought EQ=0x16). Emitting the
   compiler's number silently executed the WRONG interp op. Rule: new compiler-side
   opcodes MUST pick values from the INTERP's free slots and be added to both files
   atomically; grep both files' define tables before choosing a value.
5. **Interpreter missing condition codes (m68k).** Adding compiler-side Bcc values
   is not enough — `cond_true()` in wubu_m68k_interp.c only implemented signed cases
   and returned 0 (never branch) for anything else. Every "branch on condition"
   ISA needs its condition evaluator audited, not just its assembler emitter.
6. **ptx has TWO switches** — a text-emitter switch whose default prints
   `/* MIR op N — not yet implemented */`. Inserting into one switch only (or
   inserting the same case labels into both) either silently no-ops or gives
   `duplicate case value` compile errors. When fixing ptx, grep for
   `not yet implemented` first; consolidate to ONE case block per op group.
7. **count_regs()/predicate pre-pass (ptx).** Compare ops need one predicate each;
   if the first-pass counter doesn't count the new ops, predicate registers are
   under-allocated. Extend the counter's case list together with the emitter.

## Fast debugging loop that cracked every failure

Minimal single-driver probe (~30 lines): declare a local `drv_t` struct matching
`wubu_isa_driver_t`, `extern const drv_t wubu_isa_<name>;`, build the MIR program
directly with `wubu_mir_const/binop/ret`, call `compile` + `run`, print got vs want.
Link ONLY mir.c + the target's isa/interp files + softfloat/tgemm (the interps in
OS src/runtime reference `wubu_tgemm_mem8`). Avoids the full test binary and isolates
encoder vs interpreter vs test-harness in one run. For byte-level questions dump the
emitted words (`for i in steps of 4 print %08x`) and decode by hand — that is how
the mips operand-order bug and the riscv silent-nothing bug were identified.
