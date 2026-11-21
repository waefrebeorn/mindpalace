# Daemon-as-Desktop-Backend Integration (E3) — closure pattern

Captured 2026-07-08 (commit `8b4b74f`). The task: wire an EXISTING, tested daemon
(`wubu_archd.c`, 16/16) as the Desktop's **service/autostart manager** — not just a
socket client the panel connects to, but the thing the Desktop *owns and drives* at
boot/shutdown. This is the generic "existing daemon -> Desktop backend" integration,
reusable for any WuBuOS daemon (holyd REPL, proton2, etc.).

## 1. Module design (the integration layer is real, not a shim)

Create a thin Desktop-side manager module that *wraps* the daemon API and holds the
live daemon instance + the Desktop-specific bookkeeping (autostart list):

```c
/* service_mgr.h */
#include "../runtime/wubu_archd.h"
typedef struct {
    char root[WUBU_ARCHD_MAX_ROOT_NAME];
    char svc[WUBU_ARCHD_MAX_PACKAGE_NAME];
    bool booted; int last_result;
} DosguiAutostartEntry;
int  service_mgr_init(void);
int  service_mgr_register_autostart(const char *root, const char *svc);
DosguiBootResult service_mgr_boot(void);   /* iterates entries -> wubu_archd_svc_start */
void service_mgr_stop_all(void);
void service_mgr_shutdown(void);
```

Key point: the manager holds `static WubuArchd g_archd;` and calls the daemon's real
API (`wubu_archd_init`, `wubu_archd_svc_start`, `wubu_archd_svc_stop`,
`wubu_archd_shutdown`). `boot()` drives real work — on a real host
`wubu_archd_svc_start` runs `arch-chroot <root> systemctl start <svc>`.

## 2. Wire into the Desktop lifecycle (the actual integration)

In `desktop.c::desktop_init()`:
```c
if (service_mgr_init() == 0) service_mgr_boot();
```
In `desktop_shutdown()`:
```c
service_mgr_shutdown();   /* stops booted services, tears down archd */
```
This is what makes it "wired", not just "callable".

## 3. Makefile link recipe — THREE pitfalls specific to pulling in a daemon .c

**PITFALL A — the daemon has its own `main()`.** `wubu_archd.c` guards its `main`
with `#ifndef WUBD_TEST_MAIN`. When you link `wubu_archd.c` into the hosted binary
(which has its own `main`) or any GUI test that has a `main`, you get
`multiple definition of 'main'`. Fix: add `-DWUBD_TEST_MAIN` to the compile flags of
every link line that includes `wubu_archd.c`. (Confirm the daemon you're pulling in
uses the same guard — `wubu_archd.c:990` does; `hosted.c`'s `main` is NOT guarded, so
defining `WUBD_TEST_MAIN` only suppresses archd's, which is what you want.)

**PITFALL B — the daemon drags deps.** `wubu_archd.c` references symbols from
`wubu_arch.c` (`wubu_arch_bootstrap`/`wubu_arch_install` via `wubu_ramdisk.c`),
`wubu_container.c`, `styx.c`, `styxfs.c`, `wubu_host_exec.c`, `wubu_ct_isolate.c`.
Every target that links your new module MUST also list `wubu_archd.c` AND these deps,
or you get `undefined reference to wubu_archd_init` / `wubu_arch_bootstrap`. Targets
that needed the addition this session: `hosted` (the real binary), `test_hosted`,
`test_daemon_panel`, `test_service_mgr`. Concrete link fragment:
```make
$(RT)/wubu_archd.c $(RT)/wubu_arch.c $(RT)/wubu_ramdisk.c \
$(RT)/wubu_host_exec.c $(RT)/wubu_ct_isolate.c \
$(RT)/wubu_container.c $(RT)/styx.c $(RT)/styxfs.c \
```
Also add the module `.c` to `GUI_OBJS` / every `$(JIT_SRCS)`-based direct link target
that compiles GUI (grep for `daemon_panel.c` — your module belongs right next
to it) and to `RT_OBJS` if it's runtime-loadable.

**PITFALL C — pre-existing broken targets.** `test_hosted` was ALREADY broken at
baseline (missing `wubu_welcome.c`, `wubu_wallpaper.c`, `hc_eval`, etc. — present in
the working `hosted` binary but absent from `test_hosted`'s link line). Once you touch
that target's deps, align its object list with the working `hosted` link so it builds.
Verify with `git stash` + run the target at baseline to confirm a failure is
pre-existing, not introduced. `test_hosted` is NOT in the `make test` aggregate, so a
pre-existing break there doesn't fail the gate — but don't leave it worse than baseline.

## 4. Regression test strategy for sandbox-unavailable real work

The daemon's real effect (`arch-chroot systemctl start`) needs root + a real Arch root,
absent in the sandbox. Don't fake it and don't assert the (unavailable) side effect
succeeded. Instead assert the **real behavior your module owns**:
- init creates a live handle (`service_mgr_active()` / `handle() != NULL`);
- registering N distinct entries grows the count by N; a duplicate does NOT;
  invalid (null/empty) registers are rejected;
- `boot()` iterates every entry and calls the daemon API once per entry, recording
  per-entry results (`attempted == started + failed`, `booted` flagged);
- `shutdown()` tears down (active=false, count reset) and re-init is idempotent.

This proves the integration does real work (iteration + bookkeeping + correct API
calls) without requiring root. The sandbox `svc_start` returning <0 is fine — you
assert the *attempt* happened, not that systemd started.

## 5. Verification
```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
make runtime && make hosted && make test      # gate stays green
make test_service_mgr                         # 19-check E3 regression
make test_daemon_panel                        # must still link (now pulls archd deps)
python3 ~/.hermes/profiles/mind-palace/skills/software-development/wubuos-battleship-gaps/scripts/find_real_gaps.py src  # 0/0
```
