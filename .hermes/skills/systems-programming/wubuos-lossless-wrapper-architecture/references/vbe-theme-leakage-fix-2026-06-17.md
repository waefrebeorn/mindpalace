# VBE Theme Leakage Fix — 2026-06-17

## Problem
Two parallel GUI systems compiled and linked together ("VBE theme leakage"):
- **Legacy** (`wm.c`, `startmenu.c`, `taskbar.c`, `desktop.c`, `theme.c`) — hardcoded Win98 colors via VBE
- **New** (`wubu_wm.c`, `wm.c`, `desktop.c`, `startmenu.c`, `wubu_theme.c`) — runtime-switchable theme engine

Both were in `GUI_OBJS` and `HOSTED_OBJS`, causing symbol conflicts and dual theme systems.

---

## Solution

### 1. Removed Legacy GUI from Build
**Makefile changes:**
```makefile
# Before
GUI_OBJS = ... $(GUI)/wm.o $(GUI)/taskbar.o $(GUI)/desktop.o $(GUI)/theme.o ...
HOSTED_OBJS = ... $(GUI)/wm.o $(GUI)/taskbar.o $(GUI)/desktop.o $(GUI)/theme.o ...

# After
GUI_OBJS = $(GUI)/gui_dbuf.o $(GUI)/wubu_theme.o ... $(GUI)/wm.o $(GUI)/desktop.o $(GUI)/startmenu.o
HOSTED_OBJS = ... $(GUI)/gui_dbuf.o $(GUI)/wubu_theme.o $(GUI)/wm.o $(GUI)/desktop.o $(GUI)/startmenu.o ...
```

### 2. Updated REPL to Use DosGuiWM API
**`src/apps/repl.c`:**
```c
// Before: wm_create_window() + wm.h
// After:
#include "../gui/wm.h"
DosGuiWindow *win = wm_create(100, 100, 400, 400, "HolyC REPL");
win->on_draw  = repl_draw;
win->on_key   = repl_handle_key;
```

### 3. Added Per-Window Input Callbacks to DosGuiWM
**`src/gui/wm.h`:**
```c
typedef struct DosGuiWindow {
    ...
    void (*on_key)(DosGuiWindow *win, uint32_t key, uint32_t mods);
    void (*on_mouse)(DosGuiWindow *win, int x, int y, int btn, int kind);
} DosGuiWindow;
```

**`src/gui/wm.c`:**
```c
void wm_handle_key(uint32_t key, uint32_t mods) {
    // Dispatch to focused window first
    if (g_dwm.focused_id >= 0) {
        DosGuiWindow *w = &g_dwm.windows[g_dwm.focused_id];
        if (w->alive && w->on_key) {
            w->on_key(w, key, mods);
            return;
        }
    }
    // Global hotkeys...
}

void wm_handle_mouse(...) {
    // Dispatch to focused window on mouse move/click
    if (g_dwm.focused_id >= 0 && kind == 0) {
        if (w->alive && w->on_mouse) w->on_mouse(w, x - w->x, y - w->y, btn, kind);
    }
}
```

### 4. Created Test Stubs
**`src/gui/wm_test_stub.c`** — stubs `launch_app`, `shutdown`, `startmenu_toggle`
**`src/gui/startmenu_test_stub.c`** — stubs `taskbar_height`, `wm_screen_h`, `launch_app`, `shutdown`

### 5. Updated Test Targets
```makefile
test_wm:
	$(CC) ... $(GUI)/wm.c $(GUI)/wubu_theme.c $(GUI)/wm_test_stub.c ... 

test_startmenu:
	$(CC) ... $(GUI)/startmenu.c $(GUI)/wubu_theme.c $(GUI)/startmenu_test_stub.c ...
```

---

## Results

### Tests Passing (747+)
- Core: JIT, memory, tasking, input, HolyC, Styx, double-buffer
- GUI: `test_wm` (16/16), `test_startmenu` (4/4)
- Syscall: `test_syscall` (5/5)
- Bridge: `test_bridge_flip` (13/13)

### Theme Engine (`wubu_theme.c`)
Runtime-switchable with 4 themes:
- Win98 Classic (teal/silver/navy)
- XP Luna Blue (Bliss blue/green Start)
- XP Media Orange/Black (dark/orange)
- WuBu Green (custom dark green)

### Real Apps Working
- **`calc.c`** — Calculator with Standard/Scientific/Programmer modes
- **`terminal.c`** — PTY terminal with tabs, scrollback, HolyC REPL toggle (Ctrl+Alt+T)
- **`repl.c`** — HolyC REPL window (updated to DosGuiWM API)

---

## Key Insight
> **Only one GUI system should own VBE** — the new theme-aware DosGuiWM. Legacy code paths removed from build entirely.