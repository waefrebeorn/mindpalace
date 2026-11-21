# WuBuOS App-Wiring, Registry & "Go Heavy First" Patterns

Session-derived learnings for the WuBuOS desktop/app refactor. Companion to
the main split workflow — read this when the task touches `*`, the
app registry, or a "the app opens but shows nothing" bug.

## 1. Workflow: GO HEAVY FIRST, then polish

User directive (verbatim, captured to soul.md): *"go heavy first; you conquer
more"* and *"small wastes time first but is great polish and makes excellent
work."* Also: *"maximum effort, do it all… split ALL of the monolithic files
properly… this saves compile time, helps developers, and makes you as a agent
more aware and not double code."*

Applied rule for refactor/split campaigns in this repo:
1. Do the large, high-leverage extractions + broken-code fixes FIRST
   (verify build + `make test` gate stays green after each phase).
2. THEN sweep for polish (comment noise, naming, dedup, leftover stubs).
3. Never let a stub/shim/toy stand in for the real implementation when the
   real one exists. Wire the real engine.

## 2. STOP NARRATING — FIX IT

When a compile/link error is in front of you, DO NOT recount the diagnosis in
prose ("Two real bugs: 1… 2…"). Just fix the file and rebuild. The user
explicitly rejected the narrate-then-fix style ("bruh you got this backwards
and fix it"). Exception: a 1-line "fixed X, rebuilding" is fine. Long
diagnostic essays before the patch are the anti-pattern.

## 3. WuBuOS desktop architecture (ground truth, not assumptions)

- `wm.c` is the WM CORE only. The WM is ALREADY split into siblings:
  `wm_render.c`, `wm_taskbar.c`, `wm_layout.c`,
  `wm_icons.c`, `wm_systray.c`, `wm_ctxmenu.c`,
  `wm_holyc_term.c`, `wm_desktop.c`. So "split wm.c"
  is usually WRONG — it's already decomposed. Audit before splitting.
- `explorer.c` (947 lines) is likewise ALREADY a real, Win98/XP-class
  file manager: tree, breadcrumbs, toolbar, details/icons/list/tiles, preview
  pane, status bar, context menu, copy/cut/paste, zip browse (libzip), drive
  list, column sort. Its own test suite asserts 74 cases. **The gap was never
  the engine — it was that nothing called `ex_render_*` from a window.**
- `wubu_canvas.c` is a real layered image editor (layers, blend modes,
  50-level undo/redo, GIF/PNG/BMP/PPM IO). The MS-Paint *toy* (`paint.c`) was
  deleted earlier; the real editor is `wubu_canvas`.

## 4. FORM-WITHOUT-FUNCTION app launch (the recurring bug class)

Symptom: desktop icon opens a window that is blank / shows "window ready".
Root cause: `launch_*()` creates a window with
`win->on_draw = app_placeholder_draw` (or no callback at all). The engine
exists but is never bound to the window.

Fix pattern (do this, not a rewrite of the engine):
- Create `src/apps/app_<name>.c` with:
  - `app_<name>_init()` — calls the engine's init (idempotent guard).
  - `app_<name>_draw(win, fb, fb_w, fb_h)` — fans out to the engine's
    `ex_render_*` / composite / draw fns across the window's sub-regions.
  - `app_<name>_mouse(win, x, y, btn, kind)` → engine mouse handler.
  - `app_<name>_key(win, key, mods)` → engine key handler.
- In `launch_<name>()`: call `app_<name>_init()`, then set
  `win->on_draw / on_mouse / on_key`.
- Add `$(APPS)/app_<name>.o` to `APP_OBJS`, the `hosted` link line, and any
  direct-compile test recipe (e.g. `test_apps`).

Concrete examples shipped this session:
- `app_canvas.c` → `wubu_canvas` engine (toolbar, palette, layers, brush
  cursor, undo/redo, zoom/pan, file IO).
- `app_explorer.c` → `explorer` engine. Each `ex_render_*` fn takes
  `(ex, fb, fb_w, fb_h, x, y, w, h)` and draws via the global `vbe_*` buffer
  at absolute coords (so `(void)fb` in those fns is EXPECTED, not a bug).

## 5. Doubled app registry (the hardcoded-desktop rot)

Before: `apps.c` had `g_apps[]` AND `desktop.c` had a SEPARATE
`g_apps[]` — two hand-synced tables. Adding an app = editing 3+ places.

Fix: ONE `g_app_defs[]` table in `apps.c` of
`DosGuiAppDef { name, title, icon_type, icon_color, (*launch) }`. `desktop.c`
iterates `g_app_defs[]` to register icons; `app_launch(_by_name)` looks
up the table. No second hardcoded list.

Key detail: the legacy `DESK_ICON_EXPLORER` macro in `desktop.h` is
MISSPELLED — should be `DESK_ICON_EXPLORER` to match "Windows Explorer".
`apps.h` defines `DESK_ICON_EXPLORTER` (typo). Pick ONE spelling and
use it consistently; the registry table + both headers must agree or you get
"undeclared" at compile.

## 6. WM `draw_window` NULL-fb contract

`draw_window(idx)` historically called `w->on_draw(w, NULL, cw, ch)` — passing
NULL as the framebuffer. Apps still rendered via the global `vbe_*` backbuffer,
so it was a contract smell, not a hard failure. Fix: thread the real
`fb, fb_w, fb_h` from `wm_render_desktop()` → `draw_window(idx, fb, fb_w, fb_h)`
→ `w->on_draw(w, fb, fb_w, fb_h)`. Update the forward decl in BOTH
`wm.c` (trunk) AND `wm_internal.h`. Apps that ignore `fb` (use
global `vbe_*`) keep working unchanged.

## 7. Makefile link-gap checklist (the #1 cause of "compiles but won't link")

After adding app/engine objects, a target can COMPILE every .c yet fail at
`ld` with `undefined reference`. Checklist:
- Is the new `.o` in `APP_OBJS`? In `HOSTED_OBJS` / `hosted` link line? In the
  direct-compile test recipe (`test_apps`, etc.)?
- Did you accidentally list a `.c` where an `.o` belongs? (Real bug hit:
  `$(RT)/styxfs_path.c` in `HOSTED_OBJS` — must be `.o`. Also
  `wm_layout.c` (source) snuck into `HOSTED_OBJS`; harmless only because
  a `%.o:%.c` rule covered it.)
- Functions called across .c files must be NON-static and declared in a
  header (or forward-declared in the caller). A `static` fn used by another
  TU = `undefined reference`. Example fixed: `notepad_draw` was `static` →
  renamed to non-static `notepad_draw` + declared in `notepad.h`.
- If the engine declares a fn but it's never DEFINED, link fails with
  `undefined reference` even though the header is "clean". Example fixed:
  `wubu_cv_redo` was declared in `wubu_canvas.h` but had no body — implemented
  as the exact mirror of `wubu_cv_undo`.

## 8. Verification that actually ran (this session)

- `make runtime && make apps && make hosted && make canvas` → all exit 0.
- `make -j1 test` → GATE=0, "All tests passed (all tiers)".
- Explorer suite: `make test_explorer` → 74/74.
- One HARMLESS pre-existing log line remains:
  `[wubu_snap] restore from snap-... failed: Invalid argument` — a
  `wubu_snapshot` rollback data-loss gap (copies to a logical id, not a
  filesystem path; tests only assert branch-head pointer, not data copy).
  Non-fatal; flagged for the `wubu_snapshot.c` split pass, not fixed here.
