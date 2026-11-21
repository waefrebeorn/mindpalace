# clamshell-guard.sh -- lid detect + panel control.
# Copy to ~/.local/bin/, chmod +x.  See SKILL.md for the unit and pitfalls.
#
# Env overrides used for testing without hardware:
#   WUBU_LID_STATE   path to a file shaped like /proc/acpi/button/lid/LID0/state
#   WUBU_LID_OUTPUT  xrandr output name (default eDP-1)
#   WUBU_LID_POLL    poll seconds (default 1)
#   WUBU_LID_DRY_RUN log the action instead of calling xrandr
#   WUBU_LID_LOG     append log lines here (syslog is used normally)

#!/bin/sh
set -u

LID_STATE=/proc/acpi/button/lid/LID0/state
OUTPUT=eDP-1
POLL=1
DRY=0
[ -n "${WUBU_LID_STATE:-}" ]   && LID_STATE=$WUBU_LID_STATE
[ -n "${WUBU_LID_OUTPUT:-}" ]  && OUTPUT=$WUBU_LID_OUTPUT
[ -n "${WUBU_LID_POLL:-}" ]    && POLL=$WUBU_LID_POLL
[ -n "${WUBU_LID_DRY_RUN:-}" ] && DRY=$WUBU_LID_DRY_RUN

export DISPLAY=${DISPLAY:-:0}
export XAUTHORITY=${XAUTHORITY:-$HOME/.Xauthority}

# Always defined: act() reads it, and under `set -u` an unset variable aborts the
# whole guard when the first poll happens before any successful read.
LID_STATE_READ=unknown

log() {
    logger -t wubu-clamshell "$1" 2>/dev/null
    [ -n "${WUBU_LID_LOG:-}" ] && echo "$(date '+%H:%M:%S') $1" >> "$WUBU_LID_LOG"
}

act() {   # $1 = off | on
    if [ "$DRY" = "1" ]; then
        log "DRY-RUN: xrandr --output $OUTPUT --$([ "$1" = off ] && echo off || echo auto)"
        return 0
    fi
    if xrandr --output "$OUTPUT" --$([ "$1" = off ] && echo off || echo auto) >/dev/null 2>&1; then
        log "lid $LID_STATE_READ ($1): $OUTPUT turned $1"
    else
        log "FAILED to set $OUTPUT $1"
    fi
}

read_lid() {
    if [ ! -r "$LID_STATE" ]; then LID_STATE_READ=unknown; echo unknown; return; fi
    LID_STATE_READ=$(sed -n 's/^state:[[:space:]]*//p' "$LID_STATE" | head -1 | tr -d '[:space:]')
    LID_STATE_READ=${LID_STATE_READ:-unknown}
    echo "$LID_STATE_READ"
}

# NOTE ON THE SLEEP INHIBITOR
#   Do NOT spawn it here as a background child: systemd kills the whole unit cgroup
#   on stop/restart, taking the inhibitor with it while the guard keeps running.
#   Instead the unit wraps this script:
#     ExecStart=/usr/bin/systemd-inhibit --what=sleep:handle-lid-switch \
#         --mode=block --who=wubu-clamshell --why=... this-script

prev=$(read_lid)
log "guard started; lid is $prev, output $OUTPUT"
case "$prev" in
    closed) act off ;;
    open)   act on ;;
esac

while :; do
    cur=$(read_lid)
    if [ "$cur" != "$prev" ]; then
        case "$cur" in
            closed) act off ;;
            open)   act on ;;
        esac
        prev=$cur
    fi
    sleep "$POLL"
done
