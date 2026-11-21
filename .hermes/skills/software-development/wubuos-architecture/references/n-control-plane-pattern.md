# /n Control Plane — the "rip off other OSes, do it better" pattern

WuBuOS expresses every other-OS concern (systemd units, Snapper rollback,
Flatpak/Bottles, pkg managers) through ONE Styx/9P filesystem namespace at
`/n`. This is the concrete implementation shipped 2026-07-13 in
`src/runtime/wubu_ns_bridge.{c,h}` + `wubu_ns_snap.c` + `wubu_ns_fs.c`.

## The mapping thesis
Other OSes invent a different daemon/tool per concern. WuBuOS uses one
dispatch fabric + one filesystem:

| Other OS | Their mechanism | WuBuOS `/n` file (the "better" version) |
|----------|----------------|------------------------------------------|
| systemd `systemctl start <svc>` | PID1 + D-Bus | `echo start > /n/svc/<root>/<svc>/ctl` |
| systemd `systemctl status <svc>` | `systemctl` | `cat /n/svc/<root>/<svc>/status` |
| Snapper `snapper rollback <id>` | btrfs + snapperd | `echo <id> > /n/snap/<c>/rollback` |
| Snapper `snapper list` | snapperd | `cat /n/snap/<c>/list` |
| Flatpak/Bottles `bottles-cli run <n>` | Python daemon | `echo run > /n/bottles/<n>/ctl` |
| Chaotic-AUR `pacman -S chaotic-x` | prebuilt AUR repo | `echo x > /n/pkg/install` (P2, not built) |
| CachyOS kernel-manager | GUI + scx-manager | `echo bore > /n/kernel/scheduler` (P3, not built) |
| CachyOS `chwd` GPU switch | hw-detect daemon | `echo amd > /n/hw/primary/mode` (P3, not built) |

Key insight: each "vibe" is the SAME pattern — publish a directory under `/n`,
write a `status`/`list` snapshot file, and expose `ctl`/`create`/`rollback`
action files that dispatch to a pure function. The pure dispatcher is what a
live 9P server's write handler would call (the in-memory tree is the
synthesized control surface; serving it over real 9P is a later step).

## Module layout (verified, green)
- `wubu_ns_bridge.h` — public API + `wubu_ns_svc_ops_t` injectable ops table
  (svc_start/stop/restart/enable/disable/status). DI lets tests use mocks
  (the svc test verifies routing WITHOUT shelling out to arch-chroot/systemctl).
- `wubu_ns_bridge_internal.h` — MINIMAL internal header: only `g_ns_root`,
  `ns_mkdir`, `ns_write` (the FS core) + `wubu_ns_state_str`. NOT a god header.
- `wubu_ns_fs.c` — the FS core (extracted from `wubu_ns_bridge.c`, see below).
- `wubu_ns_bridge.c` — svc + bottle dispatch + `wubu_ns_svc_ops_real` (the
  production ops table wrapping `wubu_archd_svc_*`). Pulls in archd + bottles.
- `wubu_ns_snap.c` — snapshots as `/n/snap/<c>/{list,create,rollback,delete}`,
  driving the REAL `wubu_snapshot_*` API (overlayfs store, no root needed).
  `list` is a LIVE view — refreshed after `create`.

## FS-core extraction (the split that made the snap test linkable)
`wubu_ns_bridge.c` originally held `g_ns_root`/`ns_mkdir`/`ns_write`/
`wubu_ns_bridge_create`/`wubu_ns_state_str` AND the svc/bottle dispatch. Because
the dispatch references `wubu_archd_svc_*` + `wubu_bottle_*`, any binary linking
the bridge pulled in archd + bottles — too heavy for a small snap test in this
memory-constrained WSL (see `wubuos-build-recovery`).

Fix: extract the FS core into `wubu_ns_fs.c` (depends only on stdio + archd.h
for the `WubuArchServiceState` enum in `wubu_ns_state_str`). Now the snap test
links `wubu_ns_fs.c + wubu_ns_snap.c + snapshot(3) + wubu_fs_util.c` — 7 files,
no archd/bottles. This is the opaque-struct / self-contained-module discipline
applied: a lightweight subtree should NOT transitively require a heavy one.

## Test split rule (memory budget)
A single test binary that links snapshot + bottles + archd + styx (~30 files)
OOM-segfaults the linker here. So:
- `test_ns_bridge` = svc + bottle tests (29/29), restored to its original working
  object set.
- `test_ns_snap` = SEPARATE small binary (16/16) for the snapshot subtree.
Keep each test binary under ~10-12 objects. See `wubuos-build-recovery`
"Memory-constrained linker" for the full recipe.

## Heap-struct rule (runtime stack-overflow)
`WubuSnapshotManager` is ~56 MB. Tests MUST `calloc(1, sizeof(...))` it — a
stack local segfaults (ASan: `stack-overflow`). `WubuSnapshot snaps[1024]` is
also too big for the 8 MB stack; heap-allocate a modest cap (256). Mirror the
real `wubu_snapshot_test.c` `smgr()` helper.
