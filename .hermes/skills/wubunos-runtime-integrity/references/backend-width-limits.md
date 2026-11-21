# Backend WIDTH limits: 8-bit and 16-bit cores silently truncate MIR values

Established by tools/test_backend_diff.c. Do not "fix" these in a test by
masking the expected value -- that certifies a backend that corrupts data.

## MIR values are 64-bit (int64_t). These backends cannot hold one.

  8-bit:  6502, z80, 8051, avr, pic
          Verified: a 32-bit shift test returns the low byte.
          (-3 << 4) = -768 needs 11 bits; 8-bit cores truncate mid-expression.

  16-bit: 8086, m68k
          Verified: 200000 came back as 3392, which is 200000 & 0xFFFF.
          EVERY MIR value is stored through ax / D0 and truncated. Tests whose
          result happens to fit in 0..65535 pass, which is why this hid for so
          long -- (7+9)*56 = 896 fits.

  64-bit: x86-64, arm64, riscv, ptx, spirv

## What the oracle does about it

  - 8-bit: the expected value is compared as (int8_t)(want & 0xFF), because
    these targets sign-extend their byte result. That IS correct for them.
  - 8-bit AND 16-bit: any test whose expected result leaves their width is
    SKIPPED, not passed. The shift test skips both because its INTERMEDIATE
    overflows, not just its result.
  - 8086/m68k also skip the f64 test (no 64-bit register).

Current result: total=72 pass=72 fail=0 skipped=19.

## The rule

A SKIP is honest when the target physically cannot represent the value.
A PASS is dishonest if the target truncated on the way. Never let the second
case report success -- that is precisely the bug class this oracle was built
to catch (the Vulkan runner printed 0 while computing 892).

## Related: m68k IS 16-bit but 68000 is 32-bit

m68k's ARITHMETIC shift fix used ASR.L (0xE088) on a 32-bit register, which
is correct for the ISA but the backend still stores slots 16-bit wide. Both
statements are true at once: the instruction is right, the data path is not.

Note Z80's RRC A (0x0F) is a ROTATE (it replicates bit7 into bit0), not a
shift -- do not reach for it as an SRA substitute.