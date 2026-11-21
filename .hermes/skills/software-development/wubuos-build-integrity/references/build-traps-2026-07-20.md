# Build Traps — 2026-07-20 Session

## 1. Gui-shot / test-harness stale-object trap

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

## 2. App-launch registry key vs title mismatch

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

## 3. Overlapping-window layout in GUI harness

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

---

## 4. Test-suite opaque-struct accessor pattern

**Problem:** Tests reach into opaque structs (`CalcState`, `TaskManagerState`, `RegeditState`, `FileManagerState`, `ControlState`, `NotepadState`) → compilation errors when headers only forward-declare.

**Solution:** Add **read-only accessors** to each module's public API rather than exposing internals. This preserves opacity while giving tests verified inspection capability.

Pattern applied across 6 modules this session:

```c
// Public header (e.g., taskmgr.h)
int    taskmgr_get_active_tab(const TaskManagerState *tm);
int    taskmgr_process_count(const TaskManagerState *tm);
int    taskmgr_process_pid(const TaskManagerState *tm, int i);
const char *taskmgr_process_name(const TaskManagerState *tm, int i);
double taskmgr_process_cpu(const TaskManagerState *tm, int i);
double taskmgr_total_cpu(const TaskManagerState *tm);
int    taskmgr_hist_idx(const TaskManagerState *tm);

// Implementation (taskmgr.c)
int taskmgr_get_active_tab(const TaskManagerState *tm) { return tm ? tm->active_tab : 0; }
// ... etc.
```

**For leaf data structs that ARE public** (like `WubuLayer`, `RegKey`), expose the full struct in the public header — tests can then navigate `.name`, `.children`, `.child_count` directly. This mirrors `WubuLayer` in `wubu_canvas.h`.

**Test rewrite:** Convert all `state->field` pokes to accessor calls. 34 test sites converted this session, `test_apps` now 40/40 green.

---

## 5. Headless deterministic GUI capture harness patterns

**Problem solved this session:** The harness produced overlapping windows (Calculator fully behind Notepad), zero-size Control Panel, and non-deterministic layout.

**Fix patterns (now in wubu_gui_shot.c):**

1. **Deterministic seed** — `srand(12345)` at top of `main()` so `rand()` positions are reproducible for exact cropping.

2. **Tiled, non-overlapping layout** — explicit coordinates for every app window, no randomness:
   ```c
   if (calc)   { calc->x = 24;   calc->y = 56;   calc->w = 300;   calc->h = 420; }
   if (note)   { note->x = 344;  note->y = 56;   note->w = 500;   note->h = 400; }
   if (ctrl)   { ctrl->x = 344;  ctrl->y = 472;  ctrl->w = 520;   ctrl->h = 440; }
   // canvas, fm, taskmgr, editor, repl — each in its own zone
   ```

3. **Focus the app you want verified active** — call `wm_set_focus(win)` on the window that should show navy (active) title bar:
   ```c
   if (calc) wm_set_focus(calc);  // calc title = navy, others gray
   ```

4. **Layout dump for exact cropping** — `fprintf(stderr, "[layout] name=%s x=%d y=%d w=%d h=%d\n", ...)` after tiling so verification scripts can compute precise crop rects without guessing.

5. **Layout-ordered z-index** — windows are tiled in launch order; later windows sit on top. If you need a specific window on top, launch it last or explicitly raise it.

**Verification workflow (PIL, no vision tool needed):**
```python
from PIL import Image
im = Image.open("/tmp/ppng/02_apps_win98.png").convert("RGB")
# crop exact calc rect: x=24, y=56, w=300, h=420
crop = im.crop((24, 56, 324, 476))
# count white text pixels in display panel, navy in title bar, bevel patterns
```

This caught the real bug: Calculator was correct, but Notepad covered it. The tiled layout + focus call makes every frame independently verifiable.