# Clipboard Gap Closure Patterns (2026-06-29)

## Gap: `wubu_clipboard.c` — 43 void casts → Multi-MIME clipboard implemented

**Status**: ✅ DONE (17 tests passing)

### Before (REAL_GAP: defensive void casts only)

```c
// Old: single text/plain storage, void casts in listeners
char *primary_text; size_t primary_len;
char *clipboard_text; size_t clipboard_len;

// Wayland listeners had (void)data; (void)offer; (void)mime_type;
// data_source_send only handled text/plain
static void data_source_send(void *data, struct wl_data_source *source, const char *mime_type, int32_t fd) {
    (void)data; (void)source;
    if (strcmp(mime_type, CLIPBOARD_MIME_TEXT) == 0 && g_clipboard.clipboard_text) {
        write(fd, g_clipboard.clipboard_text, g_clipboard.clipboard_len);
    }
    close(fd);
}
```

### After (Multi-MIME architecture)

```c
// New: ClipboardMimeEntry array supporting 8 MIME types per selection
#define WUBU_CLIPBOARD_MAX_MIME_TYPES 8

typedef struct {
    char *mime_type;
    void *data;
    size_t size;
} ClipboardMimeEntry;

typedef struct {
    ClipboardMimeEntry primary_mimes[WUBU_CLIPBOARD_MAX_MIME_TYPES];
    int primary_mime_count;
    ClipboardMimeEntry clipboard_mimes[WUBU_CLIPBOARD_MAX_MIME_TYPES];
    int clipboard_mime_count;
    // ... Wayland objects ...
} ClipboardState;

// Helper functions (available in both test and Wayland modes)
static int clipboard_find_mime(ClipboardMimeEntry *mimes, int count, const char *mime_type);
static bool clipboard_add_mime(ClipboardMimeEntry *mimes, int *count, const char *mime_type, const void *data, size_t size);
static void clipboard_clear_mimes(ClipboardMimeEntry *mimes, int *count);
static ClipboardMimeEntry* clipboard_get_mime(ClipboardMimeEntry *mimes, int count, const char *mime_type);

// Wayland source send now dispatches by MIME type
static void data_source_send(void *data, struct wl_data_source *source, const char *mime_type, int32_t fd) {
    (void)data; (void)source;
    ClipboardMimeEntry *entry = clipboard_get_mime(g_clipboard.clipboard_mimes, g_clipboard.clipboard_mime_count, mime_type);
    if (entry && entry->data) {
        write(fd, entry->data, entry->size);
    }
    close(fd);
}

// Same pattern for primary_source_send
```

### Supported MIME Types (from `wubu_clipboard.h`)

| Constant | MIME Type |
|----------|-----------|
| `CLIPBOARD_MIME_TEXT` | `text/plain;charset=utf-8` |
| `CLIPBOARD_MIME_HTML` | `text/html` |
| `CLIPBOARD_MIME_IMAGE_PNG` | `image/png` |
| `CLIPBOARD_MIME_IMAGE_JPEG` | `image/jpeg` |
| `CLIPBOARD_MIME_URI_LIST` | `text/uri-list` |

### API Implementation

```c
// Set multiple MIME types at once
bool wubu_clipboard_set_data(ClipboardSelection selection, const ClipboardData *data, int count) {
    // 1. Clear existing MIME entries for selection
    clipboard_clear_mimes(mimes, mime_count);
    
    // 2. Add all MIME types from data array
    for (int i = 0; i < count; i++) {
        clipboard_add_mime(mimes, mime_count, data[i].mime_type, data[i].data, data[i].size);
    }
    
    // 3. Create Wayland source with all MIME types offered
    if (selection == CLIPBOARD_SELECTION_CLIPBOARD && g_clipboard.data_device_manager) {
        g_clipboard.current_source = wl_data_device_manager_create_data_source(g_clipboard.data_device_manager);
        wl_data_source_add_listener(g_clipboard.current_source, &data_source_listener, NULL);
        for (int i = 0; i < *mime_count; i++) {
            wl_data_source_offer(g_clipboard.current_source, mimes[i].mime_type);
        }
        wl_data_device_set_selection(g_clipboard.data_device, g_clipboard.current_source, 0);
    }
    
    // 4. Same for primary selection
    if (selection == CLIPBOARD_SELECTION_PRIMARY && g_clipboard.primary_device_manager) {
        // ... create primary source, offer all MIME types ...
    }
    
    if (g_clipboard.changed_cb) g_clipboard.changed_cb(selection);
    return true;
}

// Retrieve specific MIME type
bool wubu_clipboard_get_data(ClipboardSelection selection, const char *mime_type, void **out_data, size_t *out_len) {
    ClipboardMimeEntry *entry = clipboard_get_mime(mimes, count, mime_type);
    if (!entry || !entry->data || entry->size == 0) return false;
    
    *out_data = malloc(entry->size);
    memcpy(*out_data, entry->data, entry->size);
    if (out_len) *out_len = entry->size;
    return true;
}
```

### Test Coverage (17 tests)

| Test | Description |
|------|-------------|
| 1-3 | Basic clipboard text set/has/get |
| 4-6 | Primary selection text set/has/get |
| 7-8 | Clear clipboard / primary |
| 9 | Convenience copy/paste helpers |
| 10-11 | Empty string / NULL handling |
| 12 | Single MIME data API |
| 13 | Unicode text (CJK + emoji) |
| 14 | Large text (10KB) |
| **15** | **Multi-MIME: text + HTML** |
| **16** | **MIME overwrite behavior** |
| **17** | **Primary multi-MIME: text + URI list** |

### Key Implementation Details

1. **Helpers placed OUTSIDE `#ifndef WUBU_CLIPBOARD_TEST_MODE`** — available in both test and production builds
2. **Empty string handling** — `text[0] == '\0'` triggers clear (not store empty)
3. **Overwrite semantics** — `set_data` clears all existing MIME types before adding new ones
4. **Dual-mode compilation** — test mode (`-DWUBU_CLIPBOARD_TEST_MODE`) and Wayland mode both compile
5. **DND support** — enter/leave/motion/drop callbacks wired to `dnd_cb`
6. **Seat capability handling** — pointer → data_device, keyboard → primary_device

### Verification

```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed

# Test mode (logic only)
make test_clipboard  # 17/17 pass

# Production/Wayland compilation
gcc -c -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM \
    -Isrc/gui -Isrc/kernel -Isrc/hosted \
    src/gui/wubu_clipboard.c -o /tmp/wubu_clipboard_prod.o  # Compiles clean
```