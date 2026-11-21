# Devil's-Advocate Prestige Update — Daemon→Desktop Integration (2026-07-23)

Triple DA on what SteamOS / Ubuntu / Arch / TempleOS actually do to get daemons
to participate in the desktop, vs. what WuBuOS's Arch daemon (`wubu_archd`) and
TempleOS/HolyC DOS daemon (`wubu_dos_proc` + `wubu_holyd`) actually do today.
Written after the 2026-07-22 crash-recovery session, which found + fixed three
real gaps (HolyC JIT SIGSEGV, Wine/`execv` seccomp, VSL wiring) and landed two
new OS personalities (CP/M, Classic Mac).

> Method note: the slate/BATTLESHIP counts were re-verified against ACTUAL CODE
> this session (per the "handoffs lie" rule). The findings below come from
> reading `service_mgr.c`, `wubu_archd_svc.c`, `wubu_dos_proc.c`,
> `wm_holyc_term.c`, `era_apps.c` — NOT from stale handoff text.

---

## A. Gaps FOUND + FIXED this session (already committed, `4357a05`)

| # | Gap (form≠function) | Where | Fix | Evidence |
|---|----------------------|-------|-----|----------|
| G1 | HolyC JIT emitted `call 0` for unregistered externs (`Print`/`FpWriteFile`) → SIGSEGV (null fn ptr) in the era demo | `holyc_codegen_expr.c` | Added `src/compiler/holyc_runtime.c` (real `wubu_print`/`wubu_fp_write_file` host effects), registered them as externs in `hc_eval`, hardened the fallback to trap instead of null-deref | `test_era_apps` "HolyC era app launches via hc_eval JIT" now passes |
| G2 | `wubu_ct_start` used `execv` (ignored `ct->envp`) → container env (`WUBU_SECCOMP_PROFILE`, `WUBU_NS_FLAGS`, `WUBU_REPO_ROOT`) never reached the child → Wine killed by default full-isolation seccomp (SIGSYS, exit -31) | `wubu_host_exec.c` | Apply `wubu_ct_add_env` into the child env BEFORE `wubu_ct_child_isolation()` (which reads it); `execv` → still used but env now set via `setenv` | `test_era_apps` "Win32 era app ... through Wine/NT syscalls" passes |
| G3 | New VSL personalities (CP/M BDOS 0xC0, Classic Mac 68K 0xB0) + `era_apps.c` were crash-landed UNWIRED (not in `make test`, non-compiling) | Makefile + `era_apps.c` | Folded `test_vsl_cpm`/`test_vsl_macclassic` into the gate; fixed invalid hex literals + class bits; wired `era_apps_register()` into `startmenu_init_enhanced()`; rebuilt `win_era_demo.exe` via mingw to write marker to `WUBU_REPO_ROOT` | `make test` ALL PASSED; 5+ VSL personalities reachable as first-class processes |
| G4 | `hosted` link broken at HEAD (sextuple `ct_iso_*` dup, missing `holyc_agi`/`holyd_lifecycle` prereqs) | Makefile | Dedup'd; added prereqs | `make clean && make hosted` exit 0 |

**Verdict on G1–G4:** these were REAL bugs, not stubs. G1/G2 were latent
crashes waiting for the era demo to exercise them. The angel-coder move
(close them, don't document) was correct.

---

## B. Triple-DA: SteamOS / Ubuntu / Arch / TempleOS daemon→desktop

### Optimist — what WuBuOS ALREADY does right
- `wubu_archd` (16/16 test) is a REAL module: roots registry, AUR/build,
  signing, health check, service start/stop/status. It is genuinely wired as
  the Desktop service manager via `service_mgr_init/boot/shutdown`
  called from `desktop_init/shutdown` (E3). That is real integration, not
  a socket stub.
- `wubu_holyd` (HolyC REPL) is wired as a Desktop terminal window
  (`wm_spawn_holyc_term`) with dependency-injected eval — the genuine
  compiler path, not a second REPL.
- `wubu_dos_proc` (in-process 8086) is reachable as a first-class DOS process via
  `era_apps.c` (DOS era) and `dos_window_test`.
- Two new OS personalities (CP/M, Classic Mac) landed with real host-effect
  round-trip tests.

### Realist — partial / risky
- **Arch daemon is a thin wrapper over external `systemctl`.** Every
  `wubu_archd_svc_*` and `health_check` shells out via `popen("arch-chroot %s
  systemctl start %s")`. On THIS build there is no Arch rootfs, so `boot()`
  records `-1` for every autostart entry. The desktop *reports* services failed
  even though the failure is "no Arch root," not "service broken." This is
  form-with-function-missing for the sandbox case: the daemon supervises
  nothing it can reach.
- **No D-Bus / service announcement bus.** SteamOS and Ubuntu desktop
  environments learn about daemons through D-Bus (+ systemd --user). WuBuOS has
  no bus; `service_mgr` knows only the static `archd-autostart.conf`
  list. A daemon that starts later (or crashes and restarts) is invisible to the
  desktop.
- **No per-user service manager.** `wubu_archd` is a single global instance
  (`g_archd`) wired at desktop init. systemd has `systemd --user` (per-session);
  WuBuOS has no per-user daemon scope, so multi-user / per-session daemons aren't
  modelled.
- **TempleOS DOS daemon is in-process, not a daemon.** `wubu_dos_proc` runs the
  8086 shim IN the caller's process (no fork). Real TempleOS is a single
  ring-0 process where the "OS" IS the running program; WuBuOS's in-process
  model is actually closer to TempleOS's design than a separate-daemon model —
  but there is NO persistent "TempleOS session" object (HolyC state + DOS state
  + RedSea-ish FS) that the desktop treats as one daemon. They are three separate
  subsystems (holyd REPL window, dos window, era-apps) with no shared
  "TempleOS personality" lifecycle.

### Pessimist — broken / missing / showstoppers
- **`boot()`'s `-1` is silent to the user.** `service_mgr_boot` records
  `failed++` but the desktop shows no tray state, no "service failed" toast, no
  retry. On a real SteamOS/Ubuntu desktop, a failed autostart service is
  visible (systemctl failed state, journalctl). WuBuOS has no such surfacing.
- **No sandbox-isolation story for the daemon itself.** `wubu_archd` runs as the
  desktop user (root in many cases) and `popen`s `arch-chroot`/`systemctl` — a
  command-injection surface if any root/svc name is attacker-controlled (they
  flow through `snprintf` into the shell). The BATTLESHIP "closure technique"
  eliminated `system()` from `src/` — but `wubu_archd_svc.c` uses `popen` with
  `arch-chroot ... %s` which is the SAME class of shell-injection vector. This
  is a reopened gap the audit missed (popen ≠ system() but equally
  injectable).
- **HolyC REPL has no persistence bridge to DOS.** The HolyC terminal and the
  DOS window are disjoint. A TempleOS user expects HolyC to spawn/inspect DOS
  processes (TempleOS has no separate kernel/user boundary). WuBuOS cannot.
- **No daemon health→desktop heartbeat.** `wubu_archd_health_check` exists but is
  only called on demand; the desktop never polls it, so a degraded Arch root
  stays green in the UI until manually re-queried.

---

## C. NEW gaps surfaced (add to BATTLESHIP board)

| ID | Gap | Class | Priority | Fix sketch |
|----|-----|-------|----------|-----------|
| N1 | `wubu_archd_svc_*` / `health_check` use `popen("arch-chroot ... systemctl %s")` — shell-injection vector, and no-op without an Arch root | REAL_GAP (security + function) | 🔴 | Replace `popen` with `wubu_run_program` fork+exec (`arch-chroot` + `systemctl` as argv), or better: a real in-WuBuOS service supervisor (see N2) |
| N2 | No real service supervisor — `wubu_archd` only wraps external `systemctl`; no in-WuBuOS unit model (deps, restart policy, stdout capture) | Parity (SteamOS/Ubuntu systemd) | 🔴 | Model a `WubuUnit` (ExecStart argv[], Restart=on-failure, After=) and supervise via `wubu_spawn` + `waitpid` + fd pipe to the unit's stdout |
| N3 | No D-Bus / service announcement bus → desktop can't discover late/restarted daemons | Parity (Ubuntu D-Bus, SteamOS) | 🟠 | Either adopt the project's OWN Styx/9P namespace as the "bus" (publish units under `/n/services/*`) or add a minimal name-service; desktop watches the namespace |
| N4 | `boot()` failures are silent (no tray/toast/retry) | UX/form≠function | 🟠 | Surface per-service state in systray; on `-1` show "Arch root missing" vs "unit failed" distinctly; offer retry |
| N5 | No per-user (`systemd --user`) scope | Parity (Arch/Ubuntu) | 🟡 | Add a per-session `WubuArchd` instance keyed by session; desktop owns the user-scoped one |
| N6 | No persistent "TempleOS DOS daemon" lifecycle object uniting holyd + dos_proc + FS | Parity (TempleOS monolithic ring-0) | 🟡 | Introduce `WubuTempleSession` holding holyd compiler state + active dos procs + a RedSea-ish ramfs; era-apps/DOS window/holyc term all hang off it |
| N7 | HolyC REPL ↔ DOS window disjoint (no cross-spawn/inspect) | Parity (TempleOS) | 🟡 | HolyC `SpawnDos(prog)` / `Ps()` builtins that drive `wubu_dos_proc` and report into the REPL |
| N8 | Daemon health not polled by desktop (no heartbeat) | form≠function | 🟡 | Desktop timer calls `wubu_archd_health_check` per root; degrades tray icon |

---

## D. What SteamOS / Ubuntu / Arch ACTUALLY do (the bar WuBuOS is measured against)

- **Ubuntu/Arch (systemd):** daemons are `*.service` units supervised by
  `systemd` (PID 1) or `systemd --user` (per session). The desktop (GNOME/KDE)
  learns about them via **D-Bus** (`org.freedesktop.systemd1`,
  `org.freedesktop.DBus`) and **Polkit** for privilege. Autostart =
  `/etc/xdg/autostart/*.desktop` + `systemctl --user enable`. Failure is
  visible: `systemctl status` shows `failed`, `journalctl` has the log. Restart
  policy (`Restart=on-failure`) is declarative. stdout/stderr captured to the
  journal.
- **SteamOS:** same systemd base, PLUS gamescope as the session composer and
  the Steam client as the "desktop." Daemons the game needs (Proton, Pressure
  Vessel, Steam Input) are launched by Steam, not the DE. The "desktop" IS an
  app. SteamOS's genius is that it collapses "daemon" and "app" — the session
  manager (gamescope) owns everything.
- **TempleOS:** there is NO daemon/desktop split. The OS is one ring-0 program;
  the "shell" (HolyC) and "apps" (DOS/RedSea programs) run in the SAME address
  space. A "daemon" in TempleOS is just a long-running HolyC function. This is
  the opposite of systemd's model and is actually CLOSER to WuBuOS's
  in-process `wubu_dos_proc` — WuBuOS should lean INTO this, not imitate
  systemd, for the TempleOS personality.

**Resolution (the angel-coder move):** WuBuOS should NOT try to clone systemd.
Its leverage is the **Styx/9P namespace as the integration bus** (the
architecture already says "ONE Styx namespace instead of a pile of bespoke
daemons"). So:
- N2/N3 collapse: model `WubuUnit` and publish it under `/n/services/*` on the
  existing Styx bus. The desktop watches that namespace. This reuses the
  project's own infrastructure instead of importing D-Bus.
- N6/N7 collapse: model the TempleOS personality as a single `WubuTempleSession`
  (ring-0-flavored, in-process) — which is HONEST to TempleOS, not a
  systemd-imitation.
- N1 is a security MUST-FIX regardless of architecture: kill the `popen`/shell
  injection before anything else.

This is the "bridge spans the river" fix: WuBuOS's daemon integration should be
**Styx-namespaced units + in-process TempleOS sessions**, not a systemd clone.

---

## E. Verification (so the next session doesn't re-litigate)

```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
make clean && make runtime && make hosted && make test   # GATE EXIT 0 (verified)
make test_era_apps       # ALL PASSED (DOS/Win/Linux/HolyC launch; CP/M/Mac gap -1)
make test_vsl_cpm        # ALL PASSED
make test_vsl_macclassic # ALL PASSED
# Confirm the N1 shell-injection surface still present (do NOT "fix" without plan):
grep -nE 'popen\("arch-chroot' src/runtime/wubu_archd_svc.c   # → N1 confirmed
```
