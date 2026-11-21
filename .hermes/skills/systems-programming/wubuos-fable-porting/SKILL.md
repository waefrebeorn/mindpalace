---
name: wubuos-fable-porting
category: systems-programming
description: Port Mythos Fable bare-metal kernel features into WuBuOS as windowing agent
---

# WuBuOS Fable Windowing Agent Port

## Overview
Ported Mythos Fable repo (`/home/wubu/mythos-fable/`) into WuBuOS as a windowing agent (Cell 400-402). Fable = windowing agent (NOT guest container) — ports ZealOS bare-metal features into hosted Arch desktop.

## Ported Components

### vbe.c additions
- **64-glyph 8x8 font** — Fable's built-in font
- **VBE primitives** — gradient, circle, shade, clip operations
- **Window chrome** — title bar, close box, cursor drawing

### wm.c (Cell 400+)
- Full window manager: drag, z-order, focus, taskbar, icons
- **HolyC Terminal window type** (HolycTerm) with persistent HCCompiler
  - Per-window HolyC compiler state (symbols, history, line buffer)
  - Command history with ↑/↓ navigation
  - Blinking cursor, syntax highlighting ($ prompt)
  - `wm_spawn_holyc_term(x, y, w, h)` API
- **System Tray / Notification Area** (Phase 4.1 - Cell 480+)
  - `DosGuiSysTrayIcon` struct (name, color, visibility, on_click/on_right_click callbacks, notification badge count)
  - `systray_add/remove/set_notification_count()` API
  - Draws icons in taskbar with 3D raised bevel, notification badges
- **Notification Center** (Phase 4.1 - Cell 480+)
  - `DosGuiNotification` struct (id, app_name, summary, body, timestamp, urgency, read flag)
  - `notif_center_add/mark_read/clear/toggle/render()` API
  - Sliding panel on right side (350px wide, full height above taskbar)
  - Color-coded urgency: red=critical, yellow=normal, green=low
  - Auto-marks read when opened; badge count on "Notifications" systray icon
  - Integrates with `wubu_notify` daemon
- **Real Taskbar Clock** (Phase 4.1)
  - `taskbar_get_clock_str()` returns `HH:MM` format from `time(NULL)` + `localtime()`
  - Replaces uptime counter with real system clock
  - Updates on each render frame
- **Mouse Handling for Tray/Notifications** (Phase 4.1)
  - Left-click systray icons → triggers `on_click` callback
  - Right-click systray icons → triggers `on_right_click` callback
  - Click notification center toggle area → opens/closes panel
  - Click notification in panel → marks as read

### Desktop Icons & Context Menus (Phase 4.2 - Cell 401+)
- **Enhanced Icon Types** — `DeskIconType` enum: APP, SHORTCUT, FOLDER, DRIVE, FILE, URL with `target`, `icon_path`, `icon_color`, `on_execute`
- **Context Menu System** — `DosGuiContextMenu` + `DosGuiCtxItem` (action/separator/submenu) with hover highlighting, keyboard navigation, submenu support
- **Default Context Menus** — Icon right-click: Open/Rename/Delete/Properties; Desktop right-click: New→Shortcut/Folder/Text Document, View→Sort By, Refresh/Properties
- **Shortcut Creation** — `shortcut_create()` (green icon) + `shortcut_create_url()` (orange icon) with target path/URL
- **Icon Management API** — `icon_add_ex()`, `icon_remove()`, `icon_find_at()`, `icon_set_position()` with grid collision detection
- **Mouse Integration** — Right-click on icon → context menu; right-click empty desktop → desktop context menu; click outside → dismiss
- **Submenu Support** — Hover over submenu item → opens to the right; click action → executes and closes all menus
- 16/16 tests green

### Start Menu Enhancements (Phase 4.3 - Cell 402+)
- **Search Bar** — Real-time filtering (case-insensitive substring match), search bar UI at top of menu with blinking cursor, Tab to toggle, Enter to launch first result, Escape to clear
- **Recently Used Programs** — Automatic tracking via `startmenu_recent_add()`, MRU list up to 10 items with timestamps and run counts
- **Power Options** — Extended shutdown menu: Shut Down, Restart, Log Off, Sleep, Hibernate rendered as themed buttons in sidebar/bottom
- **All Programs Tree** — Hierarchical Auto-built from program database: Accessories/WuBuOS/System with programs as leaves, expand/collapse folders, recursive rendering with indentation
- **Enhanced Input Handling** — Tab toggles search mode, Enter launches first result, Escape clears/closes, Backspace deletes, printable keys append to query
- **Program Database** — 16 built-in entries across Accessories (Notepad, Paint, Editor, WuBu Canvas, FreeDoom), WuBuOS (HolyC Terminal, Temple REPL, Package Manager, Container Manager, File Manager, Settings), System (Terminal, Calculator) with category metadata
- **Tree Rendering** — Recursive descent with indentation, folder expansion state, program leaf nodes showing executable names

### Desktop & StartMenu
- `desktop.c` — desktop with icons (including "HolyC Term" icon)
- `startmenu.c` — Win98-style start menu (WuBuOS → HolyC Terminal)
- Both integrate with wm

### HolyC Terminal App Integration
- `src/apps/apps.h/c` — `launch_holyc_term()` handler
- Registers with desktop icon and Start Menu

## Build Integration

### Makefile additions
```makefile
GUI_OBJS += $(GUI)/wm.o $(GUI)/desktop.o $(GUI)/startmenu.o
HOSTED_OBJS += $(GUI)/wm.o $(GUI)/desktop.o $(GUI)/startmenu.o
```

### Test targets
```makefile
test_wm: -DVBE_HOSTED
test_startmenu: -DVBE_HOSTED
test_holyc_terminal:  # HolycTerm drag/click/input + HolyC eval (73 tests)
test_holyc_ptx:       # PTX emission + nvptx validation (31 tests)
```

## Key Insight
Fable is a **windowing agent** that runs in the WuBuOS host process, not a guest container. It brings ZealOS bare-metal VBE/windowing features to the hosted Arch desktop environment. **HolyC terminal is now a first-class draggable window** with persistent compiler state per instance.

## Common Pitfalls & Fixes

### RGB Macro Bug (wubu_theme.c)
**Symptom**: All colors in screenshots are wrong (e.g., teal icons appear yellow, gray taskbar appears yellow)
**Root Cause**: `RGB(r,g,b)` macro was defined as BGR format: `(b<<16 | g<<8 | r)` instead of RGB: `(r<<16 | g<<8 | b)`
**Fix**: Change macro to `#define RGB(r,g,b) ((uint32_t)((r)<<16 | (g)<<8 | (b)))`
**File**: `src/gui/wubu_theme.c:12`

### Missing Theme Initialization
**Symptom**: Desktop renders but all colors are default/uninitialized (icons yellow, taskbar gray instead of themed colors)
**Root Cause**: `wubu_theme_init()` not called before `wm_init()`
**Fix**: Add `wubu_theme_init();` before GUI initialization in `hosted.c`
**File**: `src/hosted/hosted.c:745`

### Missing vbe_swap() in Demo Recorder
**Symptom**: Demo recorder produces black/empty frames
**Root Cause**: `desktop_render()` writes to back buffer but `vbe_swap()` not called to copy to front buffer
**Fix**: Add `vbe_swap();` after `desktop_render()` in `src/tools/wubu_demo_record.c:118`

### X11/Wayland Setup for WSL2
**Environment**: WSL2 lacks native Wayland compositor
**Fix**: Use Xvfb + weston:
```bash
Xvfb :99 -screen 0 1024x768x24 &
weston --backend=x11-backend.so --width=1024 --height=768 &
WAYLAND_DISPLAY=wayland-1 ./src/hosted/wubu --gui-screenshot output.png
```

### Text Overlap in Window Rendering (2026-06-23)
**Symptom**: Icon labels off-screen, taskbar clock overlaps window buttons, start menu items overflow, window button titles truncated
**Root Cause**: No bounds checking before `vbe_draw_text()`, no space reservation for clock/tray
**Fixes Applied** (in `wm.c`, `startmenu.c`):
- **Icon labels**: Bounds check `label_y + 8 <= fb_h`, ellipsis truncation with `DOSGUI_ICON_LABEL_H=16`
- **Taskbar clock**: Reserve space using `bx` (last button position) as boundary, position clock left of buttons
- **Start menu items**: Truncate with ellipsis, reserve space for arrow indicator
- **Window button titles**: Ellipsis truncation when `text_w > bw-16`, reserve `right_reserve` for clock+tray
- **Icon label bug fix**: Fixed uninitialized `truncated` variable in `vbe_text_width()` call (line 1297)
- All fixes use `vbe_text_width()` for bounds checking before `vbe_draw_text()`

### Zune Theme Support (2026-06-23)
**Feature**: Added THEME_ZUNE (id=4) with dark + orange accent palette
**Files**: `wubu_theme.c`, `wubu_theme.h`, `hosted.c`
- Zune theme: dark (#1A1A1A) background, orange accent (#E86C00), teal highlights
- Rounded buttons, gradient titles, orange accent on active elements
- CLI: `./src/hosted/wubu --theme zune --gui-screenshot output.ppm`
- Verification: 3,915 orange pixels + 29,459 dark gray pixels detected

## Testing
```bash
make test_wm
make test_startmenu
make test_holyc_terminal
make test_holyc_ptx
# All tests pass (73 + 31 = 104 tests)
```

## Phase 4 Tests
```bash
make test_wm       # WM + icons + context menus + systray + notifications
make test_startmenu_enhanced  # Search + recent + tree + power options
```

## Phase 5: Desktop Polish & GAAD Snap (2026-06-28)

### GAAD Snap Regions (Grid Aligned Application Design)
**File**: `src/gui/wm.c` — `snap_window_to_gaad()`
- **Trigger**: Applied on window drag end (`kind == 2` mouse up)
- **Snap targets** (12px margin):
  - Screen edges: left (0), right (screen_w), top (0), bottom (screen_h - task_h)
  - Quadrants: top-left, top-right, bottom-left, bottom-right (quarter screen)
  - Halves: left half, right half (vertical split)
- **Behavior**: Window position/size snapped to nearest grid region; bounds clamped after snap
- **Integration**: Called from `wm_handle_mouse()` on drag end

### Virtual Desktop Migration
**File**: `src/gui/wm.c` + `src/gui/wm.h`
- **Window struct**: Added `int desktop` field to `DosGuiWindow` (0..8)
- **Filtering by current desktop** in:
  - `hit_test()` — only hit-test windows on current desktop
  - `wm_render_desktop()` — only render windows on current desktop
  - `taskbar_render()` — only show taskbar buttons for current desktop
- **New API functions**:
  - `wm_move_window_to_desktop(win, desktop)` — move specific window
  - `wm_get_current_desktop()` / `wm_set_current_desktop()` — desktop navigation
  - `wm_move_focused_window(delta)` — move focused window to adjacent desktop
- **Keyboard shortcuts**: `Win+Shift+Left/Right` — migrate focused window between desktops

### HolyC Terminal Modifier Key Support
**File**: `src/gui/wm.c` — `holyc_term_key()`
- **Removed** `(void)mods` cast; now uses modifiers:
  - `Ctrl+C` — clear input line (`^C` echoed)
  - `Ctrl+L` — clear screen/history buffer
  - `Ctrl+U` — delete current input line
  - `Shift+Right` — tab-complete from history (fills rest of line from history entry)
  - `Up/Down` — history navigation (existing)
- **Per-window persistent state**: Each HolyC terminal maintains its own `HolycTerm` with compiler, history, line buffer

### Taskbar Window Filtering
- Taskbar now only shows buttons for windows on the current virtual desktop
- Focused window tracking respects desktop boundaries
- Desktop switch via `Ctrl+Alt+Left/Right` updates focus correctly

## Testing
```bash
make test_wm       # 16/16 pass (includes GAAD snap + virtual desktop)
make test_startmenu # 4/4 pass
make test_explorer  # 71/71 pass
make test_holyc_terminal   # HolyC terminal with modifier keys
# All desktop tests green
```