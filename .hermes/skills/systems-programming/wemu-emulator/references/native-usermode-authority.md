# Native user-mode authority in WEMU

Use when extending the SIGSYS/native-execution layer: executable fds,
threads, signals, dispositions, or pidfds. Keep this in the native-usermode
owner (`wemu_usermode.c`, public header, clone3/signal gates), not in the ISA
cores. Every admitted shape gets a real host differential; every unsupported
shape gets a named refuse reason with no host dispatch.

## Fd and exec authority

- `execveat` dirfd is an `int`: normalize the low 32 bits from the SIGSYS
  register (`(long)(int32_t)rdi`) or glibc's zero-extended `AT_FDCWD` is
  misread as a huge positive fd. Leave `flags` unmasked so unknown bits fail
  closed.
- Fill the admitted-fd table only from successful guest open/openat/dup3.
  A supervisor fd that exists on the host but was never opened by the guest
  must return -EBADF even when the host could exec it.
- Bind an admitted fd to its open-file description, not just its number:
  use kcmp for OFD identity and a dev/ino fallback when kcmp is unavailable.
  A close+reopen reusing the number, an unadmitted fd and unsupported flags
  must all fail closed. CLOEXEC fexecve parity uses a PRIVATE internal dup
  closed before returning control; prove with an fd census that it does not
  leak into the guest.

## Threads, masks and dispositions

- Per-thread virtual signal masks and per-thread disposition tables are the
  hardened path: a CLONE_THREAD child inherits a COPY; a synchronous fault
  is delivered from the faulting thread's slot. Keep the process-wide table
  only as a negative control, where one thread's sigaction clobbers another's
  and the byte stream diverges from the host oracle.
- Bounded clone3 admits only the modeled v0 CLONE_THREAD shape. pidfd flags,
  pidfd fields, sigmask extensions, namespaces, exit signals, set_tid,
  cgroup and malformed sizes fail closed with distinct refusal counters.
  Old-path switches must reproduce -EINVAL/-ENOSYS with no thread/queue.
- Bounded `tgkill` targets an admitted sibling and respects that thread's
  virtual mask and disposition. Bounded process-directed `kill` is admitted
  only for the calling admitted thread with `SI_USER` siginfo. Signal 0,
  non-whitelisted signals, wrong pid/tgid and unadmitted targets fail closed
  with exact reasons. A queued cross-thread signal is consumed at the
  target's next syscall checkpoint — do not call it asynchronous.
- pidfd authority: mint a real host pidfd only for a TID WEMU created;
  `pidfd_getfd` only for a minted pidfd plus an admitted target fd;
  `pidfd_send_signal` only for a whitelisted benign signal with no siginfo.
  Out-of-scope shapes refuse with named reasons and no host dispatch.

## Gate discipline

- Every new switch needs BOTH a positive byte-exact host differential and a
  switch-off negative control whose output differs. Coarse-diagnostic off
  must fold exact refusals back into generic -ENOSYS/-EINVAL; that is the
  control proving the named reasons are real.
- When two WEMU legs start from the same parent commit, rebase ONE onto the
  other and resolve conflicts by keeping both feature sets: dispatch defines,
  result counters, pure-shape predicates and gate sections. Delete stale
  refusal blocks that the newer authority owner has superseded, then grep
  for conflict markers, rebuild from clean, and re-run the COMBINED narrow
  suite. A per-leg green before the rebase is not evidence for the merge.
- Publish the combined leg by SHA into its named remote branch and move the
  parent gitlink to that combined SHA; do not leave the parent pointing at
  the pre-rebase leg while the branch tip contains both features.
