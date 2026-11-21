# C11 port order, exposure, and bound checks

The order below is the order that worked on a physical-modeling audio engine
(a Rust -> C11 slerm). It generalises: pure helpers first, then the thing that
produces the signal, then the network it drives, then the engine that schedules
it.

## 1. Math helpers -- header-only, no allocation

Port every transcendental through the platform `<math.h>`. Reproduce the
original's quirk helpers exactly; callers depend on them.

| original | C |
|---|---|
| `clamp(x, lo, hi)` | `wg_clamp` |
| `lerp(a, b, t)` | `wg_lerp` |
| `smoothstep(e0, e1, x)` | `wg_smoothstep` |
| `pow(2, c/1200)` | `*_cents_to_ratio` |
| mulberry32 PRNG | `*_rng_init/next/bipolar/gauss` |
| one-pole smoother | `*_smoother_init/step` |
| filtered-noise drift | `*_drift_init/step` |

Keep these `static inline` in a single header. Everything below depends on them,
so a mistake here propagates everywhere.

## 2. The source (oscillator / glottis / valve)

The module that turns control parameters into one sample of the primary
quantity (area, flow, voltage). Port state into an opaque struct, expose:

- `*_init(struct *, double fs)` -- set every default from the original's
  default-struct literal, and precompute the coefficients that depend on `fs`
  (smoothing factors are `1 - exp(-TAU*rate/fs)`).
- `*_reset(struct *)` -- phase and smoothed gates only.
- `*_next(struct *, <driving input>)` -- one sample.
- telemetry fields the UI/gate need: the smoothed gate, the instantaneous
  frequency actually used, the last output value.

**Expose the shape function** (`*_shape(ph, ...)`) if the original has one.
It is `static` in the source and the gate needs it; making it public with a
clear name beats a test-only backdoor.

## 3. The network / tract

Ports of a physical network carry per-node state and a step that couples them.
Keep the coupling order identical to the original -- reordering changes the
output. Port the node struct and the step function; do not "simplify" the
linear algebra.

## 4. The engine / voice

The scheduler: sub-block phase, per-block bookkeeping, event dispatch. Port the
sub-block constant and the phase arithmetic exactly; a host must be able to
render in any block size and get the same samples.

## Bound checks that catch a wrong mental model

A port compiles long before it is correct. These checks fail on a
misread of the original rather than on a typo:

- **Bounded output.** Drive the model over a long run and assert the output
  stays within its physical range. A wrong sign or a missing clamp shows up as
  an excursion.
- **Gate opens/closes.** If the original has a physiological or physical gate
  (pressure threshold, minimum energy), assert the output is silent below it
  and active above it. A misread threshold constant fails here.
- **Cycle count matches the frequency.** Count rising-edge crossings over a
  known duration and assert it is within a few percent of `f0 * duration`. A
  wrong period scale or a missing division by `fs` fails here.
- **The shape function's landmarks.** Assert the value at the phase the
  original's comment names (peak, closure, zero). Read the landmark off the
  source's own formula -- the peak of `0.5 - 0.5*cos(pi*t/s)` is at `t = s`, not
  at `t = 0`.
- **Extreme parameters stay bounded.** Max out every chaos/nonlinearity
  parameter and assert no NaN and no unbounded growth.
- **Idempotence and null-safety.** Double-close, NULL input, zero length.
