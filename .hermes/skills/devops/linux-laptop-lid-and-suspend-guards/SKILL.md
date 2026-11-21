---
name: linux-laptop-lid-and-suspend-guards
description: "Use when a closed lid must not suspend the host."
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [linux, systemd, lid, clamshell, suspend, display, xorg, cinnamon]
    related_skills: [linux-shell-terminal-setup]
---

## When to Use

- "close the laptop and keep working", "clamshell mode", "lid closed still
  suspends", "the box turns off when I shut the lid".
- The host desktop locks or blanks at moments that interrupt the workflow.
- Any task that needs the machine to stay up unattended (long builds, agents).

## Goal shape

| Lid | Panel | System |
|---|---|---|
| closed | off | keeps running -- sleep blocked |
| open | back on | keeps running |

## Procedure

1. **Find out who handles the lid.** Three candidates, and they differ:
   - `systemd-logind` (`HandleLidSwitch*` in `/etc/systemd/logind.conf`) -- needs root.
   - **Cinnamon's `csd-power`**, which sets `inhibit-lid-switch=true`, i.e. it TAKES
     OVER the lid switch from logind and applies its OWN action. Confirm with
     `gsettings list-recursively org.cinnamon.settings-daemon.plugins.power | grep lid`.
   - A third-party daemon (`tlp`, `laptop-mode-tools`).
   Check `systemd-inhibit --list`: an entry whose WHAT includes `handle-lid-switch`
   means that process owns the lid.
2. **Do it in USER SPACE when root is not available.** This box has no passwordless
   sudo, and none of these guards need it:
   - sleep inhibition: `systemd-inhibit --what=sleep:handle-lid-switch --mode=block`
   - panel control: `xrandr --output <panel> --off|--auto`
   - lid state: `/proc/acpi/button/lid/LID*/state` (readable by any user)
   - persistence across logout: `loginctl enable-linger <user>` (needs the user's
     own sudo -- ask them to run it once).
3. **Write the guard** (see `templates/clamshell-guard.sh`): poll the lid state,
   act on transitions only, log to syslog plus an optional file.
4. **Install as a systemd --user unit** (`templates/clamshell.service`) and WRAP THE
   WHOLE UNIT in `systemd-inhibit` via `ExecStart=`.
5. **Neutralise the desktop's own lid action**: set Cinnamon's
   `lid-close-ac-action` and `lid-close-battery-action` to `'nothing'`.
6. **Make it stick**: Cinnamon reverts its schemas after restarts, so re-assert them
   from a periodic user timer (this box uses a 5-minute `wubu-no-lock.timer`).
7. **Verify** (see below), then hand the physical test back to the user.

## Verification

```bash
cat /proc/acpi/button/lid/LID0/state          # closed | open
systemctl --user is-active wubu-clamshell.service
systemd-inhibit --list | grep wubu-clamshell   # must show sleep:handle-lid-switch
DISPLAY=:0 xrandr | sed -n '/^eDP-1/,+3p'       # no active mode => panel off
uptime -p                                      # continuous => did NOT suspend
journalctl -b | grep -i 'lid\|suspend'        # what actually acted
```

A correct "closed" state reads: lid `closed`, panel connected with NO resolution
line, uptime advancing through the close, inhibitor listed, and no suspend target in
the journal.

Test the transition logic without touching hardware: run the guard with
`WUBU_LID_STATE` pointed at a scratch file shaped like the procfs one, toggle it, and
read the log. Add `WUBU_LID_DRY_RUN=1` to skip calling xrandr.

## Pitfalls

- **A background `systemd-inhibit ... &` inside the service DIES with the unit.**
  systemd kills the whole unit cgroup on stop/restart, so the lock vanishes while the
  guard keeps running -- and the guard looks healthy. Wrap the entire `ExecStart` in
  `systemd-inhibit` instead; the lock then lives exactly as long as the service.
- **`csd-power` owning the lid makes a logind-level inhibitor useless.** Its
  `inhibit-lid-switch=true` means it replaces logind's handling, then runs
  `lid-close-*-action` itself (default `suspend`). Fix the gsetting, not just logind.
- **DPMS may be deliberately disabled** by another guard, so use
  `xrandr --output <panel> --off/--auto` -- deterministic and independent of DPMS.
- **User units stop at logout** unless lingering is enabled; without it the guards die
  whenever the session ends.
- **Desktop power schemas revert after a restart.** Anything asserted once must also
  be re-asserted on a timer, or it silently comes back.
- **Variables read before they are guaranteed to exist abort a `set -u` script.**
  User units run with a much smaller environment than an interactive shell (no
  DISPLAY, XAUTHORITY, session vars), and a value produced by a function may never be
  assigned if an early branch returns first -- then any later reference dies with
  "parameter not set" and the unit exits. Initialise EVERY variable the script reads
  at the top, and make helper functions assign their own output variables on every
  path, including the error path.
- **Reproduce the unit's environment without root:**
  `env -i HOME=$HOME PATH=/usr/bin:/bin /path/to/script` runs it as systemd would.
  Test the guard that way BEFORE installing the unit; a shell-run test passes because
  the interactive environment hides the missing values.
- **Don't `pkill -f <pattern>` where the pattern appears in your own command line** --
  you will kill the shell running the command. Match by PID or by a marker that cannot
  appear in the invoking shell.
- **Detach helper children from the service's stdout/stderr.** A grandchild holding the
  pipe makes any caller waiting on output hang after the main process exits.
- **The lid state file DOES update on real hardware closes**; if it reads `open` after
  a close, re-read it before concluding the sensor is broken.
- **Closing the lid removes airflow.** Sustained heavy load (all-core builds) with the
  lid shut will thermally throttle; check `sensors` and warn the user rather than
  handing over an overheater silently.

## Watchdog cron jobs (do not recreate)

Two script-only (`no_agent`) Hermes cron jobs run on this box and deliver to the
user's Telegram DM. Check `cronjob(action='list')` BEFORE adding another --
near-duplicates are how you end up double-reporting.

| Job | ID | Interval | Script |
|---|---|---|---|
| zombie-watch | d21557dc4854 | 15m | `~/.hermes/scripts/wubu_zombie_watch.sh` |
| thermal-watch | 3668f25c5893 | 5m | `~/.hermes/scripts/wubu_thermal_watch.sh` |

Both are WATCHDOGS: empty stdout sends nothing at all, so they are silent by default.
Non-zero exit or timeout raises an error alert instead.

- **zombie-watch** reports only when zombies exist, tracks the count across ticks and
  flags GROWTH, and names the parent process responsible.
- **thermal-watch** reads real sensors (coretemp/acpitz/nvme/NVML GPU), reports ONLY
  on escalation (level rises above `WUBU_THERMAL_WARN`/`CRIT`, default 80/92C), and
  clears state when healthy so a later rise alerts again.

### Fan control: what actually exists here

This machine has **no writable fan control**. All four `fan*_input` nodes under
`msi_wmi_platform` are read-only RPM; there is no `pwm*`/`pwm*_enable` anywhere in
sysfs and no MSI platform device. Do NOT offer PWM control as if it were available.

Direct EC writes over port I/O are the only remaining route and can brick the laptop
on wrong offsets -- never do them blind. The watchdog therefore calls a configurable
hook once per escalation:

```
WUBU_FAN_RAMP_CMD="/path/to/controller"   # invoked as: <cmd> <sensor> <degC>
```

Wire msi-ec, NBFC or a vendor tool there; until then it says plainly that no controller
is wired. RAM temperature remains `n/a` on Linux (no DIMM/SPD sensor in sysfs);
`WUBU_RAM_TEMP_SYSFS` points at one if the user ever supplies a path.

## Files

- `templates/clamshell-guard.sh` -- the lid watcher/panel controller.
- `templates/clamshell.service` -- the user unit (wraps the guard in systemd-inhibit).
- Live install on this box: `~/.local/bin/wubu-clamshell-guard.sh` and
  `~/.config/systemd/user/wubu-clamshell.service`; enforcement rides
  `~/.local/bin/wubu-no-lock.sh` on `wubu-no-lock.timer`.
