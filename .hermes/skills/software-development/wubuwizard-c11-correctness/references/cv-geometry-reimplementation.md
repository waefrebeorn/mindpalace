# Reimplementing CV / calib3d primitives in plain C11

Verified recipes from porting an OpenCV-shaped module set into wubuwizard-style
C11 (no deps, `-std=c11`, tests in `tools/test_*.c`). Every number below came
from a real run against synthetic data with a known answer.

## The test standard for numeric code

A numeric function passes only when it recovers a *known* answer:

- Known shift `(2,3)` -> flow `(2.00,3.00)`.
- Known pose `t=(0,0,0.5)`, `R=I` -> recovered to 1e-6.
- Known camera `K={500,0,80 / 0,500,80 / 0,0,1}` -> recovered to 1e-6.

`isfinite()` and `!= 0` assertions prove nothing and hide sign/scale bugs.
Where an exact answer is impossible (interpolation bias, border clamping), put
the measured error in the pass condition (`mean error < 0.35 px`) and print it.

## Optical flow ladder (cheapest first)

1. **Sparse LK**, then **pyramid LK**: build up to 5 half-res clones of both
   frames, solve at the coarsest, double the flow, refine at each finer level.
   Recovers `(6,7)` exactly where single-scale cannot.
2. **Block matching** (dense, integer): SAD over `±search`, step 2 in the block.
   Only interior blocks agree on a known shift; border blocks lose content to
   clamping, so exclude them from the accuracy assertion (49/64 overall vs
   36/36 interior on the same data).
3. **Sub-pixel block flow**: 1-D parabola over the neighbouring SADs per axis.
   `d = 0.5*(S- - S+)/(S- - 2S0 + S+)`, clamped to ±0.5. Measured 0.125 / 0.109 px
   on a `(3.4,4.6)` shift.
4. **Horn-Schunck** (dense, variational): iterate
   `u = u_bar - Ix*(Ix*u_bar + Iy*v_bar + It)/(a^2 + Ix^2 + Iy^2)`, gradients
   averaged over both frames. `alpha=8`, 300 sweeps -> 0.206 / 0.151 px on `(2,3)`.
   Initialise to zero; a zero field is the correct answer for identical frames.

**Farneback shortcut is a trap.** Approximating the polynomial's linear
coefficient with `b = <Ix*I>` and solving `d = -0.5 A^-1 (b2-b1)` gave 475 px
error on a `(2,3)` shift. The shortcut drops the intensity centring that
normalized convolution provides. Real Farneback fits `[1, x, y, x^2, xy, y^2]`
with a Gaussian window (6x6 solve per pixel) before the displacement solve.
Do not ship the shortcut under the Farneback name.

## PnP and calibration

- **DLT**: `>= 6` points, fix `p34 = 1`, 11 unknowns, normal equations + Gaussian
  elimination with partial pivoting. Hartley-normalize 3D (centroid, mean
  distance) and 2D (same) first or the system is ill-conditioned.
- **Denormalisation is where it breaks.** With `u = u_n/s2 + c2u`, the correct
  map is `P = T2inv * M` where rows 0/1 carry `1/s2` and the centroid term comes
  from row 2 *unscaled*. Scaling all rows and then adding `c2*M2` gives ~94 px
  RMS on exact data. Correct version: 2.4e-14 px.
- **RQ for `P = K[R|t]`**: bottom-up Gram-Schmidt — express row `i` in the basis
  `Q[i..2]`, so the coefficient matrix is upper triangular. `K` then comes out
  exactly. Two wrong families to avoid: RQ via QR of the transpose actually
  yields **LQ** (K came back with 2.6e14 entries), and reversing rows/columns
  first is the same mistake in disguise.
- **Pose from one marker quad**: `A = K^-1 H`, `lambda = 1/|a1|`,
  `r1 = lambda*a1`, `r2 = lambda*a2` (Gram-Schmidt), `r3 = r1 x r2`,
  `t = lambda*a3`, and negate all three if `t_z < 0`. Exact on synthetic data.
- **Bundle-style refinement**: numeric Jacobian over 6 DOF, 6x6 normal equations.
  Apply rotation with a **Rodrigues exponential**, not `I + [w]x`: first-order
  updates drift off SO(3) (`R00` came back 1.0007). Accept a step only if the
  cost decreases, else revert and stop.
- **Multi-marker**: concatenate every marker's corner correspondences into one
  solve; do not average separately-solved poses when a joint solve is available.

## Marker decode

Warp the quad to a `(payload+2)` cell grid with `wubu_homography` + bilinear
sample, read cell centres (payload starts at cell index 1), build the bit word,
then Hamming-match against the dictionary. Require `hamming <= max_hamming`
(`0` for exact synthetic tests) and reject degenerate quads.

## Test-harness traps that produced false greens

- **Vacuous loop over a negative count.** A trace call returned `-1`; the
  assertion loop `for (i = 0; i < n; i++)` skipped, and a follow-up
  "all points on an edge" check passed on zero iterations. Assert the count
  first (`tn > 20`), then loop; never let `-1` mean "empty".
- **Freed fixture.** A later test block reused an image freed by an earlier
  block; the sampling function returned 0 for everything and the block reported
  `n = 0`. Rebuild fixtures locally in each block or keep them alive to the end.
- **Name collision in a monolithic test file.** `fp` was already a keypoint
  array; a new `wubu_pose fp[2]` failed to compile. Prefix new locals (`pfposes`,
  `pft`) instead of reusing short names.
- **Wrong expectation vs wrong code.** A warp test "failed" because I assumed a
  2x scale where the quad was a pure translation. Recompute the expected value
  by hand before changing the implementation.

## Cadence

One wave = implement module + property test -> `bash tools/count_gate.sh` ->
commit and push -> record the count in the module doc. `count_gate.sh` deletes
`test_*` binaries first so `make` cannot skip up-to-date targets; expect ~4-5
minutes, so run it in the background and grep the log rather than blocking.
