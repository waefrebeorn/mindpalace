# Split Pitfalls for Large Translation Units (verified this session)

Captured during the `hosted.c` (1219 → 415 lines) → `hosted_wayland.c` (844)
split. The parent SKILL.md is over the patch-size limit, so these are filed
here; read this alongside the main workflow when splitting a >1000-line TU.

## 1. Brace-counting region extraction can silently TRUNCATE the new module
The extractor moves `lines[start:end+1]` into the module and splices the host.
If `end` is miscalculated (off-by-one at a function boundary, or the
banner/blank-line walk-back lands on the wrong line), the module file ends
**mid-function** — e.g. `pointer_button()` closed with no `}` and everything
after it (touch handlers, frame blit, entry points) vanished. The host `.c`
compiled; the module failed at `expected declaration at end of input`, and a
naive recompile surfaced it late.

**Fix / prevent:**
- After the splice, immediately `wc -l` BOTH files and `grep` the module for
  the LAST expected symbol + a closing `}`. If the module is suspiciously
  short, re-derive `end` from `git show HEAD:<orig>` and re-extract.
- Trust byte/line counts, not "it compiled."

## 2. read_file / execute_code truncate and intermittently KeyError on big files
`hosted.c` (1219 lines) exceeded the read buffer: `read_file()` returned
truncated content AND threw `KeyError: 'content'` on retry. The `LINE|CONTENT`
framing also breaks `split("\n")` parsing.

**Fix for >1000-line files:** read with
`subprocess.check_output(["cat", path])` inside `execute_code`, or slice with
`sed -n`. Do NOT rely on `read_file` for the actual split surgery on large TUs —
use it only for inspection.

## 3. Don't rebuild the module by re-patching a half-broken copy
When the first module write was corrupt, re-running `execute_code` over the
on-disk (already-trimmed) host double-applied the trim and orphaned a banner
comment.

**Robust path:** regenerate the module from `git show HEAD:<orig>` (pristine,
full), compute the region once with `sed -n` for exact start/end line numbers,
and write the complete module + trimmed host atomically.

## 4. Verify a split with REAL RUNTIME, not just a green link
A clean `make hosted` only proves symbols resolved. Prove the refactor didn't
change behavior:
```
./src/hosted/wubu -h --screenshot /tmp/x.ppm
```
Should print `hosted_init returned 0`, run the loop, save the screenshot, and
exit 0. In WSL (no Wayland display) `hosted_wl_connect` returns -1 and the
launcher degrades to headless — that path exercising the new entry points is
itself the proof. Link-green + headless-run-green = split verified.

## 5. Makefile: a split adds ONE object — update exactly where the host was referenced
For a hosted TU, add `hosted_wayland.o` to `HOSTED_OBJS` (incremental link) AND
to any direct-compile test recipe that lists `hosted.c` (e.g. `test_gui_screenshot`,
`test_hosted`). Use `.o` in `OBJS` variables, `.c` in direct-compile recipes.
A missing `.o` in `HOSTED_OBJS` surfaces only after `make clean` (stale objects
mask it). See `wubuos-build-recovery` "make clean exposes latent orphaned-prereq
gaps".
