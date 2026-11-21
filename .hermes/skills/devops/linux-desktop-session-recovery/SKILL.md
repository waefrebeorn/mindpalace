---
name: linux-desktop-session-recovery
description: Use when the desktop shell/WM is gone; diagnose and restore.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [linux, desktop, cinnamon, xorg, systemd, recovery]
---

# Linux desktop session recovery

## When to Use
- The user reports the desktop is broken, blank, frozen, or "your work
  broke the desktop"; windows lack decorations/panel, or input seems dead.
- An agent working headlessly must restore the user's VISIBLE session.

## Procedure
1. **See what is actually on screen before touching anything.**
   `computer_use(action='capture', app='screen', mode='vision')`, then read
   the panel/taskbar, window titles and any error text in the image.
2. **Collect the session facts in one pass.**
   ```bash
   ps -eo pid,ppid,stat,etime,cmd | grep -Ei 'Xorg|cinnamon|muffin|nemo|csd-'
   pgrep -a <shell-name>; pgrep -a <wm-name>
   DISPLAY=:0 wmctrl -m          # names the WM; BadWindow => no WM managing windows
   DISPLAY=:0 xrandr --query | head -5
   DISPLAY=:0 xset q | grep -A4 DPMS
   loginctl show-session <id> -p State -p LockedHint -p Active
   DISPLAY=:0 xinput list | head -20
   journalctl --user -b -p err --no-pager -n 50
   coredumpctl list --no-pager | grep -Ei '<shell>|<wm>'
   systemctl --user list-units --type=service --all | grep -iE '<shell>|<wm>|restore'
   systemctl --user status <restore-unit> --no-pager -l
   ```
   A prior restore unit that ended in `Result: core-dump` with `signal=SEGV`
   is a real crash record; read the JS/Clutter assertions immediately above
   it before classifying the fault.
   Read the session's required-components file to learn what SHOULD be
   running before calling anything "missing" (Cinnamon declares its shell
   and killer daemon in `/usr/share/cinnamon-session/sessions/cinnamon.session`).
3. **Classify the fault.** Session daemons alive but no shell/WM process and
   `wmctrl -m` failing = shell/WM died. `LockedHint=yes` = lock screen.
   No active `xrandr` mode = panel power state. No Xorg at all = display
   manager/session failure — do not restart the shell in that case.
4. **Start the shell as a self-restarting user unit**, with the session's
   environment carried explicitly. Give each restore a fresh unit name;
   `Restart=on-failure` turns a repeat shell crash into a short outage
   instead of another broken desktop:
   ```bash
   systemd-run --user --unit=desktop-restore-2 \
     --property=Restart=on-failure --property=RestartSec=2 \
     --setenv=DISPLAY=:0 --setenv=XAUTHORITY=/home/<user>/.Xauthority \
     --setenv=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus \
     --setenv=XDG_RUNTIME_DIR=/run/user/<uid> \
     /usr/bin/cinnamon --replace
   ```
   Substitute the user's actual shell/WM binary. A user unit survives the
   tool call that created it; do not rely on a child of a short-lived shell.
   Clear stale failure state with `systemctl --user reset-failed <old-unit>`.
5. **Verify with fresh output**, not the launch command's exit code:
   `systemctl --user status desktop-restore`, `pgrep -a <wm>`,
   `DISPLAY=:0 wmctrl -m` (must name the WM), D-Bus `ListNames` containing
   the shell's service, and a second screenshot showing the panel/taskbar.
6. **Report evidence and keep the cause honest.** State which processes and
   markers were checked; if there is no crash/OOM/kill record, say the cause
   is unresolved. Do not accept or assert blame for the breakage without a
   record connecting an action to it.

## Pitfalls
- **A running session daemon is not a running desktop.** `cinnamon-session-binary`
  plus `csd-*` children can stay up for days after the shell and WM have
  exited; check for the shell/WM process and `wmctrl -m` separately.
- **A composited full-screen capture shows windows even with no WM.** Unmanaged
  windows still draw; the missing panel/taskbar and window titles, plus
  `wmctrl -m` failing, are the discriminators.
- **Skip `nohup`/`setsid`/`disown` as the launcher.** The Hermes terminal tool
  rejects shell-level background wrappers; `systemd-run --user` both passes
  the guard and gives the shell a unit that outlives the tool call.
- **`wmctrl` `BadWindow` is a finding, not a tool error to work around.** It
  means no window manager answered the `_NET_SUPPORTING_WM_CHECK` query.
- **Check lock and panel state before blaming the desktop shell.** `loginctl`
  `LockedHint`, `xrandr` and DPMS each explain a "broken" screen with a
  different, cheaper fix.
- **Do not guess a kill cause from logs that contain only other processes'**
  crashes.** Read the PID and binary in each coredump/OOM line before
  attributing it to the shell; otherwise report "no record found".
- **Never let an agent gate or headless test drive the live `:0` display.**
  Weston/X11 windows and monitor-churning helpers can trigger shell layout
  crashes. Run product captures offscreen with `env -u DISPLAY -u
  WAYLAND_DISPLAY`, and do not start `make window`, `*-weston.sh`, or
  compositor scripts against the user's session during audit work. A gate
  that needs pixels should prove them from an offscreen framebuffer.
- **When the user says the desktop keeps breaking, harden the trigger after
  restoring.** Finding the crash record is not enough: isolate the display
  variables in the gate that touches graphics, re-run it with the shell
  active before and after, and record the standing rule where the next
  session will see it.
