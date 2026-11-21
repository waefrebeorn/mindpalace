# Extraction Integrity & Entry-Point Facade (hosted.c → hosted_wayland.c)

## Context
Splitting a 1219-line `hosted.c`: the Wayland client subsystem (SHM pool, all
`wl_*` listeners, evdev→WuBuOS key translate, frame blit) was moved to
`hosted_wayland.c`. Two problems surfaced that the base workflow doesn't warn
about: (1) the trimmed core still called the moved internals directly, and
(2) the first extracted module came out **CORRUPTED** (truncated at 500 lines,
mid-`pointer_button`, with every function after `touch_cancel` gone).

## Technique 1 — entry-point facade when the core still uses internals
After extracting, the trimmed core referenced `wl_registry_add_listener`,
`shm_buffer_create`, `wayland_frame_render`, the SHM globals, etc. A split is
only clean when the core stops touching module internals.
- Add **non-static entry points** in the module:
  `hosted_wl_connect(state)` (wl_display_connect + bind globals + create surface
  + wire all listeners + create SHM buffers), `hosted_wl_disconnect()` (destroy
  globals, disconnect), `hosted_wl_dispatch()` (dispatch_pending + flush),
  `hosted_wl_frame_render()` (the actual blit body).
- Rewire the core: `hosted_init` → `hosted_wl_connect`, `hosted_run` →
  `hosted_wl_dispatch` + `hosted_wl_frame_render`, `hosted_shutdown` →
  `hosted_wl_disconnect`, `hosted_blit` → `hosted_wl_frame_render`.
- Globals owned by the module stay `static` there; only the entry-point
  prototypes + shared types go in the internal header. The core drives the
  module through the facade and never names a module-local symbol.

## Technique 2 — shared type used by BOTH TUs moves to the internal header
`shm_buffer_t` + `SHM_BUFFERS` were defined inside the extracted region (private
to `hosted_wayland.c`) but the header's `hosted_wl_frame_render` prototype
referenced them. Move the typedef + `#define` into `hosted_internal.h`.
**Rule:** any type referenced by a header declaration that both TUs include must
live in the shared internal header, not in either `.c`. Also: a global referenced
by both TUs must be `extern` in the header and defined **once** (non-`static`) in
exactly one TU — the other TU uses it via the `extern`.

## Technique 3 — verify the extracted module is NOT truncated
Brace-counting write-back can silently truncate. After writing the module:
1. `wc -l <module>.c` — compare to source-region size + added header/entry-point
   lines. A shortfall means truncation.
2. `grep -c <last-fn-in-region> <module>.c` — must be > 0. (For hosted, `touch_down`
   is the last callback; `grep -c touch_down` must be ≥ 1.)
3. Symptom of truncation: `error: expected declaration or statement at end of
   input` at the last function, or a function body cut mid-brace.
4. If corrupt, **regenerate from pristine HEAD** (don't trust the working tree):
   ```python
   import subprocess
   orig = subprocess.check_output(["git","-C",repo,"show","HEAD:src/hosted/hosted.c"]).decode()
   lines = orig.split("\n")
   # locate region by content (SHM banner -> Filesystem-helpers banner), slice, write
   ```
5. `make clean && make <target>` — a stale `.o` from a prior broken link masks
   missing-symbol errors. Always do a clean rebuild after a split.

## Technique 4 — `read_file` `KeyError: 'content'` fallback
`read_file(path)["content"]` intermittently raises `KeyError: 'content'` inside
`execute_code`. Fallback: `raw = subprocess.check_output(["cat", path]).decode()`,
then strip the `LINE|CONTENT` prefix: `re.match(r"^\d+\|(.*)$", ln)`.

## Technique 5 — pre-existing Makefile gaps are NOT your bug
`make hosted` failed with `cannot find src/runtime/wubu_archd_fs.o` and
`make test_hosted` failed with `undefined reference to fs_add_dir`. Confirmed
**both fail identically on pristine HEAD** (`git stash` the split files, run the
target, `git stash pop`). They are latent recipe gaps (a link line references a
`.o` with no build rule; a test recipe is missing source files). Note them and
move on — don't rabbit-hole fixing unrelated Makefile debt unless asked. The
split itself is proven good by `make runtime` + `make hosted` + `make test` going
green after the stale `.o` is rebuilt.
