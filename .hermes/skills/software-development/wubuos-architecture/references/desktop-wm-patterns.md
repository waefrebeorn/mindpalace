# Desktop/Window Manager Implementation Patterns

## GAAD Snap (Grid Aligned Application Design)

**File**: `src/gui/wm.c` - `snap_window_to_gaad()`

### Snap Targets
| Target | Condition | Result |
|--------|-----------|--------|
| Left edge | `w->x ∈ [-12, 12]` | `w->x = 0` |
| Right edge | `w->x + w->w ∈ [W-12, W+12]` | `w->x = W - w->w` |
| Top edge | `w->y ∈ [-12, 12]` | `w->y = 0` |
| Bottom edge | `w->y + w->h ∈ [H-task_h-12, H-task_h+12]` | `w->y = H - task_h - w->h` |

### Quadrant Snap (Corner + Size Match)
```c
int center_x = W / 2;
int center_y = (H - task_h) / 2;
// Top-left: x≈0, y≈0, w≈center_x, h≈center_y
// Top-right: x+w≈W, y≈0, w≈center_x, h≈center_y
// Bottom-left: x≈0, y+h≈H-task_h, w≈center_x, h≈center_y
// Bottom-right: x+w≈W, y+h≈H-task_h, w≈center_x, h≈center_y
```

### Half Snap (Edge + Full Height/Width)
```c
// Left half: x≈0, y≈0, w≈W/2, h≈H-task_h
// Right half: x+w≈W, y≈0, w≈W/2, h≈H-task_h
```

### Trigger
Called from `wm_handle_mouse()` on `kind == 2` (mouse up) after drag:
```c
if (g_dwm.drag_id >= 0 && g_dwm.windows[g_dwm.drag_id].alive) {
    snap_window_to_gaad(&g_dwm.windows[g_dwm.drag_id]);
}
g_dwm.drag_id = -1;
```

---

## Virtual Desktop Migration

**File**: `src/gui/wm.c` / `src/gui/wm.h`

### Window Struct Addition
```c
typedef struct DosGuiWindow {
    // ... existing fields ...
    int desktop;  // Virtual desktop index (0..8)
    // ...
} DosGuiWindow;
```

### Desktop Filtering (3 Locations)
1. **hit_test()**: Only hit-test windows on current desktop
2. **render_desktop()**: Only render windows on current desktop (skip minimized)
3. **taskbar_render()**: Only show taskbar buttons for current desktop

### Keyboard Shortcuts
| Keys | Action |
|------|--------|
| `Ctrl+Alt+Left` | Previous desktop |
| `Ctrl+Alt+Right` | Next desktop |
| `Win+Shift+Left` | Move focused window to previous desktop |
| `Win+Shift+Right` | Move focused window to next desktop |

### API Functions
```c
void wm_move_window_to_desktop(DosGuiWindow *win, int desktop);
int  wm_get_current_desktop(void);
void wm_set_current_desktop(int desktop);
void wm_move_focused_window(int delta);  // delta = -1 or +1
```

---

## HolyC Terminal Modifier Keys

**File**: `src/gui/wm.c` - `holyc_term_key()`

### Modifier Parsing
```c
bool ctrl  = (mods & 0x02) != 0;
bool shift = (mods & 0x01) != 0;
bool alt   = (mods & 0x04) != 0;
bool meta  = (mods & 0x08) != 0;
```

### Key Bindings
| Keys | Action |
|------|--------|
| `Enter` | Execute input via `hc_eval()` |
| `Backspace` | Delete char |
| `Up/Down` | History navigation |
| `Ctrl+C` | Clear input, add `^C` line |
| `Ctrl+L` | Clear screen (`line_count = 0`) |
| `Ctrl+U` | Delete current line |
| `Shift+Right` | Complete from history at cursor |

---

## Runtime Theme Cycling

**File**: `src/gui/wubu_theme.c` + `src/gui/wm.c`

### Theme IDs
```c
typedef enum {
    THEME_WIN98_CLASSIC    = 0,  // Teal, 3D borders, navy title
    THEME_XP_LUNA_BLUE    = 1,  // Blue gradient, rounded, Luna orb
    THEME_XP_MEDIA_ORANGE = 2,  // Orange/black, Media Center
    THEME_WUBU_CUSTOM     = 3,  // Green-tinted, WuBu branded
    THEME_ZUNE            = 4,  // Zune-inspired
    THEME_COUNT           = 5,
} WubuThemeId;
```

### Theme Properties
| Property | Win98 | XP Luna | XP Media | WuBu |
|----------|-------|---------|----------|------|
| `rounded_buttons` | false | true | true | true |
| `gradient_title` | false | true | true | true |
| `Luna_start_button` | false | true | true | true |

### Runtime Switch
```c
wubu_theme_set(THEME_XP_LUNA_BLUE);  // Instant switch
wubu_theme_cycle();  // Next theme (bound to key 0x3F / F1 in wm)
```

---

## Screenshot Generator Frames

**File**: `src/tools/screenshot.c` - 26 frames

| Frame | File | Feature |
|-------|------|---------|
| 0 | frame_00_desktop.ppm | Clean desktop with all icons |
| 1 | frame_01_startmenu.ppm | Start menu open |
| 2 | frame_02_apps.ppm | Multiple app windows |
| 3 | frame_03_taskbar.ppm | Taskbar hover highlight |
| 4 | frame_04_focus.ppm | Window focus click |
| 5 | frame_05_control.ppm | Control panel |
| 6 | frame_06_paint.ppm | Paint app |
| 7 | frame_07_freedoom.ppm | FreeDoom demo |
| 8 | frame_08_gaad_left.ppm | **GAAD left half snap** |
| 9 | frame_09_gaad_quadrant.ppm | **GAAD top-right quadrant** |
| 10 | frame_10_vdesk_0.ppm | **Virtual desktop 0** |
| 11 | frame_11_vdesk_1.ppm | **Virtual desktop 1 (empty)** |
| 12 | frame_12_vdesk_1_win.ppm | **Virtual desktop 1 with window** |
| 13 | frame_13_vdesk_migrate.ppm | **Window migrated via Win+Shift+Right** |
| 14 | frame_14_vdesk_1_after_migrate.ppm | **Desktop 1 after migration** |
| 15 | frame_15_holyc_term.ppm | **HolyC terminal** |
| 16 | frame_16_holyc_eval.ppm | **HolyC eval 2+2=4** |
| 17 | frame_17_holyc_cleared.ppm | **HolyC cleared with Ctrl+L** |
| 18 | frame_18_theme_win98.ppm | **Win98 Classic theme** |
| 19 | frame_19_theme_xp_luna.ppm | **XP Luna Blue theme** |
| 20 | frame_20_theme_xp_media.ppm | **XP Media Orange theme** |
| 21 | frame_21_theme_wubu.ppm | **WuBu Green theme** |
| 22 | frame_22_explorer.ppm | **File Manager** |
| 23 | frame_23_control_panel.ppm | **Control Panel (daemon)** |
| 24 | frame_24_container_mgr.ppm | **Container Manager** |
| 25 | frame_25_notifications.ppm | **Notification Center** |

### PPM Writer
```c
static void write_ppm(const char *filename, uint32_t *fb, int w, int h) {
    FILE *f = fopen(filename, "wb");
    fprintf(f, "P6\n%d %d\n255\n", w, h);
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            uint32_t c = fb[y * w + x];
            fwrite((unsigned char[3]){(c>>16)&0xFF, (c>>8)&0xFF, c&0xFF}, 1, 3, f);
        }
    }
    fclose(f);
}
```