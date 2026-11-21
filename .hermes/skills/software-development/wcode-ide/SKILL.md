---
name: wcode-ide
description: Use when working on the W-CODE agentic IDE.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wcode, ide, agentic, c11, holyc, wubuos]
    related_skills: [wubuos-dosgui-wm, wubuos-test-suite, waefrebeorn-repo-creation]
---

# W-CODE -- the WuBuOS agentic IDE

## When to Use

- Any work in `/home/wubu/W-Code` or on the `waefrebeorn/W-Code` repo.
- Adding an editor, agent, build or syntax feature to the IDE.
- Wiring W-CODE into WuBuOS as a desktop app.
- Explaining where W-CODE sits in the WuBuOS body (kernel -> VSL -> Styx ->
  KV-FS -> IDE).

## What it is

An IDE with two frontends over **one core**:

| frontend | how you talk to it |
|---|---|
| human | raw-termios TUI: file tree, editor with C11/HolyC syntax colour, build output, status bar |
| agent | newline-delimited JSON on stdin/stdout (`--agent`) |

Both drive the SAME buffer, file tree, build runner and diagnostic parser.
There is no second code path, so an agent's view of a project cannot drift
from the human's. **Never add an agent-only or TUI-only shortcut around the
core** -- if an op is worth having, it goes in the shared module.

## Where it lives

- Repo: `https://github.com/waefrebeorn/W-Code` (branch `main`)
- Local: `/home/wubu/W-Code`
- License: WaefreBeorn Umbrella License v3.0 (all WaefreBeorn repos)
- W-CODE is an **app**, not the OS. It sits on top of WuBuOS: kernel at ring 0
  -> VSL (NT-organised syscalls) -> Styx/9P file layering -> KV-FS -> W-CODE.

## Build and verify

```bash
cd /home/wubu/W-Code
make            # builds ./wcode
make test       # the assertion suite -- run it after every change
make agent-demo # scripted agent round trip
```

Always close with BOTH:

```bash
make test                                                  # 100/100 expected
cc -O1 -g -std=c11 -D_POSIX_C_SOURCE=200809L \
   -fsanitize=address,undefined -Isrc \
   src/wcode_buf.c src/wcode_syntax.c src/wcode_fs.c \
   src/wcode_build.c src/wcode_agent.c tests/wcode_test.c -o /tmp/wt_asan
/tmp/wt_asan      # must be 0 ASan/UBSan reports
```

Then prove it from a CLEAN CLONE, not the working tree:

```bash
rm -rf /tmp/wc_clone && git clone -q https://github.com/waefrebeorn/W-Code.git /tmp/wc_clone
cd /tmp/wc_clone && make && make test
```

## Module map -- one concern per file

| file | owns |
|---|---|
| `src/wcode_buf.c` | text buffer + editor operations (insert/delete/split/join) |
| `src/wcode_syntax.c` | C11/HolyC token classification + per-line run scanner |
| `src/wcode_fs.c` | lazy file tree (a directory is read only when expanded) |
| `src/wcode_build.c` | fork/exec with captured output + GCC/Clang diagnostic parser |
| `src/wcode_agent.c` | the JSON protocol AND the shared IDE state both frontends use |
| `src/wcode_tui.c` | panels, key handling, prompts |
| `src/main.c` | `--agent` / `--version` / `--help` |
| `src/wcode.h` | the whole public surface -- keep it the single include |

Adding a feature means adding it to the core module and exposing it through
`wcode.h`; the TUI and the agent then both get it.

## Agent protocol

One JSON object in, one JSON object out. Ops:

`status` `list` `read` `open` `write` `save` `edit` `keys` `build` `diags` `help`

- `status` -- version, root, open path, cursor, line count, last build
- `list {path?}` -- directory entries, dirs first
- `read {path?}` -- file text, or the open buffer when `path` is omitted
- `open {path}` -- load into the buffer
- `write {path,text}` / `save {path?}`
- `edit {line,col,insert?,remove?}` -- edit at a position
- `keys {keys:[...]}` -- replay logical key names through the editor
- `build {cwd,argv:[...]}` -- run, capture, parse diagnostics
- `diags` -- last build's diagnostics with path/line/col/severity

Verify the protocol by piping a script, never by reading the code:

```bash
printf '%s\n' '{"op":"status"}' '{"op":"open","path":"src/wcode.h"}' \
  '{"op":"edit","line":1,"col":1,"insert":"/* x */"}' \
  '{"op":"save"}' '{"op":"build","cwd":".","argv":["make","-n"]}' \
  '{"op":"diags"}' | ./wcode --agent
```

## Conventions

- **C11**, `-D_POSIX_C_SOURCE=200809L`, no dependencies beyond libc. It must run
  over a serial console and inside a WuBuOS container with no terminfo.
- Tabs expand to 4 spaces; the editor inserts spaces, never a literal tab.
- Language is detected from the extension: `.c/.h/.cpp/.cc` -> C11,
  `.hc/.holyd` -> HolyC, `.md/.txt` -> plain. Unknown -> C11.
- C11 and HolyC are the system code. HolyC sources get the same editor, the
  same syntax colour and the same build path as C.

## Integration state in WuBuOS

W-CODE builds clean and its suite is **120 passed, 0 failed**. It IS now wired into
WuBuOS as a first-class app:

- `launch_wcode()` in `src/apps/apps.c`, declared in `apps.h`, registered in the single
  app table `g_app_defs[]` (`DESK_ICON_COUNT + 16`) -- so it appears on the desktop and
  in the Start menu.
- Binary resolution order: `$WUBU_WCODE_BIN`, `/usr/local/bin/wcode`,
  `/usr/bin/wcode`, `$HOME/W-Code/wcode` (dev checkout), then PATH via execvp.
- Hosting goes through the real tabbed terminal: `wcode_terminal_launch()` (defined in
  `src/gui/term.c`) opens/reuses the terminal window and calls `term_spawn_exec()` to
  exec the TUI directly on a pty. apps.c only declares it WEAK.
- Opening a FILE in W-CODE goes through `ex_launch_with_wcode()` (defined in apps.c,
  declared WEAK in `src/gui/explorer_internal.h`), called by the Explorer's
  "Open With..." menu item and by `explorer_open_entry()`. It takes an optional path
  argument, so the desktop launcher and the file-open path share one binary-resolution
  helper instead of duplicating the lookup order.

What WuBuOS already had that this rode on:

- `src/gui/term*.c` -- a COMPLETE tabbed PTY terminal: `term_pty.c` (`posix_openpt`,
  fork, setsid/TIOCSCTTY, winsize), `term_ansi.c`, `term_render.c`, `term_tabs.c`,
  plus `term_spawn_shell` / `term_spawn_holyc` / `term_spawn_container`. Do not
  conclude "there is no pty" without searching this directory (see the pitfall below).
- `term_spawn_exec(argv, label)` / `term_pty_spawn_exec(argv, cwd, pty)` -- added to
  exec an ARBITRARY program with no login-shell flags. Every pre-existing entry point
  assumed the child was a shell.
- `src/apps/apps.h` -- one data-driven registry (`g_app_defs[]`), icons keyed by
  `DESK_ICON_*`; adding an app is a table entry plus a launch fn. There is also an
  in-OS editor (`launch_editor()` -> `editor_launch()`, `apps/editor/`), which the
  `.wet` applet header still refers to as "the IDE".

Explorer wiring now exists: right-click dispatches Open / Open With... / Cut / Copy /
Paste / Delete / Rename / Properties, and `explorer_open_entry()` gives files a real
open action (directories/drives navigate; `.wet`/`.c`/`.h`/`.hc` go to W-CODE through
the weak `ex_launch_with_wcode` hook). Still open: no dedicated `.wet` applet editor
-- "Open With..." opens the file in W-CODE's buffer, which is not the in-place applet
editing the `apps.h` comment promises.

## Pitfalls

- **Never conclude a capability is ABSENT from the tree after a scoped grep.** Searching
  only `src/hosted/*.c` and `src/gui/shell/*.c` for `forkpty|openpty|posix_openpt`
  returned zero hits, which was written down as "there is no pty anywhere" -- the real
  implementation was in `src/gui/term_pty.c`, one directory away, and the claim then
  misdirected the whole integration plan. Grep the WHOLE tree by SYMBOL (no path
  filter) before writing "does not exist"; a scoped search that finds nothing is
  evidence about the search, not about the code.
- **Optional-module dependencies use a WEAK HOOK, not a direct call and not a stub
  file.** Calling into another subsystem directly (apps.c -> term.c) drags its whole
  dependency tree into every lean test that merely wanted to enumerate apps, and the
  link fails on that subsystem's symbols. Putting its symbols in a shared stub file is
  WORSE: including its header there can conflict with unrelated stubs already in that
  file. Instead make ONE symbol weak where it is consumed and define it where the
  module lives. Which FORM depends on how the consumer calls it:

  - **Consumer calls by name** -> a weak FUNCTION:

        __attribute__((weak)) DosGuiWindow *wcode_terminal_launch(char *const *argv);

  - **Consumer takes the ADDRESS** (`if (hook) hook(path)`) -> a weak function is NOT
    enough: it still needs a body at link time in a non-PIE build, so lean targets fail
    to link. Declare a weak POINTER OBJECT instead, which makes an undefined reference
    resolve to NULL:

        __attribute__((weak)) void (*const ex_launch_with_wcode)(const char *path);

    The owning module defines that pointer strongly, pointing at the real function.

  Declare the object ONCE. Writing a plain `extern` declaration plus a weak definition
  of the same object links under GCC but is sloppy and invites drift between the two
  shapes. Targets without the module see NULL and report failure; targets with it get
  the real thing. Same convention as desktop_stubs.c and the petdex hook.
- **A new tab must not spawn twice.** When adding an exec-based launcher, creating the
  tab through the normal constructor AND spawning afterwards double-spawns: the
  constructor already starts a session for shell/holyc/container types and the second
  child leaks. Add an internal "create without spawning" path rather than a new
  session type -- a new type touches every switch site across render, input and
  teardown.
- **A buffer helper must tolerate a zero-initialised struct.** The shared IDE
  state in `wcode_agent.c` is `memset`, not `wcode_buf_new`, so `line` is NULL
  and `n_lines` is 0. Any function that indexes `b->line[i]` must either guard
  the range or lazily allocate. Same for the TUI's own state.
- **Copy a line's tail BEFORE freeing the line.** The multi-line insert path
  needs the original tail after replacing the line; freeing first is a
  use-after-free that ASan catches and a release build silently corrupts.
- **A trailing newline terminates a line; it does not create an extra empty
  one.** `"a\nb\n"` is two lines. Off-by-one here makes every file look like
  it has a phantom last line.
- **The diagnostic parser must reject non-compiler lines.** A real compiler
  path never contains a space or `*`, so `make: *** [Makefile:5: all] Error 1`
  is filtered. Conversely it must STRIP the GCC include-trace prefixes
  (`In file included from X:1:2,` and `from X:1:2:`) rather than rejecting
  them -- the path follows the prefix, not the line start.
- **An agent demo that edits a real file leaves the tree dirty.** Run demos
  against a temp path, or restore the file afterwards and re-run `make test`.
- **Fixed-size response buffers truncate silently.** `op_read`/`op_diags`
  cap at ~64 KB; a large file or many diagnostics will be cut. Check the
  length before trusting the output.
