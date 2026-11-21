# OS-Source Steal Workflow (research -> /n control plane)

Reusable technique from 2026-07-13: the user asked to "download CachyOS source
so we can steal from source and update the SteamOS image." Turned a vibes-only
research ask into a source-verified, buildable plan.

=====================================================================
WORKFLOW
=====================================================================
1. **Clone the target OS's source** (not just docs) into `vendor/<os>/`:
   - Pick the repos with STEALABLE SOURCE, not the ISO. For CachyOS:
     `github.com/CachyOS/linux-cachyos` (kernel patch set + scheduler config)
     and `CachyOS/Cachyos-pkgbuilds` (helper tools + meta packages).
   - Shallow clone to save space/time: `git clone --depth 1 <url>`.
   - Verify disk + network first: `df -h .`, `curl -sL -o /dev/null -w
     "%{http_code}" https://github.com`.

2. **Mine concrete, citable facts** (the opposite of vibes):
   - Scheduler strategy: `linux-cachyos/linux-cachyos/PKGBUILD` `_cpusched`
     ∈ {bore, eevdf, bmq, rt, rt-bore, hardened}; runtime flip via `scx-manager`
     (sched-ext). BORE = patch ON EEVDF for bursty-interactive (gamescope/proton).
   - Gaming stack (verbatim deps): `pkgbuilds/cachyos-gaming-meta/PKGBUILD`
     `depends=(...)` -> proton-cachyos-slr, protontricks, wine-cachyos-opt,
     winetricks, vulkan-tools, lib32-{alsa-plugins,giflib,gtk3,libjpeg-turbo,
     libva,mpg123,ocl-icd,openal}. This is the canonical "out of box gaming" set.
   - Raw kernel patches: `cachyos/kernel-patches` (e.g. `0001-handheld.patch`,
     `0001-hardened.patch`, `0001-rt-i915.patch`) — fetch via raw.githubusercontent
     if not in the cloned PKGBUILD repo.

3. **Map stealables to WuBuOS's secret weapon — the Styx/9P namespace.**
   Every other OS uses a DIFFERENT mechanism per concern (systemd sockets,
   Flatpak D-Bus, Bottles JSON, pacman). WuBuOS expresses ALL of them through
   ONE `/n` filesystem the `wubu_ns_bridge` already provides:
     snapper rollback     -> echo <id> > /n/snap/<c>/rollback   (wubu_snapshot_*)
     chaotic-aur install  -> echo x    > /n/pkg/install         (wubu_pkg_* — reuse,
                                                                   NOT oci/; flatpak-style
                                                                   .wubu packages w/ dep
                                                                   DAG + repo sources)
     kernel-manager GUI   -> echo bore  > /n/kernel/scheduler
     chwd GPU switch      -> echo amd   > /n/hw/<gpu>/mode
     cachyos-hello        -> (writes the above files)
     bottles-cli run      -> echo run   > /n/bottles/<n>/ctl     (DONE)

   KEY RULE — **reuse, don't reimplement.** Each `/n` subtree wraps an EXISTING
   WuBuOS API (wubu_snapshot_*, wubu_pkg_*, wubu_archd_svc_*, wubu_bottle_*).
   The new module is a thin 9P control-plane adapter, not a reimplementation of
   the stolen OS's tool. This is the "do it better" half: one namespace, zero
   new daemons, and the stolen logic is the *real* WuBuOS code path.

6. **Implement as a /n subtree + own small test binary.** The bridge already
   exists (`wubu_ns_bridge.c`, `wubu_ns_fs.c`, `wubu_ns_snap.c`,
   `wubu_ns_pkg.c`, `wubu_ns_kernel.c`). Each new subtree is one small `.c`
   that reuses `g_ns_root`/`ns_mkdir`/`ns_write` from `wubu_ns_fs.c` (via
   `wubu_ns_bridge_internal.h`) and drives the real API. Ship a
   `wubu_ns_<x>_test.c` asserting file<->API routing — but link it as its OWN
   binary (see `wubuos-build-recovery` "memory-constrained linker"): this box
   segfaults `cc`/`ld` on ~20+ TUs at once, so a heavy subtree (snapshot,
   bottles) MUST NOT be linked into the shared `test_ns_bridge` binary. Split:
   `test_ns_snap` (7 files, 16/16), `test_ns_pkg` (own binary, 13/13),
   `test_ns_kernel` (own binary, 13/13). Heap-allocate any giant struct
   (`WubuSnapshotManager` is ~56MB — `calloc`, never stack). The test drives the
   REAL API (no DI mocks needed when the API is in-process), unless the API
   shells out to a backend daemon — then inject a mock ops table like
   `wubu_ns_bridge`'s `wubu_ns_svc_ops_t`.

7. **gitignore the vendor clone.** Add `vendor/` to `.gitignore` (re-cloneable
   reference; keeps the repo lean). Keep the files on disk for stealing.
   here was `os-studies/steamos/steamos_study.md` (a study doc, not a disk
   image). "Updating it" = appending a SOURCE-VERIFIED section that cites the
   cloned facts and maps them to `/n`. SteamOS + CachyOS share the same
   Arch+Proton+gamescope+Vulkan base, so CachyOS is the performance layer on
   the same stack — high-signal to lift.

5. **Write a build spec, not just notes.** `docs/cachyos_source_steal.md`
   enumerates P1-P5 (P1=/n/snap rollback, P2=/n/pkg, P3=/n/kernel/scheduler,
   P4=BOTTLE_PRESET_GAMING, P5=/n/hw) — each cited to the cloned source, each
   a future module with a `*_test.c` asserting file<->API routing.

6. **gitignore the vendor clone.** Add `vendor/` to `.gitignore` (re-cloneable
   reference; keeps the repo lean). Keep the files on disk for stealing.

=====================================================================
WHY THIS IS THE "RIP OFF + DO BETTER" THESIS
=====================================================================
CachyOS implements each vibe as a SEPARATE daemon/tool (snapper, pacman,
kernel-manager, chwd, hello). WuBuOS expresses ALL of them through the SAME /n
9P namespace. One filesystem, zero bespoke daemon UX, one dispatch fabric.
That is the concrete payoff of "rip off the other OSes, do it better."

=====================================================================
GRAHAOS AUDIT REFINEMENTS (2026-07-18) — adopt the core, REJECT the stubs,
and DO NOT create a parallel in-tree subsystem
=====================================================================
Audited `github.com/waefrebeorn/grahaos_audit` (a from-scratch capability-based
x86_64 OS) to adopt its architecture into WuBuOS. Two refinements to the steal
workflow that bit us this session:

A. **Adopt the core; reject the stubbed edges.** GrahaOS's CORE is genuinely
   good and worth porting: capability-only authority (no uid/root, generation-
   counted revoke), the bootcap cascade root (diminishing-derive, revoke cascades
   to all descendants), snapshot/transactional rollback (`snap` COW + `txn`
   buffered-send replay), and a single machine-readable manifest (`gcp.json`)
   that drives kernel + userspace. BUT its EDGES are stubs: TLS stack is a
   634-byte `-ENOSYS` no-op; FS syscalls (OPEN/STAT/FSYNC/CLOSE) are `-ENOSYS`
   "until Phase 19"; SNAPSHOT RESTORE is `-ENOSYS` "until W16"; the in-kernel AI
   loop is non-functional (blocked on the TLS stub). **Do NOT copy those stubs.**
   WuBuOS already has the real equivalents — Styx9P FS for the FS ops, hosted
   userspace (not in-kernel) for the AI loop, real container/TLS via the hosted
   layer. When adopting, wire the core to WuBuOS's EXISTING real subsystems so
   you never ship `-ENOSYS`. The lesson: distinguish "real, adopt" from
   "stubbed, reject" before porting a single line.

B. **Before creating a "new" module from the audit, grep the tree for an
   existing equivalent.** This session built a fresh `src/runtime/wubu_spec/`
   capability module (mint/derive/revoke/table) — then discovered WuBuOS ALREADY
   had a full GrahaOS-ported capability subsystem at `src/runtime/wubu_cap/`
   (object/token/revoke/handle + a green `test_cap` target, 24/24). The new
   `wubu_spec/` was a **redundant duplicate** (version-skew risk — exactly the
   "monolith/divergence" anti-pattern). Fix: `rm -rf` the duplicate, extend the
   EXISTING module instead. Concretely: `wubu_cap/` was missing only the bootcap
   cascade root — so we added `wubu_cap_system.c` (+ `wubu_cap_handle_resolve_kind`
   in `wubu_cap_handle.c`) and extended `test_cap` to 34/34. The "simplify before
   extending / no parallel subsystems" rule applies to audit-driven work too:
   the reference repo is a SOURCE OF IDEAS, not a license to re-create what the
   tree already has. Grep order before writing:
     `grep -rln '<concept>' src --include='*.c' --include='*.h'`
   e.g. `grep -rln 'cap_object\|wubu_cap' src` would have surfaced `wubu_cap/`
   before the `wubu_spec/` mistake.

C. **Audit output belongs in `docs/`, not as scattered plan files.** Write a
   single `docs/<OS>_AUDIT_AND_WUBUOS_ADOPTION.md` with: what to steal (real),
   what to reject (stubs), a concrete adoption subtree (opaque structs, no god
   headers, C11), and a scorecard table (property × reference-OS × WuBuOS-today ×
   WuBuOS-after). This is the proven deliverable shape (shipped this session).
