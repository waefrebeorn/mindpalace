# Property-test oracles for CV / geometry / signal primitives

A primitive is not done when it "runs" and returns 0. It is done when a test
asserts a NUMERIC PROPERTY that would fail for a plausible wrong
implementation. This file is the recipe and the oracle patterns that actually
caught bugs (and the ones that caught nothing).

## The module-wave loop

One wave = one capability. Do not batch two capabilities into one commit; a
failed gate then cannot tell you which one broke.

1. Declare the API in the module header (and only what the module owns — see
   P83 before naming a foreign type).
2. Implement in the `.c`, compile ALONE first:
   `gcc -O2 -Wall -Wextra -std=c11 -I include -c src/wubu_X.c -o /tmp/x.o`
   Fix every warning before touching the test tree; implicit-declaration
   warnings under `-std=c11` are real bugs (P17/P42).
3. Add the property test to the module's existing test file (one test binary
   per module family, not one per function).
4. `make test_X` and read the printed measurement, not just PASS/FAIL.
5. Run the honest gate: `bash tools/count_gate.sh` (deletes top-level `test_*`
   binaries so make cannot skip; prints binaries run / ALL-PASSED lines / FAIL
   lines). It takes ~4-5 minutes — run it in the background with a log:
   `bash tools/count_gate.sh 2>&1 | tee <scratch>/gate.log | tail -3`, then
   `sleep 250; grep -E 'binaries run|ALL-PASSED lines|FAIL lines' <log>`.
6. Commit with the measured number in the message ("recovers (6,7) within
   0.8 px", "RMSE 0.885 vs 7.642"). A commit message that says "added X" with
   no measurement is a claim without evidence.
7. Update the module-status doc in the same commit — a table row that still
   says "queued" after the code landed is how a repo starts lying.

If a foreground `sleep`/gate is pushed to the background by an incoming
message, do not re-run it: the command is still alive, so poll the log file
it was teeing to.

## Oracle patterns (use one per capability)

**Known-transform recovery.** Apply a synthetic transform with known
parameters, then assert the estimator returns them within a stated tolerance.
- integer shift (2,3) -> exact `(2.00, 3.00)` for LK; `0.206/0.151 px` for
  dense Horn-Schunck; `(6,7)` for pyramid LK; 36/36 interior blocks for block
  matching; `0.125/0.109 px` for sub-pixel block flow on (3.4,4.6).
- Never assert on the border (P82): clamping makes border cells wrong on
  correct code.

**Exact identity / round-trip.** The strongest oracle when it exists.
- `down2x(uplift2x(x)) == x` exactly — a mass-conserving zoom cannot invent
  pixels; this single equality validates both kernels.
- `hash(rotate90(img)) == hash(img)` for a D4-canonical hash.
- identical frames -> exactly zero motion field.

**Lattice / structure counting.** For detectors, assert the COUNT and the
GEOMETRY, not "found something".
- checkerboard 160x160, 20 px cells -> exactly 49 interior corners, every one
  within 2 px of the lattice; then a shuffled input must order back to a 7x7
  grid (origin 19,19 -> far 139,139) with monotonic x per row.
- contour tracing -> every traced point lies on an edge pixel, angular order
  with at most one wrap, loop closes within 3 px of its start.

**Statistical sanity with a fixed critical value.** For RNGs, pin a vector and
add a chi-square with the tabulated critical value (310.46 for 256 bins at
0.01), plus a 10k-sample hash as the cross-arch guard. See
`deterministic-rng-testing.md`.

**Super-resolution / multi-frame.** Compare against a KNOWN high-resolution
scene and against a naive baseline — a bare "output is 2x" assertion proves
nothing. Burst SR hit RMSE 0.885 vs 7.642 for single-frame bilinear upsampling.

**Quality-vs-cost.** When the module spends budget (tokens, pixels), assert the
budget is respected exactly: `2 x 97` token budget -> 2 ROIs and
`tokens_used == 194`.

## Anti-patterns that cost time

- **Reusing a freed fixture** (P81). The call returns -1, the loop body never
  runs, the assertion passes. Always `CHECK(n > 0)` before a per-item loop.
- **Asserting an approximation matches a famous algorithm.** If the header
  says Farneback and the code is a linear-moment shortcut, the test will either
  be too loose (green, wrong) or reveal 475 px error. Name what you built (P84).
- **Tuning coefficients until one fixture passes.** A wrong derivation can be
  fitted to one displacement and fail on every other. Revert and implement the
  real method, or ship the honest simpler one you already have.
- **A test that only checks the return code.** `== 0` says the function did not
  reject its input, nothing about the output.

## Gate honesty

`make test` alone can skip (compare binary vs source timestamps) and a piped
`make ... | tail` reports tail's exit status (P78). Use the count script, and
quote its three numbers (binaries run, ALL-PASSED lines, FAIL lines) in the
report — a pass count with no run count is not evidence (P68).
