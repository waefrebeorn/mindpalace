# Async gate races: diagnosis and repair

Use when a gate passes in isolation, fails inside the full suite, or the
failure moves between different assertions across runs.

## Procedure

1. **Run a batch, not a single retry.** Invoke the exact make target 8+
   times, record each rc, and count failures. A single green run only
   proves the race did not fire that time; a retry-until-green wrapper is
   not evidence.
2. **Localize the moving failure.** Temporarily instrument each async
   boundary in the test with phase diagnostics, run the same 8-iteration
   batch, then restore the file in a `try/finally` block. Never commit the
   diagnostics; the goal is to learn WHICH phase flakes, not to add logging.
3. **Distinguish two common races.**
   - A read-only lookup is polled while the real reaper lives inside a
     state accessor. The lookup can stay stale forever: poll through the
     accessor that advances the state machine instead.
   - The action under test launches asynchronously. Retry the REAL action
     (button click, syscall, IPC call) a bounded number of times with a
     bounded poll between attempts. Do not replace it with a direct API
     call that bypasses the path under test.
4. **Re-verify.** Run the batch again (8+ iterations), then run the full
   suite. If practical, temporarily remove the wait/retry and confirm the
   failure returns in the batch; that is the negative control for the
   harness fix.

## Pitfalls

- Bounded retries belong in the harness, not in production code, when the
  production operation is genuinely asynchronous; an unbounded wait hides
  a deadlock instead of proving liveness.
- A phase diagnostic that changes timing can itself hide the race. Keep it
  to a single fprintf per phase and always restore the original file.
- After merging a batch of green legs, regenerate checked-in inventories
  and re-run the full gate; a stale manifest or a parallel GUI test can be
  the only red target even when every leg was green alone.
- A global IPC/filesystem name derived from a fixed fixture identifier (for
  example `/tmp/<tool>-<name>.sock`) is a shared resource under `-jN`: a
  sibling gate can steal it and the failure moves between assertions.
  Derive the fixture name per process (append the PID), then re-run both
  the 8-iteration batch and the full parallel suite. An isolated green run
  proves nothing about a name that only collides in parallel.
