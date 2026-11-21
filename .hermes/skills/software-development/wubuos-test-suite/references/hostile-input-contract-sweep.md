# Hostile-input contract sweep: probe every entry point with bad arguments

A unit suite exercises handlers with VALID inputs, so nothing checks pointer arguments.
That is exactly where the crashes live: a caller-supplied pointer is dereferenced without
a null test, a length field is trusted from the wire, an enum index walks off a table.
Observed repeatedly in this tree — `getenv((void*)0)`, an unconditional `raise(SIGTRAP)`,
and a `strchr`-style walk past the end of a section header.

## The pattern

For each registered slot / dispatch entry, call it once with all-zero (or otherwise
hostile) arguments. Run each probe in a **forked child** under `alarm(1)`:

- a crash costs one child instead of taking down the gate;
- a hang cannot stall the build (the alarm kills it, the parent records the failure);
- the status comes back over a pipe or `waitpid`, so the parent decides PASS/FAIL.

```c
typedef void (*probe_fn)(const char *);
static int run_isolated(probe_fn fn, const char *arg)
{
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) { alarm(1); fn(arg); _exit(0); }
    int st = 0;
    waitpid(pid, &st, 0);
    if (WIFSIGNALED(st)) return -1;              /* crashed */
    if (!WIFEXITED(st) || WEXITSTATUS(st) != 0) return WEXITSTATUS(st);
    return 0;
}
```

For a dispatch table, iterate slots and probe each entry — that is how the real NT
syscall family got swept (every registered slot, all-zero arguments, one fork each).
Report the SLOT NUMBER, not just "crashed": "slot 179 SIGSEGV" is actionable,
"one probe failed" is not.

## Wire the sweep into the gate as its own target

The sweep is a product gate, not a debugging aid: `make test_<subsystem>_contract`,
linked against the REAL module plus its real dependency closure, so a future refactor
that removes the guard makes the gate red rather than the user's process crash.

## Pitfalls

- **Isolate storage FIRST.** A sweep that calls into a module writing to its default
  path will happily write to the operator's real files while probing for crashes.
  Redirect the store env var before the first probe (see the isolation rule in
  SKILL.md), and give each child a per-PID scratch path if the probe writes at all.
- **A fork inherits the parent's environment and fds.** Anything the parent opened
  before the fork is visible to the child; close or redirect what the probes must not
  touch.
- **`alarm()` is a coarse timer.** A probe that hangs for 900 ms then succeeds still
  counts as a hang. That is usually the right call, but do not use it to assert timing.
- **Do not assert "no signal" for functions that legitimately raise one.** A syscall
  facade for `NtRaiseException` may be SUPPOSED to trap; the check is that it returns a
  status instead of killing the process, which needs a per-case expectation rather than
  a blanket no-signal rule.
- **Forking inside a suite that also runs the same code in-process is fine**, but make
  sure the suite's own state is re-initialised after the sweep children exit — the
  children share nothing, yet a leaked allocation mid-sweep can break a later check
  that counts allocations (observed: a deliberately-refused free leaked into a later
  "empty heap" assertion).
