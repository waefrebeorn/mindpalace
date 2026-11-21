---
name: wubuglott-vocal-synth
description: Use when porting the chimera vocal synth to C11 (WuBuGLOTT).
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wubuos, audio, synth, c11, port, chimera]
    related_skills: [wubuos-hosted-product, wubuos-egojar-room]
---

# WuBuGLOTT -- the chimera vocal synth in C11

WuBuGLOTT is a C11 reimplementation (slerm) of
[jamesondh/chimera-vocal-synth](https://github.com/jamesondh/chimera-vocal-synth),
a physical-modeling voice synthesizer. Every sound comes from a simulated
airway (lungs, vocal folds, branched vocal tract, lips, nose), never samples.

Port target: `src/audio/glott/` in WuBuOS.

## When to use

- Porting more of chimera (`crates/chimera/src/`) into WuBuGLOTT.
- Debugging the glottal source, the airway network, or the voice.
- Wiring WuBuGLOTT into the product (the device sink already exists).

## The model, in one paragraph

The glottis produces an **area** waveform, not flow. Flow comes from the
airway network (Bernoulli + inertance), so pulse skewing, F1 ripple and
devoicing under oral closure emerge from the physics instead of being
scripted. Voicing is gated physiologically: transglottal pressure must clear
~2-3 cmH2O and the folds must be adducted.

## What is ported (verified)

| file | from | state |
|---|---|---|
| `wubuglott_math.h` | `math.rs` | done, header-only |
| `wubuglott_physics.h` | `physics.rs` | done, constants only |
| `wubuglott_glottis.[ch]` | `sources/glottis.rs` | done, gated (`make test_glottis`) |
| `wubuglott_network.[ch]` | `airway/network.rs` | done, gated (`make test_glott_network`) |
| `wubuglott_voice.[ch]` | `voice/human_voice.rs` + `human_airway.rs` | done, gated (`make test_glott_voice`) |
| `wubuglott_decimator.[ch]` | `airway/decimator.rs` | done, gated (`make test_glott_decimator`) |
| `wubuglott_geom.[ch]` | `anatomy/geom.rs` | done, gated (`make test_glott_geom`) |
| `wubuglott_artic.[ch]` | `anatomy/human.rs` (HumanArtic/body) | done, gated (`make test_glott_artic`) |

`wubuglott_glottis` carries: LF-style area pulse, the voicing gate, jitter,
shimmer, vibrato, fry double-pulsing, diplophonia, and a logistic-map chaos
path into period doubling. `wg_glottis_shape()` is exposed for the UI and
the gate.

`wubuglott_voice` is the instrument: the full airway layout (trachea,
pharynx, oral, nasal, piriform fossae, sinus, lungs, glottal and velum
ports, lip/nostril radiation), the oversampled render loop, the 1 kHz
control rate, DC blocker and limiter. It renders a real voice: fundamental
at ~110 Hz with a strong H2, and /a/ vs /i/ centroids 527 vs 1404 Hz.

`wubuglott_decimator` is the Kaiser-windowed sinc FIR (taps = factor*24+1,
cutoff 0.46/factor, beta 8.5); it owns the oversampling ratio, so the render
loop renders sub-samples until it returns a sample. Its gate proves the
point of the filter: at 48 kHz / factor 4 a 5 kHz tone survives (0.862) and
a 9 kHz image is attenuated to 0.000.

`wubuglott_geom` is the 2D toolkit the tract geometry is built from: Vec2,
the flat polyline, ray crossings with exit flags, Bezier/arc samplers,
Catmull-Rom splines and circle tangents. `wubuglott_artic` is the control
surface those splines consume: HumanArtic's 17 keys, NEUTRAL, the three
bodies and BodyMix's weighted blend.

## What is NOT ported yet

- **The tract spline `compute()`** -- `anatomy/human.rs` (1506 lines): the
  splined tongue, rotating jaw, velum flap and lip aperture that turn
  `wubuglott_artic`'s parameters into the real area functions. The geometry
  toolkit and the articulation model it consumes are ported;
  `compute_areas()` in `wubuglott_voice.c` is a shaped constriction law
  (position + degree + jaw + lips) with the same interface, and
  `resample()` is ported.
- `airway/frequency.rs`.
- `sources/syrinx.rs`, `sources/valves.rs`, the creatures, the phonetics
  front ends (English/Korean), the beatbox.

## References

- `references/tract-geometry-interface.md` -- what `resample()` consumes, the
  tract's landmarks, what `compute()` does in order, and the slew limiter a
  replacement must keep (closures click without it).

## Pitfalls

- **The glottis emits AREA, not flow.** Do not wire its output straight to a
  sink; it drives the glottal port of the network. A port that skips the
  network will produce silence or a click.
- **The pulse shape peaks at `t = skew`, not at phase 0.** `shape(ph,oq,skew,sharp)`
  is closed at `ph=0`, peaks at `ph = oq*skew`, closed from `ph = oq`. A gate
  that asserts a peak at phase 0 is wrong.
- **`M_PI` is not C11.** The port uses `WG_PI`; do not introduce `M_PI`
  (it needs `_USE_MATH_DEFINES`/gnu mode and breaks `-std=c11`).
- **Node count is bounded by the CFL condition.** `dx` must exceed
  `(c/fs)/0.93` = 0.783 cm at 48 kHz; an 8.3 cm tube takes 10 sections, not
  32. Too many sections makes the leapfrog scheme blow up (pressure grows
  ~11x per sample). A property of the model, not a bug.
- **`rad_of` must be initialised to -1** (the original is `vec![-1; n]`).
  `malloc` without the init gives every node a random radiation load and
  sealing an aperture stops working.
- **Never let one capacity cover several arrays.** `tubes`/`tube_length`/
  `tube_specs` grow together; three separate `GROW` calls on one cap leave
  the second and third NULL.
- **The output is d/dt of radiated flow, in CGS.** It arrives enormous.
  chimera's `output_gain` is `5.5e-7`; with `1.0` the limiter pins the
  output at full scale and the "voice" is a square wave (47k of 48k samples
  at exactly +-32000). If a render looks like a stuck full-scale signal,
  check the gain first.
- **Gate on `wg_network_radiated_flow`, not on the output, when testing a
  seal.** Sealing an aperture makes a step in that flow, so the *output*
  spikes while the *radiated flow* correctly decays (at 0.995/step).
- **cmH2O vs dyn/cm^2.** Threshold pressure is `2.5 * WG_CM_H2O`. Mixing
  units gives a voice that never voices or always voices.
- **The RNG is mulberry32 with 32-bit state.** Determinism is a feature
  (chimera guarantees bit-identical samples across targets). Keep the exact
  operation order; do not "simplify" the wrapping arithmetic.
- **`wg_glottis.h` includes `wubuglott_math.h`** because its struct embeds
  `wg_rng`/`wg_drift`. Forgetting that include gives "unknown type name
  'wg_rng'".

## Building and gating

```bash
make test_glottis        # the source gate (8 checks)
make test_glott_network  # the airway solver gate (6 checks)
make test_glott_voice    # the instrument gate (6 checks, renders a WAV)
make test_glott_decimator # the FIR gate (5 checks, image rejection)
make test_glott_geom     # the 2D toolkit gate (8 checks)
make test_glott_artic    # the articulation model gate (7 checks)
make test_glott_speak    # the product facade gate (5 vowels through the sink)
```

The gate is not assert-nothing: it drives the model with a real
transglottal pressure and checks no vibration below threshold, real
amplitude and several glottal cycles above it, bounded non-negative area,
the pulse shape, f0 with vibrato off, fry pulling f0 toward 45-48 Hz, and
chaos staying bounded over 1 s.

## Where the sound comes out

`src/audio/wubu_glott.c` is the product facade: `wubu_glott_speak(vowel, ms,
f0)` renders one of the five cardinal vowels and pushes it through
`wubu_audio_sink_int16` (int16 PCM -> float -> big-mac's `bigmac_out`:
Pulse -> ALSA -> WAV). The desktop opens the sink at boot.

The agent channel reads `$HOME/.wubu/n/agent/speak` (a vowel name), speaks
it once, and consumes the flag -- the same pattern as `open_walkthrough`.

Gate: `make test_glott_speak` (run with `BIGMAC_BACKEND=wav`, reads the WAV
back and measures RMS + the f0 bin).

## Wiring pitfalls

- **A gate that removes the sink's wav out from under the open `FILE*`**
  sends the audio into an unlinked inode. Close, remove, reopen.
- **`bigmac_out` buffers the wav until `bigmac_out_close()`** (which patches
  the RIFF header). Use `bigmac_out_flush()` / `wubu_audio_sink_flush()`
  before reading.
- **`src/*/test_*` is gitignored.** Name test files `*_test.c`.
- **A pointer-returning function with no header declaration gets its return
  truncated to `int`** (implicit declaration) -- a garbage pointer handed to
  printf. Declare every accessor.
- **The network stores tube-spec pointers; copy anything the caller may
  free.** The nasal profile is copied into the network and freed with it.
