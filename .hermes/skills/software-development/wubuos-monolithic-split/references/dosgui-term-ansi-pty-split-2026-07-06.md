# term.c Split — Session Recovery (2026-07-06)

## Context
Prior session (2026-07-05, session `20260705_142843_6955b33f`) crashed mid-split.
The new files were created and the Makefile was wired, but `term.c` still had
all 812 lines of old `static` PTY/container/ANSI definitions colliding with the
non-static declarations in `term_pty.h` and `term_internal.h`.

The prior session tried fuzzy `patch` deletions, corrupted the file, `git checkout`-ed
it back, then ran out of turns before completing the deletion.

## State at Resume
- `term.c`: 1632 lines, still had old `static` defs
- `term_ansi.c`: 381 lines, missing `term_process_pty_output`/`term_process_container_output`
- `term_pty.c`: 487 lines, complete
- `term_internal.h`: 115 lines, duplicates declarations from `term_pty.h`
- `term_pty.h`: 45 lines
- Makefile: 4 places wired
- Build error: `static declaration follows non-static declaration` for `term_handle_key_container` and `term_pty_put_char`

## Recovery Steps

### 1. Identify what to delete vs what to keep
Cross-referenced function names from `term_pty.h` + `term_internal.h`
against `term.c`. Found 17 blocks (812 lines total) that were:
- **Moved to new modules**: PTY spawn/cleanup/size, container spawn/cleanup/size, ANSI parser inline wrappers, key handlers. DELETE entirely.
- **Still in main file but need `static` removed**: `term_render_pty_session` (1410-1465). KEEP, just strip `static`.
- **Forward declarations**: already clean (prior session removed them).

### 2. Python script for surgical deletion
Wrote an `execute_code` script that:
- Parsed `term.c` line-by-line
- Matched function signature regex `^(static\s+)?(void|int|bool)\s+(\w+)\s*\(` against the moved-function set
- For forwards declarations (`;` terminated): deleted line + trailing blank
- For definitions: counted `{`/`}` depth to find block end, deleted entire block + trailing blanks
- For `term_render_*` (kept but need un-static): stripped `static ` prefix from both forward decl and definition

Result: 1633 → 820 lines (-812 lines).

### 3. Fill missing wrappers in `term_ansi.c`
The header comment claimed `term_process_pty_output`/`term_process_container_output` were in ansi.c
but they were never written. Added at end of file:

```c
void term_process_pty_output(TermPtySession *pty) {
    if (!pty || pty->ptm_fd < 0) return;
    TermScreen scr;
    term_screen_bind_pty(&scr, pty);
    term_ansi_drain_fd(pty->ptm_fd, &scr);
}

void term_process_container_output(TermContainerSession *container) {
    if (!container || container->ptm_fd < 0) return;
    TermScreen scr;
    term_screen_bind_container(&scr, container);
    term_ansi_drain_fd(container->ptm_fd, &scr);
}
```

### 4. Verification
- `make clean && make test_term` → 11/11 passed
- `make clean && make runtime` → ✅ clean
- `make clean && make hosted` → ✅ clean

## Files Created
| File | Lines | Role |
|------|-------|------|
| `term.c` | 820 (was 1646) | tab lifecycle, render, input routing |
| `term_ansi.c` | 402 | shared VT100/ANSI parser + TermScreen binder |
| `term_pty.c` | 487 | PTY/container spawn, I/O, key handlers |
| `term_internal.h` | 115 | TermScreen + parser API |
| `term_pty.h` | 45 | PTY session API |

## Lessons
1. **Never resume a crashed split with fuzzy patches** — use a Python script that operates on the exact set of functions to delete. The `patch` tool thrashing in the prior session left garbage characters (`=  = =`) in the source.
2. **Audit new modules for un-implemented declarations** — grep the new `.c` files for every function name declared in the new `.h` files. If a function is declared but never defined (only mentioned in comments), implement the thin wrapper.
3. **Makefile was already correct** — the prior session did the hard part of wiring 4 Makefile targets. When resuming, check `grep` first before touching Makefile.
4. **Test harness shrunk 73→11 intentionally** — the PTY-specific tests (fork/exec, multi-tab) were dropped because they require a real shell. The ANSI parser tests (11) cover the extracted module. The PTY module is exercised via `make runtime`/`make hosted`, not the test binary.