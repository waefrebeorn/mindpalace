# HolyC Terminal Implementation Reference

## Overview
The HolyC Terminal (`HolycTerm`) is a first-class draggable GUI window in `wm.c` with a persistent `HCCompiler` per terminal instance. This enables REPL sessions with variable/function persistence across evaluations.

## Key Structures

```c
// In wm.c
#define HOLYC_TERM_MAX_LINES  2000
#define HOLYC_TERM_LINE_LEN   512
#define HOLYC_TERM_HISTORY    100

typedef struct {
    HCCompiler       compiler;        // Persistent HolyC compiler state
    char             lines[HOLYC_TERM_MAX_LINES][HOLYC_TERM_LINE_LEN];
    int              line_count;
    char             input[HOLYC_TERM_LINE_LEN];
    int              input_pos;
    int              cursor_blink;
    char             history[HOLYC_TERM_HISTORY][HOLYC_TERM_LINE_LEN];
    int              history_count;
    int              history_pos;     // -1 = current input, 0..count-1 = history
    bool             initialized;
} HolycTerm;

static HolycTerm g_holyc_terms[DOSGUI_MAX_WINDOWS] = {0};
```

## API

```c
// Spawn a HolyC terminal window
DosGuiWindow *wm_spawn_holyc_term(int x, int y, int w, int h);

// HolycTerm operations
static void holyc_term_init_compiler(HolycTerm *term);
static void holyc_term_eval(HolycTerm *term, const char *input);
static void holyc_term_key(DosGuiWindow *win, uint32_t key, uint32_t mods);
static void holyc_term_draw(DosGuiWindow *win, uint32_t *fb, int fb_w, int fb_h);
```

## Integration Points

1. **Desktop Icon**: `desktop.c` registers "HolyC Term" at grid (1,3)
2. **Start Menu**: `startmenu.c` adds "HolyC Terminal" under Programs → WuBuOS
3. **Click Handler**: `apps.c` provides `launch_holyc_term()`

## Usage in HolyC

```holyc
// Variables persist across evaluations
I64 x = 10;
x + 5;  // = 15

// Functions persist
I64 fact(I64 n) { if (n <= 1) return 1; return n * fact(n-1); }
fact(5);  // = 120
```

## Test Coverage

- `test_holyc_terminal`: 73 tests (lexer, parser, codegen, eval, persistent state)
- Run: `make test_holyc_terminal`