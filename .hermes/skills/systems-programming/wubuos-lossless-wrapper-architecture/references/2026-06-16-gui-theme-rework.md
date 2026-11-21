# 2026-06-16 — Win98 → XP Classic Themed Desktop Complete Rework

## Session Summary
Complete rework of WuBuOS DosGui Desktop (Cells 400-412) from Win98 hardcoded colors to full runtime theme engine with 4 switchable themes (Win98 Classic, XP Luna Blue, XP Media Orange, WuBu Green).

## Files Modified

### Core Theme Engine
- `src/gui/wubu_theme.c` / `wubu_theme.h` — 4 predefined themes + runtime cycling

### DosGui Window Manager (Cell 400)
- `src/gui/wm.c` — Complete rewrite:
  - Uses `wubu_theme_colors()` and `wubu_theme_get()` for all rendering
  - XP gradient titles + rounded chrome (radius=4) on XP themes
  - Win98 flat titles + square 3D chrome on Win98 theme
  - Luna Start orb (green "Start" text) on XP themes
  - Maximize/Minimize/Close buttons (full implementation)
  - Icon drag-drop with grid snap on release
  - Virtual desktops (9) with GAAD φ-snap
  - Wayland resize handling (SHM destroy/recreate + VBE/WM reinit)
  - Wallpaper support (center/tile/stretch modes)

### DosGui StartMenu (Cell 402)
- `src/gui/startmenu.c` — Complete rewrite:
  - XP sidebar with "WuBuOS" branding + Log off/Turn Off
  - Luna Start orb button
  - Cascading submenus: Programs → {Accessories, WuBuOS, System}
  - Hover tracking → auto-expand submenus
  - Keyboard navigation (arrows, Enter, Esc)
  - Shutdown submenu (Shutdown/Restart/Logoff/MS-DOS)

### DosGui Desktop (Cell 401)
- `src/gui/desktop.c` — Uses theme colors for desktop_bg, icon text

### VBE Layer
- `src/kernel/vbe.h` / `vbe.c` — New primitives:
  - `vbe_fill_rect_rounded`, `vbe_rect_rounded`, `vbe_3d_raised_rounded`, `vbe_3d_sunken_rounded`
  - Integer quadrant approximation (no libm)

### Hosted Binary
- `src/hosted/hosted.c` — Wayland resize handling, Ctrl+T theme cycling, hover tracking

## Theme Specifications

| Theme | Desktop | Window Face | Title Active | Title Inactive | Start Button | Window Chrome |
|-------|---------|-------------|--------------|----------------|--------------|---------------|
| Win98 Classic | 0x008080 (teal) | 0xC0C0C0 | 0x000080 | 0x808080 | "+ NEW", square 3D | Square, 3D raised/sunken |
| XP Luna Blue | 0x00528A (Bliss) | 0xE8E8E8 | 0x00539E→0x0099CC | 0xB0B0B0→0xD8D8D8 | Green orb "Start" | Rounded r=4, gradient |
| XP Media Orange | 0x1A1A1A (near-black) | 0x2A2A2A | 0xE86C00→0xFF9933 | 0x4A4A4A→0x3A3A3A | Orange orb | Rounded r=4, gradient |
| WuBu Green | 0x0A2A1A (dark green) | 0x1A3A2A | 0x008050→0x00C080 | 0x2A3A30→0x1A2A1A | Green orb | Rounded r=4, gradient |

## Keyboard Shortcuts
- **Ctrl+T** / **F5**: Cycle theme
- **F11**: Toggle fullscreen/maximize on focused window
- **Win Key**: Toggle Start menu
- **Esc**: Close focused window
- **Ctrl+Alt+Left/Right**: Switch virtual desktop
- **Start Menu**: Arrow keys navigate, Enter launches, Esc closes

## New VBE Primitives (Zero libm)

```c
// vbe.h declarations
void vbe_fill_rect_rounded(int x, int y, int w, int h, int radius, uint32_t color);
void vbe_rect_rounded(int x, int y, int w, int h, int radius, uint32_t color);
void vbe_3d_raised_rounded(int x, int y, int w, int h, int radius);
void vbe_3d_sunken_rounded(int x, int y, int w, int h, int radius);

// Implementation uses 45° integer quadrant approximation
// |dx| = r, |dy| = r at 45°, interpolated for intermediate angles
// No cos/sin, no libm dependency
```

## Wayland Resize Handling

```c
static void xdg_toplevel_configure(void *data, struct xdg_toplevel *toplevel,
                                   int32_t width, int32_t height, ...) {
    if (width <= 0 || height <= 0) return;
    if (vs->width != width || vs->height != height) {
        // 1. Destroy all SHM buffers
        for (int i = 0; i < SHM_BUFFERS; i++) shm_buffer_destroy(&g_shm_bufs[i]);
        // 2. Reinit VBE with new dimensions
        vbe_shutdown(); vbe_init(width, height);
        // 3. Reinit WM + Desktop
        wm_init(width, height);
        // 4. Recreate SHM buffers
        shm_buffer_create(&g_shm_bufs[0], width, height);
        shm_buffer_create(&g_shm_bufs[1], width, height);
        // 5. Realloc host framebuffer
        state->framebuffer = realloc(state->framebuffer, width * height * 4);
    }
}
```

## Demo Output
- `make hosted` → 720KB binary builds clean
- `make test_wm` → 16/16 tests pass
- `./src/hosted/wubu -h` → Headless mode: kernel + GUI + Styx init OK
- Demo capture → 100 frames → 11.9MB GIF / 100KB MP4

## Verification Commands
```bash
cd ~/.hermes/profiles/mind-palace/home/myseed
make hosted                # 720KB binary
make test_wm        # 16/16 tests
./src/hosted/wubu -h       # Headless OK
```