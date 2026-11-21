# Gui-shot / test-harness stale-object trap (2026-07-20)

**Symptom:** A test binary or harness (`wubu_gui_shot`, `test_gui_screenshot_apps`, etc.) runs but crashes / misbehaves (segfault, wrong layout, wrong window order) even though the source code looks correct.

**Root cause:** The target's prerequisite list in the Makefile omits most of the `.o` files it actually links. Example: `gui_shot` listed only 3 objects (`wm.o wubu_theme.o vbe.o`) but the link line pulled 20+. Editing `calc.c` rebuilt `calc.o` but `make gui_shot` didn't relink it → stale `calc.o` (with old `calc_draw_button` logic) linked → segfault at `calc_draw_button` with `w=-2` (impossible in current code).

**Fix:** The target's prerequisites MUST enumerate every `.o` that appears in its link recipe. Either:
- List all objects explicitly in the target's prereq line, OR
- Use a macro that expands to the full set (e.g. `$(GUI_OBJS) $(RT_OBJS) ...`) so `make` sees the full dependency graph.

**Check command after any header edit:**
```bash
find src -name '*.o' -older src/gui/<edited_header>.h
```
If any object is older than the header you just changed, that's the bug — `make` won't rebuild it.

**Pattern to audit:** Any `test_*` or harness target whose recipe has a long `$(CC) ... $(GUI)/foo.c $(GUI)/bar.c ...` line but whose prereq line is just `target: a.o b.o c.o`. Those are stale-object bombs.

---

# Control Panel / App launch by name matches title instead of registry key (2026-07-20)

**Symptom:** `app_launch_by_name("Control Panel")` returns `NULL` even though the app is registered.

**Root cause:** The registry entry for Settings/Control Panel is `{ "Settings", "Control Panel", ..., launch_settings }` — the first field (`name`) is the launch key, the second (`title`) is the window title. `find_by_name` matched only on `name`, so `"Control Panel"` (the title) failed.

**Fix:** Extend `find_by_name` to match on **either** `name` **OR** `title` — callers can resolve an app by the string a user would click.

```c
const DosGuiAppDef *app_find_by_name(const char *name) {
    if (!name) return NULL;
    for (int i = 0; i < g_app_def_count; i++)
        if (strcmp(g_app_defs[i].name, name) == 0 || strcmp(g_app_defs[i].title, name) == 0)
            return &g_app_defs[i];
    return NULL;
}
```

This is the angel-coder fix: the lookup should resolve a window by the name a user would click, not just the internal registry key.

---

# Overlapping-window layout in GUI harness (2026-07-20)

**Symptom:** Calculator fully hidden behind Notepad in `wubu_gui_shot` frames — harness used `rand()` for some windows and fixed positions for others, causing overlap. Visual verification impossible.

**Fix:** Rewrite harness `main()` with deterministic, tiled, non-overlapping layout. Key patterns:

```c
// Tiled positions — every app visible
if (calc)   { calc->x = 24;   calc->y = 56;   calc->w = 300;   calc->h = 420; }
if (note)   { note->x = 344;  note->y = 56;   note->w = 500;   note->h = 400; }
if (ctrl)   { ctrl->x = 344;  ctrl->y = 472;  ctrl->w = 520;   ctrl->h = 440; }
// ... etc

// Focus the app you want verified active (navy title)
if (calc) wm_set_focus(calc);
```

Plus `srand(12345)` for deterministic `rand()`-based layout if any remains.

**Verification:** After rebuild, crop each window's exact coordinates from the full frame and pixel-count the expected colors (white text pixels, navy title bar, button bevel patterns).