# Clipboard Implementation Patterns — Verified Working (2026-06-29)

## Test Results
```bash
make test_clipboard  # 14/14 PASS
```

## Implementation Summary

The clipboard system implements **both clipboard selection (Ctrl+C/V)** and **primary selection (highlight/middle-click)** using Wayland protocols.

### Key Architecture

**Test Mode Compilation** — `#ifndef WUBU_CLIPBOARD_TEST_MODE` guards all Wayland-specific code:
```c
#ifndef WUBU_CLIPBOARD_TEST_MODE
#include <wayland-client.h>
#include "primary-selection-client.header"
#endif

typedef struct {
    char *primary_text;
    size_t primary_len;
    char *clipboard_text;
    size_t clipboard_len;

#ifndef WUBU_CLIPBOARD_TEST_MODE
    struct wl_data_device *data_device;
    struct wl_data_device_manager *data_device_manager;
    struct wl_seat *seat;
    struct zwp_primary_selection_device_manager_v1 *primary_device_manager;
    struct zwp_primary_selection_device_v1 *primary_device;
    // ... Wayland objects
#endif

    ClipboardChangedCallback changed_cb;
    ClipboardDnDCallback dnd_cb;
    bool dnd_active;
} ClipboardState;
```

**Test Mode Implementations** — provide full API without Wayland (compiles and runs without Wayland):
```c
#ifdef WUBU_CLIPBOARD_TEST_MODE
int wubu_clipboard_init(void *wl_seat) {
    (void)wl_seat;
    memset(&g_clipboard, 0, sizeof(g_clipboard));
    return 0;
}

bool wubu_clipboard_set_text(ClipboardSelection selection, const char *text) {
    // Full implementation using local buffers only
}

bool wubu_clipboard_get_text(ClipboardSelection selection, char **out_text, size_t *out_len) {
    // Return local buffer copy
}

void wubu_clipboard_clear(ClipboardSelection selection) {
    // Free local buffers
}
// ... all API functions implemented
#endif
```

**Data Transfer via Pipe** — synchronous read from Wayland offer with timeout:
```c
static bool ex_clipboard_read_pipe(int fd, char **out_text, size_t *out_len, int timeout_ms) {
    struct pollfd pfd = { .fd = fd, .events = POLLIN };
    if (poll(&pfd, 1, timeout_ms) <= 0) { close(fd); return false; }
    char buf[8192]; size_t total = 0; char *result = NULL; ssize_t n;
    while ((n = read(fd, buf, sizeof(buf))) > 0) {
        char *new_result = realloc(result, total + n + 1);
        if (!new_result) { free(result); close(fd); return false; }
        result = new_result; memcpy(result + total, buf, n); total += n;
    }
    close(fd); if (n < 0) { free(result); return false; }
    if (result) result[total] = '\0'; *out_text = result; *out_len = total; return true;
}
```

**Selection Handler** (non-blocking with 100ms timeout):
```c
static void data_device_selection(void *data, struct wl_data_device *device, struct wl_data_offer *offer) {
    g_clipboard.current_offer = offer;
    g_clipboard.current_selection = CLIPBOARD_SELECTION_CLIPBOARD;
    if (offer) {
        wl_data_offer_add_listener(offer, &data_offer_listener, NULL);
        int fds[2];
        if (pipe(fds) == 0) {
            wl_data_offer_receive(offer, CLIPBOARD_MIME_TEXT, fds[1]);
            close(fds[1]);
            char *text = NULL; size_t len = 0;
            if (ex_clipboard_read_pipe(fds[0], &text, &len, 100)) {
                if (g_clipboard.clipboard_text) free(g_clipboard.clipboard_text);
                g_clipboard.clipboard_text = text;
                g_clipboard.clipboard_len = len;
                if (g_clipboard.changed_cb) g_clipboard.changed_cb(CLIPBOARD_SELECTION_CLIPBOARD);
            }
        }
    } else {
        if (g_clipboard.clipboard_text) { free(g_clipboard.clipboard_text); g_clipboard.clipboard_text = NULL; }
        g_clipboard.clipboard_len = 0;
        if (g_clipboard.changed_cb) g_clipboard.changed_cb(CLIPBOARD_SELECTION_CLIPBOARD);
    }
}
```

### Primary Selection (Highlight/Middle-Click)

Uses `zwp_primary_selection_device_manager_v1` protocol (KDE/GNOME standard):
- Bound in `hosted.c` registry_global for `"zwp_primary_selection_device_manager_v1"`
- Creates device per seat on `WL_SEAT_CAPABILITY_KEYBOARD`
- Selection changes trigger `primary_device_selection` callback
- Data read same way via `zwp_primary_selection_offer_v1_receive`

### Makefile Test Target

```makefile
test_clipboard:
	$(CC) -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM -DWUBU_CLIPBOARD_TEST_MODE \
		-I$(GUI) -I$(KERNEL) \
		$(GUI)/wubu_clipboard.c $(GUI)/wubu_clipboard_test.c \
		-o $(GUI)/wubu_clipboard_test
	$(GUI)/wubu_clipboard_test
```

### Test Coverage (14 Tests)

| Test | Description |
|------|-------------|
| 1 | Set clipboard text |
| 2 | Check clipboard has data |
| 3 | Get clipboard text (round-trip) |
| 4 | Set primary selection |
| 5 | Check primary selection has data |
| 6 | Get primary selection text |
| 7 | Clear clipboard |
| 8 | Clear primary selection |
| 9 | Convenience helpers (copy/paste, primary copy/paste) |
| 10 | Empty string handling |
| 11 | NULL handling |
| 12 | Set data with MIME type |
| 13 | Unicode text (UTF-8) |
| 14 | Large text (10KB) |

## Remaining Gaps (43 void casts → Wayland Production)

| Gap | Location | Fix Needed |
|-----|----------|------------|
| `wl_display_roundtrip` after setting selection | `wubu_clipboard_set_text` | Add `wl_display_roundtrip(g_wl.display)` after `wl_data_device_set_selection` |
| MIME type negotiation | `data_offer_offer`, `primary_offer_offer` | Track offered MIME types, support `text/html`, `image/png`, `text/uri-list` |
| Primary selection device cleanup | `wubu_clipboard_shutdown` | Add `zwp_primary_selection_device_v1_destroy` |
| DND action handling | `data_source_action`, `data_source_dnd_drop_performed` | Implement DND action feedback |
| UTF-8 validation on receive | `ex_clipboard_read_pipe` | Validate UTF-8 before storing |
| Selection timeout/staleness | — | Add timestamp, auto-clear stale selections |
| Large data handling (>64KB) | `ex_clipboard_read_pipe` | Increase buffer, handle partial reads |

## Related Skills
- `wubuos-architecture` — Wayland callback patterns in `hosted.c`
- `wubuos-test-suite` — Running clipboard and GUI tests