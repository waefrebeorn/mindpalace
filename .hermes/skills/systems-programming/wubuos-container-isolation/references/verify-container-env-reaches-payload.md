# Verify container env actually reaches the payload

When you register isolation/env via `wubu_ct_add_env(ct, "NAME=VALUE")`
(seccomp profile, namespace flags, repo root, etc.) and the payload still
behaves as if the setting is absent, the cause is almost always one of:

1. **`execv` ignores `ct->envp`.** `wubu_ct_start`'s child calls
   `execv(argv[0], argv)` — `execv` takes NO envp argument, so `ct->envp[]`
   entries are NEVER passed to the payload unless you `setenv` them in the
   child BEFORE `execv`. Fix: loop `ct->envp[]` and `setenv` each before exec.
2. **Order: env applied AFTER the thing that reads it.** `wubu_ct_child_isolation()`
   reads `WUBU_SECCOMP_PROFILE` / `WUBU_NS_FLAGS` from `getenv`. If you
   `setenv` the `ct->envp` entries *after* `wubu_ct_child_isolation()` runs
   (e.g. right before `execv`), the isolation was already installed from the
   *parent's* inherited env (often empty → default full-isolation seccomp).
   **The `setenv` loop must run BEFORE `wubu_ct_child_isolation()`.**

## The probe that caught the order bug

After applying the `setenv` loop, instrument the child to confirm the env
actually arrived. Put a one-line stderr print at the TOP of
`wubu_ct_child_isolation()` (before the seccomp filter is built):

```c
fprintf(stderr, "[seccomp-debug] pid=%d profile=%s sp=%d ns=%s\n",
        (int)getpid(),
        getenv("WUBU_SECCOMP_PROFILE") ? getenv("WUBU_SECCOMP_PROFILE") : "(null)",
        (int)sp,
        getenv("WUBU_NS_FLAGS") ? getenv("WUBU_NS_FLAGS") : "(null)");
```

Run the payload and grep the launcher's stderr:

- `profile=(null)` → the `setenv` loop is NOT reaching the child, OR it runs
  after isolation. (This session: first attempt applied env right before
  `execv`; debug showed `profile=(null) sp=1` → SIGSYS on Wine. Moving the
  loop above `wubu_ct_child_isolation()` made it show `profile=none` and the
  crash went away.)
- `profile=none` / `profile=wine` as intended → env reached the child; if it
  still dies, the problem is the *profile contents* (allowlist too narrow),
  not delivery.

Remove the debug print once green.

## Wine-specific: CWD is NOT where you launched from

Even with env delivered, a Win32 payload via Wine writes CWD-relative marker
files to the **`.exe`'s directory**, not the launching process's CWD. The era
demo's `CreateFileA("WUBU_ERA_WIN.OK")` landed in `/tmp` (next to the temp
`.exe` written by `wubu_exec_win_pe`) while the test asserted the marker in the
repo. Fix: pass an absolute output path via env — `wubu_exec_win_pe` sets
`WUBU_REPO_ROOT` (from the launcher's `getenv("WUBU_REPO_ROOT")`), and the demo
does `CreateFileA(getenv("WUBU_REPO_ROOT") + "/marker")`. Also: `WUBU_REPO_ROOT`
must be propagated through `wubu_ct_add_env` (see pitfall 1/2 above) — Wine's
`getenv` reads the child's env, which only has it if the `setenv` loop ran.

## Quick delivery checklist

- [ ] `wubu_ct_add_env(ct, "X=Y")` called by the launcher (parent).
- [ ] Child does `setenv` over `ct->envp[]` BEFORE `wubu_ct_child_isolation()`.
- [ ] Child does NOT use `execv` expecting `ct->envp` to arrive — it arrives
      via the inherited environment after the `setenv` loop, so `execv` is fine
      (or switch to `execve` with an explicit envp built from `environ`+overrides).
- [ ] `[seccomp-debug]` probe confirms `profile`/`ns` are non-null as intended.
- [ ] For Win32: marker path is absolute (via `WUBU_REPO_ROOT`), not relative.
