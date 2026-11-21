# Build traps observed 2026-07-19 (WuBuOS desktop gap-closing)

Companion to SKILL.md. Exact recipes + C gotchas from the session where
`DOSGUI_MAX_ICONS` was bumped and the desktop delete/auto-arrange/theme/show-icons
features were added.

## 1. New call → new link dependency (recurring)
When `src/gui/wm_ctxmenu.c` started calling `wubu_trash_move()`
(from `src/gui/wubu_trash.c`), the link failed:
```
undefined reference to `wubu_trash_move'
```
`wubu_trash.c` itself needs `wubu_arch_mkdir_p` (→ `src/runtime/wubu_arch.c`)
and `wubu_settings_get` (→ `wubu_settings.c` etc., already linked). So the
full transitive set to add was `wubu_trash.c` + `wubu_arch.c`.

Recipes that compile `wm_ctxmenu.c` and needed the dep added:
- `test_wm` (Makefile ~line 665): added
  `$(GUI)/wubu_trash.c` and `$(RT)/wubu_arch.c` to the link line.
- `test_control` (Makefile ~line 798): added `$(GUI)/wubu_trash.c`.

`control_test.c` (the test source) also needed `#include "../gui/wubu_theme.h"`
to use `THEME_XP_LUNA_BLUE` / `wubu_theme_get()` after `control_set_theme()`
was added. `wubu_theme.c` was already in the link.

**Procedure:** after adding a cross-module call, `grep -rn` for the calling
`.c` in all Makefile recipes and add the new source(s) + every transitive
dep to each. `-MMD` does NOT do this for you.

## 2. Avoid full boot initializer in unit tests
`desktop_init()` references `g_app_defs`/`g_app_def_count` (defined in
`src/apps/apps.c`) and `daemon_panel_tick`/
`service_mgr_*`, and transitively `dos_window.h` →
`wubu_dos_proc.h` (DOS emulator). Linking all of that into `test_wm`
cascaded into "fatal error: wubu_dos_proc.h: No such file".

Fix: the test does NOT call `desktop_init()`. It verifies the boot
restore by running the exact line the initializer executes:
```c
wm_shutdown();
wubu_settings_init();
wm_init(1024, 768);
wm_set_auto_arrange(wubu_settings_get()->theme.auto_arrange);
CHECK(wm_get_auto_arrange() == true, "auto-arrange ON after re-init (boot path)");
```
Keep `test_wm`'s link minimal (no `desktop.c` / `apps.c`).

## 3. Test-fixture naming collides with guard logic
A test created a desktop file `Trash.desktop`. The trash dir is
`$XDG_DATA_HOME/Trash`. `wubu_trash_move()` guards with
`strncmp(abs_path, g_trash.trash_dir, strlen(g_trash.trash_dir)) == 0`
→ returns -1 ("can't trash trash") because `/.../Trash.desktop` shares the
`/.../Trash` prefix. The file was never moved, so the "removed from ~/Desktop"
assertion failed — a test bug, not a code bug. Rename the fixture to e.g.
`Note.desktop`. **Rule:** never name a test fixture with a prefix that matches
a substring/guard check in the code under test.

## 4. C declaration gotchas when adding functions
- **static-before-definition:** `wm_set_auto_arrange()` called
  `reflow_icons_column()` (a `static` fn defined later). C emitted an implicit
  non-static `int reflow_icons_column()` decl → later the real `static`
  definition caused "static declaration follows non-static declaration". Fix:
  add `static void reflow_icons_column(void);` forward decl before first use.
- **bool in header:** adding `bool` params to `control.h` without
  `#include <stdbool.h>` → "unknown type name 'bool'". Fix: add the include.
- **public-API hygiene:** `control.c` needed `g_dwm` / `reflow_all_icons_column`
  (WM internals). Instead of reaching into `wm_internal.h`, promote
  `wm_refresh_desktop` / `set_auto_arrange` / `get_auto_arrange` /
  `set_icons_visible` to the public `wm.h` and call those. Keeps modules
  self-contained (golden rule: no god-header reach-through).

## 5. Adding a NEW GUI source to every link recipe (mechanical)
When you add a new GUI module (e.g. `wm_icon_glyphs.c`, the Chicago→XP
glyph renderer), it must be linked into: GUI_OBJS (runtime), the hosted binary
link, AND every GUI test recipe (`test_wm`, `test_control`,
`apps_test`, the hosted link). Hand-patching each is error-prone.

Mechanical recipe: the token `$(GUI)/wm_icons.c` appears in ALL of those
link lines (GUI_OBJS uses it too). Patch it with `replace_all`:
- old: `$(GUI)/wm_icons.c`
- new: `$(GUI)/wm_icons.c $(GUI)/wm_icon_glyphs.c`
This inserts the new module right after `wm_icons.c` in every recipe in
one shot. Verify with `grep -n "wm_icon_glyphs.c" Makefile`. Works
because the anchor `$(GUI)/wm_icons.c` is present in each GUI link line
and nowhere else as a substring. Pick whatever anchor repeats across all target
recipes (another candidate: `$(GUI)/wm_render.c`).
