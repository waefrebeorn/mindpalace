# Encoder/interpreter opcode contract (census lesson, 2026-11-19)

Every interpreted ISA pair (pic, avr, 8051, z80, m68k, ...) must share ONE
opcode header. The executor's numbering IS the contract; the encoder
conforms. Private tables in both files drift silently and ship bugs.

## The incident that proved it

wubu_isa_pic.c and wubu_pic_interp.c kept private tables. Drift found by
`wubuos/tools/hardcode_census.py --root /home/wubu/wubunos`:

- MIR_EQ emitted 0x16 where the executor runs GTS (signed >). EQ is 0x18.
  Equality compiled to greater-than.
- MIR_LT / MIR_ULT emitted 0x15 where the executor runs LEU (<=).
  Less-than compiled to less-or-equal.
- MIR_GT (signed) emitted GTU (unsigned): GT(-5,3) was true.

It shipped because test_isa_driver had ZERO EQ/LT coverage. The fix
(wubunos a3cf7c5, wubu-integration): wubu_pic_opcodes.h as the single
owner; encoder GT->GTS, LT->GTS with operands swapped (a<b <=> b>a),
ULT->LEQ (0x1E); a 16-case signed+unsigned comparison battery added to
test_isa_driver across all 13 ISAs. Verified 356/392, pic 16/16, the 22
pre-existing failures unchanged. The battery newly exposed z80 signed
lt/gt (4), mips eq (1), ptx (9) — open backend items.

## Rules

1. Before touching a backend, check its comparison coverage (EQ/LT/GT
   signed incl. negatives, ULT/ULE/UGT/UGE). Missing coverage is how
   opcode drift ships.
2. When two files define the same opcode names, merge into one header
   in the same commit; never "fix the value" in one table only.
3. Signed LT with no direct opcode: swap operands into signed GT.
4. The census classifier compares define VALUES comment-free; identical
   values with different comments are mirrors, not conflicts.
5. Remaining wubunos conflicts are triage classes, not bugs: CC_LE/CC_NE
   (HolyD IR vs m68k hardware Bcc — layer-local), OP_RETURN (wasm vs
   spirv — file-local ISA tables), MAX_TESTS (test-local caps).

The org-wide protocol lives in wubuos docs/CONSTANTS.md and
docs/compendium/04-roadmap/hardcoding-census.md.
