# Geometric vision in C11: worked recipes and the traps that cost real time

Scope: `wubu_cv`, `wubu_flow`, `wubu_calib` and friends — modules whose output is
a number (a pose, a focal length, a pixel shift) rather than a flag.

## The one rule that covers all of it

Prove the answer, never the shape. Build synthetic data from a known truth
(exact corner lattice, exact shift, exact pose, exact K), run the estimator,
print the measured error, and assert recovery. `isfinite()` and `!= NULL` are not
tests. Several of the failures below passed "it runs" checks while being wrong
by hundreds of pixels.

## DLT PnP

- Fix p34 = 1 and solve 11 unknowns by normal equations on 2n rows.
- Normalise BOTH sides (Hartley): centroid subtract, mean-distance scale
  (`sqrt(3)/d3`, `sqrt(2)/d2`). On exact data this takes the reprojection RMS
  from "drifts" to 2.4e-14 px.
- Denormalise as `P = T2inv * M * T3`. Rows 0 and 1 carry `1/s2`; the centroid
  term `c2 * row2` is added with row 2 unscaled. Scaling all three rows by 1/s2
  uniformly is harmless (projective scale), but mixing scaled rows with an
  unscaled centroid term gave 94 px RMS on data with zero noise.
- Guard `n >= 6`; return -1 otherwise rather than solving an underdetermined
  system silently.

## RQ decomposition (K from P)

- Correct method: bottom-up Gram-Schmidt. For i = 2..0, project row i onto the
already-built Q rows i+1..2, store those coefficients in R[i][j], normalise the
remainder into Q[i]. Result: R upper triangular, Q orthogonal, M = R Q.
- Wrong method that looks right: QR of M^T gives M = Rb^T Qb^T with Rb^T LOWER
triangular — that is an LQ factorisation. Symptom: K entries around 1e14.
- After the split, verify by reconstructing P and reprojecting. For an already
triangular P (axis-aligned camera) K should come back exactly and R as identity.
- `t = K^-1 p4` after normalising K[2][2] = 1. For P with a non-zero principal
point, t is NOT the value in the fourth column — p4 = (0,0,6) with cx = cy = 80
gives t = (-0.96,-0.96,6). That is correct; do not "fix" it.

## Rotation updates inside Gauss-Newton

- `R <- (I + [w]x) R` is only valid infinitesimally. Accumulated over 20+ steps
  it drifts off SO(3) — observed R00 = 1.0007 after translation had converged.
- Use Rodrigues: `R_d = I + sin(t)K + (1-cos(t))K^2` with `K = [w]x / |w|`.
- Keep step rejection: save R,t, evaluate cost after the step, revert and break
  if it got worse. Accepting every GN step lets a bad linearisation ruin a
  converged solution.
- Verify the rotation as a whole matrix (`sum |R - expected| < 1e-6`), not one
  entry.

## Planar marker pose and fusion

- Single marker: `A = K^-1 H`, `lambda = 1/|a1|` (averaging 1/|a1| and 1/|a2|
  is more stable), `r1 = lambda a1`, `r2 = lambda a2`, `r3 = r1 x r2`,
  `t = lambda a3`. Fix the sign so `t_z > 0`, then Gram-Schmidt r1/r2 before
  recomputing r3.
- Fusion: weighted mean translation; rotations as quaternions with hemisphere
  alignment (flip sign when dot(q, q_ref) < 0) before normalising. Identity plus
  90 deg yaw must fuse to exactly 45 deg (cos = 0.707107) — a one-line check that
  the quaternion path is right.

## Distortion: what is and is not identifiable

- Model: Brown-Conrady first two terms; inverse by fixed-point iteration
  (`x = nx/(1 + k1 r^2 + k2 r^4)`), ~20 steps, round-trips to 2.8e-14 px.
- Whole-image undistortion: output pixel p samples the source at `distort(p)` —
  the opposite direction from the point inverse. Test with a SMOOTH frame; a
  checkerboard gives ~72 levels of error purely from two resamplings straddling
  cell edges, which is not a warp bug.
- Fitting k1/k2 with a free pose from one view: degenerate. Returned
  k1 = k2 = 0.780, t_z = 6.817 for true (0.12, -0.03) and 0.5.
- "Undistort observations, then fit the pose" is worse than degenerate: pose
  absorbs the distortion error, so the cost is flat in k2 (0.112 / -0.006).
- Moving residuals into the distorted domain (project -> distort -> compare)
  with three views at 0/20/-17 deg and 0.6-0.9 m STILL gave 0.112 / -0.004:
  a planar grid's homography absorbs radial distortion.
- Conclusion: k1/k2 need capture whose points reach the image corners at several
  depths, then one joint bundle over poses and coefficients. Do not re-tune the
  alternating search; it is the wrong instrument.

## Measurement honesty in flow and features

- Report block-matching accuracy on the interior grid. Border blocks lose
  content to clamping and drag the number down (77% overall vs 36/36 interior on
  a known (3,4) shift) — quote the honest subset and say why.
- Name the algorithm for what it does. Integer centroid refinement is not
  "sub-pixel"; a SAD search is not "Farneback". If the name overpromises,
  rename before commit.
- Farneback via the linear-moment shortcut is wrong for the polynomial
  coefficients (mean error 475 px in x, 351 px in y on a (2,3) shift). The route
  that works is a 6x6 normalised-convolution fit over
  `[1, x, y, x^2, xy, y^2]` followed by the displacement solve.

## Test-vacuity traps seen in this codebase

- Using an image or buffer after `wubu_img_free` — the "passing" test measures
  zeros. Build the fixture inside the test that needs it.
- Asserting a quantity computed from a different mapping than the code uses
  (expecting 2x scale where the quad maps by pure translation). When a test
  fails, first ask which model the assertion encodes.
- Reusing a struct or array name already in scope (`fp` for poses vs keypoints)
  — the compile error looks unrelated to the change. Prefix test locals.
- A Makefile edit that "should" add a source file but silently matches nothing:
  after the edit, confirm the new test's output actually appears.
