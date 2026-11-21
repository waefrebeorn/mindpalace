# Scalar-Intrinsic Parity Proof Pattern

## When to use
Proving a SIMD / hardware-accelerated fast path is correct by showing it is
byte-for-byte identical to an already-audited scalar reference, *before* the
fast path is trusted to replace it.

Applies to any architecture with a portable-slow / accelerated-fast pair:
AES-NI vs scalar AES (FIPS-197 known-answer), SHA-NI vs scalar SHA, SIMD
CRC vs naive CRC, AVX/NEON dot vs scalar dot, etc.

## The rule
**`assert fast == scalar` is the test — never assert against an independent
source unless the fast path and the scalar path already share the
same round-key / coefficient derivation.**

A fast path is only as trustworthy as the data path it reuses. The audit
evidence lives in the *scalar* path (e.g. the FIPS-197 round-key schedule,
generated and verified by the NIST KAT). If the intrinsic path derives its
keys/schedules independently, a passing parity test only proves the two
schedules agree — not that either one is correct. Therefore:

1. **Share the data path.** Generate the round key schedule (or polynomial
   coefficients, permutation tables, whatever the path *acts on*) in exactly
   one place, and have both the scalar core and the intrinsic core consume
   that same schedule. For AES, the 11/13/15 round keys produced by
   `wubu_aes_setkey` must be handed to both the byte-loop Encrypt/Decrypt
   (Sec 5.1/5.3) and the `_mm_aesenclast_si128`/`_mm_aesdeclast_si128` sequence.
2. **Gate the fast path on the same CPU feature the parity test uses.**
   `wubu_cpu_aesni()` must be the single boolean that selects the fast path
   at runtime, and the test must check it on the host that ran the build
   (`/proc/cpuflag` or `__builtin_cpu_supports`). Do not assert parity when
   the feature flag is wrong — the "fast path" then ran scalar code and the
   test was vacuous.
3. **Assert identity across the full input space of the KAT**, for every
   supported data width: encrypt and decrypt, all key sizes, every NIST
   Appendix-C vector. One shared-schedule path that matches the scalar
   schedule on all of them inherits the scalar path's audit. A single
   failing byte means the schedules diverged at derivation time — fix the
   schedule, not the intrinsic call ordering.
4. **Never trust a "fast path matches my hand-written table"** assertion —
   hand-written tables are where transcription errors live (the duplicate
   S-box entry at one slot that makes one vector pass and silently corrupts
   the rest). Generate the table from the specification (GF(2^8) inverse +
   affine map, FIPS-197 Sec 5.1.1) at first use; the KAT is the oracle, not
   the table.

## Non-conformance is the defect
If scalar and intrinsic disagree, the fault is **not** "the CPU is weird" —
it is one of:
- the round-key schedule differs between the two paths (the common one;
  intrinsics that rebuild the schedule with `_mm_aeskeygenassist_si128`
  must produce the identical key array the scalar path uses);
- an endianness/lane-alignment mismatch in how the 16-byte block is loaded
  into `__m128i` (`_mm_loadu_si128` vs a byte-shift) — assert the raw
  `__m128i` on one known block before stepping the round loop;
- a single round applied an extra/missing time in the unrolled intrinsic
  sequence versus the scalar loop bounds.

All three surface on the *smallest* KAT (AES-128, 10 rounds, one block).
Debug there.

## Recipe (AES case study, generalizes verbatim)
```c
/* 1. one schedule, both paths */
wubu_aes_setkey(&ctx, key, keybits);          /* fills ctx.rk + ctx.nr, used by both */
wubu_aes_encrypt_scalar(&ctx, in, out);       /* audited byte loop */
wubu_aes_encrypt_aesni(&ctx, in, out_ni);     /* intrinsics, same ctx.rk */
CHECK(memcmp(out, out_ni, 16) == 0);          /* 2. parity, all KAT vecs, encrypt+decrypt */

/* 3. dispatch gated on the same predicate the test ran under */
int (*enc)(struct wubu_aes*, const void*, void*) = wubu_cpu_aesni()
    ? wubu_aes_encrypt_aesni : wubu_aes_encrypt_scalar;
```
The public `wubu_aes_encrypt`/`decrypt` dispatch table is a *fourth* path
only if `wubu_cpu_aesni()` is correct — so assert it directly first:
`CHECK(wubu_cpu_aesni() == 1)` on a known-AES-NI host, else the parity
test proved nothing about the fast path.

## Pitfalls
- **Fast path matches a hand-transcribed table, not the scalar path.**
  Two wrongs look right on the vectors that share the corruption. Generate
  the table from the spec; let the KAT be the oracle.
- **Asserting on decrypt without also asserting on encrypt** can read
  garbage that *looks* like plaintext and pass — parity must cover both
  directions for every key size.
- **A 32-byte key schedule is not "more of the same" as a 16-byte one.**
  AES-192 rotates the schedule differently (RotWord boundary at a
  non-block-aligned word count). Assert each key size's `nr` and
  key-array length independently before trusting the shared path.