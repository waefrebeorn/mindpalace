# WuBuOS term Monolithic Split — Session 2026-07-05

## Overview

Split `src/gui/term.c` (1646 lines) into three modules:

| File | Lines | Role |
|------|-------|------|
| `term.c` | ~960 | Tab/window management, render orchestration, public API |
| `term_ansi.c` | 381 | Canonical VT100/ANSI parser (superset: 256-color SGR, full ED/EL, DECSC/DECRC) |
| `term_pty.c` | 478 | PTY/container session management, I/O, key handling |

Plus headers:
- `term_internal.h` — Polymorphic `TermScreen` abstraction + shared API
- `term_pty.h` — PTY/container session management API

## Problem: Duplicate ANSI Parsers

Two near-identical inline parsers existed:
- `term_process_pty_output` (~240 lines) — superset with 256-color SGR, full CSI modes
- `term_process_container_output` (~170 lines) — subset, missing 256-color, DECSC/DECRC, fewer CSI modes

Both used buggy `static` parser state shared across ALL tabs (one tab's CSI could corrupt another's).

## Solution: Dedup-First Extraction

### 1. Polymorphic `TermScreen` Abstraction

Both `TermPtySession` and `TermContainerSession` have identical screen/attrs/cursor layouts:

```c
typedef struct {
    int    *cols, *rows;
    int    *cursor_x, *cursor_y;
    int    *saved_cursor_x, *saved_cursor_y;
    uint8_t *cur_attr, *cur_fg, *cur_bg;
    char    *screen;   // flat: row * MAX_COLS + col
    uint8_t *attrs;
    int      max_cols, max_rows;
} TermScreen;
```

Binders wire the flat pointers:
```c
void term_screen_bind_pty(TermScreen *out, TermPtySession *pty) { ... }
void term_screen_bind_container(TermScreen *out, TermContainerSession *container) { ... }
```

### 2. Canonical Parser in `term_ansi.c`

Single implementation `term_ansi_parse(TermScreen*, const char*, int)` handles:
- Normal text, CR/LF, tab, backspace, bell
- ESC/CSI state machine
- Cursor movement (CUU/CUD/CUF/CUB/CUP/HVP)
- Erase in Display (ED: 0,1,2,3)
- Erase in Line (EL: 0,1,2)
- SGR: bold/underline/reverse, 16-color, 256-color (38;5;N / 48;5;N)
- Save/Restore cursor (DECSC/DECRC)
- Mode set/reset (SM/RM) + DSR (no-ops)

**Per-call parser state** (not shared) — `AnsiParser ap` on stack each call. Original buggy shared state eliminated.

### 3. Thin Wrappers in `term.c`

```c
static void term_process_container_output(TermContainerSession *container) {
    char buf[4096];
    ssize_t n = read(container->ptm_fd, buf, sizeof(buf) - 1);
    if (n <= 0) return;
    TermScreen scr; term_screen_bind_container(&scr, container);
    term_ansi_parse(&scr, buf, (int)n);
}

static void term_process_pty_output(TermPtySession *pty) {
    char buf[4096];
    ssize_t n = read(pty->ptm_fd, buf, sizeof(buf) - 1);
    if (n <= 0) return;
    TermScreen scr; term_screen_bind_pty(&scr, pty);
    term_ansi_parse(&scr, buf, (int)n);
}
```

### 4. PTY Module Extraction (`term_pty.c`)

~567 lines moved:
- `term_pty_spawn`, `term_pty_cleanup`
- `term_update_pty_size`, `term_reset_pty_screen`
- `term_pty_push_line`
- `term_pty_put_char`, `term_pty_cursor_move`
- `term_handle_key_pty`, `term_handle_key_holyc`, `term_handle_key_container`
- `term_container_spawn`, `term_container_cleanup`, `term_update_container_size`

## Test Coverage Added

7 direct parser tests in `term_test.c`:
- Basic text + CR/LF
- Cursor movement (CUU/CUD/CUF/CUB)
- Cursor position (CUP/HVP)
- Erase display/line (ED/EL)
- SGR (bold, colors, 256-color, reset)
- Save/restore cursor (DECSC/DECRC)
- Polymorphic container session — same parser, different backing struct

## Makefile Updates (4 locations)

```makefile
# GUI_OBJS
GUI_OBJS = ... $(GUI)/term.o $(GUI)/term_ansi.o $(GUI)/term_pty.o ...

# HOSTED_OBJS
HOSTED_OBJS = ... $(GUI)/term.o $(GUI)/term_ansi.o $(GUI)/term_pty.o ...

# hosted direct-compile
... $(GUI)/term.c $(GUI)/term_ansi.c $(GUI)/term_pty.c ...

# test_term direct-compile
... $(GUI)/term.c $(GUI)/term_ansi.c $(GUI)/term_pty.c ...
```

## Verification

```
make clean && make test_term    → 11/11 PASS (4 original + 7 new)
make clean && make runtime             → ✅ Clean build
make test_high_gui_tier                              → All PASS
```

## Key Learnings

1. **Dedup-first** is the right order when the same algorithm appears inline multiple times. Extract the superset first, then thin wrappers.

2. **Polymorphic screen abstraction** works because both backing structs have identical field layouts for the parser-relevant fields. Flat pointer arithmetic (`screen[row * MAX_COLS + col]`) is safe.

3. **Per-call parser state** is both a correctness fix and a dedup prerequisite — original shared `static` state was already broken for multi-tab.

4. **4 Makefile locations** must all be updated for GUI modules (GUI_OBJS, HOSTED_OBJS, hosted direct-compile, test direct-compile). Missing any one masks link errors via stale `.o`.

5. **Forward declarations in host .c** must match internal header declarations (non-static) — remove `static` from both forward decl AND definition in host.

6. **Test binary direct-compile** is the most honest verification — compiles all source files together, no stale `.o` can mask missing symbols.