---
name: wubuos-wayland-migration
category: systems-programming
description: WuBuOS Wayland migration - hosted binary as C11 Wayland client with xdg-shell
---

# WuBuOS Wayland Migration Skill

## When to Use

- Building, extending, or repairing the hosted binary's Wayland/xdg-shell
  client (`src/hosted/hosted_wayland*.c`, `wayland_state.h`).
- The hosted desktop is dropped by the compositor, shows a black surface, or
  fails to connect in a nested compositor (weston, Xephyr, cage).
- Adding a Wayland protocol use (a new global, a new surface role) and needing
  the version/ordering rules before calling into it.

## Overview
Migrated WuBuOS hosted binary from X11 to Wayland (Cell 200+). The hosted.c is now a C11 Wayland client using xdg-shell with SHM double-buffering.

## The Wayland client contract (never break these)

The hosted client is a C11 Wayland/xdg-shell client. Three rules are
load-bearing: breaking any of them makes the compositor abort the client
within seconds, and the client's own log shows only a bare
`Error sending request: Broken pipe`. See
`references/wayland-client-contract.md` for the triage recipe.

1. **Read the socket.** `wl_display_dispatch_pending()` dispatches events
   already in the local queue and NEVER reads. A frame loop that calls only
   that never sees the compositor's `configure`/`ping`/buffer `release`, so
   the xdg configure is never acked and the connection dies. Poll
   `wl_display_get_fd()` (zero timeout) and call `wl_display_dispatch()`
   when readable, then `wl_display_flush()`.
2. **Bind the version you use.** `wl_surface.damage_buffer()` exists only
   from wl_surface v5. Binding `wl_compositor` at v1 and then calling it is
   a protocol error. Bind `min(advertised, 5)` and fall back to
   `wl_surface_damage()` when `wl_surface_get_version() < 5`.
3. **Configure before the first buffer.** Attaching a buffer and committing
   before the compositor's initial `xdg_surface.configure` is acked is
   `xdg_surface has never been configured` (error 3). Record a `configured`
   flag when the configure arrives and gate the first attach on it.

## Rendering and presentation are separate concerns

The frame loop owns HOW the desktop is drawn: render into the VBE back
buffer, `vbe_swap()`, `damage`, `commit`. Whether a frame is handed to the
compositor at all is a different concern, and it must not live inside that
path.

Adding change-detection to the loop -- a shadow framebuffer plus a
`memcmp` sitting beside the commit -- intermixes the two. The render contract
stops being owned by one place, and the damage/commit bookkeeping drifts from
what the renderer actually produced. The visible result is a *performance*
change that comes out as broken rendering, which is how you know a policy was
placed in the wrong layer.

When a nested window repaints too often (on a laptop panel that reads as
flashing), the fix lives in the PRESENTATION layer, never in the render path.
The presentation module owns the buffers and owns the commit: it may compare
the buffer it is about to present against the last content it presented and
skip the attach/commit when nothing changed. That keeps one owner per
concern -- the renderer draws every frame unconditionally, the presenter
decides which frames the compositor sees.

Prefer, in order: another backend/renderer, or no nested window at all. If a
change check is needed, put it in the presentation function and keep it out
of the render loop.

## Key Changes

### Build System
- **Protocol generation**: Use `wayland-scanner` to generate:
  - `xdg-shell-client.header` (public API)
  - `xdg-shell-private.code` (private implementation, compile with `gcc -x c`)
- **Makefile changes**:
  - `-lX11` → `-lwayland-client -lxkbcommon`
  - Added `$(HOSTED)/xdg-shell-private.o` target
  - Hosted target links Wayland libraries

### Code Changes
- **hosted.c**: Rewritten as Wayland client (xdg-shell, SHM double-buffer)
- **Assembly files**: Use GAS (`gcc -c`), NOT nasm
- **Kernel symbols**: Wrapped with `#ifdef MYSEED_METAL`
- **Unicode cleanup**: 198 files had box-drawing chars in comments breaking compilation — mass replaced

### Testing
- All 31 test targets pass
- Hosted binary renders screenshot correctly
- Updated: `systems-programming` skill with Wayland section + `wayland-build-notes` reference

## Commands
```bash
# Generate protocol files
wayland-scanner client-header xdg-shell.xml xdg-shell-client.header
wayland-scanner private-code xdg-shell.xml xdg-shell-private.code
gcc -c -x c xdg-shell-private.code -o xdg-shell-private.o

# Build
make hosted

## New Features
- Added `--gui-screenshot` flag to hosted binary: captures full GUI mode render (vs `--screenshot` which is headless)
- Added `--theme` flag for runtime theme selection: `--theme zune|xp|xp-media|wubu|win98`
- Requires `wubu_theme_init()` called before `wm_init()` for proper themed colors
- Theme applied before `wm_init()` so window chrome uses correct colors

## Pitfalls
- `gcc -x c` required for `.code` file (not `.c`)
- xkbcommon needed for keyboard input
- SHM buffers need proper stride/format negotiation
- Kernel symbols must be split between metal/hosted modes
- **WSL2 Wayland issue**: WSL2 doesn't provide native Wayland compositor. Workaround: use Xvfb + weston:
  ```bash
  Xvfb :99 -screen 0 1024x768x24 &
  weston --backend=x11-backend.so --width=1024 --height=768 &
  WAYLAND_DISPLAY=wayland-1 ./src/hosted/wubu --gui-screenshot output.png
  ```
- **Never add a "present only when changed" policy to the render path or
  the run loop.** Rendering owns drawing; presentation owns the commit. A
  shadow buffer compared beside `wl_surface_commit()` inside the loop is a
  second rendering policy living in the wrong place -- it has to be reverted,
  not refined. The presentation function (`hosted_wl_frame_render`) is the
  correct home: it already owns the buffers, so remembering the last content
  it presented costs nothing and keeps the render path pure.
- **A single still cannot show flashing, and a downsampled diff hides it.**
  To tell a flashing screen from an animated one, capture several consecutive
  frames of the same window and diff them at FULL resolution, then look at the
  changed bounding box: an animated mascot or a clock is a small localized
  region; a window that repaints itself is the whole window; nothing at all
  means the window is already idle. Only then decide whether anything is
  actually wrong.
- **Verify a nested compositor with the CPU renderer.** With weston's default
  GL renderer the window LOOKS right but X11 readback (`xwd -id <window>`)
  returns solid black -- the content lives in a GL drawable the X server
  cannot read back. Run weston with `--renderer=pixman` when the point is to
  capture or show the window; the desktop is then readable by ordinary X11
  tools. A black capture is not evidence that the client rendered nothing.
- **A capture showing a lock prompt or another desktop means the window is
  occluded.** A full-screen window (a session lock screen) covers the target
  and can end up in a crop of the root window. Capture the target window by
  id (`xwd -id`) and check what is on top before concluding anything about
  the client.
- **The hosted binary's size flag is `-w W H` (two arguments); `-h` is
  HEADLESS mode.** Passing `-w 960 -h 540` parses the height as `atoi("-h")`
  = 0 and yields a 0-height surface (`Error marshalling request`,
  `mmap: Invalid argument`). This is what `src/hosted/wubu-weston.sh` and
  `make window SIZE=WxH` get right.

## Text Overlap Fixes (2026-06-23)
**Symptom**: Icon labels off-screen, clock overlaps window buttons, start menu items overflow, window button titles truncated
**Root Cause**: No bounds checking before `vbe_draw_text()`, no space reservation for clock/tray
**Fixes Applied** (in `wm.c`, `startmenu.c`):
- **Icon labels**: Bounds check `label_y + 8 <= fb_h`, ellipsis truncation with `DOSGUI_ICON_LABEL_H=16`
- **Taskbar clock**: Reserve space using `bx` (last button position) as boundary, position clock left of buttons
- **Start menu items**: Truncate with ellipsis, reserve space for arrow indicator
- **Window button titles**: Ellipsis truncation when `text_w > bw-16`, reserve `right_reserve` for clock+tray
- **Icon label bug fix**: Fixed uninitialized `truncated` variable in `vbe_text_width()` call (line 1297)
- All fixes use `vbe_text_width()` for bounds checking before `vbe_draw_text()`

## Zune Theme Support (2026-06-23)
**Feature**: Added THEME_ZUNE (id=4) with dark + orange accent palette
**Files**: `wubu_theme.c`, `wubu_theme.h`, `hosted.c`
- Zune theme: dark (#1A1A1A) background, orange accent (#E86C00), teal highlights
- Rounded buttons, gradient titles, orange accent on active elements
- CLI: `./src/hosted/wubu --theme zune --gui-screenshot output.ppm`
- Verification: 3,915 orange pixels + 29,459 dark gray pixels detected

### Wayland Clipboard + Primary Selection (2026-06-25)
**Feature**: Full clipboard (wl_data_device) and primary selection (zwp_primary_selection_unstable_v1) support
**Files**: `wubu_clipboard.c`, `wubu_clipboard.h`, `hosted.c`, `hosted.h`, `primary-selection-client.header`, `primary-selection-private.code`

### Wayland Callback Completion (2026-07-03) — UPDATED 2026-07-04
**Feature**: Completed all remaining ~30 Wayland void casts in hosted.c - xdg-shell callbacks, wl_data_device DnD, wl_touch, seat capabilities, wl xd tablet manager stubs
**Files**: `hosted.c`, `hosted.h`

**Implemented**:
- **xdg_popup listener**: `configure`, `popup_done`, `repositioned` callbacks for popup/menu support — stores geometry in `hosted_state_t` (`popup_x`, `popup_y`, `popup_width`, `popup_height`, `popup_mapped`)
- **xdg_toplevel**: `configure_bounds` and `wm_capabilities` handlers for window bounds and compositor capabilities — stores `max_width`, `max_height`, `wm_caps` bitmap
- **wl_data_device DnD**: Full drag-and-drop callbacks (`data_offer`, `enter`, `leave`, `motion`, `drop`, `selection`) with clipboard integration — reads MIME data via `pipe()` + `wl_data_offer_receive()`, tracks position in `dnd_x`/`dnd_y`
- **wl_touch**: Frame/cancel proper handling with multi-touch support via seat capabilities — touch → mouse conversion with coordinate tracking
- **Seat capabilities**: Touch listener enabled/disabled dynamically when `WL_SEAT_CAPABILITY_TOUCH` is advertised/removed
- **wl_output**: `geometry`, `mode`, `done`, `scale` events implemented with logging
- **Tablet manager**: Stubbed `tablet_tool`/`tablet_pad` handlers with logging (stable headers not in system)

**DnD Integration with Clipboard** (via `wubu_clipboard.c`):
- New API: `wubu_clipboard_handle_dnd_enter/leave/motion/drop()`
- Updated `ClipboardDnDCallback` signature: `(bool entered, int x, int y)`
- Wayland callbacks in hosted.c now call clipboard DnD handlers for full integration

**State Additions** (`hosted_state_t`):
- Popup: `popup_x`, `popup_y`, `popup_width`, `popup_height`, `popup_mapped`
- DnD: `dnd_offer`, `dnd_x`, `dnd_y`
- Toplevel: `max_width`, `max_height`, `wm_caps`
- Touch device: `touch` pointer

**Wayland State Additions** (`wayland_state_t`):
- `tablet_manager`, `output`, `touch`, `data_device`

**Pitfalls Encountered & Fixes**:
- **`zwp_tablet_manager_v1_interface` missing**: System headers lack tablet protocol — skip binding with comment, keep stub handlers
- **`wl_data_device_manager_listener` missing**: System headers lack listener type — remove listener registration, use runtime binding
- **`xdg_popup_listener` member names**: `.done` → `.popup_done` (per wayland-scanner generated header)
- **Forward declaration needed**: `seat_capabilities` must be declared before `wl_seat_listener` because `touch_listener` is defined later
- **`wl_output`/`wl_touch` destroy**: Add cleanup in `hosted_shutdown()` for new Wayland objects
- **Tablet manager destroy**: Remove `zwp_tablet_manager_v1_destroy()` call (protocol not available)

**Test Results**: `make test`, `make test_vsl`, `make test_high_gui` must pass. Run them for the live status; assertion totals grow as suites land — do not cite a fixed count.

### Protocol Integration
- **Clipboard (wl_data_device)**: Standard Wayland clipboard for Ctrl+C/V
- **Primary Selection (zwp_primary_selection_unstable_v1)**: X11-style highlight/middle-click selection
- **Generated from wayland-protocols**: Used wayland-scanner to generate client header + private code

### Key Implementation Details
- **wubu_clipboard.c**: Unified API with `#ifndef WUBU_CLIPBOARD_TEST_MODE` for testable logic
  - `wubu_clipboard_set_text()` / `wubu_clipboard_get_text()` - clipboard + primary
  - `wubu_clipboard_copy()` / `wubu_clipboard_paste()` - convenience helpers
  - `wubu_primary_copy()` / `wubu_primary_paste()` - primary selection helpers
  - Wayland read path: `pipe()` + `wl_data_offer_receive()` / `zwp_primary_selection_offer_v1_receive()`
  - Wayland write path: `wl_data_source` / `zwp_primary_selection_source_v1` with `send` listener

- **hosted.c**: Added primary selection device manager binding
  - `g_primary_selection_manager` global
  - `zwp_primary_selection_device_manager_v1` binding in `registry_global()`
  - `zwp_primary_selection_device_v1` from seat capabilities (KEYBOARD)
  - Cleanup in `hosted_shutdown()`

- **Test Infrastructure**: `make test_clipboard` compiles with `-DWUBU_CLIPBOARD_TEST_MODE`
  - 14 tests pass: set/get/clear, primary/clipboard, MIME, Unicode, large text
  - No Wayland connection required for logic tests

### Pitfalls
- `zwp_primary_selection_unstable_v1` requires `primary-selection-unstable-v1.xml` from wayland-protocols
- `wayland-scanner private-code` output must be compiled with `gcc -x c` (not `.c` extension)
- Interface symbols (`zwp_primary_selection_device_v1_interface`, etc.) only defined in `.code` file
- Test mode requires duplicating API surface with no-op Wayland calls
- Seat capability `WL_SEAT_CAPABILITY_KEYBOARD` triggers primary device creation (not POINTER)

### Commands
```bash
# Generate primary selection protocol files
wayland-scanner client-header primary-selection-unstable-v1.xml primary-selection-client.header
wayland-scanner private-code primary-selection-unstable-v1.xml primary-selection-private.code
gcc -c -x c primary-selection-private.code -o primary-selection-private.o

# Test clipboard logic (no Wayland compositor needed)
make test_clipboard
```