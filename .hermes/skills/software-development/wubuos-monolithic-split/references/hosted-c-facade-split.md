# Worked Example: splitting `src/hosted/hosted.c` (launcher facade)

Verified 2026-07-14. `hosted.c` was a 415-line monolith that crammed init, frame
composition, input routing, the run-loop, shutdown, the Windows/PE launch executor,
Styx registration, and `main()` into one file. Split into a thin facade + 3
self-contained modules behind `hosted_internal.h` (opaque structs, minimal includes,
no god headers). Result: `make hosted` green, `make test_hosted` 14/14, full
`make test` "All tests passed (all tiers)".

## Concern separation (the mapping)

| Moved code (in hosted.c)            | New module            | Why it's self-contained |
|-------------------------------------|-----------------------|--------------------------|
| `render_desktop()`                  | `hosted_render.c`     | depends only on VBE + WM/desktop/startmenu public APIs + input queue |
| `input_dispatch()`                  | `hosted_render.c`     | drains kernel input queue → routes to DosGui WM |
| `hosted_pe_executor()`              | `hosted_pe.c`         | Windows/PE launch via Proton + cgroup v2 sandbox; needs only proton + ct_isolate APIs |
| `hosted_run()` (frame loop)         | `hosted_run.c`        | orchestrates render+input+Wayland blit; owns shutdown/blit/set_mode |
| `hosted_shutdown()`                 | `hosted_run.c`        | teardown sequence (WM, desktop, screenshot, clipboard, notify, session, settings, vbe, input, wl) |
| `hosted_kernel_ready()` / `hosted_wm_has_windows()` | `hosted_run.c` | behavioral-test accessors |
| `hosted_init()`, `main()`, `repl_launch_callback`, `wm_get_hosted_state`, Styx helpers | stays in `hosted.c` | the facade: orchestration + lifecycle + `g_hosted_state` |

After: `hosted.c` = 210 lines (facade), `hosted_render.c` = 46, `hosted_pe.c` = 51,
`hosted_run.c` = 169.

## Internal-header contract (`hosted_internal.h`)

Add forward decls for every symbol moved OUT of hosted.c so the facade and the
split modules agree:

```c
/* Split-out launcher-core sub-modules */
void hosted_render_desktop(hosted_state_t *state);
void hosted_input_dispatch(void);
int  hosted_pe_executor(const void *data, size_t size, const char *cmdline);
int  hosted_run(hosted_state_t *state);
void hosted_shutdown(hosted_state_t *state);
void hosted_blit(hosted_state_t *state);
void hosted_set_mode(hosted_state_t *state, hosted_mode_t mode);
int  hosted_kernel_ready(void);
int  hosted_wm_has_windows(void);
```

Each split module includes `hosted_internal.h` (for `g_hosted_state`, `g_wl`,
Wayland blit hooks like `hosted_wl_frame_render`) + ONLY the public headers it
actually calls (e.g. `hosted_pe.c` includes `../runtime/wubu_proton.h` and
`../runtime/wubu_ct_isolate.h`; nothing includes the whole GUI or kernel tree).

## Makefile wiring (critical — see wubuos-build-recovery)

Register the new `.o` files in `HOSTED_OBJS` (one entry each, exactly one list):

```
HOSTED_OBJS = \
	$(HOSTED)/hosted.o $(HOSTED)/hosted_render.o $(HOSTED)/hosted_pe.o $(HOSTED)/hosted_run.o \
	$(HOSTED)/hosted_wayland.o ...
```

`test_hosted` links `HOSTED_TEST_OBJS` (= `HOSTED_OBJS` minus `hosted.o`) + a few RT
fragments + `hosted.c` recompiled as a source (`-DWUBU_HOSTED_TEST`). The moved
symbols now resolve from the PREBUILT `hosted_render.o`/`hosted_pe.o`/`hosted_run.o`
in `HOSTED_TEST_OBJS`. **Do NOT** add `$(RT_OBJS)` to a hosted-env link (that triggers
the `multiple definition` class — see wubuos-build-recovery "HOSTED_OBJS + full
RT_OBJS" section).

## Verification (must pass before committing the split)

```
make clean && make hosted        # exit 0 — facade + split modules link
make test_hosted                 # 14/14 (the integration canary for hosted)
make runtime && make apps && make test   # full gate: "All tests passed (all tiers)"
```

## Generalization

Apply the same shape to ANY WuBuOS orchestrator/facade monolith:
1. List the top-level functions and group them by concern (render, input, run-loop,
   launch/executor, teardown, accessors, fs/styx wiring, init).
2. Keep `init` + `main` + the shared-state global + cross-cutting wiring in the facade.
3. Move each concern group to `<name>_<concern>.c` with its own minimal includes.
4. Declare moved entry points in the existing `internal.h`; never leak them into the
   public header.
5. Wire the new `.o` into the owning `*_OBJS` list (exactly one).
6. Re-run the target's build + its test + `make test` gate.
