# Deterministic RNG verification (PCG-XSH-RR and friends)

Use when a goal or module claims a specific generator (`PCG-XSH-RR`, xoshiro,
SplitMix64) or when a simulation's reproducibility is part of the contract.

## The construction (PCG32 / XSH-RR)

```c
#define PCG_MULT 6364136223846793005ULL

void seed(ws_pcg32_t *r, uint64_t seed, uint64_t seq) {
    r->state = 0;                 r->inc = (seq << 1) | 1;  /* inc must be odd */
    (void)next(r);                /* warmup 1 */
    r->state += seed;             /* stream select */
    (void)next(r);                /* warmup 2 */
}
uint32_t next(ws_pcg32_t *r) {
    uint64_t old = r->state;
    r->state = old * PCG_MULT + r->inc;
    uint32_t x = (uint32_t)(((old >> 18) ^ old) >> 27);
    uint32_t rot = (uint32_t)(old >> 59);
    return (x >> rot) | (x << ((-rot) & 31));
}
```

The output uses the **old** state; advancing first and then hashing the new
state yields a stream that is deterministic but not PCG — a pinned vector is
the only thing that catches it.

## Four checks that together mean something

1. **Pinned vector.** Hardcode the first 8 outputs for `(seed=42, seq=54)`.
   Recompute them once from your own implementation and paste them in; any
   later refactor or platform difference breaks the test. Example values:
   `2707161783, 2068313097, 3122475824, 2211639955, 3215226955, 3421331566,
   3217466285, 2167406445`.
2. **Chi-square uniformity.** 1e6 samples into 256 bins (`v & 255`). Statistic
   `Σ (obs-exp)²/exp` with df = 255. The **1% critical value is 310.46**; assert
   `chi < 310.46` and print the value on failure. Do not compute a p-value — the
   critical value is the whole test and needs no library.
3. **Run + bit balance.** 200k samples: longest run of identical 32-bit values
   must be ≤ 3 (true for a good 32-bit generator at this sample size), and
   `popcount` ratio must sit in 0.49–0.51. This catches a stuck/high-bit-only
   generator that a chi-square over low bits would miss.
4. **Cross-architecture hash.** FNV-1a 64 over the first 10,000 outputs, hashing
   each value as 4 BIG-ENDIAN bytes (endian-neutral). Pin the constant (e.g.
   `0xf4b6ad7df17336c3`). This is the artifact that makes "identical stream on
   x86-64 and aarch64" checkable on one machine: integer-only arithmetic plus a
   pinned hash means any platform that differs fails the same test.

## Rules

- **Integer-only or it is not portable.** No `float`/`double` in the generator
  or in any bounded helper that feeds it; `(float)next()/2^32` is fine at the
  call site, not inside the state machine.
- **Debias bounded ranges by rejection**, not by `%`:
  `threshold = (uint32_t)(-bound) % bound;` and redraw while `v < threshold`.
  A bare `% bound` is measurably non-uniform for ranges that do not divide 2^32.
- **Keep the legacy generator if callers depend on its stream.** Adding a new
  generator beside `xorshift64` is correct; swapping the implementation under
  existing callers silently changes every simulation replay and every golden
  file.
- **A statistical test needs enough samples to mean anything.** 1e3 samples in
  256 bins has expected count 3.9 — the chi-square is dominated by discreteness
  and passes or fails at random. 1e6 samples (expected 3906) is the floor.
