# GP / Cholesky / file-collision patterns (passes 41–44, 2026-08-01)

Condensed from closing the CC / DD / EE / FF axes in `wubuwizard` (recursive
gap-closure loop). These are the non-obvious bugs that bit and the reliable fixes.

## 1. Cholesky backsolve direction (P9)

`L` lower-triangular, `L^T * alpha = tmp`. Back-substitution equation per row `i`:
```
L[i][i]*alpha[i] + Σ_{k>i} L[k][i]*alpha[k] = tmp[i]
```
Iterate `i` DESCENDING so `alpha[k]` (k>i) are already solved. Ascending reads
garbage → corrupt `alpha` → GP mean wrong (pred=45.46 at training point where
true=25.0, var≈0). Fix: `for (int i = n-1; i >= 0; i--)`.

Oracle: at an OBSERVED training point, `|mean - y| < 1e-3` (GP interpolates);
var ≈ 0. If mean is off but var≈0, backsolve direction is wrong.

## 2. Header must include its own dependencies (P10)

`wubu_bo.h` referenced `wubu_gp_t` + `WUBU_GP_MAX_DIM` (defined in `wubu_gp.h`)
without `#include "wubu_gp.h"` → `unknown type name 'wubu_gp_t'`. Fix: every
header includes every header whose symbols it names. Self-contained headers,
not relying on transitive includes.

## 3. `static` helper not callable from another TU (P11)

`static double rng_f(unsigned*)` in module A is invisible to module B / test C.
Calling it from a test → `undefined reference to rng_f`. Fix: expose a public
`wubu_X_rand` helper, or use a local RNG inside the test. (Distinct from P8,
which is same-TU static-before-definition.)

## 4. FILE-NAME COLLISION = SILENT OVERWRITE (the dangerous one)

`write_file src/wubu_X.c` does NOT check whether the file already exists with
UNRELATED content. This session:
- `write_file src/wubu_vision.c` (new ViT-patch embed) OVERWROTE the existing
  27-layer GGUF ViT (`wubu_vision.c` already in CORE_OBJ). Rescued via
  `git checkout HEAD -- src/wubu_vision.c include/wubu_vision.h`.
- new `wubu_replay_t` collided with `wubu_replay_t` already declared in
  `wubu_metagame2.h` (AH10 replay buffer) with a DIFFERENT layout →
  `conflicting types`. Renamed to `wubu_experibuf_t` + files.

The collision only surfaced as a duplicate-symbol link error AFTER the overwrite.
MANDATORY before any `write_file` on a `src/wubu_X.c` / `include/wubu_X.h`:
```
git show HEAD:src/wubu_X.c >/dev/null 2>&1 && echo "EXISTS — pick a new name"
git show HEAD:include/wubu_X.h >/dev/null 2>&1 && echo "EXISTS — pick a new name"
```
If it exists and you did NOT mean to edit it, give the new module a DISTINCT
name (e.g. `wubu_imgenc.c` for image-encoder, `wubu_experibuf.c` for replay).
Rename BOTH the file AND the type if the type name also collides.

## 5. Optimizer coefficient-range + invariant-sign traps

- GP/SR hill-climbing over coefs: init range `[-2,2]` can't reach true coef `3.0`
  → stuck in local min (MSE=1.67). Widen init (`[-5,5]`), adaptive step, more
  restarts.
- Invariant template `{c0, c1, c2}` = `c0 + c1*x + c2*y >= 0`. `{25,-1,0}` means
  `x <= 25` (NOT `x >= 25`). "tok_s >= 25" must be `{-25, 1, 0}`. Verify direction
  by hand, not just "it was found."

## Verification cheatsheet

| Module | Oracle |
|--------|--------|
| GP surrogate | `|mean(train_pt) - y| < 1e-3`, var≈0; var(far pt) > var(near pt) |
| Acquisition (EI) | EI>0 when mean≫f*; EI(low mean) < EI(high mean) at same σ |
| SINDy | discovered coeff ≈ true (e.g. dx/dt=2x → Xi[0][1]≈2.0) |
| CEGIS | finds f=max(x,y) from grammar {max,+,−} |
| Prover | proves (A⇒B)⊢(A∧A⇒B); rejects (¬A)⇒B |
| Invariant | discovers `tok_s>=25` (with correct sign) + `iter>=0` |
| Thompson bandit | winner arm pulled ≥ loser arm after 50 rounds |
| BO loop | found tok_s>27 on toy optimum (~30) after ≤8 evals |
