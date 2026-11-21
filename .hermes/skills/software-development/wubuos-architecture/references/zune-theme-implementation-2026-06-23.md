# Zune Theme Implementation - WuBuOS (2026-06-23)

## Overview
Added THEME_ZUNE (id=4) as the 5th built-in theme with dark background and orange accent.

## Theme Colors (wubu_theme.c)

```c
[THEME_ZUNE] = {
    .id = THEME_ZUNE,
    .name = "Zune",
    .colors = {
        .desktop_bg        = RGB(0x1A,0x1A,0x1A),   // Near-black
        .win_face          = RGB(0x22,0x22,0x22),   // Dark gray
        .win_title_active  = RGB(0xE8,0x6C,0x00),   // Zune orange
        .win_title_inactive= RGB(0x33,0x33,0x33),
        .win_title_text    = RGB(0xFF,0xFF,0xFF),
        .win_title_text_ina= RGB(0x88,0x88,0x88),
        .border_light      = RGB(0x44,0x44,0x44),
        .border_face       = RGB(0x22,0x22,0x22),
        .border_dark       = RGB(0x11,0x11,0x11),
        .border_darkest    = RGB(0x00,0x0x00,0x00),
        .btn_face          = RGB(0x2A,0x2A,0x2A),
        .btn_hover         = RGB(0xE8,0x6C,0x00),   // Orange hover
        .btn_pressed       = RGB(0xB0,0x54,0x00),
        .btn_text          = RGB(0xFF,0xFF,0xFF),
        .taskbar_bg        = RGB(0x11,0x11,0x11),   // Near-black taskbar
        .taskbar_border    = RGB(0xE8,0x6C,0x00),   // Orange accent
        .start_btn_face    = RGB(0xE8,0x6C,0x00),   // Orange Start
        .start_btn_text    = RGB(0xFF,0xFF,0xFF),
        .startmenu_bg      = RGB(0x1A,0x1A,0x1A),
        .startmenu_sidebar = RGB(0xE8,0x6C,0x00),
        .startmenu_hover   = RGB(0xE8,0x6C,0x00),
        .startmenu_text    = RGB(0xFF,0xFF,0xFF),
        .select_bg         = RGB(0xE8,0x6C,0x00),
        .select_text       = RGB(0x00,0x00,0x00),
        .scroll_track      = RGB(0x11,0x11,0x11),
        .scroll_thumb      = RGB(0x33,0x33,0x33),
        .icon_text         = RGB(0xFF,0xFF,0xFF),
        .icon_text_shadow  = RGB(0x00,0x00,0x00),
        .icon_bg           = RGB(0x22,0x22,0x22),
        .icon_border       = RGB(0xE8,0x6C,0x00),
    },
    .title_gradient     = {RGB(0xE8,0x6C,0x00), RGB(0xFF,0x99,0x33), true},
    .title_gradient_ina = {RGB(0x33,0x33,0x33), RGB(0x22,0x22,0x22), true},
    .rounded_buttons    = true,
    .gradient_title     = true,
    .Luna_start_button  = true,
},
```

## Theme Enum Update (wubu_theme.h)

```c
typedef enum {
    THEME_WIN98_CLASSIC   = 0,
    THEME_XP_LUNA_BLUE   = 1,
    THEME_XP_MEDIA_ORANGE = 2,
    THEME_WUBU_CUSTOM     = 3,
    THEME_ZUNE            = 4,
    THEME_COUNT           = 5,
} WubuThemeId;
```

## CLI Theme Selection (hosted.c)

```bash
./src/hosted/wubu --theme zune --gui-screenshot output.ppm
./src/hosted/wubu --theme xp --gui-screenshot output.ppm
./src/hosted/wubu --theme xp-media --gui-screenshot output.ppm
./src/hosted/wubu --theme wubu --gui-screenshot output.ppm
./src/hosted/wubu --theme win98 --gui-screenshot output.ppm
```

## Implementation Details

### 1. Theme Enum Addition (wubu_theme.h)
Added `THEME_ZUNE = 4` and updated `THEME_COUNT = 5`

### 2. Theme Data (wubu_theme.c)
Added complete theme struct with:
- Dark background palette (#1A1A1A, #222222, #111111)
- Orange accent (#E86C00) for active elements
- Gradient titles: orange → gold (#E86C00 → #FF9933)
- Rounded buttons enabled
- Luna-style Start button (orange)

### 3. CLI Integration (hosted.c)
- Added `--theme` flag parsing in `hosted_init()`
- Stores theme name in `state->theme_name`
- Applied after `wubu_theme_init()` but before `wm_init()`
- Maps theme names to enum values

## Verification

```bash
# Build
make hosted

# Test Zune theme
WAYLAND_DISPLAY=wayland-1 ./src/hosted/wubu --theme zune --gui-screenshot /tmp/zune.ppm

# Convert to PNG
ffmpeg -y -i /tmp/zune.ppm -update 1 /tmp/zune.png

# Verify colors
python3 -c "
from PIL import Image
img = Image.open('/tmp/zune.png')
pixels = list(img.getdata())
non_black = [p for p in pixels if p != (0, 0, 0)]
orange = sum(1 for p in pixels if p == (232, 108, 0))  # E86C00
dark = sum(1 for p in pixels if p == (26, 26, 26))    # 1A1A1A
gray = sum(1 for p in pixels if p == (17, 17, 17))    # 111111
print(f'Orange (E86C00): {orange}')
print(f'Dark (1A1A1A): {dark}')
print(f'Gray (111111): {gray}')
"
```

### Expected Results
- Orange pixels (~3,915) — title bars, start button, selection highlights
- Dark gray pixels (~29,459) — taskbar, window backgrounds
- Non-black pixels ~783,574 / 786,432 (99.6%)

## Design Rationale

The Zune theme implements Microsoft's Zune media player aesthetic:
- **Dark mode first** — reduces eye strain, modern look
- **Orange accent** — distinctive Zune brand color (#E86C00)
- **Minimal chrome** — flat buttons, subtle borders
- **Gradient titles** — subtle depth without heaviness
- **High contrast** — white text on dark backgrounds

## Theme Switching
```bash
# Cycle themes at runtime
wubu_theme_cycle()

# Set specific theme
wubu_theme_set(THEME_ZUNE)
```