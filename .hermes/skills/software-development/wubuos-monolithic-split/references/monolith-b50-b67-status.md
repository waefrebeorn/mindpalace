# Monolith Busting — B50–B67 Status (post 2026-07-11 third pass)

Authoritative state after the third monolith-busting pass. Re-read at the START of a
monolith session instead of trusting the SKILL.md "Cumulative Split Status" block
(which is historical and was proven wrong once before — see its own warning).

## Bottom line

> **UPDATED 2026-07-15 — the "COMPLETE" claim below is now STALE.** This session
> dissolved `wubu_editor.c` (814 → 468 core + `wubu_editor_undo.c` /
> `_selection.c` / `_find.c`; technique in
> `references/cross-module-helper-promotion.md`) and found the build-graph broken
> on a **clean tree**: ~22 split-module `.o` files were never wired as
> prerequisites (they only linked because a warm `make gui`/`make runtime` left
> them around), and `styx_fid.o` had been dropped from `RT_OBJS`. All fixed in the
> repo. **The REAL bar is `make clean && make test`, not a warm-cache pass** —
> warm trees mask missing-`.o` gaps. Treat "complete" as suspect on every new
> monolith session; re-audit with `wc -l` first.

Monolith busting of cleanly-separable leaves is **largely complete but NOT
closed**. Remaining large files that may still be multi-concern (audit before
trusting this doc): `startmenu.c` (1000), `explorer.c` (948),
`wubu_clipboard.c` (678), `wubu_proton.c` (511). Many big files
(`fat32.c`, `holyc_codegen_expr.c`, `interrupt.c`, `wubu_math.c`, `memory.c`,
`jit.c`) are cohesive single-responsibility managers — do NOT artificially
fragment those.

- `make clean && make test` -> green (all tiers, 42 groups) as of 2026-07-15.
- `test_apps` is NO LONGER known-broken from the link-gap class (the
  clean-tree gaps that broke it are fixed). A fresh failure there means a real
  regression, not the historical opaque-struct rationale.

## This pass's extractions (all on `fixup/organize-exclusions`, pushed)

Anti-pattern reverted first (commit `9982215`): the `303de7e` opaque-struct exposure
was unwound; only the correct `wubu_container_registry` accessors were kept.

| Commit | Leaf | Parent -> New module |
|--------|------|----------------------|
| `5ffac34` | fs-copy | `wubu_snapshot.c` -> `wubu_snapshot_copy.c` |
| `e40276a` | fs/rm_rf | `wubu_archd.c` -> `wubu_archd_fs.c` (`archd_rm_rf`) |
| `3b6f867` | fs/rm_rf | `wubu_bottles.c` -> `wubu_bottles_fs.c` (`bottles_rm_rf`) |
| `5d8b1e9` | default config getters | `wubu_deploy.c` -> `wubu_deploy_config.c` |
| `6cdee34` | manifest->JSON | `wubu_pkgmgr.c` -> `wubu_pkgmgr_manifest.c` |
| `d9b0794` | macro record/playback | `wubu_editor.c` -> `wubu_editor_macro.c` |
| `036af4d` | file-metadata classification | `explorer.c` -> `explorer_info.c` |
| `ccfbf9e` | HID/USB/MIDI enum | `wubu_proton2.c` -> `wubu_proton2_device.c` |
| `af0c7d2` | format sniffing | `wubu_ramdisk.c` -> `wubu_ramdisk_format.c` |
| `d5bd572` | CNI plugin | `wubu_network.c` -> `wubu_network_cni.c` |
| `d5bd572` | WireGuard peers | `wubu_network.c` -> `wubu_network_wg.c` |
| `d5bd572` | Tailscale | `wubu_network.c` -> `wubu_network_ts.c` |
| `76d7f2f` | GC + retention rules | `wubu_snapshot.c` -> `wubu_snapshot_gc.c` |
| `71e4b40` | dep-resolution + conflicts | `wubu_pkgmgr.c` -> `wubu_pkgmgr_resolve.c` |
| `5b3d9cf` | integrity verification | `wubu_pkgmgr.c` -> `wubu_pkgmgr_verify.c` |
| `c781c63` | gamescope/wine cmd | `wubu_proton2.c` -> `wubu_proton2_gamescope.c` |
| `527499b` | app launch/control | `wubu_proton2.c` -> `wubu_proton2_launch.c` |
| `9e17453` | DNS record mgmt | `wubu_network.c` -> `wubu_network_dns.c` |
| `9e17453` | QoS / traffic shaping | `wubu_network.c` -> `wubu_network_qos.c` |
| `58ca5d5` | network-create (8 variants) | `wubu_network.c` -> `wubu_network_create.c` (promoted `emit_event`) |
| `14ce00e` | config save/load | `wubu_gamelib.c` -> `wubu_gamelib_config.c` (promoted `g_gamelib`) |
| `5e3278c` | start-menu .desktop | `wubu_gamelib.c` -> `wubu_gamelib_startmenu.c` (renamed `ensure_dir`->`gamelib_ensure_dir`) |
| `c44ba6a` | WASM backend | `wubu_exec.c` -> `wubu_exec_wasm.c` |
| `8268216` | Mach-O backend | `wubu_exec.c` -> `wubu_exec_macho.c` |
| `f354b89` | container payload | `wubu_exec.c` -> `wubu_exec_container.c` |
| `2ce38ee` | tarball export/import | `wubu_snapshot.c` -> `wubu_snapshot_xport.c` |
| `bc4f971` | playtime tracking | `wubu_gamelib.c` -> `wubu_gamelib_playtime.c` |

## Parent file line counts after extraction (cohesive managers, left intact)

- `wubu_snapshot.c` 583 -> 498 (create/incremental/mount/list/rollback/inspect/tree)
- `wubu_network.c` 938 -> 331 (lifecycle + endpoint connect/disconnect/list/stats)
- `wubu_pkgmgr.c` 532 -> 292 (init/shutdown/repo-mgmt/clean_cache/autoremove/get_stats)
- `wubu_gamelib.c` 448 -> 339 (state/CRUD/category/favorite/launch)
- `wubu_exec.c` 593 -> 429 (vsl init/run + ELF/PE/HOLYC/C/shell/python backends + dispatcher)
- `wubu_proton2.c` 503 -> 353 (lifecycle + add_app + dxvk-config[DUPLICATE] + accessors)
- `wubu_ramdisk.c` 381 -> ~341
- `wubu_editor.c` 850 -> 468 (undo/redo → wubu_editor_undo.c; selection/clipboard
  → wubu_editor_selection.c; find/replace → wubu_editor_find.c; 2026-07-15)
- `explorer.c` 1207 -> (file-info extracted; tree-scan core left cohesive)

## Remaining genuine defect (DEDUP) — CLOSED

**BOTH dedup items are DONE (commits `8cbd776`, `62b5738`):**

1. **`rm_rf` triplicate** -> canonical `src/runtime/wubu_fs_util.{c,h}`
   (`wubu_fs_rm_rf`). The three byte-identical copies (`rm_rf` in
   `wubu_proton_util.c`, `archd_rm_rf`, `bottles_rm_rf`) are now 1-line
   wrappers. `wubu_fs_util.o` wired into `RT_OBJS`/`GUI_OBJS`/`HOSTED_OBJS`
   + the direct-compile test recipes.

2. **`wubu_proton_dxvk_*` divergent duplicate** -> canonical core
   `src/runtime/wubu_proton_dxvk.{c,h}`. The divergent runtime + GUI copies
   (different conf-path layouts; runtime copy had a `DxvkConfigUI` typo)
   became thin adapters registering a layout resolver (+ GUI-only
   prefix-state pull/push hooks). Typo `DxvkConfigUI` -> `DxvkConfigUI`
   corrected. Wired into `RT_OBJS`/`GUI_OBJS`/`HOSTED_OBJS` + every recipe
   that compiles `wubu_proton.c` / the GUI adapter directly.

After both: `make clean && make runtime/hosted/paint/doom` green, full
`make test` gate green (all tiers, 32/32 proton tests pass).

## What NOT to re-extract / re-dedup

Any leaf in the table above, AND both dedup items above. Separable-leaf
monolith busting AND the dedup follow-ups are COMPLETE. The only legitimate
future work in this file-class is: (a) genuinely NEW monoliths introduced by
later feature work, or (b) a NEW divergent/identical duplicate spotted by
code review. Do NOT re-open the `rm_rf` or proton-dxvk items — they are
resolved. (Per user directive, a divergent duplicate is authorized REAL_GAP
work via the canonical-core pattern, not a stop-and-ask; see
`references/dedup-shared-core-patterns.md` sections 8 and 11.)

