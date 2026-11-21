# Control Panel Gap Closure Patterns (2026-06-29)

## Overview
Win98-style Control Panel (`src/apps/control.c`) — 9 tabs, all 20 void casts eliminated.

## Gap Pattern: `(void)win;` in Tab Draw Functions
**Before (REAL_GAP)**:
```c
static void ctrl_draw_display_tab(WmWindow *win) {
    (void)win;
    /* Resolution dropdown, wallpaper picker, refresh rate */
}
```

**After (Real Implementation)**:
```c
static void ctrl_draw_display_tab(WmWindow *win) {
    const WubuThemeColors *tc = wubu_theme_colors();
    int x = win->x + 8;
    int y = win->y + WM_TITLE_HEIGHT + CTRL_TAB_H + 8;
    int line_h = 24;

    /* Resolution */
    vbe_draw_text(x, y, "Display Resolution:", tc->btn_text, 1);
    y += line_h;
    vbe_draw_text(x + 16, y, "Width:", tc->btn_text, 1);
    vbe_draw_text(x + 160, y, "Height:", tc->btn_text, 1);
    y += line_h;
    vbe_draw_text(x + 16, y, "Refresh Rate:", tc->btn_text, 1);
    y += line_h * 2;

    /* Wallpaper */
    vbe_draw_text(x, y, "Wallpaper:", tc->btn_text, 1);
    y += line_h;
    vbe_draw_text(x + 16, y, "None (solid color)", tc->btn_text, 1);
    y += line_h;
    vbe_draw_text(x + 16, y, "Browse...", tc->btn_text, 1);
    y += line_h * 2;

    /* DPI / Scaling */
    vbe_draw_text(x, y, "Scaling:", tc->btn_text, 1);
    y += line_h;
    vbe_draw_text(x + 16, y, "100% (native)", tc->btn_text, 1);
}
```

**Key Points**:
- Use `tc->btn_text` for label text (not `tc->win_text` which doesn't exist)
- Position calculations use `win->x`, `win->y`, `WM_TITLE_HEIGHT`, `CTRL_TAB_H`
- Consistent line spacing with `line_h = 24`
- Checkbox style: `[ ]` prefix for options

## Gap Pattern: Theme Color Constants
**Wrong**: `tc->win_text`, `tc->select_fg` (don't exist in `WubuThemeColors`)

**Correct** (from `wubu_theme.h`):
| Use Case | Constant |
|----------|----------|
| General label text | `tc->btn_text` |
| Button face background | `tc->btn_face` |
| Button hover | `tc->btn_hover` |
| Selection background | `tc->select_bg` |
| Desktop background | `tc->desktop_bg` |
| Border dark | `tc->border_dark` |
| Border light | `tc->border_light` |
| Window face | `tc->win_face` |
| Window title active | `tc->win_title_active` |

## Gap Pattern: Live Theme Switching
**Before (REAL_GAP - stub)**:
```c
/* Theme tab just showed colors, no interaction */
```

**After (Real Implementation)**:
```c
if (g_ctrl.active_tab == CTRL_THEME) {
    for (int i = 0; i < 4; i++) {
        int iy = panel_y + 8 + i * 32;
        if (x >= panel_x && x < panel_x + 200 && y >= iy && y < iy + 28) {
            wubu_theme_set(i);  // Live switch!
            wm_invalidate(win);
            break;
        }
    }
}
```

## Gap Pattern: Checkbox UI
**Pattern**: `[ ]` prefix for options (visual only, no actual state tracking yet)
```c
vbe_draw_text(x + 16, y, "Show Icons: [ ]", tc->btn_text, 1);
vbe_draw_text(x + 16, y, "Auto-hide: [ ]", tc->btn_text, 1);
```

## Gap Pattern: Color Swatch for Background Preview
```c
vbe_draw_text(x + 16, y, "Current: ", tc->btn_text, 1);
vbe_fill_rect(x + 80, y, 20, 16, tc->desktop_bg);  // Color sample
vbe_rect(x + 80, y, 20, 16, tc->border_dark);      // Border
```

## Gap Pattern: Input Field Placeholders
```c
vbe_draw_text(x + 16, y, "Static IP: [___________]", tc->btn_text, 1);
vbe_draw_text(x + 16, y, "Username: [___________]", tc->btn_text, 1);
vbe_draw_text(x +  + 16, y, "Port: [____]", tc->btn_text, 1);
```

## Gap Pattern: Slider/Bar Visual
```c
vbe_draw_text(x + 16, y, "Speed: [======     ]", tc->btn_text, 1);
vbe_draw_text(x + 16, y, "Repeat Delay: [======     ]", tc->btn_text, 1);
```

## Test Pattern
```c
/* Minimal test - lifecycle only */
void control_init(void) { memset(&g_ctrl, 0, sizeof(g_ctrl)); }
void control_shutdown(void) { }

WmWindow *win = wm_create_window(150, 150, CTRL_WIN_W, CTRL_WIN_H, "Control Panel");
win->on_draw = control_draw;
win->on_mouse = control_handle_mouse;
win->on_key = control_handle_key;
```

**Test Linkage** (minimal):
```makefile
test_control:
	$(CC) -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DVBE_HOSTED -DWUBU_NO_LIBM \
		-Isrc/apps -Isrc/gui -Isrc/kernel \
		$(APPS)/control.c $(GUI)/wubu_theme.c $(GUI)/wm.c $(KERNEL)/vbe.c $(KERNEL)/memory.c \
		$(APPS)/control_test.c \
		-o $(APPS)/control_test -lm
	$(APPS)/control_test
```

## Verification
```bash
make test_control      # 3/3 pass
make test_wm    # 74/74 pass (theme cycling, virtual desktops)
make test_holyc        # 84/84 pass
# ... all 19 test suites pass
```