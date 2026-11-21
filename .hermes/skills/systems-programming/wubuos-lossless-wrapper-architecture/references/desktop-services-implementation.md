# Desktop Services Implementation Patterns (WuBuOS Phase 2)

Documentation of patterns used implementing GNOME-standard desktop services for WuBuOS.

## Screenshot Tool (wubu_screenshot.c)

**Key Pattern: Wayland SHM Buffer Readback**
```c
// Access framebuffer via global Wayland state
extern wayland_state_t g_wl;

static wubu_sshot_t *capture_framebuffer(int x, int y, int w, int h) {
    if (!g_wl.shm_buffer || !g_wl.shm_data) return NULL;
    // g_wl.shm_data points to SHM buffer pixels (RGBA)
    // g_wl.width / g_wl.height = surface dimensions
    // Copy region from g_wl.shm_data to new buffer
}
```

**Region Selection Overlay**
- Mouse drag state machine in `wubu_region_selector_t`
- Render dimmed screen + brightened selection rect in `wayland_frame_render()`
- Callback on mouse release delivers captured region

**Hotkeys (Linux evdev scancodes)**
- PrintScr (99) = full screen
- Alt+PrintScr = focused window
- Shift+PrintScr = region select

**PNG Writer** - bundled minimal implementation (no libpng dependency):
- PNG signature + IHDR + IDAT (zlib uncompressed blocks) + IEND
- Valid for screenshots, not production quality

**Integration in hosted.c**
```c
// Keyboard handler
case 99: /* KEY_SYSRQ / PrintScr */
    if (g_key_map[56] || g_key_map[100]) wubu_screenshot_handle_alt_printscr();  /* Alt */
    else if (g_key_map[42] || g_key_map[54]) wubu_screenshot_handle_shift_printscr(); /* Shift */
    else wubu_screenshot_handle_printscr();
    break;

// Pointer motion - update region selector
if (wubu_screenshot_has_active_region_selector()) {
    wubu_screenshot_update_region_selector(x, y, g_mouse_buttons & 1);
}

// Frame render - overlay region selector
if (wubu_screenshot_has_active_region_selector()) {
    wubu_screenshot_render_region_selector(buf->pixels, buf->width, buf->height);
}
```

## MIME System (wubu_mime.c)

**Built-in MIME Database**
```c
static const MimeTypeEntry builtin_mimes[] = {
    {".txt", "text/plain", "Plain Text", "wubu-text-editor", true, 10},
    {".png", "image/png", "PNG Image", "wubu-image-viewer", false, 10},
    // ... 30+ types
};
```

**.desktop File Parser** (simplified FreeDesktop spec)
- Sections: `[Desktop Entry]`, `[Desktop Action name]`
- Keys: Name, Exec, Icon, Type, MimeType, Categories, Terminal, Hidden, NoDisplay
- Exec placeholders: `%f` (file), `%u` (URL), `%F`/`%U` (multiple)
- Scans: `$XDG_DATA_HOME/applications` + `$XDG_DATA_DIRS/applications`
- User dir overrides system dirs (by ID)

**Launch API**
```c
static int execute_command(const char *cmd_template, const char *file_path) {
    // Substitutes %f/%u with quoted file_path
    // fork() + setsid() + execl("/bin/sh", "sh", "-c", cmd, NULL)
}
```

**Default Handlers** - created `.desktop` files in `.local/share/applications/`

## Trash System (wubu_trash.c)

**FreeDesktop Trash Spec Compliance**
```
~/.local/share/Trash/
├── files/          # Actual deleted files/dirs
└── info/           # .trashinfo files
    └── name.trashinfo  # [Trash Info]
                        # Version=1
                        # Path=/original/path
                        # DeletionDate=2026-06-15T14:30:00
```

**Key Patterns**
- Unique name generation: `basename` + `_N` suffix on conflict
- Size tracking for max-size enforcement (auto-evict oldest)
- Auto-expire: delete entries older than N days
- Load existing trash on init by scanning `info/` directory

**Common Bug Fixed**
```c
// WRONG - basename() may return pointer to static buffer
char *base = basename(strdup(original_path));
free(base);  // INVALID: basename returns pointer INTO strdup, not the allocation!

// CORRECT
char *path_copy = strdup(original_path);
char *base = basename(path_copy);  // base points INTO path_copy
free(path_copy);  // Free the allocation
```

## Makefile Integration Pattern

**Add to GUI_OBJS:**
```makefile
GUI_OBJS = ... $(GUI)/wubu_screenshot.o $(GUI)/wubu_mime.o $(GUI)/wubu_trash.o ...
```

**Add to HOSTED_OBJS and hosted: target:**
```makefile
HOSTED_OBJS = ... $(GUI)/wubu_screenshot.o $(GUI)/wubu_mime.o $(GUI)/wubu_trash.o

hosted: $(HOSTED_OBJS) ...
    $(GUI)/wubu_screenshot.c $(GUI)/wubu_mime.c $(GUI)/wubu_trash.c \
```

**Test Targets:**
```makefile
test_mime:
    $(CC) ... $(GUI)/wubu_mime.c $(GUI)/wubu_theme.c $(GUI)/wubu_settings.c \
        $(GUI)/wubu_mime_test.c -o $(GUI)/wubu_mime_test

test_trash:
    $(CC) ... $(GUI)/wubu_trash.c $(GUI)/wubu_settings.c $(GUI)/wubu_theme.c \
        $(GUI)/wubu_trash_test.c -o $(GUI)/wubu_trash_test
```

## Wayland Integration Notes

**wayland_state_t extended for screenshot access:**
```c
typedef struct {
    // ... existing fields
    int width, height;
    struct wl_buffer *shm_buffer;
    void *shm_data;
} wayland_state_t;
```

**SHM Buffer Setup** in `hosted_init()`:
```c
g_wl.width = state->width;
g_wl.height = state->height;
g_wl.shm_buffer = g_shm_bufs[0].wl_buf;
g_wl.shm_data = g_shm_bufs[0].pixels;
```

## XDG Base Directory Compliance

- Config: `$XDG_CONFIG_HOME/wubu/` ($HOME/.config/wubu)
- Data: `$XDG_DATA_HOME/wubu/` ($HOME/.local/share/wubu) + scan `$XDG_DATA_DIRS`
- State: `$XDG_STATE_HOME/wubu/` ($HOME/.local/state/wubu)
- Cache: `$XDG_CACHE_HOME/wubu/` ($HOME/.cache/wubu)

Use in init functions:
```c
const char *home = getenv("HOME");
const char *xdg_config = getenv("XDG_CONFIG_HOME") ?: home "/.config";
const char *xdg_data = getenv("XDG_DATA_HOME") ?: home "/.local/share";
```