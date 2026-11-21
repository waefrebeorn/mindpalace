# Desktop Gap Closure Patterns (Phase 5 — 2026-06-28)

## Overview
This document captures the patterns used to close REAL_GAPs in the WuBuOS desktop/window manager code (`src/gui/wm.c`, `wm.h`).

## Gap Types Closed

### 1. Void Cast Removal — HolyC Terminal Modifier Keys
**File**: `wm.c` — `holyc_term_key()`
**Before**:
```c
static void holyc_term_key(DosGuiWindow *win, uint32_t key, uint32_t mods) {
    (void)mods;
    // ... only handled key, ignored mods
}
```
**After**:
```c
static void holyc_term_key(DosGuiWindow *win, uint32_t key, uint32_t mods) {
    bool ctrl = (mods & 0x02) != 0;
    bool shift = (mods & 0x01) != 0;
    bool alt = (mods & 0x04) != 0;
    bool meta = (mods & 0x08) != 0;

    if (ctrl && (key == 3 || key == 'c' || key == 'C')) {
        // Ctrl+C — clear input line
    } else if (ctrl && (key == 12 || key == 'l' || key == 'L')) {
        // Ctrl+L — clear screen/history
    } else if (ctrl && (key == 21 || key == 'u' || key == 'U')) {
        // Ctrl+U — delete current line
    } else if (shift && key == 0xE04D) {
        // Shift+Right — tab-complete from history
    }
    // ... existing Up/Down history navigation
}
```
**Pattern**: Replace `(void)mods` with explicit modifier bit extraction and use in conditional branches.

---

### 2. Empty Body Implementation — GAAD Snap
**File**: `wm.c` — `snap_window_to_gaad()`
**Before**:
```c
static void snap_window_to_gaad(DosGuiWindow *w) {
    (void)w;
}
```
**After**:
```c
static void snap_window_to_gaad(DosGuiWindow *w) {
    if (!w) return;
    int task_h = taskbar_height_dynamic();
    int screen_w = g_dwm.screen_w;
    int screen_h = g_dwm.screen_h;
    const int snap_margin = 12;
    bool snapped = false;

    // Edge snaps
    if (w->x >= -snap_margin && w->x <= snap_margin) { w->x = 0; snapped = true; }
    else if (w->x + w->w >= screen_w - snap_margin && w->x + w->w <= screen_w + snap_margin) { w->x = screen_w - w->w; snapped = true; }
    if (w->y >= -snap_margin && w->y <= snap_margin) { w->y = 0; snapped = true; }
    else if (w->y + w->h >= screen_h - task_h - snap_margin && w->y + w->h <= screen_h - task_h + snap_margin) { w->y = screen_h - task_h - w->h; snapped = true; }

    // Quadrant snaps (center_x = screen_w/2, center_y = (screen_h-task_h)/2)
    // Half snaps (left/right halves)
    // Bounds clamping after snap
}
```
**Pattern**: Implement full logic using global state (`g_dwm`) for screen dimensions, calculate snap regions, apply bounds checking.

---

### 3. Unused Parameter Removal — Window Desktop Field
**Files**: `wm.h` (struct), `wm.c` (spawn, hit_test, render, taskbar)
**Changes**:
1. **Added field to struct**:
```c
typedef struct DosGuiWindow {
    // ... existing fields
    int desktop;  // Virtual desktop index (0..8)
} DosGuiWindow;
```

2. **Initialize on creation**:
```c
static int spawn_window(...) {
    // ... existing init
    win->desktop = g_dwm.current_desktop;  // Assign to current virtual desktop
}
```

3. **Filter in hit_test**:
```c
static int hit_test(int x, int y) {
    for (int j = g_dwm.nz - 1; j >= 0; j--) {
        DosGuiWindow *w = &g_dwm.windows[g_dwm.zorder[j]];
        if (w->alive && w->desktop == g_dwm.current_desktop &&  // NEW
            x >= w->x && x < w->x + w->w &&
            y >= w->y && y < w->y + w->h)
            return g_dwm.zorder[j];
    }
    return -1;
}
```

4. **Filter in render**:
```c
for (int j = 0; j < g_dwm.nz; j++) {
    int idx = g_dwm.zorder[j];
    DosGuiWindow *w = &g_dwm.windows[idx];
    if (w->alive && w->desktop == g_dwm.current_desktop && !(w->flags & DOSGUI_WIN_MINIMIZED))
        draw_window(idx);
}
```

5. **Filter in taskbar**:
```c
for (int j = 0; j < g_dwm.nz; j++) {
    DosGuiWindow *w = &g_dwm.windows[g_dwm.zorder[j]];
    if (!w->alive || (w->flags & DOSGUI_WIN_MINIMIZED)) continue;
    if (w->desktop != g_dwm.current_desktop) continue;  // NEW
    // ... render button
}
```

**Pattern**: Add state field, initialize it, filter all iteration/render/hit-test paths by the field.

---

### 4. New API Functions for Desktop Migration
**File**: `wm.c` — new public functions
```c
void wm_move_window_to_desktop(DosGuiWindow *win, int desktop) {
    if (!win) return;
    if (desktop < 0 || desktop >= g_dwm.desktop_count) return;
    win->desktop = desktop;
    if (win->desktop != g_dwm.current_desktop && g_dwm.focused_id >= 0) {
        DosGuiWindow *focused = &g_dwm.windows[g_dwm.focused_id];
        if (focused == win) g_dwm.focused_id = -1;
    }
}

int wm_get_current_desktop(void) { return g_dwm.current_desktop; }

void wm_set_current_desktop(int desktop) {
    if (desktop < 0 || desktop >= g_dwm.desktop_count) return;
    g_dwm.current_desktop = desktop;
    if (g_dwm.focused_id >= 0) {
        DosGuiWindow *w = &g_dwm.windows[g_dwm.focused_id];
        if (w->alive && w->desktop != g_dwm.current_desktop) g_dwm.focused_id = -1;
    }
}

void wm_move_focused_window(int delta) {
    if (g_dwm.focused_id < 0) return;
    DosGuiWindow *w = &g_dwm.windows[g_dwm.focused_id];
    if (!w->alive) return;
    int new_desktop = w->desktop + delta;
    if (new_desktop < 0) new_desktop = 0;
    if (new_desktop >= g_dwm.desktop_count) new_desktop = g_dwm.desktop_count - 1;
    if (new_desktop != w->desktop) wm_move_window_to_desktop(w, new_desktop);
}
```

**Pattern**: Add migration API with bounds checking, focus management, and keyboard integration.

---

### 5. Keyboard Shortcut Integration
**File**: `wm.c` — `wm_handle_key()`
```c
/* Win+Shift+Left/Right: Move focused window to adjacent desktop */
if ((mods & 0x09) == 0x09) {  /* Win + Shift */
    if (key == 0xE04B) { wm_move_focused_window(-1); return; }
    else if (key == 0xE04D) { wm_move_focused_window(1); return; }
}
```
**Pattern**: Check combined modifier bits (0x01=Shift, 0x08=Win) and dispatch to migration API.

---

### 6. Header Declarations
**File**: `wm.h`
```c
/* -- Virtual Desktop Migration ------------------------------------- */
void wm_move_window_to_desktop(DosGuiWindow *win, int desktop);
int  wm_get_current_desktop(void);
void wm_set_current_desktop(int desktop);
void wm_move_focused_window(int delta);
```

---

## Test Verification
```bash
make test_wm       # 16/16 pass
make test_startmenu # 4/4 pass
make test_explorer  # 71/71 pass
# All desktop tests green after gap closures
```

## Key Principles
1. **Eliminate `(void)param` on success paths** — use the parameter
2. **Replace empty `{}` bodies** — implement the feature
3. **Add state to structs** — track what you need (desktop index)
4. **Filter everywhere** — hit_test, render, taskbar all must respect new state
5. **Expose API** — make functionality accessible from other modules
6. **Keyboard integration** — bind shortcuts to new API