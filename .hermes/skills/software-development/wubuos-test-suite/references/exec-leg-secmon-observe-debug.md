# Execution-leg exit-code debugging: seccomp + secmon ptrace traps

When an execution-leg test (`test_exec_elf` / `test_exec_pe`) builds a real
binary, dispatches it through the exec path, but the exit code comes back
**wrong** (a small wrong number like 1) or as a **negative signal** (`-31` =
SIGSYS, etc.), the payload ran but something between `wubu_ct_start` and
`wubu_ct_wait` interfered. Two runtime bugs this pattern surfaces, both fixed:

## 1. Unregistered seccomp profile -> child killed by SIGSYS (`-31`)

`wubu_exec_win_pe` sets `WUBU_SECCOMP_PROFILE=observe` for the AGI syscall
camera. In `ct_iso_seccomp.c` the child-side `wubu_ct_child_isolation()` reads
that env var and maps known names to a `SeccompProfile`; an **unrecognized
name falls through to `SECCOMP_PROFILE_BASIC`**, whose ~150-syscall allowlist
is far too tight for Wine-9.0 -> the child dies on the first disallowed syscall
(`SIGSYS`, reported as exit code `-31`).

Diagnosis: no strace needed - the exit code `-N` (negative = `-WTERMSIG`)
means the child was **signaled**, and a container child that should have run a
payload getting SIGSYS is a seccomp-filter kill.

Fix: the camera observes via **ptrace (secmon), not seccomp** - so `observe`
must NOT install a filter. In `wubu_ct_child_isolation()` map
`"observe"` -> `SECCOMP_PROFILE_NONE` (skip the filter). Do not map it to
GPU/WINE - those allowlists are also too tight for a full Wine/desktop stack.

Related: `wubu_ct_setup_isolation()` (parent side) sets the child's
`WUBU_SECCOMP_PROFILE` env from `runtime_to_seccomp(ct->runtime)`; an explicit
`WUBU_SECCOMP_PROFILE=none` in the environment is honored as a test/trusted
opt-out rather than overridden.

## 2. secmon ptrace tracer races `wubu_ct_wait` -> real exit code lost (returns 1)

When the profile is not `none`, `wubu_ct_start` (parent) creates a secmon and
`PTRACE_ATTACH`es the child (`ct->secmon`). The OLD `wubu_ct_wait` did a plain
`waitpid(ct->pid, &status, 0)` - but a ptrace-traced child only reports its real
exit status to its **tracer**. The plain `waitpid` reaps a ptrace-stop, never
sees the exit code, and returns a bogus value (observed: 1 instead of 42).

Diagnosis: the payload demonstrably ran (Wine prints its errors; a direct
`wine <exe>` returns the right code) but `wubu_ct_wait` returns a small wrong
number, AND `ct->secmon` is non-NULL. That combination = the wait race.

Fix: when `ct->secmon` is set, `wubu_ct_wait` must **drive the tracer to
completion** and read the exit code it captured, not race it with a plain
`waitpid`:
- Add `exit_code` + `exited` fields to the secmon struct; populate them in
  `wubu_secmon_poll()` on the `WIFEXITED(status) || WIFSIGNALED(status)` branch
  (`WEXITSTATUS` / `-WTERMSIG`).
- Expose `wubu_secmon_exit_code(m)` (valid once `m->exited`).
- In `wubu_ct_wait`: `if (ct->secmon) { wubu_secmon_wait(secmon); exit_code =
  wubu_secmon_exit_code(secmon); ... }` else the plain `waitpid` path.

Because `wubu_host_exec.c` now references `wubu_secmon_wait`/`_exit_code`,
GUI test recipes that link the **stub** TU (`wubu_ns_pkg_stub.c`, where
`wubu_secmon_create` returns 0 so `ct->secmon` is NULL and these are never
called) need matching stub definitions - add them to the stub file, do NOT add
the real `wubu_secmon.c` to those link lines (multiple-definition). See the
SWEEP stub-file exception in SKILL.md.

## Rule of thumb
- Exit code `-N` (negative) = child was **signaled** -> seccomp profile killed it
  (bug 1). Fix the profile mapping so it doesn't filter.
- Exit code is a **small wrong positive** (1, not the payload's code) while the
  payload clearly ran = `wubu_ct_wait` raced the ptrace tracer (bug 2). Route
  the wait through the tracer's captured exit code.
