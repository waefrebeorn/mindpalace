---
name: devils-advocate-audit
description: Use when asked to find missed work via research + probes.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [audit, review, research, gates, self-critique]
---

# Devil's-advocate audit: find missed work recursively

## When to Use
- The user asks to attack your own (or the project's) recent work and find
  what was missed — "devil's advocate", "what did we miss", recursive
  self-audit using online research + ingenuity.
- Before declaring a milestone done on a large system.

## Procedure (in order)

1. **Research the state of the art on the SAME problem.** Primary sources:
   the reference projects' own docs, testing guides, and conference talks.
   Extract two things: (a) which architectural path they chose (e.g. every
   production tool-loader is a USER-mode emulator + syscall translation,
   not full-system emulation), and (b) their OWN acceptance/smoke standard
   (e.g. QEMU: static busybox + LTP). Compare against what we built; each
   divergence is a finding with a citation.
2. **Probe for bug-class siblings.** Every fix you made implies the same
   class may live elsewhere: a compiler-flag drift fixed in the kernel ->
   grep every other freestanding build (firmware, boot stubs) for the same
   inherited flag. A fix in one place is a hypothesis about its siblings.
   Scan ALL build paths, not just Makefiles — shell scripts that compile
   (run-*.sh with their own LCFLAGS) are build paths too. For the
   distro-march-drift family specifically: `-mno-sse` does NOT block BMI2
   (gcc still emits rorx/shlx for rotates/shifts under a v3 default), so
   the only safe fix is an explicit `-march=x86-64 -mtune=generic` pin on
   EVERY freestanding compile line. Reproduce by compiling the suspect
   file with the runner's default `-march=x86-64-v3` and objdump-counting
   BMI2/SSE insns, then with the pin (must drop to 0).
3. **Expand your gates until they catch real bugs.** A gate covering only
   the cases you remembered is survivorship bias. Widen dimensions (ops,
   widths, flag combinations, carry-in, direction flags) and add
   differential comparison against an independent model (native execution
   or independent C semantics). If the expansion finds nothing, suspect
   the expansion, not the code.
   Before trusting a new regression check, run it against the PRE-FIX
   implementation: swap in the HEAD version of the single changed file,
   run the test, restore and rebuild in a try/finally. A check that still
   passes on the old code is not testing the fix — assert an effect the
   old code cannot produce (table state, replacement semantics) rather
   than a returned value the buggy version also happened to return.
   For a separate submodule/library, link the NEW gate source against the
   OLD compiled library instead of editing one file in place. Prefer a gate
   written with pre-existing APIs only, so the old library compiles and fails
   BEHAVIORALLY: a macro-guard abort proves only that a symbol is absent,
   while a behavioural failure proves the old implementation takes the wrong
   path. State which kind of control each new gate has.
4. **Re-run every self-report.** Agent summaries, prior audit docs, and
   your own earlier claims are hypotheses. Run the gate yourself and read
   the real output before repeating a PASS. Audits that only read code
   miss runtime lies (a "mounted" banner printed over a silently failed
   mount); pair each code claim with a runtime probe where one exists.
5. **Check the security/contract surface, not just function.** Does the
   sandbox actually confine (can guest code jump outside the trap window)?
   Do claimed features match executed features? Does the gate assert real
   behavior or merely non-crash? Audit ABI/number tables against the
   canonical source: diff the project's syscall-number header against the
   host kernel headers (/usr/include/x86_64-linux-gnu/asm/unistd_64.h) —
   a single wrong number dispatches to the wrong handler and produces
   silent wrong behavior, not an error (a mislabeled nr made gettimeofday
   run fchown, so date printed epoch 0). Audit EVERY copy of the table, not just the header: the marshalling layer's case labels drift independently (a bridge case can marshal a nr as the wrong syscall even after the header is fixed). A guest->host syscall bridge must FAIL CLOSED: a default case passing unlisted syscalls to host handlers with guest pointers intact dereferences guest addresses as host pointers (silent corruption wherever mapped) — pass only a scalar-arg whitelist plus handlers proven to store-not-dereference a guest pointer, and -ENOSYS everything else until marshalled and gated. Write the diff script to a file
   and run it; an inline heredoc listing every syscall name can trip the
   command safety filter (reboot/shutdown etc. are blocklisted words).
   A fail-closed whitelist needs TWO more passes: map every listed number
   to its canonical name from the kernel header AND to the handler actually
   installed in the dispatch table, then read each handler's body. Classify
   each pointer-taking entry as: no handler (honest -ENOSYS — safe), stores
   the pointer without dereferencing (safe), or passes it to a host syscall
   (fail-open). "Looks scalar" is not evidence; the handler's cast is.
6. **Deliver findings as legs, and fix the cheap ones NOW.** Each finding:
   evidence (citation or probe output), what's missing, smallest real
   increment, acceptance gate. Write them into the project's roadmap doc;
   implement + gate the ones that fit the turn. For every gap still open
   at the end of the turn, either start the isolated worktree leg with an
   owner and a differential gate, or say plainly that it is blocked.
   An audit that only lists is half an audit.

## Pitfalls

- **When a full gate is red, first prove whether it is yours.** Check out a
  detached worktree at the session's starting commit and re-run the exact
  failing targets. A red baseline means pre-existing breakage; fix it as its
  own leg, but never claim your change caused it (or that the tree was
  green) without that comparison. Re-run the FULL gate after repairs.
- **A feature macro must not be a library's include guard.** A claim like
  "TLS is compile-gated off / VERIFY_NONE when enabled" is a hypothesis:
  actually compile the path. If the enable macro equals a header guard
  (e.g. `MBEDTLS_SSL_H`), defining it makes the header skip its own
  contents and the feature is dead; config calls made BEFORE a
  `*_config_defaults()` are reset by it. Prove both branches with a real
  handshake/bundle gate and a negative control before asserting either
  "insecure" or "fixed".
- **Tests ≠ correct. Run the negative control BEFORE claiming a defect.**
  A probe that passes with the fix and also passes with the old code is
  not a gate. Swap the old implementation back in, run the new probe,
  and require the expected failure; if it passes both ways, the
  hypothesis is disproved — revert the speculative fix and record the
  negative result. A read-modify-write bounce (preload guest bytes into
  a host buffer, then copy the whole buffer back) preserves adjacent
  bytes, so a fixed-size bounce is NOT automatically a clobber.
- **Toy gates prove mechanism, not mission.** A hand-assembled
  return-42 program passing says nothing about running real tools; adopt
  the reference project's own smoke standard as the bar.
- **Static-only is not "runs their binaries".** Real programs are dynamic
  (interpreter + libs) and threaded (futex/clone); name those as legs
  instead of implying the static gate covers them.
- **Don't stop at the first plausible root cause.** A CI-only fault has at
  least two variables (compiler AND emulator version); isolate each
  (reproduce the runner compiler locally rootless via apt-get download +
  dpkg -x; bisect machine/CPU) before naming the cause.
- **Never park a finding as an "honest remaining gap".** A gap section is
  not a deliverable: implement and gate it in this turn, or convert it to
  an in-flight leg with a named owner, worktree, and differential gate.
  Record STATUS (closed / in-flight with owner), not prose that merely
  names the absence — a phrased absence reads as work avoided. When told
  to fix every "honest" section, also sweep the doc for historical notes
  that still say "stub"/"open" and patch them to CLOSED with the gate
  that proved it; do not just add a newer entry and leave the stale line.
- **An ABSENT/MISSING verdict needs detector-liveness controls.** A probe that reports a tool, symbol, or capability missing must prove the detector can also report PRESENT: assert a known-present control is FOUND, a synthetic absent sentinel is MISSING, and a temporary shim flips the same detector MISSING→FOUND. Without those controls the verdict may come from a broken always-MISSING detector. Fail closed when any control misbehaves, and label the result VERIFIED_NEGATIVE rather than PASS.
- **A verified negative is a closure, not a parked gap.** When a leg adds
  real mechanism but must end in a precise fail-closed refusal (a new
  error code plus reason, distinct from the old vague failure), record it
  as CLOSED at that boundary with the differential gate and the exact
  refusal output. Do not relabel it an "honest gap" or claim the higher
  capability shipped, but do list what the refusal still blocks.
- **A verified-negative probe must be a passing assertion in the default
  tier.** Assert the exact refusal (errno/reason, no side effects) and exit
  0; if truthful execution must exit non-zero, keep it opt-in and label the
  result VERIFIED_NEGATIVE / NO PASS ASSERTED, with a negative control
  proving a forced success is detected. A raw non-zero in `make test` reads
  as a regression and hides the closure.
- **Shape gates pass on wrong data.** exit-0 + non-empty assertions let a
  program print garbage and still PASS (date printing 1969 passed a shape
  gate). For any semantically checkable output, pair the shape check with
  a VALUE assertion against an independent oracle (host coreutils output,
  the current year, a known checksum). A gate that passes on wrong data is
  worse than a failing gate — it hides the bug.
- **Pin every input before asserting determinism.** A check that polls live
  sensors, clocks, or load twice is comparing different inputs and will
  flake. Add explicit overrides for every external channel, use them in
  the test, and assert one override is applied verbatim — otherwise a
  green run proves only that the flake did not fire that time.
- **Poll asynchronous state; never sample it once.** A check that reads
  "is it RUNNING?" immediately after an async launch passes alone and
  flakes under a parallel gate. Wait on a bounded deadline (the same
  pattern as the marker/file wait) and assert the terminal state; one
  green run only proves the race did not fire. Poll through the accessor
  that ADVANCES the state machine (the reaping `state()` call), not a
  read-only lookup that can stay stale forever. When the action itself is
  async, retry the REAL action a bounded number of times with a poll
  between attempts; do not swap in a direct API call that bypasses the
  path under test. If a flake moves between assertions, add temporary
  phase diagnostics under try/finally, run at least eight iterations,
  and restore the instrumented file automatically before fixing.
- **Timing gates must measure leak removal, not retry until green.** Fix
  bit-length, vary the secret-dependent dimension, randomize trial order, and
  time CPU-bound work with `CLOCK_PROCESS_CPUTIME_ID` — wall-clock time
  counts deschedules as secret-dependent cost. Judge the hardened path
  RELATIVE to the leaking baseline measured in the same run (correlation
  delta and t-statistic ratio), not against an  absolute r threshold that
  frequency drift can cross while the operation count stays constant.
  Size the sample count for the busiest full-gate run, not a quiet standalone
  run, and require margin over the fixed threshold; a detector that goes
  vacuous under `-jN` is under-sampled, not wrong. A retry wrapper that
  reruns a statistical gate until it passes is not a gate: fix the estimator,
  then require consecutive clean runs. Call it a statistical differential,
  never "formally constant-time", unless codegen and the primitive's
  internals are proven. See `references/statistical-gates.md`.
- **Optional-dependency gates belong in the default tier with honest SKIP.**
  A check hidden behind an opt-in target is not part of the suite. Wire it
  into the default test tier with an explicit SKIP when its dependency is
  absent, assert the skip count (a partial skip set fails closed), and never
  convert a missing devroot into a silent PASS. Prove the default tier can
  go RED by injecting a regression into the shipped path and restoring it;
  otherwise a fresh tree is green while the guarded capability is broken.
- **Treat external strings as untrusted at every boundary.** Parameterize
  SQL with bind_text/bind_int instead of snprintf interpolation; prove the
  hole on a scratch DB with a stacked statement before patching. Validate
  identifiers before they become glob patterns, using ONE shared validator
  called both at ingest and at public API boundaries — binding a string
  into SQL does not make it safe as a filesystem pattern.
- **Dispatch-table collisions are silent.** Two #defines with the same
  number (lchown=95 vs umask=95) make designated-initializer table entries
  overwrite each other — one handler vanishes without any warning. When
  auditing a number table, also check for DUPLICATE numbers and structural holes (a define with no table entry, a NULL handler, a stale entry name), not just
  wrong ones. And libc-wrapper syscall handlers must TRANSLATE return
  semantics: libc getcwd returns the buffer pointer, the syscall returns
  the length — passing the pointer through made the consumer copy
  pointer-sized garbage (segfault).
- **Relink scratch probes after every library rebuild.** A probe binary
  linked against a stale .a keeps showing the OLD bug after the fix;
  several debug cycles were spent chasing "still broken" that was just a
  stale runner. Same for whitebox CPU probes: HLT latches (clear halted
  or use a fresh cpu between runs), and get blob addresses from nm, never
  from .org arithmetic.
- **Name the exact failing instruction and its owner before claiming a
  boundary.** Take the fault RIP, fault code, syscall log and the failing
  store/load, then attribute it to a subsystem; do not infer "allocator"
  or "stdio" from a symptom like a bad write count. Why: two adjacent
  subsystems can produce the same output shape, so a symptom-named closure
  gates the wrong mechanism and leaves the real boundary untested.
- **Move a state-sensitive real case into a fresh child process.** When a
  full probe spins or changes behavior only after earlier cases in the same
  process, put the real case in its own process and keep the accumulated
  cases in the default gate. Why: leaked engine/registry/signal state is
  part of the observation, so an in-process "fix" can pass by avoiding the
  state rather than by closing the gap; a fresh process keeps the
  differential honest and reproducible.
- **Remote boot-gate failures: find WHERE it stopped, not just WHAT is
  missing.** A marker list ("kernel_main reached: MISSING") says what
  didn't happen, not where the chain stalled. On failure, dump the boot
  log's last words (the loader/firmware print explicit FAIL markers that
  pinpoint the stall) and upload the log as a CI artifact. To discriminate
  slow-vs-hung on a throttled runner, add chunked progress markers inside
  the long silent stretch (e.g. hash the image in 256KB chunks, print
  n/total) — if even the first chunk never completes, it is hung, not slow.
  Make subprocess timeouts window-aware (a 300s boot window inside a 180s
  subprocess timeout false-fails); honor the env override everywhere, don't
  hardcode a smaller window in one gate path.
- **Cadence-based liveness markers are timing-dependent on device MMIO.**
  A 5 Hz heartbeat from a full-frame redraw misses a fixed boot window under
  TCG even while the loop is alive; assert a scheduler-level marker
  (continuous promotions) instead, and KEEP the first-frame, display and
  error-marker assertions — swap the oracle, don't weaken the gate. Apply
  it to every path that renders to device memory, not just the one that
  first exposed it.
- **See `references/ci-probe-recipes.md`** for reading Actions job logs,
  dispatching a watched run without putting the token into shell text, and
  keeping negative controls portable to shallow CI checkouts.
- **See `references/statistical-gates.md`** for the stable timing-gate recipe
  (clock, randomized order, same-run baseline, negative control, no retries).
- **See `references/async-gate-races.md`** for the 8-run diagnosis recipe
  (temporary phase diagnostics, state-driving poll, bounded real-action retry).
