# Phase 2: GNOME-Standard Desktop Services (Complete)

## Settings Daemon (Item 1)
- XDG Base Directory config at `~/.config/wubu/settings.conf`
- 7 categories: Theme, Fonts, Keyboard, Mouse, Display, A11y, Privacy
- Minimal JSON parser/writer (no external deps), live apply

## Session Manager (Item 2)
- Auto-start from `~/.config/wubu/autostart/` (`.desktop`-like JSON)
- Session save/restore at `~/.local/state/wubu/session.json`
- Shutdown dialog (Logout/Shutdown/Restart/Suspend/Hibernate)
- Idle inhibition + power management sysfs checks

## Notification Daemon (Item 3)
- Desktop Notifications Spec (summary, body, icon, urgency, timeout, actions, hints)
- Slide-in/out animations, history (100 items), keyboard dismiss (Escape)
- Convenience API: `wubu_notify_simple()`, `wubu_notify_progress()`, `wubu_notify_system()`

## Clipboard Manager (Item 4)
- Wayland data device manager + primary selection
- Sync API: `wubu_clipboard_copy/paste()`, `wubu_primary_copy/paste()`
- Change callbacks, DND enter/leave tracking

## Screenshot Tool (Item 5)
- PrintScr (full), Alt+PrintScr (window), Shift+PrintScr (region drag)
- PNG save with bundled writer (no libpng), auto-save to `~/Pictures/WuBuOS/`
- Annotations: rect, ellipse, arrow, freehand, highlight, text
- Region selector overlay with dimming + border
- Clipboard integration placeholder

## MIME System (Item 6)
- .desktop file parser (simplified FreeDesktop spec)
- XDG directory scanning (`~/.local/share/applications`, `XDG_DATA_DIRS`)
- 30+ built-in MIME types, file associations, default apps
- Launch API with `%f`/`%u` placeholder substitution
- 8 default handlers (text-editor, code-editor, image-viewer, audio/video-player, pdf-viewer, archive-manager, container-runner)

## Trash Implementation (Item 7)
- FreeDesktop Trash spec: `~/.local/share/Trash/files/`, `info/`
- Move with unique name conflict resolution, restore individual/all
- Size limit enforcement with oldest-first eviction
- Auto-expire by age (configurable days)
- `.trashinfo` format (DeletionDate ISO 8601, Path)

## Phase 3: Proton/Wine Integration (Item 1)

### Wine Prefix Management
- Per-game prefixes at `~/.local/share/wubu/proton/prefixes/<id>/`
- Create/remove/set-default, config persistence (JSON)
- ESYNC/FSYNC enabled, DXVK_ASYNC, DLL overrides preset

### Steam Detection & Library Scanning
- Detects Steam at `~/.steam/steam`, `~/.local/share/Steam`, flatpak
- Parses `libraryfolders.vdf` and `appmanifest_*.acf` for game metadata
- Auto-populates game list with install paths, exe detection

### Proton-GE / DXVK / VKD3D
- Proton-GE auto-detect at `/usr/share/proton-ge`, version query
- DXVK/VKD3D install via winetricks, detection via `d3d11.dll`/`d3d12.dll`
- Steam compat env: `STEAM_COMPAT_DATA_PATH`, `PROTON_PATH`

### Wine Execution via Bubblewrap
- GPU passthrough: `/dev/dri` bind-mount
- Wine prefix bind-mount, game directory ro-bind
- Env vars: `WINEPREFIX`, `WINEDLLOVERRIDES`, `WINEESYNC`, `WINEFSYNC`, `DXVK_ASYNC`
- Wrappers: `winecmd`, `regedit`, `winetricks`

### Config Persistence
JSON at `~/.local/share/wubu/proton/config.json`

## Phase 2/3 Makefile Integration Pattern
```
1. Add to GUI_OBJS and HOSTED_OBJS
2. Add source to hosted build command
3. Add to test_hosted command with -lm for math
4. Add dedicated test_<module> target
5. Run all tests: make test_hosted test_bridge test_wm test_startmenu test_mime test_trash test_proton
```