# Missing Symbols Fix Patterns (2026-06-30)

## Context
Fixed all missing symbols preventing hosted binary build + screenshot capture. Original issue from BATTLESHIP.md gap list.

## Fixed Symbols & Patterns

### 1. StyxFS POSIX API (styxfs.h/c)
**Missing**: `styxfs_stat`, `styxfs_opendir`, `styxfs_open`, `styxfs_read`, `styxfs_write`, `styxfs_close`, `styxfs_readdir`, `styxfs_opendir`, `styxfs_create`, `styxfs_remove`, `styxfs_rename`, `styxfs_mkdir`, `styxfs_rmdir`

**Pattern**: Add POSIX headers to `.h` and `.c`, implement using existing `styxfs_resolve()` and `file_alloc()`:
```c
// styxfs.h - add POSIX types
#include <sys/types.h>
#include <sys/stat.h>
#include <dirent.h>
#include <unistd.h>
#include <fcntl.h>

// styxfs.c - implement using existing internal state
int styxfs_stat(const char *path, struct stat *st) {
    styxfs_file_t *f = styxfs_resolve(g_styxfs_server, path, 0);
    if (!f) return -1;
    memset(st, 0, sizeof(struct stat));
    if (f->qid_type == STX_QTDIR || f->is_dir) {
        st->st_mode = S_IFDIR | 0755;
    } else {
        st->st_mode = S_IFREG | 0644;
    }
    st->st_size = (off_t)f->payload_size;
    st->st_mtime = (time_t)f->mtime;
    // ... rest
}
```

### 2. Clipboard Get Text (wubu_clipboard.c)
**Missing**: `wubu_clipboard_get_text` for non-test mode

**Pattern**: Implement in both `#ifndef WUBU_CLIPBOARD_TEST_MODE` and `#else` blocks:
```c
// In Wayland mode section (before #else)
bool wubu_clipboard_get_text(ClipboardSelection selection, char **out_text, size_t *out_len) {
    ClipboardMimeEntry *mimes = (selection == CLIPBOARD_SELECTION_PRIMARY) ? 
        g_clipboard.primary_mimes : g_clipboard.clipboard_mimes;
    int count = (selection == CLIPBOARD_SELECTION_PRIMARY) ? 
        g_clipboard.primary_mime_count : g_clipboard.clipboard_mime_count;
    
    ClipboardMimeEntry *entry = clipboard_get_mime(mimes, count, CLIPBOARD_MIME_TEXT);
    if (!entry || !entry->data || entry->size == 0) return false;
    
    *out_text = malloc(entry->size + 1);
    if (!*out_text) return false;
    memcpy(*out_text, entry->data, entry->size);
    (*out_text)[entry->size] = '\0';
    if (out_len) *out_len = entry->size;
    return true;
}
```

### 3. Start Menu Shutdown (startmenu.c)
**Missing**: `startmenu_shutdown`

**Pattern**: Simple wrapper calling existing shutdown:
```c
void startmenu_shutdown(void) {
    shutdown();
}
```

### 4. Public mkdir_p (wubu_arch.h/c)
**Missing**: `mkdir_p` used by `wubu_trash.c`

**Pattern**: Expose static helper as public API:
```c
// wubu_arch.h
int wubu_arch_mkdir_p(const char *path, mode_t mode);

// wubu_arch.c
int wubu_arch_mkdir_p(const char *path, mode_t mode) {
    return mkdir_p(path, mode);
}
```

### 5. Infinite Recursion Fix (apps.c)
**Problem**: Launch functions called `app_launch()` which looked them up in registry and called them back → infinite recursion.

**Pattern**: Launch functions create windows DIRECTLY, not via registry:
```c
// BEFORE (recursive):
DosGuiWindow* launch_file_manager(void) { return app_launch(DESK_ICON_EXPLORER); }

// AFTER (direct):
DosGuiWindow* launch_file_manager(void) {
    DosGuiWindow* win = wm_create(100, 80, 800, 600, "File Manager");
    return win;
}
```

### 6. Hosted Headless Screenshot (hosted.c)
**Problem**: `--screenshot` flag set mode to HEADLESS but render loop only rendered in GUI mode.

**Pattern**: Render desktop in all non-TEMPLE modes:
```c
if (state->mode == HMODE_GUI) {
    render_desktop(state);
    vbe_swap();
    // copy to framebuffer
} else if (state->mode == HMODE_TEMPLE) {
    // black
} else {
    // HMODE_HEADLESS or HMODE_CONSOLE - render for screenshot
    render_desktop(state);
    vbe_swap();
    VBEState *vs = vbe_state();
    if (vs && vs->fb) {
        memcpy(state->framebuffer, vs->fb, ...);
    }
}

// Also: exit loop after rendering a couple frames in headless
if (screenshot_requested && state->mode == HMODE_HEADLESS) {
    frame_count++;
    if (frame_count >= 2) {
        state->running = false;
        break;
    }
}
```

### 7. Makefile Wayland Protocol Linking
**Problem**: `zwp_primary_selection_device_manager_v1_interface` undefined reference.

**Pattern**: Add generated Wayland protocol file to HOSTED_OBJS:
```makefile
HOSTED_OBJS = ... $(HOSTED)/primary-selection-private.o

$(HOSTED)/primary-selection-private.o: $(HOSTED)/primary-selection-private.c
	$(CC) $(CFLAGS) -I$(HOSTED) -c $< -o $@

hosted: $(HOSTED_OBJS) $(HOSTED)/xdg-shell-private.o
	$(CC) ... $(HOSTED)/xdg-shell-private.o $(HOSTED)/primary-selection-private.o ...
```

## Test Verification Commands
```bash
# All fixed symbols verified via these tests:
make test_clipboard       # 17/17 PASS
make test_styxfs          # 11/11 PASS
make test_explorer # 74/74 PASS
make test_startmenu # 4/4 PASS
make test_wm       # 16/16 PASS
make test_holyc           # 84/84 PASS
make test_vsl             # 55/55 PASS
make test_term     # 4/4 PASS

# Hosted binary:
make hosted               # Builds clean
./src/hosted/wubu --screenshot /tmp/test.ppm  # Generates PPM
```