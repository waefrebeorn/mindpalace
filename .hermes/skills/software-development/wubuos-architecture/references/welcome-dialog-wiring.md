# Welcome Dialog Wiring — First-Run UX Pattern

**Date:** 2026-07-07  
**Files:** `src/gui/wubu_welcome.h`, `src/gui/wubu_welcome.c`  
**Wired in:** `src/hosted/hosted.c` (hosted_init, after startmenu_init)

## Overview

The welcome dialog is a one-shot modal window that displays keyboard shortcuts
and a brief project description on first boot. It creates a marker file at
`~/.config/wubu/first-run-done` so it only shows once per machine.

## File Layout

```
src/gui/
├── wubu_welcome.h    # Public API: wubu_welcome_init, is_dismissed, dismiss
├── wubu_welcome.c    # Implementation: marker file, modal window, draw callback
```

## Implementation Details

### Marker File (file-based, no JSON)

```c
static const char *marker_path(void) {
    // Resolves to ~/.config/wubu/first-run-done
    // Fallback: /tmp/wubu-first-run-done when $HOME unset
}

bool wubu_welcome_is_dismissed(void) {
    return access(marker_path(), F_OK) == 0;
}

void wubu_welcome_dismiss(void) {
    // Creates the config directory, writes a marker file
    mkdir(dir, 0755);  // best-effort
    fprintf(f, "WuBuOS first-run welcome acknowledged\n");
}
```

### Draw Callback

The `welcome_on_draw` callback renders the welcome content **at absolute screen
coordinates** computed from `win->x + offset`:

```c
static void welcome_on_draw(DosGuiWindow *win, uint32_t *fb, int cw, int ch) {
    int x0 = win->x + 4;   // border offset
    int y0 = win->y + 4;
    int y = y0 + 8;

    vbe_draw_text(x0 + 10, y, "Welcome to WuBuOS!", highlight);
    // ... shortcuts table ...
    vbe_draw_text(x0 + 10, y, "Ctrl+T = cycle themes", 0x005050);
}
```

**Key pitfall**: `vbe_draw_text()` draws at absolute VBE framebuffer coordinates,
NOT relative to the window's client area. The `fw`/`fh` parameters from the
callback are the full framebuffer dimensions, not the client rect.

### Modal Window Properties

- Size: 480×330
- Position: centered horizontally, 1/3rd from top
- **Not closable via X button** — informational only, dismissed on any click
- Created with `wm_create_modal()` for proper z-ordering

## Call Site (hosted.c)

```c
// In hosted_init(), after UI init:
startmenu_init();
/* First-run welcome dialog (shown once, creates marker file) */
wubu_welcome_init();
/* Launch initial windows */
launch_app("My Computer");
```

## Makefile Changes Required

See `references/makefile-triple-place-pattern.md` — adding `wubu_welcome.c`
required edits to GUI_OBJS, hosted recipe, and HOSTED_OBJS. No test-target
changes because welcome is only called from hosted.c.

## Verification

```bash
# Force first-run (delete marker):
rm -f ~/.config/wubu/first-run-done

# Run (headless, will show dialog briefly):
./src/hosted/wubu --screenshot /tmp/test.ppm

# Check marker was created:
cat ~/.config/wubu/first-run-done
# Expected: "WuBuOS first-run welcome acknowledged"
```