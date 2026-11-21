# The tract geometry interface (for porting `compute()`)

`wubuglott_voice.c`'s `compute_areas()` is a shaped constriction law standing in for
chimera's `HumanVocalTract::compute` (`anatomy/human.rs`, ~1500 lines). The
replacement must satisfy the interface below; `resample()` is already ported
and consumes it.

## What `resample()` consumes

The tract computes a FRAME, and `resample` reads these fields off it:

| field | meaning |
|---|---|
| `grid[]` | section centres along the whole airway, ascending in `s` |
| `grid[i].s` | distance from the glottis (cm) |
| `grid[i].area` | area at that point (cm^2) |
| `pharynx_length` | where the pharynx ends and the oral cavity begins |
| `lip_s` | total length to the lips |

`resample` then:
1. splits the range at `pharynx_length` and fills the pharyngeal sections;
2. fills the oral sections from `pharynx_length` to `lip_s`;
3. below an `epi_len` flare it substitutes the epilarynx area law and lerps
   the last few millimetres into `grid[0].area` (so there is no step at the
   top of the epilarynx);
4. finds the area at arbitrary `s` by binary search on `grid`, then for each
   output section takes 8 sub-samples and uses the HARMONIC mean
   (`sub / sum(1/a)`) -- with a point closure (`a <= 1e-5`) sealing the
   section to 0;
5. also reports each section's sub-sample minimum, which drives the kinetic
   losses.

## The tract's own landmarks (body frame, cm, before scaling)

`HumanVocalTract::new` builds these with Catmull-Rom splines, then the
articulation transforms them:

- `phar_wall` -- posterior pharyngeal wall, bottom to top
- `palate` -- the oral roof
- `pns` -- the posterior nasal spine, where the velum flap hangs
- `condyle` -- the jaw's rotation centre
- `polar_c`, `polar_c2` -- tongue pivot points
- `nasal_cavity` -- the nasal roof profile

`p(x, y)` maps template coordinates to body coordinates: the oral region
(`x > 0.5`) is compressed by 0.86, the pharynx (`y < 7`) is shortened by the
body's pharynx factor, and everything is scaled by the body size. This is why
the same template gives a ~17.5 cm neutral tract on an adult male.

## What `compute()` does, in order

1. larynx offset moves the glottis;
2. the jaw rotates about the condyle by `-clamp(jaw,-0.2,3.0) * k / jaw_r`;
3. the velum flap rotates from the PNS, its angle from the port area;
4. the tongue body is a spline through the pivots, deformed by `tb_x/tb_y`,
   `tt_x/tt_y`, `tt_curl` and `root`;
5. the lips form an aperture from `lip_ap`, `lip_prot` and `lip_width`;
6. the epilarynx narrows by `epilarynx` (twang) and `ventricular`;
7. rays are cast from a midline point outward to the walls to build the grid.

## The rate limiter (a real trap)

`HumanAirway::apply` does not set the areas directly. It slew-limits them
against the values the control step STARTED from, with a rate that grows with
cross-section and eases down near contact:

```
open:   (max_area_rate*k2 + area_rate_gain*A) * dt
close:  (close_r(A) + area_rate_gain*A) * dt
close_r: seal_r*sqrt(A/seal_ease)         for A < seal_ease
         seal_r + (open_r - seal_r)*smoothstep(lo, hi, A)   otherwise
```

The closing rate deliberately slows with sqrt(A) near contact: at a constant
rate the flow's slope drops to zero instantly, which is a step in the
radiated pressure (an audible click). Any replacement for `compute_areas`
must go through the same slew limit, or closures click.

## Honest status

Do not claim the tract is ported until `compute()` is. The shaped law produces
a correct vowel space (measured: /a/ centroid 527 Hz, /i/ 1404 Hz) and the
voice is intelligible, but it is not chimera's tongue.
