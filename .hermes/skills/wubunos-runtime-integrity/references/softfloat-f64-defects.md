# wubu_softfloat f64: what is fixed and what is still broken

## FIXED (2ae4b05): f64 multiply returned 0 for essentially every input

    uint64_t comb = (hi2 << 36) | (lo2 >> 18);   /* ~89 bits */
    r.m = comb << sh;                            /* into uint64_t -> 0 */

hi2 is up to 53 bits, so `hi2 << 36` overflows a 64-bit word. Only the LOW 64
bits survive, and for a normal product those are all zero. Fix: the product is
exactly `hi2 * 2^54 + lo2`, and hi2 is already the top 53 bits, so it fits as
-is. Keep `r.m = hi2`, `r.k = a.k + b.k + 54`, `r.s2 = (lo2 != 0)`.

## STILL BROKEN: norm64() is fundamentally wrong for f64

    static inline void norm64(uint64_t *m, int32_t *k) {
        int sh = sf_clz64(*m);
        *m <<= sh; *k -= sh;
    }

It normalizes so the MSB sits at bit 63. An f64 significand must be 53 bits
with the implicit 1 at bit 52. So every norm64() call over-shifts and breaks
the invariant that sf_round() depends on.

Observed with SFDBG on `10.0 + (-1e-9)`:

    ak=-60 am=a000000000000000        <- 64 bits, should be 53
    rm=fffffffdda3e82fc rk=-63        <- sign bit set on a positive result

This is why f64 add/sub still fail against the host's native double:
`x + 0.0` loses x, and `10 - 1e-9` returns -2.0.

I attempted two fixes and REVERTED both because they traded one failure for
another without addressing the root cause:

1. Reordering the magnitude comparison (`a.k < b.k` is backwards given k is
   the UNBIASED exponent) plus a zero special case. It fixed `0.25 + 0.0` and
   broke nothing, but the remaining failures were all in the opposite-sign
   path and still failed.
2. Gating the guard-bit restore on `dk < 53`. Correct in isolation, but made
   no measurable difference because norm64 had already corrupted the value.

Fixing f64 add/sub means rewriting norm64 for f64 (normalize to 53 bits, MSB
at bit 52, not to bit 63) and re-checking every caller. That is a real piece of
work, not a patch. Do not re-attempt the ordering/guard tweaks alone.

## Oracle

`/tmp/sfcheck`-style harness: sweep wubu_sf_f64_{mul,add,sub,div} against the
host's native double over a value grid. Before the fix: 1257/1278.
After the mul fix: mul is correct except inf/overflow comparisons, add/sub
carry the norm64 bug.