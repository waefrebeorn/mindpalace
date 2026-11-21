# A self-contained terminal interface in C11

No UI library: termios for raw mode, the alternate screen for the canvas,
ANSI for colour, `select` for the refresh loop. About 200 lines.

## Setup and teardown

```c
static struct termios g_saved;
static int g_raw = 0;

static void raw_on(void) {
    if (tcgetattr(STDIN_FILENO, &g_saved) != 0) return;
    struct termios t = g_saved;
    t.c_lflag &= ~(ICANON | ECHO);
    t.c_cc[VMIN] = 0;              /* non-blocking reads */
    t.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSANOW, &t);
    g_raw = 1;
    printf("\x1b[?1049h");        /* alternate screen */
    printf("\x1b[?25l");          /* hide the cursor */
    fflush(stdout);
}

static void raw_off(void) {
    if (!g_raw) return;
    printf("\x1b[?25h");
    printf("\x1b[?1049l");
    fflush(stdout);
    tcsetattr(STDIN_FILENO, TCSANOW, &g_saved);
    g_raw = 0;
}
```

Always restore, including on the quit path and on Ctrl-C. A leaked raw
terminal leaves the user's shell unusable.

Ctrl-C arrives as **SIGINT**, not as a byte, because `ISIG` is left enabled.
A handler that only sets a flag lets the loop restore cleanly -- do NOT
clear `ISIG` and treat 0x03 as a keypress, and do NOT leave the default
action in place (it kills the process with the screen still raw):

```c
static volatile sig_atomic_t g_interrupted = 0;
static void on_signal(int sig) { (void)sig; g_interrupted = 1; }

/* in raw_on(), after tcsetattr: */
signal(SIGINT,  on_signal);
signal(SIGTERM, on_signal);

/* in the loop, where select() is called: */
if (ready < 0 && errno == EINTR) { if (g_interrupted) break; continue; }
if (ready <= 0)               { if (g_interrupted) break; continue; }

/* after the loop, before returning: */
raw_off();
```

Verify it in a pty (not by eye): spawn the interface, send SIGINT, and assert
the captured output contains both `\x1b[?1049l` (alternate screen exited) and
`\x1b[?25h` (cursor restored). A shell-level `&` job cannot prove this -- the
wrapper pid is not the process under test.

## Size, clear, and the refresh loop

```c
static void term_size(int *w, int *h) {
    struct winsize ws;
    *w = 80; *h = 24;                       /* a sane default */
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0 && ws.ws_col > 0) {
        *w = ws.ws_col; *h = ws.ws_row;
    }
}

for (;;) {
    sample_and_draw();
    fd_set fds; FD_ZERO(&fds); FD_SET(STDIN_FILENO, &fds);
    struct timeval tv = {1, 0};             /* refresh about once a second */
    if (select(STDIN_FILENO + 1, &fds, NULL, NULL, &tv) <= 0) continue;
    char key[8];
    ssize_t n = read(STDIN_FILENO, key, sizeof(key));
    if (n <= 0) continue;
    handle_key(key, (int)n);
}
```

## Pitfalls

- **Arrow keys arrive as three bytes**: `ESC [ A/B/C/D`. Read them together
  and dispatch on the third byte; a one-byte read leaves the `[` and the
  letter queued as bogus keypresses.
- **Gate the whole interface on `isatty`** for stdin AND stdout. Piped output
  is the plain report.
- **Position with `\x1b[<row>;<col>H`** (1-based) and keep a `text(x, y, s,
  color)` helper that no-ops off-screen; drawing past the edge of a small
  terminal wraps and smears.
- **256-colour codes are `\x1b[38;5;<n>m`**; reset with `\x1b[0m` after every
  coloured run or the colour bleeds into the next line.
- **Wrap long sentences yourself** -- a headline longer than the terminal
  width will wrap mid-word and push the layout apart. Greedy wrap on spaces
  into a fixed line buffer.
- **A status line that changes length shifts everything below it.** Keep the
  panel sizes fixed and let the text inside them change.
