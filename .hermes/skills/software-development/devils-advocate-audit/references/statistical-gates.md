# Stable statistical differential gates

Use for timing or side-channel gates where a single run is noisy.

## Procedure

1. **Pin every input except the tested dimension.** Fixed bit length or
   fixed payload size; vary only the secret-dependent dimension (e.g.
   Hamming weight). Add a functional-equivalence check between the old and
   new implementations over many distinct random inputs before any timing
   verdict.
2. **Randomize trial order.** A monotonic sweep measures clock drift as a
   leak. Shuffle the input indices and time old and new side by side under
   the same conditions.
3. **Use process CPU time for CPU-bound work.** `CLOCK_MONOTONIC` counts
   deschedules and other tenants as secret-dependent cost;
   `CLOCK_PROCESS_CPUTIME_ID` excludes preemption while still measuring the
   work. Keep enough reps and trials to average out timer granularity.
4. **Judge leak removal against the same-run baseline.** Require the old
   implementation to leak (significant positive correlation and a bounded
   spread). For the hardened implementation require a large drop in that
   correlation and t-statistic relative to the old measurement, plus a
   bounded spread. An absolute `abs(r_new) < threshold` verdict fails when
   frequency drift moves a flat ladder's measured correlation.
5. **Prove the negative control.** Compile the pre-fix implementation
   side by side and confirm it fails the new gate in the expected direction.
   Report the measured numbers, not just PASS.
6. **Require consecutive clean runs.** Run the gate three or four times
   without changing sources. A retry wrapper that accepts the first PASS
   after failures is gate theater: fix the estimator, do not mask the noise.

## Structural multi-configuration evidence

For a constant-time claim backed by source plus compiled machine code, one
compiler/optimization level is a single data point. Run the same structural
checker under at least two DISTINCT usable configurations (different
compiler binaries or optimization levels): require every configuration to
accept the shipped code, inject a secret-dependent branch into a temp copy
and require every configuration to reject it, then assert all verdict
patterns are identical. If fewer than two configurations are usable, fail
closed with an explicit VERIFIED_NEGATIVE probe transcript — never promote
a single-config result to a PASS. Why: a branch that disappears at -O2 may
reappear at another level, and a checker that cannot see a deliberate
regression in one configuration is a vacuous gate.

Keep the claim bounded: say "structural evidence under these compiler
configurations", not "formally constant-time". Record what is NOT covered
(e.g. -O0 stack-slot taint, clang, microarchitectural channels) in the same
doc as the evidence, and wire the gate into the default tier with a
fail-closed verdict rather than leaving it opt-in.

## CI wiring

- Keep one fail-fast aggregate for all opt-in gates with a pinned,
  repo-local toolchain root — no scratch-directory paths, no secrets.
- Do not add statistical retries to CI. Once the estimator is stable, every
  gate runs exactly once; a failure must remain a failure.
- A detector that passes alone but goes vacuous under a parallel full gate
  is under-sampled, not wrong: sibling jobs contending for CPU shrink the
  control's t-statistic. Increase ONLY the sample count (expose an env
  override with a sane clamp) and re-run at the same `-jN` the full gate
  uses; keep the significance thresholds fixed and still require one pass.
  Log the worst observed control margin so the next under-sampling is
  visible before it crosses the threshold. Why: loosening a threshold turns
  a real leak detector into one that always passes, while more samples
  recover the statistic without changing what counts as a leak.
- Treat a bare threshold crossing as under-sampled too: if the worst control
  margin at the full gate's `-jN` is only slightly above the fixed threshold,
  raise the sample count again and re-run before calling the gate stable.
  Why: a margin that survives one run can flip under different sibling-job
  load, so the verdict must not depend on which targets happen to run.
- A cross-configuration driver should invoke the EXISTING timing gate with
  compiler/optimization environment overrides instead of duplicating the
  timing harness. Why: a copied harness drifts in thresholds or sampling and
  the configurations stop being comparable.
- Call the result a statistical differential, not a formal constant-time
  proof. State exactly which internals and compiler behavior remain
  unverified.
- When promoting a statistical gate into the default suite, print an explicit
  SKIP (never a silent PASS) when its toolchain root is absent, and assert
  the skip count in the output. A suite that quietly omitted the gate is not
  evidence that the gate held.
