# Embed a Daemon REPL as a PTY-backed Process in a Terminal Tab (E4 — 2026-07-08, commit 7c1cfe1)

The HolyC terminal tab was a **static placeholder** ("WuBuOS HolyC REPL" text, no
real REPL). The gap-class: a subsystem (the `wubu_holyd` HolyC REPL daemon) exists
and is tested, but the Desktop terminal does NOT host it as a live, interactive
session. Closing it = embed the daemon's REPL as a real PTY-backed process in the
terminal tab — reusing the existing PTY machinery, not writing a second REPL.

## The pattern (reusable for ANY daemon with an in-process eval API)

1. **Give the daemon a TTY REPL mode.** The daemon's `main` (in `wubu_holyd_lifecycle.c`)
   already has a `wubu_holyd_init` + event-loop. Add a `--repl` flag that, instead of
   the socket event loop, does: `wubu_holyd_session_create` → `wubu_holyd_repl_start` →
   `while (fgets(line, stdin)) { wubu_holyd_repl_eval(d, "repl", line, out, n); printf("%s\n", out); }`.
   `wubu_holyd_repl_eval` is the REAL compiler entry (it calls `hc_eval`); this reuses it
   verbatim — no second REPL implementation. Verified end-to-end:
   `echo '1+2*3' | ./src/runtime/wubu_holyd_bin --repl` → `9`.

2. **Build the daemon REPL binary.** Add a Makefile target `wubu_holyd_bin` that links the
   daemon `.c` files + the compiler (`holyc_*.c`) + `JIT_SRCS` + `wubu_spawn.c` WITHOUT
   `-DWUBD_TEST_MAIN` (so the `main` in `wubu_holyd_lifecycle.c` is the entry point).
   The daemon `.c` guards its `main` with `#ifndef WUBD_TEST_MAIN`, so the test target
   (`-DWUBD_TEST_MAIN`) builds the lib+tests, while the bin target builds the CLI.

3. **Make the terminal tab embed the REPL via PTY.** Two changes:
   - Change `TermHolycSession` to **embed a `TermPtySession pty`** (the REPL runs as a
     process, so it is a PTY session — do NOT keep a separate opaque `holyc_term` field).
   - In `term_new_tab(TERM_SESSION_HOLYC)`, call `term_pty_spawn("wubu_holyd",
     HOME, &tab->session.holyc.pty, (const char*[]){"--repl", NULL})`.

4. **Route render/key/IO to the holyc PTY.** Reuse the shell-tab paths:
   - `term_render_holyc_session` → delegate to `term_render_pty_session(&holyc->pty, ...)`.
   - `term_handle_key_holyc` → same key→byte mapping as `term_handle_key_pty`, write to
     `holyc->pty.ptm_fd`.
   - `term_pty_write` / `term_pty_read` → add `TERM_SESSION_HOLYC` branches
     that use `tab->session.holyc.pty`.
   - Delete the now-dead static placeholder renderer and any empty `term_holyc_eval`.

## PITFALL — `term_pty_spawn` only took a single shell string

`term_pty_spawn(shell, cwd, pty)` did `execvp(shell, {"shell","-l",NULL})` — no argv
support, so `wubu_holyd --repl` (with args) was impossible. Fix: extend the signature
with `const char *const *extra_argv` (NULL = default `{"-l"}`); when non-NULL, build
`argv = [shell, ...extra_argv, NULL]` and `execvp`. Update ALL callers (only one: the
shell tab passes NULL) and BOTH header decls (`term_internal.h`, `term_pty.h`).

## PITFALL — daemon `.c` has its own `main()`

`wubu_archd.c` and `wubu_holyd_lifecycle.c` both define `main`, guarded by
`#ifndef WUBD_TEST_MAIN`. Linking them into `hosted` (which has its own `main`) or a GUI
test gives `multiple definition of 'main'`. Add `-DWUBD_TEST_MAIN` to every link line
that includes such a `.c`. (The hosted/hosted_test `main` in `hosted.c` is NOT guarded,
so the define only suppresses the daemon's — correct.)

## PITFALL — dep cascade for the daemon `.c`

`wubu_holyd_lifecycle.c` pulls `wubu_holyd.c`/`wubu_holyd_session.c`/`wubu_holyd_exec.c`
(+ window/input/9p/save/event) + the compiler (`holyc_*.c`) + `JIT_SRCS`. A target that
links the daemon REPL bin or a terminal test pulling the module must list those, or you
get `undefined reference to wubu_holyd_*`. This session affected: `wubu_holyd_bin`,
`hosted`, `test_hosted`, `test_term`.

## PITFALL — pre-existing broken targets (carry-over from E3)

`test_hosted` was ALREADY broken at baseline (missing `wubu_welcome.c`,
`wubu_wallpaper.c`, `hc_eval`, … present in the working `hosted` binary but absent from
`test_hosted`'s link line). Confirm with `git stash` + run at baseline before assuming
your change broke it. Then align the object list with `hosted`. `test_hosted` is NOT in
the `make test` aggregate (so a `make test` green does not cover it).

## Regression test (asserts FIXED behavior, not just non-crash)

Add `test_holyc_embed` to `test_term`:
- `term_new_tab(TERM_SESSION_HOLYC, NULL, NULL)` returns >= 0; tab type == HOLYC.
- `tab->session.holyc.pty.ptm_fd >= 0` — the REPL PTY master was created (the REPL
  process was spawned). This holds even if `wubu_holyd` isn't on PATH (the child exec
  may fail, but the PTY master is still created by `term_pty_spawn`).
- Make the tab active, `term_handle_key('1', 0)`, assert `ptm_fd` is stable
  (write path didn't crash; REPL PTY still alive).

The test asserts the TERMINAL-LAYER wiring (spawn + routing), which is the real new work;
the REPL's actual eval is covered by `make test_holyd`.

## Full Makefile fragment (wubu_holyd_bin target)

```make
wubu_holyd_bin:
	$(CC) -O2 -std=c11 -D_POSIX_C_SOURCE=200809L -Wno-format-truncation \
		-I$(RT) -I$(COMP) -I$(JIT) -I$(GUI) \
		$(COMP)/holyc_lexer.c $(COMP)/holyc_parse.c $(COMP)/holyc_codegen.c \
		$(COMP)/holyc_codegen_emit.c $(COMP)/holyc_codegen_expr.c \
		$(COMP)/holyc_codegen_stmt.c $(COMP)/holyc_codegen_api.c \
		$(JIT_SRCS) $(RT)/wubu_spawn.c \
		$(RT)/wubu_holyd.c $(RT)/wubu_holyd_session.c $(RT)/wubu_holyd_exec.c \
		$(RT)/wubu_holyd_window.c $(RT)/wubu_holyd_input.c $(RT)/wubu_holyd_9p.c \
		$(RT)/wubu_holyd_save.c $(RT)/wubu_holyd_event.c $(RT)/wubu_holyd_lifecycle.c \
		$(GUI)/wm_test_stub.c \
		-o $(RT)/wubu_holyd_bin -lpthread
	@echo "✅ wubu_holyd binary built (./src/runtime/wubu_holyd_bin)"
```

Key: NO `-DWUBD_TEST_MAIN` (so `wubu_holyd_lifecycle.c`'s `main` is the entry);
`wm_test_stub.c` satisfies any WM coupling without pulling the full Wayland stack.
