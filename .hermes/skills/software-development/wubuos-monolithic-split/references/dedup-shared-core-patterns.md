# Shared-core dedup & cross-build wiring patterns (WuBuOS monolith splits)

Condensed, session-agnostic techniques that emerged while splitting the
WuBuOS monoliths and fixing the proton-dxvk double-coding defect. Pair with
the main SKILL.md procedure.

## 1. Collision with an existing non-static definition
When the helper you want to promote ALREADY exists as a **non-static** duplicate
in another module (real example: `ensure_dir` defined non-static in
`src/gui/wubu_proton_util.c`, hit while extracting gamelib's start-menu leaf),
do NOT promote a second copy — it produces a `multiple definition` link error.

Fix: rename the extracted copy with a **module prefix** and declare it in the
internal header, same as the `archd_rm_rf` / `bottles_rm_rf` collision-avoidance
pattern already in the skill. Example: `ensure_dir` -> `gamelib_ensure_dir`.
Full dedup of the three `rm_rf` / `ensure_dir` copies is a separate, flagged task.

## 2. Shared helper module used by BOTH runtime and GUI
When you extract a core that both an `src/runtime/*.c` and a `src/gui/*.c`
depend on (example: `wubu_dxvk_conf.c` shared by runtime `wubu_proton.c` and
GUI `wubu_proton_dxvk.c`), wire the `.o` into ALL of:
- `RT_OBJS` (runtime build / RT recipes)
- `GUI_OBJS` (gui build)
- `HOSTED_OBJS` (hosted binary -- links GUI objects, so it needs the RT-core `.o`
  referenced as `$(RT)/wubu_dxvk_conf.o`, NOT `$(GUI)/...`)
- every **explicit test recipe** that compiles the dependent `.c` directly
  (recipes that list `$(RT)/wubu_proton.c ...` instead of `$(RT)/wubu_proton.o`
  will fail to link the shared symbol). Add the shared `.c` to each such recipe.

Also add `-I$(RT)` to any recipe that compiles GUI sources but lacks it
(example: `test_gamelib` only had `-I$(GUI) -I$(KERNEL)` -> couldn't find the
shared `wubu_dxvk_conf.h` in `src/runtime/`).

## 3. Cold-build race (missing prerequisite)
A test recipe that *links* a `.o` (e.g. `$(RT)/styx_fid.o`) but does NOT declare
it as a make **prerequisite** builds fine after any earlier target already
produced that `.o`, but FAILS on a cold `make clean` + sweep with
`cannot find ... .o`. Fix: add the `.o` prerequisites to the target line, not
just the link command.

## 4. Extracting multi-function leaves
For a leaf that is several functions (e.g. the dxvk block: config_write/read +
set_hud/async/nvapi/present/memory + config_ui_get/set), do NOT slice one big
line range. The in-file brace counter can truncate when a block isn't a single
contiguous function or contains string/comment braces. Instead, compute each
function's extent individually via a brace-counting `fn_end()` and concatenate
the verified-balanced pieces. Compile the host + the new module after every
extraction.

## 5. Verify extracted config cores with a standalone harness
Stub-only tests will NOT catch logic bugs. `test_proton`'s dxvk checks only
assert return codes (comment in the test: "Stubs return 0 but don't actually
write"). Compile the shared module + a tiny `main()` that exercises
set / get / remove / parse / build as a roundtrip and print the buffer. This is
how the `find_key_line` bug below was caught.

## 6. Parser line-start delimiter bug (real, shipped-broken)
When writing a "find `key = value` line" parser, the line-start check must
accept `\n` as a delimiter, not just space/tab/start-of-buffer:

    if (ls == buf || ls[-1] == ' ' || ls[-1] == '\t' || ls[-1] == '\n') { ... }

Without the `|| ls[-1] == '\n'`, any key NOT on the first line is never matched,
silently breaking get/set/remove for all continuation-line keys (the buffer
*looks* correct on print, but `get_key` returns -1 for every later key).

## 7. Full verification = COLD sweep
`make clean` then build each test target from scratch, one per invocation.
Running targets in sequence after a prior build hides missing-prereq races
(item 3). Expect the known-broken `test_apps` (opaque-struct poke test,
intentionally red per the skill's hard rule) -- everything else must PASS.

## 8. Divergent (not identical) duplicates -> canonical core + adapter hooks
When two copies of a subsystem are NOT byte-identical but share the same
config-file logic, a blind merge regresses one build's semantics. The
from-scratch-C fix (per user: "rewriting from scratch in C is the point of
the project → anything under that is REAL_GAP, don't stop at divergent"):

- Extract ONE canonical core (`src/runtime/<name>_core.{c,h}`) owning ALL
  the shared logic, parameterized by a **layout resolver** callback:
  `typedef int (*resolver)(const char *id, char *out, size_t sz);` set via
  `void <name>_set_resolver(resolver r);` (call from a `__attribute__((constructor))`).
- For GUI-only extras (e.g. prefix live-state in `g_proton`), add a SECOND
  optional callback pair `state_pull` / `state_push` (nullable). The core's
  `config_ui_get` calls `state_pull` after parsing the file; `config_ui_set`
  calls `state_push` before writing. Runtime registers NULL → file-only.
- The two legacy files become THIN ADAPTERS: each defines ONLY its
  resolver (+ state hooks for GUI) and a `__attribute__((constructor))`
  registration. They must NOT redefine the public `wubu_<name>_*` symbols
  (that collides with the core → multiple definition). The core owns them.
- Fix any typo'd type in the legacy copy (e.g. runtime `DxvkConfigUI` → the
  correct `DxvkConfigUI` defined in `wubu_proton.h`).

## 9. Makefile link-wiring checklist for a new shared core (both builds)
After creating the core, grep EVERY recipe that compiles a dependent `.c`
directly (runtime `wubu_proton.c`, GUI `wubu_proton_dxvk.c`, etc.) and add
the core `.o` (or `.c`) to each. Miss one → `undefined reference to
<core>_set_resolver` at link. Mechanical loop:

    for ln in $(grep -nE "wubu_proton\.c " Makefile | cut -d: -f1); do
      sed -i "${ln}s/\$(RT)\/wubu_dxvk_conf.c/\$(RT)\/wubu_dxvk_conf.c \$(RT)\/<core>.c/" Makefile
    done

Also add `$(RT)/<core>.o` to `RT_OBJS`, `GUI_OBJS`, `HOSTED_OBJS` so the
incremental (object-link) builds pick it up. Verify with a COLD
`make clean && make runtime && make hosted && make test`.

## 10. Shell-expansion trap in commit messages / inline edits
`$(RT)` / `$(GUI)` are make variables; inside a bash `git commit -m "..."`
or `echo`, the shell expands `$(RT)` as a command and fails with
`RT: command not found`. Write literal `$(RT)` in Makefile edits (the patch
tool preserves it), but in shell context use single quotes or spell the
path (`src/runtime/...`). The committed file is correct; only the shell
interpolation is the hazard.

## 11. Divergent-dupe decision override (user correction)
The skill's "divergent → design decision, do NOT blindly merge" rule is
OVERRIDDEN by the user's standing directive: *"rewriting from scratch in C
is the point of the project — anything under that is reclassified as work
REAL_GAP."* So a divergent duplicate is NOT a stop-and-ask; it is authorized
work. Perform the canonical-core extraction (§8) rather than leaving two
copies. (Still fix divergences correctly — don't silently pick one layout;
route via the resolver so both builds keep their existing paths.)

> **See also:** [`references/monolith-b50-b67-status.md`](references/monolith-b50-b67-status.md) — both the `rm_rf` triplicate and the `wubu_proton_dxvk_*` divergent dup are CLOSED (commits `8cbd776`, `62b5738`). Separable-leaf monolith work is COMPLETE.

## 12. The skill's "separable leaves COMPLETE" claim is WRONG for `src/hosted/`
The B50–B67 audit + STOP CONDITION enumerated ONLY `src/runtime/` and
`src/gui/`. `src/hosted/` was **never audited** and holds the LARGEST
monoliths in the tree: `wubu_metal.c` (~1508), `hosted.c` (~1219),
`wubu_vulkan.c` (~990). Siblings (`wubu_display.c`, `wubu_drm_direct.c`,
`wubu_gbm.c`, `wubu_vulkan.c`) are already split — but `wubu_metal.c` still
crams separable backends (audio: ALSA/Pulse/PipeWire; DRM/X11/Wayland
surfaces; VBE; unified surface creation). **Do NOT trust the "all monoliths
split" claim as license to stop** — when the user says "split ALL", audit
EVERY build-graph dir (`find src -name '*.c' | xargs wc -l | sort -rn`),
not just the two the skill lists. First real hosted bust done this session:
wubu_metal audio backends → `src/hosted/wubu_metal_audio.{c,h}` (wubu_metal.c
1508→1225). Remaining hosted leaves if user wants truly-ALL: DRM/X11/Wayland
surface creation, unified surface, VBE in wubu_metal.c; and `hosted.c` itself
(1219, has `main()` + dispatcher — verify it isn't a cohesive entry point
before splitting).

## 13. Makefile bug class: prereq VAR defined but NO target builds it
Cold-build races (§3) are when a recipe *links* a `.o` it didn't *prereq*.
A SECOND, distinct bug class bit this session: a prereq object list exists
(`APP_RT_OBJS` = styx_fid.o, wubu_session.o, wubu_ct_isolate_cgroup.o, …)
but **no `make` target ever builds those `.o`** — `apps:` built only
`APP_OBJS`, so `make paint`/`make doom` (which link `$(APP_RT_OBJS)`) failed
with `cannot find src/runtime/styx_fid.o` even though `make -n paint` showed
the `.o` in the link command. Symptom: `make X` (the target that owns the
prereq var) reports exit 0 but produces ZERO `.o` for that var, and a
dependent link target fails. Fix: add the var to a real builder target
(`apps: $(APP_OBJS) $(APP_RT_OBJS)`) and make the dependent targets depend
on that builder (`paint: apps runtime ...`). Also: a link target that
references `$(RT)/<x>.o` but whose graph only builds it via the `runtime`
target will fail on cold build unless it depends on `runtime` (or lists
`$(RT_OBJS)` as prereq) — fixed this session by `hosted: $(HOSTED_OBJS)
$(RT_OBJS)`.

### Probe recipe (use when a link target fails with "cannot find X.o")
1. Did `make X` actually build X.o? `make -j1 X >log 2>&1; ls -la path/X.o`
   — if missing but `make path/X.o` (explicit) succeeds, the var holding it
   isn't built by any target. Find the owner: `grep -nE "X\.o" Makefile`.
2. `make -n <linktarget> | grep -oE "src/[a-z]+/[a-z_0-9]+\.o" | sort -u`
   counts how many `.o` the target PLANS to build. 0 ⇒ prereqs treated as
   satisfied-but-absent ⇒ the var isn't wired to a builder.
3. Confirm a `$(DIR)/%.o: $(DIR)/%.c` rule exists for that dir (no rule ⇒
   make can't build it and won't error until link).

## 15. Include-order trap when a sibling must NOT pull the internal header
While extracting `wubu_metal.c` backends (evdev/X11/Vulkan) into siblings, the
siblings initially included `wubu_metal_internal.h` and got a cascade of
`mathcalls.h: expected ';' before 'extern'` errors. Root cause:
`wubu_metal_internal.h` includes `<linux/input.h>` (line ~23) **before** `<math.h>`
(line ~29); that ordering corrupts the preprocessor state for later `<math.h>`
consumers. The ORIGINAL `wubu_metal.c` did NOT include the internal header, so it
never hit this.

Rule for backend-sibling extractions:
- Mirror the ORIGINAL parent file's include set (known to compile) in each sibling
  — do NOT opportunistically switch to the richer internal header.
- If a sibling needs only a couple of extern globals (e.g. `g_input`, `g_display`),
  declare `extern <type> g_x;` directly in the sibling rather than pulling the
  whole internal header.
- A Vulkan sibling needing its own Vk type shims can carry a local
  `#ifdef WUBU_USE_VULKAN / #else` block with self-contained typedefs (do NOT reuse
  the internal header's `#else` typedefs — that double-defines and fails).

## 16. De-static shared globals when extracting cross-TU siblings
When a parent's globals are `static` (e.g. `static WubuInput g_input;`) and you
extract a backend into a separate TU that references them, the sibling can't see
them → `undefined reference to g_input` at link. Fix: drop `static` from the globals
in the PARENT (so they become `extern`-by-default at file scope), and have each
sibling declare `extern <type> g_x;` (or rely on the internal header's existing
`extern` decls — it usually already declares them). This also unblocks any OTHER
pre-existing sibling (e.g. `wubu_metal_audio.c`) that already referenced the now
non-static global. Verify with `make test_metal` (or the target linking parent +
siblings) after the change.

## 18. Orphaned module = form-without-function (verified 2026-07-18)
A split/new module that compiles clean (wired into `_OBJS`) but has **no caller
and no test** is NOT "done" — it is dead code, the exact anti-pattern called
"form without function." The fix is NOT to delete the engine (it's real) nor to
add an `app_placeholder_draw` stub as its "integration" — it is to **wire a
genuine consumer + add a real end-to-end test.**

Detection (run after any split / new-module add):
```sh
sym=the_module_public_entry   # e.g. dos_window_spawn
grep -rn "$sym" src --include=*.c --include=*.h | grep -vE "$sym\.c|$sym\.h|_test\.c"
ls src/<dir>/<module>_test.c 2>/dev/null || echo "NO TEST"
grep -o '<module>\.o' mk/objects.mk      # linked into a build?
```
**A test-only caller is still an orphan** — the `*_test.c` is the gate certifying
itself, not a consumer, so exclude it and pair "no caller" with "linked"
before reporting. No callers + no test ⇒ orphan. Wire a real consumer (for a WuBuOS GUI app,
register a launcher in `src/apps/apps.c`'s `g_app_defs[]` that calls the
engine — e.g. launch a real `.COM` via `wubu_dos_proc_launch` then host it via
`dos_window_spawn`). The test must EXERCISE the engine (launch a real
`.COM`, drive a frame, assert a non-empty/non-black RGBA frame), not assert a
faked string. Full mechanics — link recipe, `hc_eval` stub, AddressSanitizer
pinning of double-free/heap-overflow — are in the `wubuos-build-recovery` skill
(Mode D / Mode E / the ASan note). Consult that skill when actually wiring a
new module's test, and `wubuos-8086-dos-emu` for the DOS-window-host test shape.

## 19. Extracting a scaffold over the CALLER's elements: pass the stride
When the shared core you extract operates on the caller's array of structs
(example: a spring field whose bodies live inside `WubuSlimeBlob` /
`WubuRimIsland`), do NOT index the caller's array through a `WubuBlob *`.
Pointer arithmetic advances by `sizeof(WubuBlob)`, not by the caller's element
size — a `WubuBlob` is 28 bytes while `WubuRimIsland` is 40, so `bodies[1]`
lands on `island[0].t`, not on `island[1].blob`. The code compiles and runs;
the fields are silently the wrong ones (observed: islands returning NaN `t`
after ten steps, caught only by the module's own gate).

Fix: the shared entry takes the element BYTE STRIDE and walks
`(char *)bodies + i * stride`:

    void field_step(Field *f, const World *w, WubuBlob *bodies, int n, size_t stride);

Callers pass `sizeof(WubuSlimeBlob)` / `sizeof(WubuRimIsland)` (or
`sizeof(WubuBlob)` for a contiguous array). Clamp `stride < sizeof(WubuBlob)`
up to `sizeof(WubuBlob)` so a bad caller cannot index overlapping elements.

The "embed the shared struct first" trick is valid for a POINTER to the first
element (`&arr[0].member == (T *)&arr[0]`), never for array indexing — that
identity does not survive `+ i`. When a shared core must touch the caller's
elements, make the stride part of the API rather than relying on layout.
