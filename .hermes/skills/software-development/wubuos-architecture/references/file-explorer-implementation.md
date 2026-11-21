# File Explorer Implementation Patterns — WuBuOS

## Overview
Full Win98/XP-style file manager with tree view, breadcrumbs, file list, preview pane, and file operations.

## Key Files
- `src/gui/explorer.c` / `.h` — Core implementation (2328 lines)
- `src/gui/explorer_test.c` — Unit test (71 tests)

## Key State Structures

### ExExplorerState
```c
typedef struct {
    char current_path[EX_MAX_PATH];
    ExTreeNode *tree_root;
    ExTreeNode *tree_selected;
    ExEntry entries[EX_MAX_ENTRIES];
    int entry_count;
    int list_scroll_y;
    int selected_indices[EX_MAX_SELECTION];
    int selection_count;
    int focus_idx;
    int anchor_idx;
    ExViewMode view_mode;
    ExSortColumn sort_column;
    bool sort_ascending;
    ExPreviewState preview;
    bool preview_visible;
    int focus_pane;  // 0=tree, 1=breadcrumbs, 2=list, 3=preview
    // ... file operations, context menu, clipboard, zip state
} ExExplorerState;
```

### Rename State
```c
static struct {
    bool active;
    int entry_idx;
    char buffer[256];
    int cursor_pos;
    int buffer_len;
} g_rename_state = {0};
```

### Find State
```c
static struct {
    bool active;
    char query[EX_FIND_MAX_LEN];
    int query_len;
    int last_match;
    bool case_sensitive;
} g_find_state = {0};
```

## Inline Rename (F2)
```c
void explorer_rename(int idx) {
    g_rename_state.active = true;
    g_rename_state.entry_idx = idx;
    strncpy(g_rename_state.buffer, entry->name, sizeof(g_rename_state.buffer) - 1);
    g_rename_state.buffer_len = strlen(g_rename_state.buffer);
    g_rename_state.cursor_pos = g_rename_state.buffer_len;

    if (!g_explorer.show_extensions) {
        char *dot = strrchr(g_rename_state.buffer, '.');
        if (dot) *dot = '\0';
        g_rename_state.buffer_len = strlen(g_rename_state.buffer);
        g_rename_state.cursor_pos = g_rename_state.buffer_len;
    }
    snprintf(g_explorer.status_text, sizeof(g_explorer.status_text),
             "Rename: type new name, Enter=confirm, Esc=cancel");
}
```

Key handler handles:
- Escape → cancel
- Enter → commit
- Backspace → delete char before cursor
- Printable chars → insert at cursor (using `memmove`)

## File Open (Enter) — Fork/Exec with Fallback Chain
```c
void explorer_open_file(ExEntry *entry) {
    pid_t pid = fork();
    if (pid == 0) {
        execlp("xdg-open", "xdg-open", path, (char *)NULL);
        
        // Text editors
        execlp("vim", "vim", path, (char *)NULL);
        execlp("nano", "nano", path, (char *)NULL);
        
        // Images
        execlp("eog", "eog", path, (char *)NULL);
        execlp("feh", "feh", path, (char *)NULL);
        // PDFs
        execlp("evince", "evince", path, (char *)NULL);
        execlp("zathura", "zathura", path, (char *)NULL);
        // Audio
        execlp("vlc", "vlc", path, (char *)NULL);
        execlp("mpv", "mpv", path, (char *)NULL);
        // Video
        execlp("vlc", "vlc", path, (char *)NULL);
        execlp("mpv", "mpv", path, (char *)NULL);
        
        _exit(127);
    }
}
```

## Tab Navigation (Pane Focus Cycling)
```c
case 9: /* Tab */
    if (g_explorer.focus_pane == 0) g_explorer.focus_pane = 1;  // tree → breadcrumbs
    else if (g_explorer.focus_pane == 1) g_explorer.focus_pane = 2;  // breadcrumbs → list
    else if (g_explorer.focus_pane == 2) g_explorer.focus_pane = 3;  // list → preview
    else g_explorer.focus_pane = 0;  // preview → tree
    snprintf(g_explorer.status_text, sizeof(g_explorer.status_text),
             "Focus: %s", g_explorer.focus_pane == 0 ? "Tree" :
             g_explorer.focus_pane == 1 ? "Breadcrumbs" :
             g_explorer.focus_pane == 2 ? "File List" : "Preview");
    break;
```

## Find Mode (Ctrl+F)
```c
static struct {
    bool active;
    char query[EX_FIND_MAX_LEN];
    int query_len;
    int last_match;
    bool case_sensitive;
} g_find_state = {0};
```

F3 (Find Next) implemented in key handler.

## Shift-Click Range Selection
```c
// Key handler tracks modifiers
static bool g_shift_pressed = false;
static bool g_ctrl_pressed = false;

void explorer_handle_key(uint32_t key, uint32_t mods) {
    g_shift_pressed = (mods & 0x01) != 0;
    g_ctrl_pressed = (mods & 0x02) != 0;
    // ...
}

// Mouse handler uses g_shift_pressed for range selection
void explorer_handle_mouse(int x, int y, int btn, int kind) {
    bool shift = g_shift_pressed;
    // ... shift-click range selection logic
}
```

## Zip Archive Mount (Stub - requires libzip)
```c
bool explorer_mount_zip(const char *zip_path) {
    if (!zip_path) return false;
    strncpy(g_explorer.current_zip_path, zip_path, EX_MAX_PATH - 1);
    g_explorer.in_zip_archive = true;
    explorer_navigate(zip_path);
    return false; // Not implemented - requires libzip
}
```

## Test Coverage (71 tests)
1. Init/Shutdown
2. Navigation (navigate, go_up, go_back, go_forward, refresh)
3. View Modes (Details, Icons, List, Tiles)
4. Sort (Size, Date, Type, Name, ascending/descending)
5. Toggles (hidden, extensions, preview, toolbar)
6. Selection (select_all, clear, toggle, range, invalid indices)
7. File Operations Clipboard (copy/cut/paste/delete with no selection)
8. Helper Functions (type_str, view_mode_name, colors, format_size, format_time)
9. Drive Enumeration (root + /mnt + /media)
10. Navigation History (back/forward)
11. Zip Archive (stub)
12. State Accessors
13. Find (Ctrl+F)
14. Shift-Select (mouse)
15. Image Preview (NULL pixels, pixel data, large images)

Run: `make test_explorer`