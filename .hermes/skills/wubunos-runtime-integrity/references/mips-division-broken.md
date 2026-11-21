# mips division is broken: the whole sequence needs rewriting

Found by tools/test_backend_diff.c. Tracked as XFAIL, not silently passed.

## The defect

`wubu_isa_mips.c` emits, for MIR_DIV:

    div $zero, $t0, $t1     (R_TYPE(T0, T1, rd=0, ...))
    mflo $t0

Two problems, and the second means a one-register patch is NOT enough:

1. `rd` is 0. MIPS writes the quotient to lo(rd) and the remainder to hi(rd),
   so with rd = $zero the result lands in $zero while `mflo $t0` reads a stale
   value out of $t0. Observed: -100/7 returned 613566742, which is leftover
   state, not a division result.

2. More fundamentally, `mflo`/`mfhi` can ONLY read `$0` (register zero). The
   encoding `mflo $t0` has no architectural meaning on real MIPS. So even with
   rd fixed, the read-back is wrong by the ISA's own rules. This emitter and
   its interpreter agree on a fiction; real hardware would not.

MIR_UDIV / MIR_UMOD have no case at all in the mips emitter, so they return 0.

## How to fix it properly

Do not `mflo $t0`. Either:
  - branch to a real divide routine and move the result out of $0 via a
    `move $t0, $2` (the canonical MIPS idiom), or
  - restructure so the quotient/remainder never round-trips through lo/hi.

The interpreter models lo/hi as globals (`cpu.lo`, `cpu.hi`), so it will keep
agreeing with a broken emitter. That agreement is exactly why this went
unnoticed: the emitter and interpreter share the same wrong assumption.

## Why XFAIL rather than a fix-by-iteration

The rest of the arithmetic in mips is verified correct now (UDIV/UMOD aside),
and this sequence needs a design decision plus a rewrite. An XFAIL keeps the
defect visible in the aggregate output while the suite stays green. Promote it
to a hard failure the moment it is fixed -- do not let it rot in the list.

See also references/mir-shr-is-arithmetic.md and references/backend-width-limits.md.