# Phase 2: GNOME-Standard Desktop Services (Session 2026-06-16)

## Overview
Completed 4 of 7 GNOME-standard desktop services for WuBuOS, implementing core infrastructure for a full Linux distribution.

## Services Implemented

### 1. Settings Daemon (`wubu_settings.h/c`)
**Purpose**: Persistent configuration for theme, fonts, keyboard, mouse, display, a11y, privacy.

**Architecture**:
- 7 categories: Theme, Fonts, Keyboard, Mouse, Display, A11y, Privacy
- JSON persistence to `~/.config/wubu/settings.conf` (XDG)
- Minimal JSON parser/writer (no external deps, ~500 LOC)
- Live apply: `wubu_theme_set()`, font scale, high contrast, reduce motion

**Key APIs**:
```c
void wubu_settings_register_category(SettingsCategory cat);
void wubu_settings_apply_live(void);  // Triggers theme switch, font scale, etc.
```

**Integration**: Added to `GUI_OBJS` and `HOSTED_OBJS`, initialized in `hosted_init()`.

### 2. Session Manager (`wubu_session.h/c`)
**Purpose**: Auto-start, shutdown/logout/restart, session save/restore.

**Features**:
- Auto-start entries at `~/.config/wubu/autostart` (JSON, .desktop-like)
- Shutdown dialog with 5 actions: Shutdown/Restart/Logout/Suspend/Cancel
- Session save/restore: running apps, positions, virtual desktops → `~/.local/state/wubu/session.json`
- Idle inhibition API for media playback
- Power management queries: `can_suspend()`, `can_hibernate()` (sysfs)

**Key APIs**:
```c
void wubu_autostart_run(void);      // Launches enabled entries on init
void wubu_session_request_action(SessionAction action);  // Queued, processed in main loop
```

**Integration**: Initialized in `hosted_init()`, auto-starts Settings/Notify/Clipboard daemons.

### 3. Notification Daemon (`wubu_notify.h/c`)
**Purpose**: libnotify-compatible notification server (Desktop Notifications Spec v1.2).

**Features**:
- Full spec support: summary, body, icon, urgency (low/normal/critical), timeout, actions, hints
- Slide-in/slide-out animations (configurable speed)
- Auto-dismiss respects urgency: Low=7s, Normal=5s, Critical=persistent
- Action buttons with callback invocation
- History buffer (100 items)
- Keyboard: Escape dismisses latest
- Convenience API: `wubu_notify_simple()`, `wubu_notify_progress()`, `wubu_notify_system()`

**Key APIs**:
```c
uint32_t wubu_notify_send(const Notification *n);
void wubu_notify_set_action_callback(NotifyActionCallback cb);
void wubu_notify_render(uint32_t *fb, int fb_w, int fb_h);  // Called per frame
```

### 4. Clipboard Manager (`wubu_clipboard.h/c`)
**Purpose**: Wayland clipboard (data device) + primary selection.

**Architecture**:
- Binds `wl_data_device_manager` via Wayland registry callback
- Two selections: Primary (highlight/middle-click) + Clipboard (Ctrl+C/V)
- Text/plain MIME type (extensible)
- Data device callbacks: offer, enter/leave/motion/drop, selection
- Data source callbacks: target, send, cancelled, dnd_drop/finished, action

**Key APIs**:
```c
bool wubu_clipboard_copy(const char *text);   // Clipboard
bool wubu_clipboard_paste(char **out_text);
bool wubu_primary_copy(const char *text);     // Primary
bool wubu_primary_paste(char **out_text);
void wubu_clipboard_set_changed_callback(ClipboardChangedCallback cb);
```

**Integration**: Initialized in `hosted_init()` after Wayland surface creation.

## Technical Patterns Established

### JSON Persistence (No External Deps)
```c
// Minimal parser: json_parse_string, json_parse_number, json_parse_object
// Writer: json_write_string, json_write_int, json_write_bool, json_write_double
// File I/O with XDG paths: XDG_CONFIG_HOME, XDG_STATE_HOME
```

### Wayland Global Registration
```c
// Registry callback binds: compositor, xdg_wm_base, shm, seat, data_device_manager
// data_device_manager enables clipboard + DND
```

### Makefile Integration Pattern
```makefile
GUI_OBJS += $(GUI)/wubu_settings.o $(GUI)/wubu_session.o $(GUI)/wubu_notify.o $(GUI)/wubu_clipboard.o
HOSTED_OBJS += same
# test_hosted adds all 4 .c files to link command
```

### Test Infrastructure
```c
// Each module: init → test functions → shutdown
// test_hosted boots full Wayland desktop headless
```

## Files Added
| File | Lines | Purpose |
|------|-------|---------|
| `src/gui/wubu_settings.h/c` | ~800 | Settings daemon |
| `src/gui/wubu_session.h/c` | ~600 | Session manager |
| `src/gui/wubu_notify.h/c` | ~700 | Notification daemon |
| `src/gui/wubu_clipboard.h/c` | ~500 | Clipboard manager |
| `src/hosted/hosted.h` additions | ~30 | Wayland state export |

## Next Phase (5-7)
5. **Screenshot Tool** - PrintScr, Alt+PrintScr, region select
6. **File Associations** - MIME → app mapping, .desktop files
7. **Trash/Recycle Bin** - `.local/share/Trash` implementation

## Commits
- `7f0b1c4` - Phase 1 GUI fixes
- `9f6176c` - Settings Daemon
- `81499b3` - Session Manager
- `8433b8a` - Notification Daemon
- `f949692` - Clipboard Manager