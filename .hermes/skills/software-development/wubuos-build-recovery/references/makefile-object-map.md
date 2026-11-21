# WuBuOS Makefile Object Map (build-recovery reference)

Verified during the 2026-07-11 crash-recovery session. Paths relative to repo
root `/home/wubu/.hermes/profiles/mind-palace/home/myseed/`.

## Objects that define `main()` (link at most ONE per binary)

| Object | Source | Guard | Notes |
|---|---|---|---|
| `src/hosted/hosted.o` | `src/hosted/hosted.c` | (none) | The one true WuBuOS shell `main()`. Links into `hosted` only. |
| `src/runtime/wubu_archd.o` | `src/runtime/wubu_archd.c` | `#ifndef WUBD_TEST_MAIN` | Daemon `main`. |
| `src/runtime/wubu_holyd_lifecycle.o` | `src/runtime/wubu_holyd_lifecycle.c` | `#ifndef WUBD_TEST_MAIN` | Daemon `main`. |

**Rule:** standalone apps (paint/doom) must NOT link `$(RT_OBJS)` (it carries
the two daemon mains). Use the curated `APP_RT_OBJS` instead.

## No-`main` daemon variants (use these in standalone links)

- `src/hosted/archd_hosted.o` — built from `src/runtime/wubu_archd.c` +
  `src/runtime/wubu_archd_fs.c` with `-DWUBD_TEST_MAIN`. Exposes
  `wubu_archd_init`/`wubu_archd_shutdown`/`wubu_archd_svc_start` WITHOUT main.
- `src/runtime/holyd_lifecycle_app.o` — built from
  `src/runtime/wubu_holyd_lifecycle.c` with `-DWUBD_TEST_MAIN`. No main.

## Hosted-only symbols (live ONLY in `hosted.o`, which has main)

- `wm_get_hosted_state(void) -> hosted_state_t*` — `src/hosted/hosted.c:1144`.
- `g_primary_selection_manager` (type `struct zwp_primary_selection_device_manager_v1 *`)
  — `src/hosted/hosted.c:87`. Referenced by `src/gui/wubu_clipboard.c:287` via
  `extern`. Standalone apps can't link `hosted.o` → provide a NULL-returning
  shim (`src/gui/standalone_hosted_shim.c`).

## `APP_RT_OBJS` curation rule (for standalone GUI apps)

Start from `$(RT_OBJS)`, then:
- REMOVE `wubu_archd.o`, `wubu_holyd_lifecycle.o` (they carry `main()`).
- REMOVE `rt/wubu_proton.o`, `wubu_proton2.o` (collide with `gui/wubu_proton.o`
  which is in `GUI_OBJS` — see proton duplicate map below).
- ADD `archd_hosted.o` (no-main variant), `holyd_lifecycle_app.o` (no-main variant).
- ADD `wubu_compat_db.o`, `wubu_session.o` (pulled in by `service_mgr.o`
  / `wm_ctxmenu.c` via `wubu_session_launch_game` / `wubu_compat_cache_dir`).
- ADD `styx_fid.o` + `styxfs.o` + `styxfs_path.o` + `styxfs_host.o` + `styxfs_util.o`
  (if not already present — `styxfs_server.o` alone is not enough).
- ADD `wubu_ct_isolate_cgroup.o` (referenced by `wubu_ct_isolate.o`).
- `wubu_screenshot_draw.o` belongs in `GUI_OBJS` (not APP_RT_OBJS) — add it there.
- Wrap the whole link in `-Wl,--start-group ... -Wl,--end-group` so JIT/proton
  cross-references resolve regardless of order, and place `$(JIT_OBJS)` INSIDE
  the group.

## Proton duplicate-definition map (real bug, not build damage)

| Symbol | Defined in |
|---|---|
| `wubu_proton_create_prefix` | `src/runtime/wubu_proton.c:538` AND `src/gui/wubu_proton.c:179` |
| `wubu_proton_exec` | `src/runtime/wubu_proton2.c:305` AND `src/gui/wubu_proton.c` |
| `wubu_proton_dump` | `src/runtime/wubu_proton2.c:314` AND `src/gui/wubu_proton.c` |

Canonical = `src/gui/wubu_proton.c` (linked via `GUI_OBJS`). The hosted binary
links `gui/wubu_proton.o` and does NOT link `rt/wubu_proton.o` or
`wubu_proton2.o`. Standalone app links must follow the same rule. Fixing the
duplicate (deleting the older `runtime/` definitions) is a separate field-gap
task, not a build-recovery step.

## Wayland protocol objects needed by standalone apps

- `$(HOSTED)/primary-selection-private.o` (built from `primary-selection-private.c`)
- `$(HOSTED)/xdg-shell-private.o` (built from `primary-selection-private.code`
  via `$(CC) -x c`)

Both needed because `wubu_clipboard.c` references `zwp_primary_selection_*`
protocol symbols. `hosted.o` (which normally provides them) is not linkable
into standalone apps.

## Required libs on standalone app link lines

`-lm -lsqlite3 -lzstd -lz -lwayland-client -lxkbcommon -ldl -lvulkan -ljson-c`

(`-lvulkan` for `vsl_gpu_vulkan.c`; `-ljson-c` for `container/wubucontainer.c`;
`-lz` for PNG in `wubu_canvas_io.c`.)
