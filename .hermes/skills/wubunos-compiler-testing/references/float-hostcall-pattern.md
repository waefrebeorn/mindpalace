# Float Hostcall Escape-Hatch Pattern (wubunos, proven 2026-08-23, all 8 retro ISAs)

## The pattern
Interpreter backends can't do f32 natively. Instead of implementing float ALUs,
add ONE custom hostcall opcode per backend that escapes to the host and calls the
pure-C11 `wubu_softfloat` runtime (RNE, bit-exact vs host):

```
MIR_FADD → driver emits [HOSTCALL opcode][fn][dst][sa][sb] → interp dispatches
         → wubu_sf_f32_add(fa,fb) → result to slot cell → MIR_FRET returns bits
```

fn codes (keep IDENTICAL across every backend): 0=add 1=sub 2=mul 3=div
6=eq 7=ne 8=lt 9=le 10=neg 11=fret. Gate: per-ISA float smoke 1.5+2.25=3.75
bit-exact + `make test` 116/116 + `./test_fuzz_diff 10000` 0 mismatch.

## Per-backend encodings (all verified bit-exact)
- **6502**: opcode 0x02; zp_fslot cells (high ZP ≥0x80, 4-aligned). MIR_CONST must
  store BOTH the int byte AND the 4-byte float cell (dual-store).
- **Z80**: 0x0B; unified memory — code is memcpy'd into cpu.mem, fetch args via
  `cpu.mem[cpu.pc++]`, not a code[] pointer. z80_fslot = high-memory 4-byte cells.
- **M68K**: word 0x0B00; A6-relative big-endian cells (slot_disp = -(vr+1)*4);
  inline loads/stores only — no load32/store32 helpers exist in that interp.
- **RISC-V**: opcode 0x3F → emit full word 0xFC000000; fetch32() already advances
  pc — do NOT also `pc += 16` after the 4 inline words. Slots absolute in mem[]
  (fp holds a guest address; index directly, no RV_MEM subtraction).
- **MIPS**: opcode 0x3F → emit 0xFC000000 (op = inst>>26!); slots $sp-relative
  (basev = cpu.r[29]); FRET passes the result cell in the SA position.
- **8051**: reuse the EXT mechanism: FF 20 fn sa sb sd / FF 21 sa; ram[] is int64 —
  low 32 bits = f32 bits; added EXT_FCONST (FF 22 v0..v3 slot) for 4-byte consts.
- **AVR / PIC**: opcodes 0x20/0x21; int64 ram/vr cells hold f32 in low word.
  Driver duplicates the interp's #define opcode list — keep both copies in sync.

## Pitfalls that ate real time
1. **Phantom file copies**: edits landed in `wubunos/src/runtime/...` while make
   compiled `wubuos/src/runtime/...`. Symptom: binary lacks strings/sentinels from
   the source you just edited (0xAB sentinel absent in objdump). ALWAYS verify with
   `make -n TARGET | tr ' ' '\n' | grep <file>` + md5sum both paths BEFORE debugging
   logic. The wubunos Makefile's OS_INTERP mixes both repos' paths.
2. **Opcode-field encodings**: RISC-V/MIPS decode op = inst>>26 — a raw 0x3F word
   decodes as opcode 0 (SPECIAL). Emit `opcode << 26` (0xFC000000).
3. **Double pc advance**: a fetch helper that already bumps pc must not be followed
   by a manual skip of the same bytes.
4. **Flip the oracle with the contract** (2026-08-23, same session): when changing
   MIR integer semantics (WRAP32→HolyC-faithful i64), update the fuzz oracle in the
   SAME commit AND widen fuzz inputs to full 64-bit — i32-range-only inputs masked a
   real x86-64(REX.W)-vs-interp divergence. Oracle model must be pure int64
   (shifts &63, SHR arithmetic on signed, DIV/MOD guard INT64_MIN/-1).
5. **Interp struct fields**: anchor struct-field insertion on the struct's LAST real
   field (e.g. `uint8_t iflag; ...`), not `mem[...]\n}`.
6. **Duplicate local decls**: adding loop-scope `fn/sa/sb/sd` decls collides with
   per-case locals (PIC `fr`) — declare once at loop top, remove the old decl.

## Status after landing
All 8 retro ISAs (6502/Z80/8051/AVR/PIC/MIPS/RISC-V/M68K) float-capable via
hostcall; x86-64 JIT uses native SSE; MIR interp routes through wubu_softfloat.
Differential: 10k int seeds (full i64) + 5k float seeds, 0 mismatch; battery 155/155.
