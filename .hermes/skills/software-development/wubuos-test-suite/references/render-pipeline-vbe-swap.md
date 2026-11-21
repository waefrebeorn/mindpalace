# Demo Recorder & Screenshot Pipeline Patterns (2026-06-29)

## Context
The WuBuOS demo recorder captures the hosted GUI shell in action for verification and documentation.

## Critical Pattern: `vbe_swap()` After Every Render

### The Bug
The demo recorder (`src/tools/wubu_demo_record.c`) was producing **all-black frames** because it called `desktop_render()` but **forgot to call `vbe_swap()`** to copy the back buffer to the front buffer.

### The Fix
```c
// In src/tools/wubu_demo_record.c - CORRECT pattern:
while (frame < frame_count) {
    desktop_render(vbe_state()->fb, width, height);
    vbe_swap();  // <-- REQUIRED: copies back buffer to front
    wubu_gif_add_frame(0, 0, width, height);
}
```

The hosted binary (`src/hosted/wubu`) already has this correct in its render loop (line 844 in hosted.c).

### Why It Matters
- **Double buffering**: `vbe_state()->fb` is the **back buffer** (drawn to by render functions)
- `vbe_swap()` copies back buffer → **front buffer** (displayed on screen)
- Without `vbe_swap()`, front buffer stays black (uninitialized or previous frame)
- Demo recorder reads from front buffer for frame capture

## Demo Recorder Build & Run

```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed

# Build
make src/tools/wubu_demo_record

# Record 4-second demo (120 frames @ 30fps)
./src/tools/wubu_demo_record 120 30

# Output: wubuos_demo.mp4 + wubuos_demo.webm

# Extract frames for inspection
ffmpeg -i wubuos_demo.mp4 -vf "select=not(mod(n\,30))" -fps_mode vfr frame_%03d.png
```

## Headless Screenshots from Hosted Binary

```bash
# Headless screenshot (works in CI/headless)
./src/hosted/wubu --screenshot /tmp/screenshot.ppm

# Output: 1024x768 PPM with all pixels non-zero (verified)
# Convert: ffmpeg -y -i /tmp/screenshot.ppm -update 1 screenshot.png
```

## Theme-Specific Screenshots (2026-06-23)

```bash
# Zune theme (dark + orange)
./src/hosted/wubu --theme zune --gui-screenshot /tmp/zune.ppm

# XP Luna Blue
./src/hosted/wubu --theme xp --gui-screenshot /tmp/xp.ppm

# XP Media Center Orange
./src/hosted/wubu --theme xp-media --gui-screenshot /tmp/xp-media.ppm

# WuBu Custom Green
./src/hosted/wubu --theme wubu --gui-screenshot /tmp/wubu.ppm

# Win98 Classic (default)
./src/hosted/wubu --theme win98 win98 --gui-screenshot /tmp/win98.ppm
```

## Theme Screenshot Verification Script

```bash
python3 -c "
from PIL import Image
img = Image.open('/tmp/zune.png')
pixels = list(img.getdata())
orange = sum(1 for p in pixels if p == (232, 108, 0))  # E86C00
dark = sum(1 for p in pixels if p == (26, 26, 26))    # 1A1A1A
gray = sum(1 for p in pixels if p == (17, 17, 17))    # 111111
print(f'Orange (E86C00): {orange}')
print(f'Dark (1A1A1A): {dark}')
print(f'Gray (111111): {gray}')
"
```

### Expected Results for Zune Theme
- Orange pixels (~3,915) — title bars, start button, selection highlights
- Dark gray pixels (~29,459) — taskbar, window backgrounds
- Non-black pixels ~783,574 / 786,432 (99.6%)

## Screenshot Verification Checklist
- [ ] `vbe_swap()` called after every `desktop_render()`
- [ ] Front buffer has non-zero pixels (check: `nonzero > 0`)
- [ ] `--screenshot` flag works in headless mode
- [ ] Demo recorder builds and runs without segfault
- [ ] Theme screenshots show correct colors (verify with Python PIL)
- [ ] Frame capture uses front buffer (after `vbe_swap()`)

## Files Involved
| File | Purpose |
|------|---------|
| `src/tools/wubu_demo_record.c` | Demo recorder (must call `vbe_swap()`) |
| `src/hosted/hosted.c` | Hosted binary (correct pattern at line 844) |
| `src/kernel/vbe.c` | VBE framebuffer + `vbe_swap()` implementation |
| `src/gui/desktop.c` | `desktop_render()` implementation |
| `src/tools/wubu_demo_record.c` | Demo recorder build target |