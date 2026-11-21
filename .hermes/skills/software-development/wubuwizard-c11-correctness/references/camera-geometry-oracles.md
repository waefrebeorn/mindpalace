# Camera geometry (calib3d) — implementation recipes and oracles

Applies when implementing PnP, homography, warp, or marker decode in pure C11
(`wubu_calib.c`). Every recipe below is verified against synthetic ground truth;
none of it needs a real photo or a calibration target.

## Oracle discipline (the whole point)

Build the answer, then invert it. Given a known `P = K[R|t]`:

1. project N >= 8 known 3D points to 2D,
2. run the solver on those exact correspondences,
3. require reprojection RMS `< 1e-6` (measured 2.4e-14) and K/R equal to the
   known values.

A solver that passes on real (noisy) data and fails this test is wrong; a solver
that passes this test and fails real data is usually a conditioning problem, not
a derivation problem. Never accept "the picture looks aligned" as evidence.

## PnP by normalised DLT

Unknowns: 11 (`p34` fixed to 1). Per correspondence, two rows:

```
[X Y Z 1 0 0 0 0 -uX -uY -uZ] · p = u
[0 0 0 0 X Y Z 1 -vX -vY -vZ] · p = v
```

Normalise first (Hartley): centre both point sets on their centroids, scale 3D by
`sqrt(3)/mean_dist` and 2D by `sqrt(2)/mean_dist`. Build the 11x11 normal
equations, solve with partial-pivoting Gaussian elimination.

Denormalise as `P = T2⁻¹ · P_n · T3`:

```
M_row = P_n_row · s3 ;  M[3] -= s3·(P_n_row · c3)      for each row
P_row0 = M_row0/s2 + c2u · M_row2
P_row1 = M_row1/s2 + c2v · M_row2
P_row2 = M_row2
```

Scaling ALL rows by `1/s2` and adding the centroid term from the scaled matrix
gives 94 px RMS on exact data. Homogeneous scale is free, but the *relative*
weight of row 2 versus rows 0/1 is not.

## RQ decomposition (P = K[R|t])

Bottom-up Gram–Schmidt on the rows of the 3x3 left block:

```c
for (int i = 2; i >= 0; i--) {
    v = M[i];
    for (int j = i + 1; j < 3; j++) { R[i][j] = dot(v, Q[j]); v -= R[i][j]*Q[j]; }
    R[i][i] = norm(v); Q[i] = v / R[i][i];
}
```

Then `t = K⁻¹ p4` by back-substitution, after normalising `K[2][2] == 1`.

Not RQ: "QR of the transpose" (gives LQ, K entries ~1e14) and any row/column
reversal trick you cannot verify in two lines. Sign-fix per row by flipping K row
i and R row i together so the diagonal is positive.

## Homography from four pairs

Same 8-unknown linear form as one DLT slice (`H[8] = 1`). Decompose nothing — a
homography is only defined up to scale, so there is no K/R/t to extract.

`warp_perspective` must invert H (adjugate/det) and sample bilinearly; guard
`|det| < 1e-12`.

Oracle: pick a quad and a destination quad whose mapping you can state in one
line (`src→dst` spanning 40 px is a −40 translation, NOT a 2x scale — get this
right in the TEST first). Then every sampled pixel must equal the source exactly
(measured 49/49), because the mapping is pure resampling of the same grid.

## Marker decode (4x4 payload, 1-cell border)

Warp the quad to `6·cell` pixels, sample cell centres at `(c+2)·cell − cell/2`
(the `+1` skips the border cell, the `−cell/2` lands mid-cell). Threshold at 128,
pack row-major into 16 bits, match by popcount against the dictionary, accept
within `max_hamming`.

Oracle: render the marker from the dictionary entry itself (black border, white
payload bits), decode, require `id`, `bits` and `hamming == 0` exactly; then an
all-black payload must return -1 at `max_hamming = 0`. Choose dictionary entries
with pairwise Hamming distance >= 3 (print the matrix in the test so a future
edit cannot silently collapse it).

## Makefile wiring pitfall

`test_cv`'s recipe lists its sources EXPLICITLY; editing a generic source string
with `str.replace` hit a different rule and the link failed with
`undefined reference to wubu_pnp_dlt`. Patch the exact recipe line (match on the
`$(CC) ... -o test_cv ` line), and treat any `undefined reference` naming your new
function as "the recipe did not change", not "the code is missing".
