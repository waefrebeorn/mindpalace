# Text Overlap Fixes - WuBuOS GUI (2026-06-23)

## Problem
Multiple text overlap issues in WuBuOS GUI rendering:
1. **Icon labels** drawn below icons without bounds checking → off-screen
2. **Taskbar clock** overlaps with window buttons when many windows open
3. **Start menu items** overflow menu width when labels are long
4. **Window button titles** overflow button width
5. **Icon label bug** — uninitialized `truncated` variable in `vbe_text_width()` call

## Root Cause
No bounds checking before `vbe_draw_text()` calls. Text rendered without measuring width or checking screen boundaries.

## Solution Pattern
```c
// 1. Measure text width first
int text_w = vbe_text_width(label, 1);
int max_text_w = available_width - padding;

// 2. Truncate with ellipsis if needed
if (text_w > max_text_w) {
    char truncated[64];
    int len = strlen(label);
    strncpy(truncated, label, len);
    truncated[len] = '\0';
    while (len > 0 && vbe_text_width(truncated, 1) > max_text_w - 6) { // -6 for "..."
        len--;
        truncated[len] = '\0';
    }
    if (len > 0) {
        strncpy(truncated + len, "...", 3);
        truncated[len + 3] = '\0';
    } else {
        strcpy(truncated, "...");
    }
    label = truncated;
}

// 3. Draw with bounds check
if (y + font_height <= fb_h) {
    vbe_draw_text(x, y, label, color, scale);
}
```

## Specific Fixes Applied

### 1. Icon Labels (`wm.c:1185-1210`)
- Added `DOSGUI_ICON_LABEL_H = 16` constant for reserved label height
- Bounds check: `label_y + 8 <= fb_h`
- Max label width: `DOSGUI_ICON_SIZE + 4`
- Fixed uninitialized `truncated` variable in loop

### 2. Taskbar Clock (`taskbar_render`, line 1070-1085, 1210-1225)
- Compute `right_reserve = clock_w + 20 + tray_count * (DOSGUI_SYSTRAY_SIZE + 4) + 10`
- Use `bx` (last button x position) as boundary
- `clock_x = fb_w - clk_w - 10; if (clock_x + clk_w > bx) clock_x = bx - clk_w - 10;`
- Position tray icons left of clock

### 3. Window Button Titles (`taskbar_render`, line 1090-1200)
- `max_text_w = bw - 16` (16px padding)
- Ellipsis truncation in all 4 button drawing paths (rounded/focused, rounded/unfocused, square/focused, square/unfocused)
- Stop button loop when `bx + bw > screen_w - right_reserve`

### 4. Start Menu Items (`startmenu.c:190-230`)
- `max_text_w = w - 20` (reserve for arrow + padding)
- If submenu: `max_text_w -= 16`
- Ellipsis truncation before `vbe_draw_text`

### 5. Icon Label Bug Fix (line 1297)
**Bug**: `truncated` array used uninitialized in `vbe_text_width(truncated, 1)`
```c
// BUGGY:
while (len > 0 && vbe_text_width(truncated, 1) > max_label_w) {
    len--;
    strncpy(truncated, icon->name, len);
    truncated[len] = '\0';
}

// FIXED:
strncpy(truncated, icon->name, len);
truncated[len] = '\0';
while (len > 0 && vbe_text_width(truncated, 1) > max_label_w) {
    len--;
    truncated[len] = '\0';
}
```

## Testing
```bash
# Run hosted binary with GUI screenshot
WAYLAND_DISPLAY=wayland-1 ./src/hosted/wubu --gui-screenshot /tmp/test.ppm

# Convert to PNG
ffmpeg -y -i /tmp/test.ppm -update 1 /tmp/test.png

# Verify no black frames, no text overlaps
python3 -c "
from PIL import Image
img = Image.open('/tmp/test.png')
pixels = list(img.getdata())
non_black = [p for p in pixels if p != (0, 0, 0)]
print(f'Non-black: {len(non_black)} / {len(pixels)}')
"
```

## Related Files
- `src/gui/wm.c` — `wm_render_desktop`, `taskbar_render`
- `src/gui/startmenu.c` — `draw_menu_item`
- `src/gui/wm.h` — `DOSGUI_ICON_LABEL_H` constant
- `src/tools/wubu_demo_record.c` — demo recorder fix (added vbe_swap)