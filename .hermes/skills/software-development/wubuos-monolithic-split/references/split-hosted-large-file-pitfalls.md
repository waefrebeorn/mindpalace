# Large-File Monolith Split Pitfalls (hosted.c / wubu_metal.c class)

Condensed from the real `hosted.c` (1219->415) + `hosted_wayland.c` (844) split.
These burned multiple iterations; encode them so the next session does not.

## 1. `patch` tool corrupts large multi-section edits — use brace-counting via execute_code

The `patch` tool emits *"re-read the whole file before overwriting"* and in this
session **silently reverted** `write_file`/`execute_code` edits on `hosted.c`
(that were applied on top of an earlier trimmed version), leaving a file in a
contradictory state (trimmed yet still containing the moved function). It also
**left an orphaned banner** when an old block-comment opening `/* ===` was not
fully matched: `patch` matched *both* consecutive `/* ===` lines and produced a
dangling `/* ... === */` with no opener -> C syntax error.

RULE: For files >1000 lines / >10 functions to move, do NOT use `patch` for the
extract-and-trim. Use a single `execute_code` Python script that:
- reads the file via `subprocess.check_output(["cat", path])` (NOT `read_file`, see section 2),
- locates the region by content anchors (`start = line with "SHM Buffer Pool"`;
  `end = blank line before the next `/* ===` banner`),
- writes the new module + the trimmed host **in one `write_file` call each**.

`patch` is still fine for: tiny (<40 line) single-block moves, and for adding a
forward-decl / entry-point call in the trimmed host.

## 2. Reading the file inside execute_code

`read_file(path)["content"]` intermittently raises `KeyError: 'content'` on
large files in `execute_code` (transient tool glitch). `subprocess cat` is
robust. Also: `read_file` returns `"LINE|CONTENT"` prefixed lines for display —
strip them (`re.match(r"^\d+\|(.*)$", ln)`) before treating lines as raw source.

## 3. Makefile OBJS lines get truncated in tool display -> do not write them back

`read_file`/`patch` render very long `OBJS = ...` lines with a literal
`... [truncated]` suffix. If you `patch` such a line, the `... [truncated]`
**becomes part of the actual file** (a corrupted token like `$(RT)/vsl/vs...`),
and `make` then fails with *"No rule to make target 'src/runtime/vsl/vs...'"*.
This corruption is invisible until `make clean` wipes the stale `.o` that masked it.

RULE:
- Inspect raw long Makefile lines with terminal `sed -n 'Np' Makefile`, never trust
  the truncated tool preview when editing them.
- If a line is already corrupted, **recover it from git**: `git show HEAD:Makefile |
  sed -n 'Np'` gives the pristine line; restore it, then re-apply only your real edit.
- After any Makefile edit, run `make clean && make <target>` — stale `.o` files mask
  missing-link / truncated-line errors. If it fails only after `clean`, the bug was
  latent, not caused by your split.

## 4. Entry-point facade pattern (do not leave the host calling private statics)

When the extracted module owns SHM buffers + listeners + key-translation, the
*remaining* host file (e.g. `hosted.c`) must not reach into the module's `static`
functions/globals. Encapsulate the wiring the host used to do inline into 4
entry points declared in the internal header:

```
int  hosted_wl_connect(hosted_state_t *state);   /* bind globals + create surface + SHM */
void hosted_wl_disconnect(void);                 /* destroy globals + disconnect       */
void hosted_wl_dispatch(void);                   /* pump pending Wayland events         */
void hosted_wl_frame_render(void);              /* blit VBE back-buffer + commit        */
```

The host's `hosted_init/run/shutdown/blit` then call only these. Shared types
(`shm_buffer_t`, `SHM_BUFFERS`) and the cross-TU global (`extern g_hosted_state`)
live in `hosted_internal.h`; the module defines `g_shm_bufs`/`g_cur_buf`/
`g_wl` non-`static`, the host defines `g_hosted_state`.

GOTCHA: a module function (`hosted_wl_frame_render`) must be **self-contained** —
do not make it call a `static` helper that stayed in the host (cross-TU
undefined reference). Either move the helper into the module or inline its body
into the entry point.

## 5. Verify "pre-existing broken target" claims on pristine HEAD

Before reporting a test target (`make test_hosted`, `make test_oci`,
`test_gui_screenshot`) as "already broken, not my fault", **prove it**:
`git stash` your changes (or `git show HEAD:` the recipe) and reproduce the same
link error on the unmodified tree. In this session `test_hosted` failed
identically on pristine HEAD (`undefined reference to fs_add_dir` — recipe missing
`hosted_styxfs.c`), so it was genuinely pre-existing. A `make clean` can *also*
surface a latent gap (e.g. `hosted` link references `wubu_archd_fs.o` with no build
rule) — that is Makefile debt, separate from your split. Do not patch a 50-file
inline recipe you did not break; note it and move on.

## 6. Build-gate order after a split

```
make clean
make runtime      # populates RT_OBJS (VSL etc.) — required before `hosted` links
make hosted       # links HOSTED_OBJS + RT_OBJS
make test         # may chain a broken test_oci — run tier binaries directly instead:
for t in test_vsl test_syscall test_styxfs test_host_exec test_proton test_bottles test_holyc test_gc; do make $t; done
```

If `make hosted` fails with `cannot find <x>.o`, that `.o` is referenced by the link
but has no rule on the `hosted` path — compile it once (`gcc -c ... -o <x>.o`) to
confirm the split is green, then file the Makefile gap separately.
