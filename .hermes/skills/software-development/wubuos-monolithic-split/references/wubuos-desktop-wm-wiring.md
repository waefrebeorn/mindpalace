# WuBuOS Desktop / WM Wiring Patterns & Recurring Bugs

Condensed from the 2026-07-12 "maximum effort" refactor session. Use when
touching `src/gui/*`, `src/apps/apps.*`, or any app that must
render inside the WuBuOS Win98/XP desktop.

## Architecture (ground truth, verified this session)

- **The WM is already split.** `wm.c` is only the trunk (lifecycle +
  window mgmt + input routing). All rendering lives in `wm_render.c`;
  chrome in `wm_*.c` siblings (taskbar, icons, systray, ctxmenu,
  holyc_term, desktop, layout). Do NOT "split wm.c" again — it's done.
  `explorer.c` is likewise already modular (`explorer_*.c`).

- **Render entry point (post 2026-07-12):** `wm_render(fb,w,h)` is THE
  renderer. `wm_render_desktop` and `desktop_render` are 1-line
  wrappers only. `draw_window(int idx, fb, fb_w, fb_h)` is `static` in
  `wm_render.c` and receives the real framebuffer so app `on_draw`
  callbacks can render into their content region.

- **Apps draw via the global `vbe_*` backbuffer at absolute coords**
  (`win->x + offset`), NOT via the `fb` pointer passed to `on_draw`. The `fb`
  arg is for future clipped sub-region rendering; existing apps (notepad,
  repl, explorer, canvas) ignore it. Keep this pattern — do not switch to a
  per-window sub-framebuffer unless you also teach every app.

- **Two parallel WM types are NOT a real problem.** `wm.h` is a compatibility
  shim: `WmWindow` == `DosGuiWindow`, and all `wm_*` macros alias `wm_*`.
  `notepad.c` uses `WmWindow*`; that's the same struct. Don't "unify" them.

## The recurring "form-without-function" bug (the #1 gotcha)

A launch function that does `wm_create(...)` + sets `win->on_draw =
app_placeholder_draw` and nothing else is a STUB. The real engine already
exists but is never wired. Found + fixed for BOTH File Manager and WuBuCanvas:

- File Manager (`launch_file_manager`): the full Win98/XP-class
  Explorer engine (`explorer.c` + `ex_render_*`) existed and passed
  74/74 self-tests, but nothing called it from a window. Fix: `app_explorer.c`
  binds `on_draw -> ex_render_*` (toolbar/breadcrumbs/tree/file_list/preview/
  statusbar/context_menu) and `on_mouse/on_key -> explorer_handle_*`.

- WuBuCanvas (`launch_canvas` / "Paint" icon): the real layered
  `wubu_canvas` engine existed; the desktop pointed at a blank placeholder.
  Fix: `app_canvas.c` binds `app_canvas_*(w, fb, fb_w, fb_h)` into the engine.

**Rule:** when wiring an app to the desktop, grep for the engine's real
`*_render*` / `*_draw*` / public API FIRST. If it exists, wire it — do not
build a placeholder.

## App registry (single source of truth, post 2026-07-12)

`src/apps/apps.c` holds `g_app_defs[]` — one `DosGuiAppDef` per app
(name, title, icon_type, icon_color, `launch` fn). `desktop.c` iterates
this table to register icons; it no longer has its own hardcoded list. A
launch fn MUST bind `on_draw/on_mouse/on_key` (or `on_draw` for static apps).
Adding an app = one table entry + a launch fn. Do NOT re-add a second table.

## Makefile link-gap checklist (cause of most "undefined reference" failures)

`hosted` (`src/hosted/wubu`, linked from `HOSTED_OBJS`) is the strictest linker.
When you add a `.c` under `src/apps/` that an app registry entry calls, you
must add its `.o` to BOTH `APP_OBJS` AND the `hosted` link line, plus the
`test_apps` recipe. Known traps seen this session:
- `hosted` did NOT link `wubu_canvas.o`/`wubu_canvas_blend.o`/`wubu_canvas_io.o`/
  `wubu_codec.o` -> `app_canvas.c` (calls `wubu_cv_*`) failed to link.
- `hosted` did NOT link `notepad.o` (the `src/apps/notepad.c` one) ->
  `notepad_draw`/`notepad_key` undefined.
- Typo `$(RT)/styxfs_path.c` in `HOSTED_OBJS` (a `.c` source listed where an
  `.o` belongs) — must be `styxfs_path.o`.
- A function can be *declared* in the engine header but *never defined* (e.g.
  `wubu_cv_redo` in `wubu_canvas.c` was declared, missing impl). That links
  fine in isolation but fails when called. Grep the `.c` for the definition
  before assuming it exists.

## Minimal verification loop

```
make clean
make runtime >/tmp/r.log 2>&1; echo $?   # watch for error:/undefined
make apps    >/tmp/a.log 2>&1; echo $?
make hosted  >/tmp/h.log 2>&1; echo $?   # strictest link
make canvas  >/tmp/c.log 2>&1; echo $?
make -j1 test                            # full gate; GATE=0 = all tiers green
```
The `[wubu_snap] restore ... failed: Invalid argument` line in test output is a
pre-existing snapshot-rollback data-loss gap (copies to a logical id, not a
path) — non-fatal, tests still pass. Not your regression unless you touched
`wubu_snapshot.c`.
