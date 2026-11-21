---
name: wubuos-win32k-backbone
description: "Build wubuos win32k-lite WM objects, /n view."
---
# WuBuOS win32k-lite — the 'make Windows systems' backbone (P1)

win32k on Windows/ReactOS is the kernel-mode window-manager store (USER: station,
desktop, window class, message queue, hooks + GDI). The P1 slice builds that object
model on WuBuOS's `wubu_cap` authority core so every object is a revocable token.

SHIPPED (2026-11-06, host-verified): `src/runtime/win32k/wubu_win32k.{c,h}` +
`wubwin32k_test.c`. `make test_win32k` = 26/26 green, exit 0. Objects: station /
desktop / class(register/unregister) / window(owns FIFO msg queue): post/peek/get/revoke.
`wubu_win32k_snapshot()` serializes the live registry (the /n/win32 view).

P1b SHIPPED too: `/n/win32` control plane — `wubu_ns_win32.{c,h}` reads the live
win32k registry and publishes `/n/win32/{registry,stations,windows}` via the standard
ns_mkdir/ns_write namespace primitives (`make test_ns_win32` = 14/14, exit 0).

P2 GDI SHIPPED: cap-backed GDI surface objects in the same module — DC/brush/pen/bitmap
(`WUBU_CAP_KIND_GDI` 14; subtypes 0x10-0x13). Ordered exclusive lock (DC<BRUSH<PEN<BITMAP;
acquire denied if any LOWER-order object is exclusively locked by a DIFFERENT pid),
shared refcount (addref/deref), delayed deletion (mark_destroy mand, object freed only
when shared==0 AND unlocked). Folded into `wubu_win32k_snapshot` as `gdi <kind> <label>
refs=N lock=pid|free [,dead]` + published to `/n/win32/gdi`. `make test_win32k` = 49/49,
`make test_ns_win32` = 16/16, `make test_cap` = 34/34, all exit 0.

The message queue is thread-safe (a single module-wide `pthread_mutex_t g_q_lock` guard
post/peek/get) and proven across threads: `test_win32k` spawns a producer pthread that
posts 20 msgs to a window while the owning thread drains them in FIFO order — the WM-pump
shape (one pump thread, producers anywhere). The win32k module now needs -pthread on its
compile line in EVERY recipe (`test_ns_win32` earned that flag).

## GDI design gotcha (delayed deletion)
`gdi_mark_destroy` must NOT `wubu_cap_revoke` the token immediately — deref needs the
token to stay resolvable so existing holders can drain refs to 0. mark_destroy sets a
`dead` flag (refuses addref/acquire with EREVOKED) but leaves the cap live; the cap is
revoked and the entry freed only when a deref/release brings shared to 0 while unlocked.

## The /n module shape (P1b, mirrors wubu_ns_kernel.c)
- `wubu_ns_win32.c`: `#include "wubu_ns_bridge.h"` + `"wubu_ns_bridge_internal.h"`
  (g_ns_root/ns_mkdir/ns_write) + the module header. Safe no-op (`return 0`) when
  `g_ns_root` unset. Link ONLY wubu_ns_fs.o + wubu_win32k (which pulls the cap core).
- Test (test_ns_win32, mirror test_ns_kernel): set g_ns_root to a TEMP dir via
  `wubu_ns_bridge_create(tmpdir)` (defined in wubu_ns_fs.o, light), stamp the registry,
  `wubu_ns_win32_sync()`, then fopen temp/win32/* and assert. To null the root for a
  no-op check, `*(const char **)&g_ns_root = NULL` (it is `extern const char *`).
- Recipe = separate compile lines per .c + a `-no-pie` link of the .o set + a run line,
  appended at EOF of mk/tests.mk (append at end avoids the run-line-orphan pitfall).
- Include rms: test needs `wubu_ns_bridge_internal.h` for g_ns_root and `<unistd.h>` for
  rmdir (both were missing on first build — the compiler names them).

## The reusable authority pattern (the point of the module)
- Every object = one wubu_cap token, kind `WUBU_CAP_KIND_WINDOW` (added 13 to
  wubu_cap.h), subtype carried in a parallel entry struct.
- `wubu_cap_create(kind, rights, aud, 0, 0, owner_pid, parent_idx, &tok)` returns the
  SLOT JSON > 0 on success (not WUBU_CAP_OK); parent_idx links the cap tree for destroy.
- **wubu_cap_object_t is OPAQUE** — you cannot read fields (no kind_data). So tie your
  entry to the cap SLOT INDEX (`g_ent[cap_idx]`, guard idx < your registry size) instead
  of storing a pointer in kind_data. wubu_cap_resolve() returning non-NULL is only a
  pass/fail authority gate.
- Access gate: `wubu_cap_resolve(pid, tok, required)` (audience + rights + generation)
  then verify `entry.used` and `entry.gen == token_gen`. Any failure = deny.
- **Revoke: record survives, authority dies.** `wubu_cap_revoke()` invalidates the
  generation; every later resolve NULLs → post/get/peek denied while the snapshot still
  lists the object. That is the NT authority property (same one vsl_nt_cap proves).
- wubu_cap return traps (`wubunos-nt-cap-authority` skill): create returns slot >0;
  revoke returns the invalidated COUNT (>0), normalize negative; by-slot resolve needs
  slot >= 1.

## Makefile pitfall — the run-line orphan (cost real time)
Test recipes in `mk/tests.mk` are TWO commands: the gcc compile line(s) THEN a separate
`\t$(RT)/<bin>` RUN line. Inserting a new target immediately after `test_cap:`'s compile
with a Python splice DISPLACED that run line onto the new rule (tab-indented lines attach
to the nearest preceding rule), so the build compiled fine then make ran the WRONG binary
(`make: src/runtime/wubu_cap_test: No such file or directory`, Error 127). Fix: rewrite
the whole region — restore the run line under test_cap AND give the new target it own
`\t$(RT)/wubwin32k_test`. Use a python splice (split/assign/save), never the patch tool on
recipe lines (mangles TABs). Verify with `cat -A` that commands start with real `^I`.

## Gate / no-regression check
`make test_win32k` then `make test_cap` (34/34) — wubu_cap.h gained only the additive
KIND_WINDOW enum, but confirm the cap suite still green after any cap.h edit.

## Next (P1b, P2)
- P1b: bind `wubu_win32k_snapshot()` to a REAL Styx9P node under `/n/win32/*`
  (mirror the `nt_registry_styx_export` swap-callback pattern in styxfs_server).
- P2: wire classes/hooks to the dosgui WM; add GDI surface-object kind (`WUBU_CAP_KIND_WINDOW`
  + a GDI kind) and immutable-object refcount (DC->brush->pen->bitmap lock order, from the
  reactos_study).
- qemu guest-boot verification is still BLOCKED on this host until qemu-system-x86_64 is
  installed (hosted `make test_*` is the green path meanwhile).
