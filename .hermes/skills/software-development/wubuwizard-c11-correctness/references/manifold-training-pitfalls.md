# Manifold training — traps, formulas, and the test matrix

Scope: `wubu_mobius` (geometry), `wubu_manifold_train` (loss + adapter),
`wubu_hyperbolic_output_proj` (LM head). The Lean core in `wubumath` is the
source of truth for the identities; where C11 and the proofs disagree, the
proof wins.

## Coordinates

With ball radius R (curvature -1/R²):

```
exp(u)  = R * tanh(‖u‖/R) * u/‖u‖          (tangent -> ball)
log(x)  = R * atanh(‖x‖/R) * x/‖x‖          (ball -> tangent)
r       = R * tanh(‖u‖/R)  =>  ‖u‖ = R * atanh(r/R)
```

`exp` always lands inside (`c·‖exp‖² < 1`); `log` clamps ratio < 0.9999.
The pair round-trips to < 1e-4 in fp32 at the scales used in tests.

## Trap 1 — ambient vs tangent gradient

A classifier defined in the tangent chart:

```
u = log(x), v_k = log(anchor_k)
logit_k = -‖u - v_k‖² / (2R²)
dlogit_k/du = -(u - v_k)/R²
```

`dL/du = Σ_k (p_k - y_k) * dlogit_k/du` is the TANGENT gradient. If the loss
returns `dL/dx` instead (through `log_map_backward`) and the trainer does
`u -= lr * dx`, the step is scaled by the inverse metric and diverges near the
boundary. Signature: loss climbs to a cap, `‖x‖` sits at R.

Correct step:

```c
wubu_manifold_ce(&head, x, label, du, NULL);   /* du = dL/du */
wubu_log_map(x, D, R, u);
for (i) u[i] -= lr * du[i];
wubu_exp_map(u, D, R, x);                       /* stays in ball */
```

Acceptance: 300 steps, loss falls by >80%, and `‖x‖ < R` throughout.

## Trap 2 — hinge on the boundary converges asymptotically

```c
/* WRONG: r approaches lo from below forever */
if (n < lo_u) pen = (lo_u - n)^2;
/* RIGHT: hinge 5% inside the band */
float m = 0.05f * (hi_u - lo_u);
if (n < lo_u + m) pen = (lo_u + m - n)^2;
else if (n > hi_u - m) pen = (n - (hi_u - m))^2;
```

`dPen/du = 2·(n - hinge)·(u/n)` with the sign of the violated side.
Acceptance: start 64 points below the band, 300 steps of penalty descent at
lr 0.1, ≥90% (and in practice 64/64) inside `[lo, hi]` in radius terms.

## Trap 3 — adapter gradients

Forward: `out = exp(u + B(Au))`, `r = Au`, `u' = u + Br`.

```
du'  = exp_map_backward(u', out, dL/dout)
dr   = Bᵀ du'
dL/dB[k][i] = du'[k] * r[i]
dL/dA[i][j] = dr[i] * u[j]
```

Do not differentiate `exp` by hand; `wubu_exp_map_backward(v, d, R, z, dz, dv)`
implements `z = scale(v)·v` with the radial term already correct.

FD oracle: fix a random `g`, define `L(A,B) = <out(A,B), g>`; central
differences with `eps = 1e-2` on a sample of entries. fp32 gives ~2e-3 max
relative error; accept `< 1e-2`. Perturb A and B separately and restore the
entry before the next probe.

## Test matrix (all four, every change)

| test | assertion | mirrors |
|---|---|---|
| exp/log round-trip | `‖log(exp(u)) - u‖ < 1e-4` | PoincareBall.lean |
| ball closure | every `exp(u)` and adapter output has `‖x‖ < R` | ExpMapBall.lean |
| hierarchy ordering | `d(child,parent) < d(child,sibling)`; hinge 0 when ordered, >0 when violated | geodesic structure |
| radius occupancy | ≥90% of points in `[lo,hi]` after 300 steps | training stability |
| adapter FD | dA/dB relative error < 1e-2 | analytic backward |

## API shape that avoids the traps

- Loss returns the TANGENT gradient in an explicitly named `dtan` out-param.
- Hierarchy loss uses TRUE Poincaré distance (`wubu_poincare_dist`), not the
tangent approximation — the ordering claim is geometric.
- Radius penalty returns the penalty and, optionally, `dPen/du`.
- Adapter backward takes `dL/dout` (ambient), not `dL/du'`, so callers never
need the exp Jacobian themselves.

## Honest limits

- `-ffast-math` is banned in these tests; the engine's production flags can
  reassociate the radial term. Build manifold tests with the plain `-O2` path.
- fp32 `atanh` saturates near 1; for long runs accumulate in double or clamp
  the ratio first.
- No theorem says the objective is good. WuBuMath proves the operations are
  well-defined, not that the loss learns anything useful.
