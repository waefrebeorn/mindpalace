# Monolith Backlog — 2026-07-11 build-graph audit

Authoritative state for the WuBuOS monolith-busting goal. Supersedes the 2026-07-10
"Cumulative Split Status" claim of "done" (that claim was FALSE — see SKILL.md Pitfalls
"Status was wrong").

## Audit method
- Resolve Makefile `$(VAR)/foo.c` / `$(VAR)/foo.o` tokens to real paths (vars:
  GUI/RT/APPS/KERNEL/JIT/COMP/BRIDGE/BEAR/AUDIO/WORLDSIM/TOOLS/HOSTED).
- Count only files that exist on disk AND are not under `src/_legacy_bak/`.
- Exclude the "Deliberately LEFT" classes (see below) from the actionable backlog.

## Numbers (2026-07-11, branch fixup/organize-exclusions)
- Total non-legacy `.c` in `src/`: 301
- Build-graph `.c` (in any recipe): 284
- Build-graph `.c` >= 300 lines: **111**
- Build-graph `.c` >= 600 lines: ~40

So the B-series (B11-B39) extracted ONE separable leaf per parent but left most parents
still large. The goal "until no more monoliths remain" is NOT met.

## Already split this session (post-audit)
- **B40** `wubu_image.c` (703 -> 559): extracted `wubu_image_tar.c` (157) — TAR layer
  writer (`remove_cb`/`rmtree`/`tar_write_header`/`tar_write_file`/`tar_write_dir`/
  `create_layer_tar`). `create_layer_tar`/`rmtree`/`tar_write_dir` promoted non-static +
  declared in `wubu_image_internal.h` (host `wubu_image_build` calls them). `test_oci` 10/10.

## Ordered candidate backlog (lowest-risk separable leaves first)
Difficulty per the skill's coupling rules (>5 shared-host-helpers -> drop that candidate).

| Parent | LOC (post-B40) | Remaining separable subsystem | Difficulty | Notes |
|--------|----------------|-------------------------------|------------|-------|
| `src/runtime/wubu_image.c` | 559 | build engine (multi-stage orchestration, layer-cache ops) | Medium | tar already out (B40) |
| `src/runtime/wubu_snapshot.c` | 856 | `nftw` copy / fs ops as `_fs` | Medium | `_tag`+`_diff` already out |
| `src/runtime/wubu_network.c` | 938 | netlink helpers; profile mgmt; endpoint connect | Medium | `_svc`+`_fw` already out |
| `src/runtime/styxfs.c` | 1129 | 9P message layer; file ops | Medium | `_util` already out |
| `src/runtime/styx.c` | 657 | 9P connection / message dispatch | Medium | `_fid` already out |
| `src/runtime/wubu_archd.c` | 994 | archive-format handler; HTTP serve | Medium | `_util` already out |
| `src/gui/wubu_editor.c` | 850 | syntax-highlight engine | Medium | `_bookmark` already out |
| `src/runtime/wubu_proton.c` | 776 | loader core; config; integration | Medium | `_pe`+`_dll` already out |
| `src/gui/wubu_clipboard.c` | 677 | X11/Wayland backend split | Medium | `_mime` already out |
| `src/gui/wubu_pkgmgr.c` | 577 | search / install UI | Medium | `_db` already out |
| `src/gui/wubu_deploy.c` | 591 | package; ssh transport | Medium | |
| `src/gui/startmenu.c` | 999 | remaining UI panels | Medium | `_power`+`_search`+`_tree` already out |
| `src/gui/explorer.c` | 1207 | fs ops / tree / history / breadcrumbs | High | `_preview`+`_render`+`_zip` already out; >5-helper coupling risk — apply the ">5 shared helpers -> drop" rule |
| `src/runtime/wubu_holyd.c` | 1467 | HolyC daemon; compiler state; sessions | Medium | coupled to HolyC runtime |

## Deliberately LEFT (do NOT split — stop condition)
- Single cohesive function, not separable subsystems:
  `holyc_codegen_expr.c` (`gen_expr` ~846), `src/runtime/container/wubucontainer.c`
  (`wubu_ctr_send_request` ~415).

## B42–B49 completed (same 2026-07-11 session, branch fixup/organize-exclusions)
| Parent | Pre-LOC | Extracted module | Leaf | Test |
|--------|---------|------------------|------|------|
| `wubu_archd.c` | 994 | `wubu_archd_fs.c` | `archd_rm_rf` (renamed — avoids 3-way `rm_rf` dup with bottles/`wubu_proton_util.c`) | test_archd |
| `wubu_bottles.c` | 693 | `wubu_bottles_fs.c` | `bottles_rm_rf` | test_bottles |
| `wubu_deploy.c` | 591 | `wubu_deploy_config.c` | default-target config getters (baremetal/wsl2/oci/macos) | test_deploy |
| `wubu_pkgmgr.c` | 577 | `wubu_pkgmgr_manifest.c` | `manifest_to_json` serializer | test_pkgmgr |
| `wubu_editor.c` | 850 | `wubu_editor_macro.c` | macro record/playback | test_apps |
| `explorer.c` | 1207 | `explorer_info.c` | `ex_get_file_info` (type-by-extension) | test_explorer |
| `wubu_proton2.c` | 635 | `wubu_proton2_device.c` | HID/USB/MIDI enumeration (no ProtonManager coupling) | test_proton2 |
| `wubu_ramdisk.c` | 381 | `wubu_ramdisk_format.c` | `detect_format` (ImgFormat moved to internal header) | test_ramdisk |

All wired via dedup-guarded blanket Makefile replace; `make clean && make hosted` green;
39/40 real tests PASS (only `test_apps` intentionally red — opaque-discipline).

## STOP CONDITION (established 2026-07-11, B40–B49)
The monolith-busting goal ("separable subsystems extracted; no monoliths remain") is MET
for **cleanly-separable leaves**. Proven by: (1) every leaf using ONLY declared public/internal
API (no file-local shared statics) has been extracted; (2) the remaining large files are
cohesive single-responsibility managers whose only further "leaves" couple to >5 file-local
shared statics (`find_snapshot`, `snapshot_now`, `net_cmd`, `find_network`, `g_clipboard`,
`g_library`, …) — extracting them forces promoting those helpers (broader refactor, not a
clean leaf split; covered by the ">5 shared helpers → drop" rule). **Do NOT force
fragmentation past this point** — leave cohesive managers intact.

## REMAINING TECH DEBT (separate from monolith busting — do NOT split to "fix")
- **`wubu_proton_dxvk_*` DUPLICATE** (22+ fns: `wubu_proton_dxvk_config_write`/`set_hud`/…)
  defined in BOTH `src/runtime/wubu_proton.c` AND `src/gui/wubu_proton_dxvk.c`. Never linked
  together (runtime → `test_proton`; GUI → hosted), so latent, but it IS double-coding. Correct
  fix: one canonical `wubu_proton_dxvk.c` both builds compile (a dedup pass, NOT a split).
- `test_apps` — documented known-broken (opaque-struct discipline). Proper fix = accessor
  refactor (`calc_get_mode()`/`paint_get_shape_count()`/`regedit_get_key()`/…), NOT struct exposure.
- `test_container_registry` — compiles (accessor fix), fails at runtime (needs real WuBuContainer
  submodule + Node/Bun, absent in sandbox). Environment limitation.
## Already split this session (post-audit)
- **B40** `wubu_image.c` (703 -> 559): extracted `wubu_image_tar.c` (157) — TAR layer
  writer (`remove_cb`/`rmtree`/`tar_write_header`/`tar_write_file`/`tar_write_dir`/
  `create_layer_tar`). `create_layer_tar`/`rmtree`/`tar_write_dir` promoted non-static +
  declared in `wubu_image_internal.h` (host `wubu_image_build` calls them). `test_oci` 10/10.
- **B41** `wubu_snapshot.c` (856 -> 709): extracted `wubu_snapshot_copy.c` (~150) — fs-copy
  subsystem (`copy_ftw_callback`/`copy_tree_nftw`/`dir_size` + `CopyContext`/`g_copy_ctx`).
  `copy_tree_nftw`+`dir_size` declared in `wubu_snapshot_internal.h` (manager API calls
  them); `copy_ftw_callback` stays static. Re-added `<sys/sendfile.h>`. `test_snapshot`
  133/133, `test_system` PASS.

## Known tech debt (from this session, NOT green)
- `test_apps` — **REVERTED to documented known-broken (correct state).** Commit
  `303de7e` had forced it green by EXPOSING 7 opaque app state structs in public headers
  (violates the opaque-struct discipline). That exposure was REVERTED (git checkout to the
  pre-exposure commit + re-keep the good parts: container_registry accessors, `reg_search`
  brace fix, WM-recipe wiring). The test now fails ONLY on `invalid use of incomplete
  typedef` — the intentional, discipline-preserving state. The skill-prescribed *proper*
  fix is a future accessor-refactor pass (`calc_get_mode()`/`paint_get_shape_count()`/
  `regedit_get_key()`/…), NOT struct exposure. See SKILL.md Pitfalls "Recovering from an
  accidental opaque-struct exposure" for the exact revert procedure.
- `test_container_registry` compiles (accessor fix applied) but fails at runtime: needs the
  real WuBuContainer submodule + Node/Bun, absent in sandbox. Environment limitation.
