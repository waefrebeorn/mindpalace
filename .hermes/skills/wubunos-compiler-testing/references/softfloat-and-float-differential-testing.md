# Soft-float + float differential testing (2026-08-23 session)

Ground truth: the soft-float runtime in `wubu_softfloat.c` is the source of truth
for f32 correctness across **all 14 ISA backends** — every backend routes float
ops through `wubu_sf_f32_{add,sub,mul,div}` (plus `i64_to_f32` / `f32_to_i64` /
`f32_cmp`). If the runtime is wrong, every backend is wrong in the same way, so
the host-CPU differential is the decisive oracle.

## Two gates (both in the `make test` chain)

| gate | binary | what it checks |
|---|---|---|
| `make test_softfloat` | `tools/test_softfloat` (906 assertions) | f32 add/sub/mul/div, ITOF/FTOI, comparison, NaN/inf/subnormal — vs `float` on x86-64 with `volatile` forcing true f32 semantics |
| `make test_mir_float` | `tools/test_mir_float` (3 assertions) | routes `MIR_FADD/FSUB/FMUL/FDIV/ITOF/FTOI` **through the MIR interpreter** → soft-float runtime, proving the MIR→interp→softfloat path end-to-end |

Plus `tools/test_fuzz_diff.c` (`make test_fuzz_diff`): 10 000–30 000 random f32
seeds via `MIR_FADD/FSUB/FMUL/FDIV` vs host float — **15 000/15 000 bit-exact**
verified 2026-08-23.

## The canonical float oracle pattern (re-derive, do not memorize counts)

```c
/* Host oracle MUST use true f32 arithmetic. C promotes float→double, so
 * a+b in double then stored to float = DOUBLE ROUNDING — it disagrees with
 * a correctly-rounded f32 result on ~14/15k cancellation seeds. Force f32
 * via volatile so each op rounds at the f32 width: */
volatile float fa = av[0], fb = av[1], fr_;
switch (op) { case 0: fr_ = fa + fb; break; /* … */ }
float want = fr_;
```

## Bug fixed this session — the `sf_round` subnormal double-rounding class

Symptom: 21/15000 float fuzz mismatches, all on **opposite-sign add/sub** and
**mul/div** that landed in the subnormal range. The old `sf_round`:

1. rounded the exact mantissa to **24 bits** (the normal path), then
2. in the (separate) subnormal branch **shifted it down and rounded AGAIN**.

That second rounding — "round-to-24-then-shift" — loses exact-tie information
and produces off-by-1-ulp results on cancellation (a = 0.42×min-sub etc.).

Fix (applied to `sf_round` in `wubu_softfloat.c`): **round once, directly at the
target precision.** If the top-bit exponent `top_exp = k + 63` lands below
`emin`:

- compute the *usable* significand width `eff = prec - (emin - top_exp)`
- if `eff >= 1`: round to `eff` bits directly (single RNE decision), emit the
  subnormal fraction = the rounded `keep` (no second shift)
- if `eff < 1` (value below one ulp of the smallest normal): RNE against
  `half = 2^(emin - prec)` using an exact `m * 2^k >= half` compare:
  - `shift >= 64` → value < half → 0
  - `shift <= 0`  → value >= min-subnormal → return min-sub
  - exact `shift = (emin-prec) - k` (note: **half**, not min-sub, so `1 << shift`
    not `1 << (shift-1)` — the old code used `shift-1` and over-rounded)

Critical: this block **must `return` early** — it must NOT fall through into
the old "round to prec then shift by `d`" subnormal path, which would
re-introduce the double-round. The `drop2/width/eff` path and the
`threshold`/`1<<shift` path are mutually exclusive early-returns in different
exponent regimes.

Also the `1ull << shift` for `shift == 64` is **undefined behaviour** on a
64-bit `uint64_t` — guard with `shift >= 64 → zero`, not `>= 65`. (Hit on
`x÷y` where quotient ≈ 0.42 min-sub: `shift` came out exactly 64.)

## Bug fixed this session — `cdqe` after pointer inc/dec

In `holyd_codegen_expr.c` the `POST_INC`/`POST_DEC` codegen did:

```c
emit_incdec_rax(gen, 8, 1);           // add rax, 4   (pointer step)
emit_byte(gen, 0x48); emit_byte(gen, 0x63); emit_byte(gen, 0xC0);  // cdqe
emit_store_rax(gen, p_slot);
```

`cdqe` (sign-extend eax→rax) **clobbers the upper 32 bits of a 64-bit
pointer** even though the increment was 64-bit. For `int* p`: after `p++`,
rax holds `old+8`, then `cdqe` truncates the high half → `*p` derefs a
garbage address → segfault.

Fix: only emit `cdqe` when the lvalue is a **scalar ≤ 4 bytes** (int/char/short),
not a pointer. Guarded all four `POST_INC`/`POST_DEC` code paths (global/
local × inc/dec) in `holyd_codegen_expr.c`:

```c
bool is_ptr = (pt && pt->kind == HD_TYPE_PTR && pt->base);
if (is_ptr) emit_incdec_rax(gen, (int)hd_type_size(pt->base), 1);
else      { emit_byte(gen,0x48); emit_byte(gen,0xFF); emit_byte(gen,0xC0); } /* inc rax */
if (!is_ptr) {
    emit_byte(gen, 0x48); emit_byte(gen, 0x63); emit_byte(gen, 0xC0);        /* cdqe */
}
```

Note the brace discipline — `if (!is_ptr) emit_byte(...); emit_byte(...); emit_byte(...);`
only guards the **first** byte. All cdqe-emitting sites must block-brace.
