# MIR_SHR is an ARITHMETIC shift -- five backends implement it LOGICAL

Found by extending tools/test_backend_diff.c with a shift case.

## The contract

`wubu_mir.h:46` says only:

    MIR_SHR,   /* dst = a >> b */

That is ambiguous, so the real contract has to be read off the implementations.
`wubu_isa_x86_64.c:1105` settles it explicitly:

    else { rex(&e,1,0,0,0); e8(&e, 0xD3); e8(&e, 0xF8); }
    /* sar rax, cl (arithmetic, matches interpreter >> on int64) */

and `wubu_mir_interp.c:292`:

    vr[in->dst] = vr[in->a] >> (vr[in->b] & 63);

`vr` is `int64_t`, and C's `>>` on a negative signed value sign-extends, so the
interpreter is ARITHMETIC. x86-64 deliberately matches it. PTX and SPIR-V also
agree.

So MIR_SHR = arithmetic right shift. Note this rests on an implementation-
defined C behaviour -- the enum comment should be made explicit at some point.

## Who is wrong

These emit a LOGICAL shift and therefore return
4611686018427387892 (= (-48 & 0xFFFF...FFFF) >> 2) instead of -12:

  wubu_isa_riscv.c   returns the exact 64-bit logical result
  wubu_isa_m68k.c    returns the 32-bit logical result (1073741812)
  wubu_isa_8086.c    returns 16372
  wubu_isa_z80.c     returns 52   (8-bit, 0x34 = -48 & 0xFF, then >>2)
  wubu_isa_6502.c    returns 52
  also mips (0), 8051, avr, pic

Fix: use the target's arithmetic-shift instruction -- SAR on x86, ASR on
arm64, SRA on RISC-V, LSR->ASR on 8-bit cores that have one. Many 8-bit parts
have no arithmetic shift at all, so those need the sign-extension-by-hand
sequence instead.

## Why this matters beyond the test

HolyD and the C frontend lower signed division and negative shifts through
MIR_SHR. A logical shift there corrupts every negative right-shift in
compiled user code, and it is invisible to any test that only shifts
non-negative values.

## How the oracle exposed it

    wubu_mir_ret(p, wubu_mir_binop(p, MIR_SHR,
        wubu_mir_binop(p, MIR_SHL, wubu_mir_const(p, -3), wubu_mir_const(p, 4)),
        wubu_mir_const(p, 2)));

(-3 << 4) = -48, then SHR 2. Interpreter: -12. Backends: logical.

Note there is no `wubu_mir_select` in this MIR and no `MIR_SAR`; only SHL and
SHR exist. `MIR_LT` / `MIR_ULT` are the compare opcodes (there is no
`MIR_ICMP_*` prefix), and they yield 0/1 rather than a boolean register, so
branch selection is expressed as `f + cmp * (t - f)`.