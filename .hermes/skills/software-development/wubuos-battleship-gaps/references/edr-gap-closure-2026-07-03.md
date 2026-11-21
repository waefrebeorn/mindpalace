# EDR Engine — 9 REAL_GAPs Closed (2026-07-03)

**Session:** 2026-07-03 EDR Split + Host Exec Fix
**Commit:** ed3e79c
**Skill:** wubuos-monolithic-split (subdirectory split with shared state pattern)

## Gap Closure Summary

| Gap # | Description | File(s) | Implementation |
|-------|-------------|---------|----------------|
| 1 | Process pin — NETLINK_CONNECTOR + cn_proc | `edr_proc_pin.c` | Real-time `PROC_EVENT_FORK/EXEC/EXIT` subscription, discovers 59 live processes |
| 2 | Thread pin | `edr_proc_pin.c` | Same infrastructure, thread events |
| 3 | Timestomp detection | `edr_fanotify.c` | `FAN_ATTRIB` flag on fanotify mark |
| 4 | Script capture | `edr_fanotify.c` | Content read on `FAN_OPEN_EXEC` for .sh/.py/.pl/.rb/.lua/.js/.ps1 |
| 5 | Registry coverage | `edr_fanotify.c` | Expanded inotify to 6 dirs: /etc/cron.*, /etc/systemd/system, /var/spool/cron |
| 6 | Unix socket pin | `edr_poller.c` | `/proc/net/unix` diff scan for named pipes |
| 7 | Driver load pin | `edr_poller.c` | `/proc/modules` diff scan |
| 8 | Scheduled task pin | `edr_poller.c` | Cron dirs + systemd timers diff scan |
| 9 | Proc recovery | `edr_poller.c` | `/proc` tree scan for missed forks |

## Technical Patterns Used

### NETLINK_CONNECTOR Process Pin (edr_proc_pin.c)
```c
// Open netlink socket with CN_IDX_PROC
int sock = socket(AF_NETLINK, SOCK_DGRAM, NETLINK_CONNECTOR);
struct sockaddr_nl addr = { .nl_family = AF_NETLINK, .nl_groups = CN_IDX_PROC };
bind(sock, (struct sockaddr*)&addr, sizeof(addr));

// Subscribe to PROC_CN_MCAST_LISTEN
struct __attribute__((packed)) {
    struct cn_msg cn;
    enum proc_cn_mcast_op op;
} msg = { .cn.id.idx = CN_IDX_PROC, .cn.id.val = CN_VAL_PROC, .cn.len = sizeof(enum proc_cn_mcast_op), .op = PROC_CN_MCAST_LISTEN };
send(sock, &msg, sizeof(msg), 0);

// Event loop: recv, parse proc_event, push EdrEvent
struct proc_event *pe = (struct proc_event*)cn->data;
switch (pe->what) {
    case PROC_EVENT_FORK:  // pe->event_data.fork
    case PROC_EVENT_EXEC:  // pe->event_data.exec
    case PROC_EVENT_EXIT:  // pe->event_data.exit
}
```

### FAN_ATTRIB Timestomp Detection (edr_fanotify.c)
```c
// Mark with FAN_ATTRIB to catch metadata changes (timestamps, permissions)
fanotify_mark(fd, FAN_MARK_ADD | FAN_MARK_MOUNT, FAN_ATTRIB | FAN_OPEN_EXEC | FAN_CLOSE_WRITE, AT_FDCWD, "/");
```

### Periodic /proc Diff Scans (edr_poller.c)
```c
// Every 100 ticks (~1s at 10ms worker interval):
// 1. Read /proc/net/unix → diff vs baseline → new unix sockets = named pipes
// 2. Read /proc/modules → diff vs baseline → new modules = driver loads
// 3. Scan /etc/cron.*, /etc/systemd/system → diff → new tasks
// 4. Scan /proc → find PIDs not in process model → recovery events
```

## Test Verification
```bash
make test_edr
# 12/12 passed
# Results: 12 passed, 0 failed
```

All tests exercise real kernel interfaces (netlink, fanotify, inotify, /proc) with graceful degradation on non-root/WSL.

## Impact on BATTLESHIP.md
- **Previous REAL_GAP count:** 1562
- **EDR split closes:** 9 REAL_GAPs
- **New total:** 1553 (approx, next DA audit will recalculate)

## Related References
- `wubuos-monolithic-split/references/edr-engine-split-2026-07-03.md` — Full split procedure and patterns
- `wubuos-session-workflow/references/session-2026-07-03-edr-split.md` — Session summary