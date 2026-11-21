---
name: wubuos-nt-cap-gate-closure
description: Verify and close wubuos NT-cap authority gate tests.
---

# WuBuOS NT-cap gate closure

Verify and close the WuBuOS (wubuos repo) NT-cap authority gate tests — the
`vsl_syscall_nt_test` / `test_vsl_nt` cap-revoke-cascade suite. This is the
*verification/closure* counterpart to `wubunos-nt-cap-authority`, which covers
the *authority binding* of NT syscalls to wubu_cap. Always resolve the repo
by glob:

```python
R = next(d for d in sorted(glob.glob('/home/wubu/*' + chr(47')))
         if (Path(d)/'mk'/'tests.mk').is_file()
         and (Path(d)/'src/runtime/wubu_cap/wubu_cap.h').is_file())
```

## Standing rules (always apply)
- Verify each test target DIRECTLY with an explicit exit code, run straight:
  `timeout 300 ./src/runtime/wubu_vsl_nt_test; echo exit=$?` — never via a pipe
  that masks the true exit code.
- On any segfault, get a real backtrace with gdb BEFORE touching anything:
  `gdb -batch -ex run -ex "bt 25" --args ./src/runtime/wubu_vsl_nt_test`
- Don't trust a handoff's "environmental" label — the segfault in this suite
  was HYPOTHESIS, not ground truth. Re-derive the red from the actual FAIL/
  segfault lines.
- After any source edit, `rm` the specific binary, rebuild, then rerun. A stale
  object linked from an old compile is a classic bin that keeps saying "fails"
  right after your fix.

## Procedure — close the cap-gate suite

### Step 1 — Reproduce, read real output
1. `cd /home/wubu/wubuos && timeout 300 ./src/runtime/wubu_vsl_nt_test > /tmp/vsl_nt_run.log 2>&1`
   `echo exit=$?` — capture the segfault text and exit code.
2. If it segfaults, gdb before touching anything:
   `gdb -batch -ex run -ex "bt 25" --args ./src/runtime/wubu_vsl_nt_test`
3. Note WHICH assertion is the last to pass before the failure — but only
   trust that boundary if the CHECK macro flushes (see pitfalls): a
   block-buffered stdout loses the final assertions to the stdio buffer.
4. Run the BUILT BINARY directly (`./src/runtime/wubu_vsl_nt_test; echo
   exit=$?`) for the true exit code and full assertion tally; the make
   recipe pipes the binary, so a crash surfaces as "Segmentation fault
   (core dumped)" as a make error with the tally swallowed.

### Fast iteration after a one-file edit
`make test_vsl_nt`'s per-object pattern rules mean editing ONE source
rebuilds only that `.o` and relinks (seconds) — the multi-minute build is
only the first time. After an edit, just re-run the target, then the
binary directly. Do not background the target for a one-file change.

### Step 2 — Isolate the true root cause (trust the backtrace frame)
- The backtrace's frame #1 names the function where the bug lives. Fix
  THAT function, not the subsystem you assumed was broken. The classic
  wrong turn in this suite was assuming the cap-close path
  (`wubu_cap_handle_close` / `wubu_cap_handle_close_slot`) and "fixing" it
  while the real crash was two files away.
- **A gdb stop reading "Program received signal SIGCONT, Continued"
  inside libc `kill()` is the fingerprint of a process that SIGCONT'd
  itself** — Linux' default SIGCONT disposition is Stop, so a
  self-resume hangs the test (or looks like a stop inside the syscall
  under gdb). Find the handler that signals the target and make it
  refuse `getpid()` / `getpgrp()`; the "hang" was never the waitpid or
  the test harness.
- **A segfault landing in a facade/resolver means the subsystem you
  blamed is innocent** — read what the crashing line dereferences. The
  real crash here was type confusion: `vsl_nt_cap_token_sidset()` cast
  ANY cap-backed handle's `handle_table[].data` to
  `nt_token_entry_t*`, but that field holds kind-specific payload (an
  eventfd for events, a styx fid for files, a registry offset for keys).
- **Standing rule for NT handle tables**: `handle_table[].data` is a
  kind-tagged payload — validate `handle_table[].type ==
  NT_OBJECT_TYPE_TOKEN` (or the expected type) BEFORE casting. Only
  TOKEN handles name an identity; every other handle resolves to the
  calling process.
- Confirm the root cause with a focused reproduce before fixing.

### Step 3 — Fix the frame the backtrace names
- Fix the function in frame #1 of the backtrace. Only touch the cap
  handle-close path in `src/runtime/wubu_cap/wubu_cap_handle.c` when the
  backtrace actually lands there — the assumption that a cap-gate
  segfault must be a cap-close bug burned a full session here.
- Rebuild the test binary and rerun it directly for the exit code.

### Step 4 — Close out cleanly
- Verify with explicit numbers: a final exit of 0 means the alias-close
  assertion passed; any nonzero (and especially 139 = SIGSEGV) means the bug
  lives on.
- Record the verified result in the session report, not a handwave like "it
  works now".

## Pitfalls
- **Spliced patched lines silently convert TABs to spaces in Makefile
  recipes** — verify with `cat -A` (recipe lines must show `^I`) and `make -n
  <target>` before running. Prefer Python splice via `execute_code` which
  preserves tabs reliably.
- **Buffered stdout hides the failing assertion.** A C test suite's printf
  to a file or pipe is block-buffered, so a crash/stop loses the final
  assertions — the "last line" you read is NOT the last assertion that
  ran, and the apparent failure boundary is fiction. Make the CHECK macro
  `fflush(stdout)` after every print (one-line edit, permanent win), or
  run with `stdbuf -oL`. Do this BEFORE diagnosing which assertion failed.
- **A segfault is not a flake — trace the exact assertion**, but trace it
  with flushed output and a backtrace, not with the assumed subsystem.
  The backtrace's frame #1 (the function), not the assertion text, names
  the bug's home.
- **A GREEN gate does not cover app/tools** — the vsl/nt cap suite builds the
  single `wubu_vsl_nt_test` binary; after editing an app/tools source, run
  that target explicitly to prove it still links and runs.
- **Closed-handling that drops the cap before freeing the record** — the
  working wiring is `vsl_nt_cap_unbind` before `vsl_nt_free_handle` so no
  stale token outlives the object. Golden rule for the close path: revoke /
  close the cap authority FIRST, then free the record, then close the fd.
