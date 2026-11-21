# ReactOS-Learned Desktop Fixup Patterns (2026-07-07)

Concrete patterns for closing WuBuOS desktop REAL_GAPs by studying ReactOS's real
desktop source. WuBuOS desktop = `wm.c` + `desktop.c`; ReactOS desktop =
`win32ss/user/ntuser/desktop.c` + `base/shell/explorer/desktop.cpp` + `dll/cpl/desk/background.c`
+ `dll/cpl/desk/desktop.c`. The ReactOS checkout lives at `reactos-study/reactos/`.

## ReactOS Source Map → WuBuOS Responsibility

| ReactOS file | What it does | WuBuOS analog |
|---|---|---|
| `dll/cpl/desk/background.c` | Reads `Control Panel\Desktop\Wallpaper` + `WallpaperStyle` from registry; `PLACEMENT` enum (CENTER/STRETCH/TILE/FIT/FILL); `AddListViewItems()` enumerates images | `wubu_settings->theme.wallpaper_path` + `wallpaper_mode`; `src/gui/wubu_wallpaper.c` (NEW) |
| `dll/cpl/desk/desktop.c` | `DesktopIcons[]`, `HideDesktopIcons`, `IconChange[]` stores `szPath` (STRING target, not callback); `SaveDesktopSettings()`/`SetDesktopSettings()` + arrange-by | `DosGuiIcon` in `wm.h` (stores `target[256]` string); `wm_ctxmenu.c` (sort/rename/delete) |
| `base/shell/explorer/desktop.cpp` | `CDesktopThread` — desktop window on its own thread, message loop | `desktop.c` (single-thread, in-process) |
| `win32ss/user/ntuser/desktop.c` | kernel desktop object + heap | `g_dwm` global WM state (`wm_internal.h`) |

Key ReactOS lesson: **icons are string targets (CLSID/path) persisted to registry, NOT C
function pointers.** WuBuOS `DosGuiIcon.on_click/on_execute` are function pointers → cannot
be serialized → icon layout is lost on restart (a REAL_GAP). Fix = persist `name`+`grid_x/y`
to `wubu_settings` (ReactOS-style), not callbacks.

## Pattern 1 — Real Wallpaper Decode + 5 Placement Modes

File: `src/gui/wubu_wallpaper.{h,c}` (NEW). Decodes a 24/32-bit uncompressed BMP into the
VBE framebuffer pixel format and computes the dest rect for each placement mode.

**Pixel format contract (CRITICAL):** VBE backbuffer is XRGB8888 = `0x00BBGGRR`
(see `vbe_set_pixel` in `src/kernel/vbe.c`). A 24-bit BMP stores pixels on disk as BGR
bytes. Convert: `pixel = (b<<16)|(g<<8)|r`.

**BMP decode gotchas (learned the hard way):**
- `BITMAPFILEHEADER.bfOffBits` must be **54** for a 40-byte `BITMAPINFOHEADER` with no
  palette. Getting the byte offsets wrong (e.g. writing 14+40 split across bytes 10-13
  incorrectly) makes `fseek` land mid-header → segfault on `fread`.
- Rows are **bottom-up** when `biHeight > 0`: the FIRST scanline in the file is the BOTTOM
  display row. Decode into `dst_y = top_down ? y : (h-1-y)`.
- Row stride is padded to a 4-byte boundary: `pad = (4 - (w*bpp & 3)) & 3`.
- Only `biCompression == 0` (BI_RGB) and `biBitCount in {24,32}` supported. Reject else.

**Placement rect math (mirrors ReactOS `PLACEMENT`/`PLACEMENT_VALUE`):**
```c
void wubu_wallpaper_rect(WubuWallpaperMode mode, int img_w, int img_h,
                         int fb_w, int fb_h, int taskbar_h,
                         int *out_x, int *out_y, int *out_w, int *out_h) {
    int avail_h = fb_h - taskbar_h; if (avail_h < 1) avail_h = fb_h;
    // CENTER: native size, centered. TILE: native size, caller repeats.
    // STRETCH: w=fb_w, h=avail_h (distort).
    // FIT: scale to fit inside, preserve aspect (letterbox).
    // FILL: scale to cover, preserve aspect (crop overflow).
}
```
`draw_wallpaper()` samples the decoded bitmap across the rect for STRETCH/FIT/FILL;
CENTER/TILE use native pixels directly.

**Wiring into WM** (`wm.c`):
```c
void load_default_wallpaper(void) {
    if (g_dwm.wallpaper) return;
    const WubuSettings *s = wubu_settings_get();
    if (s && s->theme.wallpaper_path[0]) {
        WubuWallpaper wp;
        if (wubu_wallpaper_load(s->theme.wallpaper_path, &wp) && wp.pixels) {
            g_dwm.wallpaper = wp.pixels;            /* takes ownership */
            g_dwm.wallpaper_w = wp.w; g_dwm.wallpaper_h = wp.h;
            g_dwm.wallpaper_mode = s->theme.wallpaper_mode;  /* 0..4 */
            return;
        }
        /* decode fail -> fall through to gradient (do NOT spam) */
    }
    /* gradient fallback (classic teal->blue) */
}
```
Add `#include "wubu_wallpaper.h"` and `#include "wubu_settings.h"` to
`wm_internal.h`. Add `wubu_wallpaper.o` to `GUI_OBJS` and link it into
`test_wm` (otherwise `undefined reference to wubu_wallpaper_*`).

## Pattern 2 — Wallpaper Test (no GPU needed)

`src/gui/wubu_wallpaper_test.c`: writes a real 2x2 24-bit BMP to `/tmp`, decodes it,
asserts pixel order (top-left=red, top-right=green, bottom-left=blue, bottom-right=white
for a bottom-up BMP whose file rows are blue/white then red/green), then checks all 5
placement rects. **18 assertions, all green.** Add `test_wallpaper` target to Makefile
and wire into `test_high_gui`.

Lesson from first failed run: my test fixture wrote `bfOffBits` wrong AND I transposed the
expected pixel labels (forgot bottom-up means file's first row = bottom). The DECODER was
correct; the TEST was wrong. Always verify your fixture before blaming the decoder.

## Pattern 3 — Dead-Code Purge (de-risk "broken desktop" surface)

Legacy files `src/gui/wm.c`, `wm_test.c`, `startmenu.c`, `desktop.c`, `theme.c`,
`src/kernel/vbe_legacy.h` were NOT in `Makefile` (build uses `wm.c`,
`startmenu.c`, `wubu_theme.c`, `desktop.c`, `wubu_wm.c` — distinct files).
They only `#include "vbe_legacy.h"` (dead API) and confuse the desktop surface.

Safe purge:
```bash
mkdir -p src/_legacy_bak
git mv src/gui/wm.c src/gui/wm_test.c src/gui/startmenu.c src/gui/desktop.c \
       src/gui/theme.c src/kernel/vbe_legacy.h src/_legacy_bak/
grep -rln "vbe_legacy" src/ | grep -v _legacy_bak   # must print NOTHING
make test_high_gui                                    # must stay green
```
Quarantine (reversible) — do NOT hard-delete until a few sessions confirm no regression.

## Verification Contract (every desktop stream)
- New/updated code compiles under `make` (CFLAGS: `-Wall -Wextra -Wno-*`, c11).
- `make test_high_gui` stays green; add a focused `test_*` target per stream.
- Run a REAL decode / REAL persistence round-trip — no stub, no fake notify.
