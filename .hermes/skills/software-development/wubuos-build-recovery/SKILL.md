---
name: wubuos-build-recovery
description: Diagnose and repair broken WuBuOS Makefile builds. Covers link errors, undefined or multiple-definition symbols, missing objects, crashed or interrupted edits, daemon main() collisions, and hosted-only symbols. Use when make runtime, make hosted, make paint, or make doom fails to link, or the test gate goes red after a Makefile change. This is a recurring failure class for this repo.
---

# WuBuOS Build / Link Recovery
Adding an object to every link line that uses X: rule-body-aware dedupe
(continuation lines!) — see `references/link-line-rule-body-dedupe-2026-08-08.md`.
Macro-value conflicts between two headers (include-order race, breaks via
downstream static asserts), plus how to prove a break predates your commit with
a throwaway worktree instead of `git stash` — see
`references/macro-value-conflicts.md`. For the `make test` blocker list and the
open test_holyc codegen bug, see `references/make-test-triage.md`; HolyD JIT codegen bugs and the two open probes in `references/holyd-codegen-gaps.md`.

TWO rules that decide whether a failure is real before you act on it. (1) A failure naming two values that must not conflict/overlap may be the TEST'S OWN liveness checker, not the allocator -- print what the code actually produced first, and negative-control any checker fix by injecting a deliberate violation. (2) Two `make` jobs over one tree produce thousands of fake failures (`pass=24940 fail=5908`, every one naming a backend you did not touch): re-run the target alone and compare to baseline. Both in `references/orphan-target-repair-playbook.md` sections 9-10.

A GREEN `make test` is not evidence on its own. Three mechanisms here turn real
defects into clean exits: a test target nothing invokes, assertions whose
output never reaches stdout, and a helper implemented but never dispatched.
A build step that shells out to a binary in /tmp is a hidden dependency: /tmp is wiped between sessions and on reboot, and a `popen` miss usually returns a value instead of erroring, so the suite stays green while every test using it silently does nothing. Any tool the build invokes belongs in the repo and in make.

See `references/test-suite-honesty-gates.md` for the audits and the build-time
gates that catch each — and wire a repaired target into the aggregate in the
SAME change, or its rot returns. Once a target builds, the repair procedure and
its fixture/isolation failure modes are in
`references/orphan-target-repair-playbook.md`.

Repairing an unwired target usually surfaces a WIRING or FIXTURE problem, not a
logic bug — an unpacked archive, a generated file saved under the wrong
extension, a header referenced from the wrong directory, or a test that counts
files in the USER's real data directory. Check the payload before debugging the
code. And never whitespace-tokenise a multi-line make recipe: collapsing its
`\` continuations turns the compiler into a prerequisite
(`No rule to make target 'gcc'`).

Once a target builds and RUNS, stop assuming the code is correct because the
test is old: an assertion failure at that point can be a feature that was never
implemented. A `(void)param` discarding the argument the test drives is the tell
— read the function and its header comment, and if the comment claims behaviour
the body does not do, fix the CODE. Also check for a called function that exists
nowhere in the tree, and for two modules sharing a basename in different
directories before concluding a link is broken.

WuBuOS's `Makefile` is a hand-maintained object-list build (no automake). It
relies on big variables: `GUI_OBJS`, `RT_OBJS`, `HOSTED_OBJS`, `KERNEL_OBJS`,
`JIT_OBJS`, `APP_OBJS`, plus the recovery helper `APP_RT_OBJS`. A crashed or
interrupted edit (very common; see the recurring "session crashed" history)
leaves the Makefile half-edited: a stray trailing `\` on a prereq line swallows
the recipe, or an object list drops entries. The resulting link failures LOOK
like code bugs but are build-graph damage. Always suspect the Makefile before
the C.

## Fresh-clone recovery (repo was nuked by crash)
When the repo directory is empty (`.git` gone, no `src/`, `Makefile` missing), the crash wiped the clone. Skip partial triage — you have nothing to bisect. Scale is different: **clone and discover all breakage at once**, then fix the full batch:

1. **CHECK THE CLOCK first.** Run `date` to establish the current time context — crash artifacts (build caches, ctime-mangled submodule pointers, stale `.o` files) may be time-sensitive.

2. **Clone immediately.**
   ```bash
   cd /home/wubu
   rm -rf wubuos  # remove the empty husk (adjust name if different)
   git clone --depth 10 https://github.com/waefrebeorn/WuBuOS wubuos
   ```
   (The `--depth 10` keeps it fast — history isn't needed for the fix pass.)

   Adjust the repo name (`wubuos`) and path (`/home/wubu`) to match the actual checkout location.

3. **Build `make runtime`** first to verify the toolchain works and objects compile.

4. **Run `make test`** and capture ALL failures — NOT just the first one.
   ```bash
   make test 2>&1 | tee /tmp/full_test_output.txt | grep -E '(Results:|failed|Error|No such file)' | tail -30
   ```
   The failures fall into three categories, all of which appeared in the
   2026-07-22 fresh-clone recovery (the prototypical instance):
   - **Missing test source files** (`No such file or directory` for `test_holyc_ptx.c`,
     `test_worldsim.c`, etc.) — write the missing test file based on the module's
     public API in its header.
   - **Missing object files** (`cannot find .../wubucontainer.o`) — the cloned repo
     has NO prebuilt `.o` files, so any object that isn't in `RT_OBJS` (or its
     subsystem's `_OBJS` variable) never gets built. Add it to the right `_OBJS`
     variable.
   - **Makefile stale-object wiring** — a test's link line references `.o` files that
     are named in the link command but are NOT prerequisites of the test target.
     On a fresh clone (no stale `.o` lingering), this produces
     `cannot find <path>/<file>.o`. Fix: add the missing objects as prerequisites
     OR add the missing source files to `RT_OBJS` so `make runtime` builds them.

4. **Apply all fixes** in one batch, then re-run `make test` to confirm green.
   Do NOT fix one failure, re-run, fix another, re-run — that wastes rounds.
   The fresh-clone failure set is deterministic; fix them all, then verify once.

5. **Update memory/slate** with the fresh-clone commit so the next session starts
   knowing the baseline is clean.

## Triage recipe (run in order)

1. **Reproduce and grab the FIRST error.** `make <target> 2>&1 | tail`. Capture
   the first `undefined reference` / `multiple definition` / `no rule to make
   target`. Later errors are usually cascades from the first.
2. **Stray line-continuation (the classic crash artifact).** If you see
   `make: *** No rule to make target 'gcc'`, or a prereq that looks like a
   recipe word, inspect raw bytes:
   `sed -n 'Np' Makefile | cat -A` — look for a `\` at the end of a *prereq*
   line, or a `\` followed by trailing spaces (`\ `). Fix: delete the stray `\`.
   Confirm with `od -c` if `cat -A` is ambiguous.
3. **Map an undefined symbol to which `.o` defines it:**
   `nm src/**/*.o 2>/dev/null | grep -wE "T <sym>"` (or `nm <file>.o | grep <sym>`).
   Then add that `.o` (or its variable) to the link line / object list.
4. **Introspect a Make variable without trusting the file view:**
   - `make -n <target> 2>/dev/null | grep -oE "<token>\.o"` — does the REAL
     link command contain the object?
   - `make -s --eval='p:; @echo $(VAR)' p` — print the fully-expanded variable.
   CAUTION: very long backslash-continued variable defs can *appear* to drop
   tokens in `make -p` / `--eval` dumps. Trust `make -n <target>` (the actual
   link cmd) over a `$(VAR)` echo when they disagree.
5. **Bisect pre-existing vs introduced breakage:**
   `git stash && make <target> 2>&1 | tail; git stash pop`
   Pristine passes → your edit broke it (inspect `git diff Makefile`).
   Pristine also fails → it's bit-rot, not your edit.
6. **Fix, rebuild, repeat** until the target links.

## Crash reconciliation — the working tree AND a stash may hold the SAME fix

A crash mid-edit frequently leaves a fix **twice**: once in the uncommitted
working tree AND once in a `git stash` (e.g. a prior session stashed "crash
boot-diff s" to get a clean base, then a later session re-applied the same
intent directly to the tree). When you see BOTH `git status --short` showing the
files AND `git stash list` naming an overlapping change, treat it as a collision,
not two independent pieces of work:

1. **Diff the working tree vs HEAD** (`git diff --stat`) AND **inspect each
   stash** (`git stash show -p stash@{N} --stat`). If the same source file appears
   in both, they conflict on intent — pick ONE source of truth.
2. **Prefer the CLEAN-BASE rule for bare-metal boot changes.** The user's
   standing directive: bare-metal boot-diff s (crt0.S / isr_stubs.S / kernel.ld /
   metal_main.c) left by a crash belong stashed, NOT in the working tree. The last
   *committed* state is the known-good baseline. So: `git checkout HEAD -- <boot
   files>` to restore the clean base, and **keep the stash** (`crash-recovery-*`)
   as the recoverable record of what the fix intended.
3. **If the stashed fix is actually wanted**, re-implement it correctly (see the
   `R_X86_64_32` `.data` note above — the stashed boot fix is often the thing that
   BROKE the link, so don't blindly `git stash pop`; rewrite it right), then
   `git stash drop` the now-redundant stash.
4. **Separate the legit progress from the crash damage.** A monolith-dissolution
   (new modules compiling cleanly) is real progress — keep it. Boot-diff s that
   break `make kernel` are crash damage — restore them to HEAD.
5. **Verify the base is clean before building:** `git diff --stat <boot files>`
   should be EMPTY after a `git checkout HEAD --`, and `git stash list` should
   still show the preserved recovery stash.

Verified green 2026-07-16: a crashed session had `R_X86_64_32 against '.data'`
from a stashed+re-applied `boot_magic` `.data` scratch; restoring
`crt0.S`/`isr_stubs.S`/`kernel.ld`/`metal_main.c` to HEAD (stash kept) made
`make kernel` link, while the fat32 dissolution was preserved and
`make test` passed all tiers.

## WuBuOS-specific pitfalls (verified, recurring)

- **Daemon `main()` collisions.** `$(RT_OBJS)` includes objects that define
  `main()`: `wubu_archd.o` and `wubu_holyd_lifecycle.o` (both guarded by
  `#ifndef WUBD_TEST_MAIN`). NEVER link `$(RT_OBJS)` into a standalone binary
  (paint/doom/apps) — you'll get "multiple definition of main". Use the curated
  `APP_RT_OBJS` (full runtime minus those two, plus `archd_hosted.o` and
  `holyd_lifecycle_app.o` built with `-DWUBD_TEST_MAIN`). See
  `references/makefile-object-map.md`.
- **Hosted-only symbols.** `wm_get_hosted_state()` and
  `g_primary_selection_manager` are defined ONLY in `src/hosted/hosted.o`,
  which owns `main()`. Standalone apps can't link `hosted.o`. Provide a
  NULL-returning shim (pattern: `src/gui/standalone_hosted_shim.c`, mirrors the
  existing `wm_test_stub.c`). Returning NULL is the *correct* defined
  behaviour — callers already handle NULL (ctx_action_play treats NULL as "no
  launch"; clipboard treats a NULL manager as "primary selection unavailable").
 - **Standalone app targets need `APP_RT_OBJS`, which `make runtime` does NOT fully
 build.** A standalone binary (`canvas`) links `$(APP_RT_OBJS)` (styx_fid.o,
 wubu_compat_db.o, wubu_session.o, wubu_ct_isolate_cgroup.o, styxfs.o, …). `make
 runtime` builds `RT_OBJS` but NOT every `APP_RT_OBJS` member — only `make apps`
 does. Symptom: `ld: cannot find src/runtime/wubu_ct_isolate_cgroup.o`. Fix:
 ensure the target prereqs `apps` (`canvas: apps runtime ...`) OR run `make apps`
 before `make canvas`. If you still hit it, a stale build dir is the cause;
 `make clean` first.
 - **Output-binary name colliding with a stale source subdir.** If an old source
 dir like `src/apps/canvas/` (holding a stale `canvas.o` from a deleted stub)
 still exists, `-o src/apps/canvas` fails with `ld: cannot open output file
 src/apps/canvas: Is a directory`. Fix: `rm -rf src/apps/canvas` (the dir), then
 rebuild. A deleted `canvas/canvas.c` stub leaves this trap behind.
 - **Do NOT trust stale `/tmp/*.log` from prior background `make` runs.** A crashed
 or superseded session may have left logs showing `✅ Paint built` while the
 current tree is broken. Always run `make clean && make <target>` for ground
 truth. The captured `make <target>` exit code in a background process can also
 disagree with a fresh run (different object state).
 - **A crashed edit can leave a 0-byte file with a near-duplicate name.** This
 session left `src/runtime/holyd_lifecycle.c` (0 bytes) — note the MISSING
 `wubu_` prefix; the real source is `wubu_holyd_lifecycle.c`. Detection: after a
 crash, `git status --short` shows untracked files; `wc -l` anything 0-byte
 whose real symbol lives elsewhere, then delete it. It compiled only because
 `-Wno-implicit-function-declaration` suppresses the missing-declaration error.
- **Gui-shot / test-harness stale-object trap (2026-07-20)**
**Symptom:** A test binary or harness (`wubu_gui_shot`, `test_gui_screenshot_apps`, etc.) runs but crashes / misbehaves (segfault, wrong layout, wrong window order) even though the source code looks correct.

**Root cause:** The target's prerequisite list in the Makefile omits most of the `.o` files it actually links. Example: `gui_shot` listed only 3 objects (`wm.o wubu_theme.o vbe.o`) but the link line pulled 20+. Editing `calc.c` rebuilt `calc.o` but `make gui_shot` didn't relink it → stale `calc.o` (with old `calc_draw_button` logic) linked → segfault at `calc_draw_button` with `w=-2` (impossible in current code).

**Fix:** The target's prerequisites MUST enumerate every `.o` that appears in its link recipe. Either:
- List all objects explicitly in the target's prereq line, OR
- Use a macro that expands to the full set (e.g. `$(GUI_OBJS) $(RT_OBJS) ...`) so `make` sees the full dependency graph.

**Check command after any header edit:**
```bash
find src -name '*.o' -older src/gui/<edited_header>.h
```
If any object is older than the header you just changed, that's the bug — `make` won't rebuild it.

**Pattern to audit:** Any `test_*` or harness target whose recipe has a long `$(CC) ... $(GUI)/foo.c $(GUI)/bar.c ...` line but whose prereq line is just `target: a.o b.o c.o`. Those are stale-object bombs.

**Related fix (Control Panel launch):** `app_find_by_name()` in `src/apps/apps.c` only matched the registry `name` field ("Settings") but the harness called `launch_by_name("Control Panel")` (the display `title`). Fixed by matching both `name` AND `title` fields. This is a logic bug, not a build bug, but manifested in the same harness.

**Related fix (Overlapping window layout):** The harness launched 5 apps with overlapping default positions (Calc at 179,81 280x380, Notepad at 100,80 500x400). Fixed by adding deterministic tiled layout in `wubu_gui_shot.c` main() with explicit non-overlapping coordinates + focus calls before capture. Visual verification now possible.
 - **Double-listed objects cause multiple definition.** The same `.o` can appear
  in both `GUI_OBJS` and `HOSTED_OBJS` (e.g. `wubu_screenshot_draw.o`,
  `wubu_dxvk_conf.o`) AND in `APP_RT_OBJS` if you copy entries. ld errors on a
  `.o` listed twice. Keep each object in exactly ONE app-side list. (When you
  restore a corrupted object list, watch for accidental duplication of an entry
  that also lives in `HOSTED_OBJS`.)
- **Real duplicate-definition bugs (not build damage).** Some symbols are
  genuinely defined twice across source files, e.g. `wubu_proton_create_prefix`/
  `wubu_proton_exec`/`wubu_proton_dump` exist in BOTH `src/runtime/wubu_proton.c`
  and `src/gui/wubu_proton.c`. The hosted binary links only `gui/wubu_proton.o`
  (canonical). Do NOT add `rt/wubu_proton.o` or `wubu_proton2.o` to standalone
  app links — they collide. Treat as a separate field-gap fix, not by linking
  both.
- **Missing libs on app targets.** Standalone apps need
  `-lz -lvulkan -ljson-c -lwayland-client -lxkbcommon -ldl` (hosted pulls some
  via `pkg-config`). Vulkan symbols (`vkGetPhysicalDeviceMemoryProperties`) fail
  without `-lvulkan`; json-c symbols (`json_object_put`) without `-ljson-c`.
- **Apps have no `main()`.** The standalone image-editor binary is built from
  `src/apps/canvas_standalone.c` — a real `main()` that boots VBE + DosGui WM,
  creates a `wubu_cv_create()` canvas, composites it to the framebuffer each
  frame, and runs the app loop (`make canvas`). `g_vbe` is `static` — expose it
  via `vbe_framebuffer()` / `vbe_width()` / `vbe_height()` accessors. Do NOT
  resurrect the deleted `apps_standalone.c` shim; `canvas_standalone.c` owns
  `main`. (`src/apps/paint.c` / `doom.c` were DELETED — they were a toy MS-Paint
  and a Wolfenstein-3D raycaster clone, not the accepted FreeDoom / wubu_canvas
  engines.)

### Stale binary masks the real link failure (recurring, 2026-07-25)
`make test_X` recipes are `gcc … -o bin && ./bin`. When the **link step fails**,
`make` returns non-zero **but the previous good binary stays on disk**. If you
debug by running `./bin` directly to "see the output", you get **stale green
results** that mask the real link error and send your debug in the wrong
direction (e.g. you blame supervisor logic when the link never relinked).
**Correct gate discipline:** (1) trust the `make` **exit code**
(`echo "EXIT=$?"`), NOT the binary's stdout; (2) grep the actual diagnostics —
`make test_X 2>&1 | grep -iE 'error:|undefined ref'`; (3) only after `make`
exits 0 do you run `./bin` to read behavior; (4) `make` exit 2 with *only*
warnings* (implicit-function-declaration, missing-declaration) is a warning,
not a link error — confirm via the grep, don't assume failure from the exit
code alone; (5) if a test "fails" but `make` shows only warnings + a stale run,
the binary was never relinked — fix the harness (struct-member name, include,
signature) and rebuild; do not trace the supervisor logic. Verified this session:
3 assertions went red, `make` showed EXIT=2 + warnings only, reading the stale
binary sent debug the wrong way; the true cause was a harness struct-member
mismatch, not the supervisor. The paired zombie-liveness trap (supervisor,
`waitpid(WNOHANG)` not `/proc` existence) lives in `systems-programming` skill →
`references/supervisor-zombie-liveness-and-build-gate-2026-07-25.md`.

## MEGA-OS operator build — fail-closed external contract
When the operator layer and the kernel layer are separate projects (here: WuBuOS
operators vs **wubuwizard** kernel), build the operator side FIRST and wire the
external half as a **fail-closed contract** — never assert success on a schema
the external side hasn't signed off on. The reusable build/verification lessons
(full operator-side module order + fail-closed external-contract pattern) are in
`references/mega-os-operator-build-2026-07-25.md`.

## References
  If `make hosted` is green but `make clean && make hosted` fails with
  `ld: cannot find src/runtime/wubu_archd_fs.o`, the object was referenced by
  the link command (literal filename in the `$(CC)` args) but had NO builder.
  Causes: (a) the `.o` is missing from `RT_OBJS`/`HOSTED_OBJS` (so make never
  treats it as a prereq → the pattern rule never fires), or (b) there is no
  `$(RT)/%.o: $(RT)/%.c` rule at all. **Fix (general, verified):** add a
  `$(RT)/%.o: $(RT)/%.c` pattern rule (mirror `$(KERNEL)/%.o` etc.) AND add the
  missing `.o`(s) to `RT_OBJS` so they build under `make runtime` and the hosted
  link prereqs them. The real gate is `make clean && make hosted` building
  reproducibly — NOT a warm-cache `make hosted`.

- **A prereq object list can be CORRUPTED mid-token (not just a stray `\`).**
  A prior session left `RT_OBJS` ending in `$(RT)/vsl/vs... [truncated]` — the
  line was cut off mid-word, so make reported
  `No rule to make target 'src/runtime/vsl/vs...'`. Looks like a stray
  continuation but is a truncated token. **Fix:** recover the pristine variable
  with `git show HEAD:Makefile | sed -n '55p'` and diff vs the working tree; do
  NOT hand-repair an enormous backslash-continued variable with `execute_code`
  (its `read_file` truncates ~100KB buffers and the `LINE|CONTENT` framing
  breaks line parsing — one bad `rfind` can wipe the whole line). Use
  `git checkout HEAD -- Makefile` to restore, then re-apply only the intended
  small edits via `patch`.

- **Orphaned / duplicate Makefile TARGET (NEW, 2026-07-13).** A prior
  edit left a SECOND, malformed `test_ns_snap:` rule with no target header —
  just stray `$(RT)/wubu_ns_snap_test.c \` + `-o $(RT)/wubu_ns_snap_test`
  lines dangling between targets. `make` parses this as a continuation of the
  adjacent `test_ns_kernel:` target, so `make test_ns_kernel` tried to compile
  `wubu_ns_snap_test.c` and failed with `Permission denied` / `Error 127` even
  though `test_ns_kernel`'s own recipe was correct. **Symptom:** a target's
  recipe invokes a DIFFERENT target's source file, or `make <t>` fails while
  running the `$(CC)` commands by hand succeeds. **Fix:** `grep -nE '^test_|^[a-z_]+:' Makefile` and eyeball that every target has exactly ONE
  `^name:` header and no dangling recipe lines between targets (a recipe line
  whose preceding line is blank but has no `target:` is the orphan). Delete the
  orphan block. Verify: `make -n test_ns_kernel 2>/dev/null | grep -c snap`
  should be **0** (the kernel target must not mention snap sources).

- **THE SHARP VARIANT (verified 2026-07-13): `hermes_tools.write_file` /
  `read_file` silently truncate the WuBuOS `Makefile` to 500 LINES.** After a
  `write_file(Makefile, ...)` the file became 500 lines (was 896), dropping
  `test_oci`, `test_network`, `test_spawn`, and ~400 lines of targets — the
  ENTIRE tail, not just a mid-token cut. Symptom: `make test` fails
  `No rule to make target 'test_oci'`. This bites even when you only meant to
  change ONE line — if any step rewrites the whole Makefile through
  `hermes_tools`, it is destroyed. **RULES — never violate:**
  1. NEVER use `hermes_tools.read_file`/`write_file` on `Makefile` (or any
     file >~400 lines). The tool caps output and `write_file` persists the
     truncated copy.
  2. Edit `Makefile` ONLY with `patch` (exact old→new string, no truncation) or
     a short Python script run via `terminal` that uses bare `open()` to
     `readlines()`/`writelines()` — NOT `hermes_tools`. (The session that hit
     this recovered by `git checkout HEAD -- Makefile` then re-applying the 3
     object-list edits via a `terminal` Python `open()` script — 896 lines,
     `test_oci` present, zero `...` after.)
  3. After ANY Makefile edit, verify integrity before trusting the gate:
     `wc -l Makefile` (expect ~896), `grep -c '^test_oci:' Makefile` (expect 1),
     `grep -c '\\.\\.\\.' Makefile` (expect 0 — a literal `...` means a
     truncated token slipped in). If the line count dropped or `test_oci`
     vanished, `git checkout HEAD -- Makefile` and redo the edit the small way.

  4. **`execute_code` reading the Makefile THROUGH `terminal("cat …")` ALSO
     truncates.** Rule 2 says "use bare `open()` in a `terminal` Python
     script" — but the *transport* matters. If the Python inside `execute_code`
     reads the file via `hermes_tools.terminal("cat Makefile")` (or `read_file`),
     the tool channel caps the output at ~21 KB and emits
     `[OUTPUT TRUNCATED - 21,306]` mid-file. Writing that back via `write_file`
     persisted a **705-line** Makefile (was 1020) — silently dropping every
     `test_*` target, and `make` then failed with
     `No rule to make target 'test_oci'`. Verified 2026-07-17.
     **The ONLY safe read path is `open()` called directly inside the
     `execute_code` Python process** (the Python runtime has real FS access;
     it does NOT go through the truncated tool transport):
     ```python
     # SAFE - reads the real 1020-line file, no transport cap
     with open("Makefile") as f: lines = f.read().split("\n")
     # UNSAFE - truncates ~21KB, bakes '[OUTPUT TRUNCATED]' into the write
     # data = hermes_tools.terminal("cat Makefile") ...
     ```
     `execute_code` is the RIGHT tool for Makefile edits (it regex/line-splices
     reliably); just never feed it the file through a `hermes_tools` read.

  **SHARP NESTED-QUOTE TRAP (verified 2026-07-20):** when you build the Makefile
  edit script INSIDE `execute_code` via `terminal("cd ... && python3 -c " + repr(script))`,
  the `repr` of a multi-line string containing **TAB-prefixed backslash-continued
  Makefile lines** (`"\t$(CC) ... \\\n"`) round-trips `\n`/`\t`/`\\` through
  `repr`→shell→`eval` in a way that DROPS the trailing `\\\n` (the line
  continuation) or mangles quotes, so `python3` dies with
  `SyntaxError: unexpected character after line continuation character` and the
  edit silently does NOT happen. Symptom: you "patched" the Makefile but the next
  build still shows the OLD broken link line. **Fix:** never pass the script via
  `python3 -c " + repr(script)` inside `execute_code`. Instead either (a) write the
  script to a file with `write_file` then `terminal("python3 /tmp/fix.py")`, or
  (b) embed the whole script as a triple-quoted `'''...'''` string directly in the
  `execute_code` code body (the Python runtime executes it without a shell
  re-encode). Both preserve TABs + trailing `\\` exactly.

  **Surgical recovery when ONE long line got the `...` truncation:** do NOT
  rewrite the whole file (you'll re-introduce truncation). Recover just the
  broken line from the pristine copy and splice it with bare `open()`:
  ```python
  import subprocess
  line58 = subprocess.check_output(
      "git show HEAD:Makefile | awk 'NR==58'", shell=True, text=True).rstrip("\n")
  with open("Makefile") as f: lines = f.read().split("\n")
  lines[57] = line58.replace("$(RT)/wubu_exec_dos.o ",
                             "$(RT)/wubu_exec_dos.o $(RT)/wubu_dos_proc.o $(RT)/wubu_dos_emu.o ", 1)
  with open("Makefile","w") as f: f.write("\n".join(lines))
  ```
  Then re-verify: `wc -l Makefile` (1020), `grep -c '\.\.\.' Makefile` (0).

## ADDING A NEW RUNTIME MODULE WITH NEW SYMBOL DEPS (link-sweep + duplicate traps)

When you add a `.c` that defines symbols other modules now call (this session:
`wubu_dos_emu.c` defining `wubu_dos_emu_*`, called by `wubu_dos_proc.c` and
`wubu_exec_dos.c`), wiring it into the build has TWO distinct failure modes the
generic "add the `.o`" advice misses:

### Mode A — missing/undefined symbols (the common one)
Every link recipe that compiles a caller (`.c` listing `wubu_dos_proc.c` /
`wubu_exec_dos.c`) must ALSO carry `wubu_dos_emu.o` (or compile `wubu_dos_emu.c`
directly). Forgetting it → `undefined reference to wubu_dos_emu_create` etc.
**Sweep (verified, run after the edit):**
```sh
# any link line that mentions wubu_dos_proc but lacks wubu_dos_emu?
grep -n "wubu_dos_proc" Makefile | grep -v "wubu_dos_emu"
```
For each hit that is a backslash-continued link line, insert
`$(RT)/wubu_dos_emu.o \` on the next line (same indent+tab). For a one-line
`$(CC) … -o bin` recipe, inject ` $(RT)/wubu_dos_emu.o` before the ` -o `.
Also add `$(RT)/wubu_dos_emu.o` to `RT_OBJS` and `HOSTED_OBJS` so
`make runtime` / `make hosted` build it.

### Mode B — `.o` + `.c` duplicate definition (the non-obvious one)
If a test recipe links the **prebuilt** `$(RT)/wubu_dos_emu.o` (as a prereq OR
explicit link object) AND also compiles `$(RT)/wubu_dos_emu.c` on the link
line, you get `multiple definition of wubu_dos_emu_create` — two translation
units of the same source. Verified 2026-07-17 (`test_dos_proc` failed this way).
**Rule:** in any one link recipe, pick ONE form — either the prebuilt `.o` OR
the `.c` source, never both. `test_dos_emu` links `wubu_dos_emu.c` directly (no
`.o`); `test_dos_proc` links `wubu_dos_emu.c` directly too, and must NOT also
carry `wubu_dos_emu.o`. When the Mode-A sweep added `wubu_dos_emu.o` right after
a `wubu_dos_emu.c \` line, delete that inserted `.o` line.

### Mode C — duplicate TARGET after a block replace
Replacing a target block (e.g. `test_rescue:` → `test_dos_emu:` + `test_dos_proc:`)
via a line-replace can leave the OLD target still present if your old_string only
matched the header and the recipe shifted. Symptom: `make` shows the target
twice or a target's recipe compiles the wrong source. Fix:
`grep -c '^test_dos_proc:' Makefile` must be exactly 1; if 2, find the dead
block and delete it. (This session: an `execute_code` block-replace that matched
only `test_rescue:` + 3 lines left a SECOND `test_dos_proc:` because a prior
Python pass had already inserted one — verify target counts after every block
swap.)

### Verify before declaring green
```
make clean && make runtime && make hosted
make test                       # GATE exits 0
make test_dos_emu && make test_dos_proc   # per new target
```

### Mode D — ORPHANED MODULE (compiles fine, is never CALLED, has no test)
The most insidious failure is NOT a missing `.o` (ld errors loudly) — it is a
module that **builds clean but is dead code**: no caller, no test. It survives
every `make <dir>` because it's wired into `_OBJS`, but exercises zero logic.
This is the recurring "form-without-function" anti-pattern (a real engine with
no consumer). Verified 2026-07-18: `dos_window.c` was in `GUI_OBJS`
(compiled) but `grep -rn 'dos_window_spawn' src` found NO caller and
there was no `*_test.c` — it was a genuine host-a-DOS-process window engine that
nothing used. The fix is NOT just to delete it (the engine is real) — it is to
**wire a genuine consumer + add a real test**, so the module does work:

1. **Detect orphans fast** after any split / new-module add:
   ```sh
   # for a new public symbol, who (besides its own .c/.h) calls it?
   grep -rn 'dos_window_spawn' src --include=*.c --include=*.h \
     | grep -v 'dos_window\.c\|dos_window\.h'
   # any test for the module?
   ls src/gui/dos_window_test.c 2>/dev/null || echo "NO TEST"
   ```
   No callers + no test = orphan. Don't ship it.
2. **Wire a real consumer.** Find the registry / launch table that owns that
   subsystem (WuBuOS GUI apps live in `src/apps/apps.c` —
   `g_app_defs[]` is the single source of truth; add a launch fn + table row).
   The consumer must do REAL work, not print "window ready". For a DOS-process
   window: launch the proc via `wubu_dos_proc_launch(path, fmt)` then host it
   via `dos_window_spawn(proc, 1)`. Never add an `app_placeholder_draw`
   stub as the "integration" — that is the placeholder anti-pattern.

### Orphan subclass — BROKEN-and-UNREFERENCED (verified 2026-07-22)
A module can be an orphan AND fail to compile — the worst of both. Symptom:
untracked/modified `.c` that is (a) in NO `*_OBJS` variable and (b) referenced by
NO caller, AND (c) has compile errors that would surface the moment it's linked.
This session's `src/gui/era_apps.c` was exactly this: it used **invalid C
hex literals** `0xNT` / `0xHC` (N and H aren't hex digits → syntax error),
referenced `g_program_db` with no `extern` declaration (it didn't include the
internal header that declares it), and was not in `GUI_OBJS`/`HOSTED_OBJS` or any
`test_*` link line. It was half-written code a crashed session left orphaned.
**Fix (do NOT just delete — the intent is real):**
1. Give it a header declaring its public API + any personality/constant macros
   (e.g. `era_apps.h` with `ERA_PERSONA_*` bits and `era_apps_register()`).
2. Fix the compile errors (replace invalid literals with real VSL class bytes —
   CP/M `0xC0`, Classic Mac `0xB0`, NT/XNU `0xFF`/distinct inventory byte, DOS
   `0xD0`, HolyC `0xF0`; keep inventory bytes distinct from the live router's
   `0xFF` high-byte when you need them separate for UI grouping).
3. `#include` the header that declares the globals it touches (here
   `startmenu_internal.h` for `extern SmProgramDB g_program_db`).
4. Add its `.o` to the right `*_OBJS` list (`GUI_OBJS` + `HOSTED_OBJS` so both
   `make gui` and `make hosted` build/link it) and call its register/init hook
   from the owning subsystem's init (here `startmenu_init_enhanced()`).
5. Add its `.c` to the relevant `test_*` link line (here `test_startmenu`)
   so the build actually compiles it and the call resolves.
This closes the form-without-function trap: a module that both compiles AND is
called AND has a test.
3. **Add a real test** (mirror the repo's `X_test.c` + `X_test_stub.c`
   convention). The test must EXERCISE the engine end-to-end: launch a real
   `.COM` from a temp file, host it in the window, drive a frame, and assert the
   engine produced a non-empty RGBA frame / non-black pixels (proves real
   decode, not a faked string). Link the test like an existing equivalent
   target (e.g. `test_dos_proc`) and add it to `test_high_gui` /
   `test_medium_other`.

### Scalable orphan sweep (verified 2026-07-18, applied across ALL 373 modules)
Don't hunt orphans one file at a time — sweep the whole tree. The two-pass
scan catches BOTH failure modes:
- **Pass 1 (unwired):** a `.c` not referenced by basename `.c` OR `.o` anywhere
  in `Makefile`. Use `scripts/find_orphan_modules.py` (run from repo root):
  it cross-references every `src/**/*.c` against the Makefile's `.c`/`.o` tokens
  and prints the truly-unreferenced set. A naive `grep basename` gives false
  positives because the Makefile lists `.o` forms (`$(GUI)/desktop.o`)
  while your grep looked for `.c` — the script checks BOTH forms. False
  positives to ignore after the scan: wayland-scanner `.c` built via a
  `%.c: %.code` rule (e.g. `primary-selection-private.c`), and any file the
  `_legacy_bak/` dir holds (the scanner already excludes that dir).
- **Pass 2 (compiled-but-dead):** for each module that PASSED pass 1 (it is in
  an `_OBJS` list, so it builds), verify it has a CALLER and a TEST:
  ```sh
  sym=$(grep -rhoE '^[A-Za-z_]+ ' module.c | head -1)   # or the public symbol
  grep -rn "$sym" src --include=*.c --include=*.h | grep -v "module.c\|module.h" || echo "NO CALLER"
  ls module_test.c 2>/dev/null || echo "NO TEST"
  ```
  No caller + no test = dead code, even though `make <dir>` compiled it.

### SUB-PATTERNS of form-without-function found this session (add to the checklist)
- **Unimplemented API in the header (declared, never defined).** A module's
  public header advertises functions the `.c` never implements. Symptom: link
  fails with `undefined reference to wubu_cmd_history_add` while the header
  clearly declares it. Fix: IMPLEMENT the function (real ring-buffer / real
  logic) — do NOT delete the declaration or stub it with `return 0`. The header
  is the contract the rest of the tree expects. Verified 2026-07-18:
  `apps/cmd/cmd.c` declared `wubu_cmd_history_add/prev/next` in `cmd.h` but
  never defined them; implementing a real history buffer closed it.
- **Empty-facade `.c` (zero symbols).** A "facade" file that only `#include`s
  other modules and defines NO functions is dead weight — `nm --defined-only`
  shows nothing. Symptom: it sits in the tree, gets compiled into an `.o` that
  nothing links, and misleads readers into thinking it's the API entry point.
  Fix: DELETE it (the split `wubu_bottle_*.c` modules ARE the engine; the empty
  `wubu_bottles.c` facade added nothing). Verify with
  `nm --defined-only module.c | grep -E ' T | D '` → empty means safe to delete.
- **Joke / embedded garbage file.** A stray file deep in a handler dir (e.g. a
  `stub.c` containing an xkcd-random "execl /bin/bash -c <random>" body) is not
  a real stub — delete it. The "stub" label is a red flag; read the body before
  trusting it.
- **Struct-tag mismatch vs opaque header.** When a module defines its real
  struct as `typedef struct { ... } Foo;` (anonymous) but its public header
  forward-declares `typedef struct Foo Foo;`, the compiler treats them as
  DIFFERENT types → `conflicting types for 'Foo'` + `return &g` (incompatible
  pointer) warnings. Fix: name the struct `typedef struct Foo { ... } Foo;` so
  the tags match. Verified 2026-07-18 (`apps/cmd/cmd.c` `CmdState`→`WubuCmd`).

### Reap-hang bug class (NEW, 2026-07-18) — destroy/teardown blocks forever
A teardown path that reaps a child process via `waitpid(pid, NULL, 0)` BLOCKS
forever when the child is a LIVE interactive process (e.g. a shell spawned via
`forkpty` — bash ignores SIGTERM and stays attached). Symptom: the test runs,
prints everything up to the destroy call, then **HANGS** (timeout/124, not a
crash). This is NOT a double-free or segfault — the abort message is silent
because the process never returns.
**Fix (verified):** kill the whole process GROUP first, then reap — never a
bare `waitpid` on a possibly-live child:
```c
void wubu_cmd_destroy(WubuCmd *cmd) {
    if (g_cmd.child_pid > 0) {
        /* forkpty made the child a session leader → its pid IS a process-group
         * id. Kill the group so the shell + its children die, then reap. */
        kill(-g_cmd.child_pid, SIGKILL);
        waitpid(g_cmd.child_pid, NULL, 0);   /* now returns immediately */
        g_cmd.child_pid = 0;
    }
    if (g_cmd.pty_fd > 0) { close(g_cmd.pty_fd); g_cmd.pty_fd = -1; }
}
```
Diagnosis recipe when a test hangs (vs crashes): `timeout 15 gdb -q -batch -ex
run -ex bt ./test_bin` — a hang shows the backtrace stuck in `waitpid`/`futex`,
whereas a double-free shows it stuck in `free()`. Also: a pty read loop that uses
a NONBLOCKING fd (`fcntl(pty, F_SETFL, O_NONBLOCK)` at spawn) returns -1/0 when
no data, so the read loop itself won't hang — if it DOES hang, the block is in
teardown/reap, not the read. (See `wubuos-test-suite`
`references/debug-hang-crash-harness.md` for the general hang harness.)

### Mode E — `hc_eval` undefined when linking a DOS/exec test WITHOUT HolyC
`wubu_exec.c` calls `hc_eval(source)` unconditionally (no `#ifdef` guard). The
real definition lives in `src/compiler/holyc_codegen_api.c` (heavy HolyC
compiler — you do NOT want to pull it into a DOS-shim test). `test_dos_proc`
silently gets away with it because its link line ALSO compiles
`wubu_dos_proc_test.c` (which defines a local `int64_t hc_eval(...)`). Any NEW
target that links `wubu_exec.c` but does NOT include `wubu_dos_proc_test.c` will
fail: `undefined reference to hc_eval`.
**Fix:** add a dedicated minimal stub `src/runtime/wubu_hc_eval_stub.c`:
```c
#include <stdint.h>
int64_t hc_eval(const char *source) { (void)source; return -1; }
```
and list `$(RT)/wubu_hc_eval_stub.c` on the link line. Do NOT reuse
`wubu_dos_proc_test.c` for this (it has its own `main` → `multiple definition of
main`). This is the "runtime without HolyC" contract: returns -1 (no-op JIT).

### AddressSanitizer is the fastest way to pin a double-free / heap-overflow
When a test aborts with `double free or corruption` or segfaults in `free()`,
**don't guess** — rebuild the test binary with `-fsanitize=address` (ASan) and
run it. ASan reports the exact offending line + allocation site. Verified
2026-07-18: a DOS-window test crashed with "double free"; ASan immediately
pointed at `dos_window.c:63` as a **heap-buffer-overflow** (NOT a double
free — the abort message was a red herring), and the root cause was a bounds
check bug in `dos_win_draw` (see the real fixes below). Two genuine bugs were
found and fixed this way:
  - `dos_window_close` **double-freed the window**: it called
    `wm_destroy(win)` on a `win` the CALLER owns (the contract says
    "tear down the window's context; the caller frees the window"). Removed the
    premature `wm_destroy` call — `close` now frees only `ctx->fb` + `ctx`.
  - `dos_win_draw` **heap-buffer-overflow**: the clear loop bounds-checked
    `x < fb_w` but then wrote at `fb[(win->y + y) * fb_w + (win->x + x)]` — when
    the window sits near the framebuffer edge (`win->x + win->w > fb_w`), it
    wrote out of bounds. Fix: guard `px = win->x + x; if (px < 0 || px >= fb_w)
    continue;` (same for y). `blit_rgba` already guards correctly via
    `px < dst_w`.
Rule: when writing a framebuffer blit/clear loop, the bounds check MUST cover
the FINAL indexed coordinate (`win->x + x`), never just the loop index `x`.

### Reusable test-adder recipe (verified green 2026-07-18)
```makefile
test_dos_window: $(RT)/wubu_container.o $(RT)/wubu_exec.o \
    $(RT)/wubu_exec_dos.o $(RT)/wubu_dos_proc.o $(RT)/wubu_dos_emu.o \
    $(RT)/wubu_exec_wasm.o $(RT)/wubu_exec_macho.o $(RT)/wubu_exec_container.o \
    $(RT)/wubu_host_exec.o $(RT)/wubu_ct_isolate.o $(RT)/wubu_ct_isolate_cgroup.o \
    $(RT)/styx_names.o $(RT)/styx_enc.o $(RT)/styx_serve.o $(RT)/styx_parse.o \
    $(RT)/styx_fid.o $(RT)/styxfs_path.o $(RT)/styxfs_util.o
	$(CC) -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L \
		-I$(GUI) -I$(RT) -I$(COMP) -I$(KERNEL) -I$(JIT) -I$(HOSTED) \
		$(RT)/wubu_container.c $(RT)/wubu_exec.c $(RT)/wubu_exec_dos.c \
		$(RT)/wubu_dos_proc.c $(RT)/wubu_dos_emu.c \
		$(RT)/wubu_exec_wasm.c $(RT)/wubu_exec_macho.c $(RT)/wubu_exec_format.c \
		$(RT)/wubu_exec_container.c \
		$(RT)/wubu_host_exec.c $(RT)/wubu_ct_isolate.c $(RT)/wubu_ct_isolate_cgroup.c \
		$(RT)/styx_names.c $(RT)/styx_enc.c $(RT)/styx_serve.c $(RT)/styx_parse.c \
		$(RT)/styx_fid.c \
		$(RT)/styxfs_server.c $(RT)/styxfs_vfs.c $(RT)/styxfs_callbacks.c \
		$(RT)/styxfs_posix.c $(RT)/styxfs_path.c $(RT)/styxfs_host.o $(RT)/styxfs_util.c \
		$(GUI)/dos_window.c $(GUI)/dos_window_test.c \
		$(GUI)/dos_window_test_stub.c $(RT)/wubu_hc_eval_stub.c \
		-o $(GUI)/dos_window_test -ldl
	$(GUI)/dos_window_test
```
Notes from this recipe: (a) it compiles `wubu_exec.c` as a SOURCE on the link
line — so `wubu_exec_format.c` must ALSO be compiled there or you get
`undefined reference to wubu_detect_format` / `wubu_payload_name` (caught by
the ASan build above). (b) Add the new target to the `test_high_gui` aggregator
line so it runs in the full gate. (c) `-g` here is fine (small binary, not the
 OOM class); drop `-g` only if the link segfaults on memory.

 ### C11 Ring Attention Module (wubu_ring_attn) — Verified 2026-07-31

WuBuOS now has a built-in ring attention module (`include/wubu_ring_attn.h`, `src/wubu_ring_attn.c`) that implements chunked scan with LSE for 1M+ token contexts. Key patterns to know:

**Per-token architecture:** `ring_token_attention()` computes full-context Q·K softmax + weighted V accumulation for ONE query token. The hot loop calls it per token. This is the correct model — do NOT reuse a per-chunk output buffer across tokens; each token needs its own output.

**No INFINITY sentinel — use RING_LSE_MIN = -1e30f.** `-ffast-math` breaks `INFINITY` comparisons (`expf(-INFINITY - max) == 0` under fast-math is fine, but `== -INFINITY` comparisons may be optimized away). Use finite sentinels (`-1e30f`, `-1e29f`).

**`wubu_ring_attn_init()` pre-allocates score_scratch for `max_ctx` tokens** (full context, not chunk_size). The score buffer holds one float per token — sized for the full context length. A common bug is allocating only chunk_size entries, causing out-of-bounds writes.

**`wubu_ring_attn_forward()` is the main entry point.** It computes per-chunk local attention then merges outputs. The chunk loop runs in parallel via OpenMP. Each chunk is independent (no cross-chunk dependency in single-process mode; cross-chunk LSE merge is optional).

**Star Attention pattern:** Anchor blocks get full-context attention; periodic blocks get sparse attention via `ring_token_attention_sparse()` with a `k_slice_end` limit.

**Test target:** `make test_ring_attn` — verifies ring attention produces non-degenerate output (norm > 0) on a 256-token, 4-chunk, 2-head, dim=64 test.

**Known pitfall (FIXED):** The original `ring_chunk_local()` used a score buffer sized for chunk_size but iterated over all `max_ctx` tokens — buffer overflow → segfault. Fixed by switching to per-token `ring_token_attention()` with per-token output, and by sizing `score_scratch` for `max_ctx` entries in the context struct. Do NOT revert to the per-chunk buffer model. (NEW, 2026-07-19)
 A test binary that opens a fixture by a path relative to the **repo root**
 (e.g. `wubu_manifest_test.c` does `wubu_manifest_load("src/runtime/wubu_manifest/
 wubu_manifest.json")`) will fail to find the file if `make` runs it from a
 different CWD — the open returns NULL and the test reports "manifest loads from
 file" FAIL (or dereferences NULL). **Fix:** run the binary via `cd $(CURDIR)`
 in the recipe so the relative path resolves from the repo root:
 ```makefile
 test_manifest:
 $(CC) -O0 -g -std=c11 ... -Isrc/runtime/wubu_manifest \
 src/runtime/wubu_manifest/*.c -o $(RT)/wubu_manifest_test
 cd $(CURDIR) && $(RT)/wubu_manifest_test
 ```
 `$(CURDIR)` is make's absolute path to the Makefile's dir, so `cd` there makes
 the repo-root-relative fixture path correct regardless of where `make` was
 invoked. Add the new target to `test_medium_other` so it runs in the full gate.

 ### Removing a hostile / unreferenced file from a SUBMODULE (NEW, 2026-07-19)
 The parent repo pins a git **submodule** (`src/runtime/container/wubucontainer`).
 Its `-dirty` state can be a locally-deleted file in the *submodule's* tree — not
 the parent's. If that file is a self-extracting dropper (reads `/proc/self/exe`,
 seeks back N bytes, `execl("/bin/bash","-c",payload)`), it is NOT WuBuOS code and
 unreferenced by any build. When the repo is "all ours" (no external PR barrier):
 1. **In the submodule:** `git rm -f <file> <compiled_artifact>`, then commit.
  If the commit aborts with `empty ident name ... not allowed`, the submodule has
  no `user.name`/`user.email` (the parent may have one but the submodule doesn't —
  they are separate repos). Set a LOCAL identity only in the submodule:
  `git config user.name "..."; git config user.email "..."` (NOT `--global`), then
  `git commit` + `git push origin master`.
 2. **In the parent:** bump the pinned commit so the parent stops showing `-dirty`:
  `git add <submodule_path>`, `git commit`, `git push`. `git submodule status`
  should then show a space-prefixed (clean) entry.
 Rule: do NOT restore the hostile file, and do NOT silently commit into a sub-repo
 without intent — but removing unreferenced hostile code in an all-ours tree is
 correct. The parent's `git status` will keep showing `-dirty` until step 2 bumps
 the pin; the submodule push alone is not enough.

## THE MONOLITH-SPLIT LINK GAP (verified 2026-07-15 — broke `make test`)

When you split a monolith `foo.c` into `foo_a.c foo_b.c foo_c.c` (opaque
structs, minimal includes, C11), the new `.o` files MUST be wired into BOTH
the object-list variable AND every link recipe that references them, or a
clean `make test` (and `make canvas`/`make gui`) dies with:
`ld: cannot find src/.../foo_a.o`. This bit twice this session:

- **`wm_ctxmenu.c` split** (commit 29175ed) into
  `wm_clock.c` / `wm_ctxmenu_engine.c` / `wm_window_state.c`.
  The split added them to `HOSTED_OBJS` + the `test_hosted` link line but
  **dropped them from `GUI_OBJS`** and never listed them as *prerequisites* on
  `test_wm` / `test_hosted` / `test_control` / `test_gui_screenshot` /
  `test_apps`. On a warm tree the `.o` lingered from a prior `make gui`,
  so it only failed on `make clean && make test`. The link line referenced
  `$(GUI)/wm_clock.o` etc. but make never *built* them (no prereq →
  pattern rule never fires).
- **`canvas` `APP_RT_OBJS` gap** (earlier session's fix was mangled + reverted):
  `APP_RT_OBJS` had `styxfs_path/host/server/util` but was **missing**
  `styxfs_vfs.o` + `styxfs_callbacks.o` + `styxfs_posix.o` + `wubu_archd_svc.o`
  + `wubu_archd_fs.o`, leaving `normalize_path` / `styxfs_*_cb` /
  `wubu_archd_*` undefined at the canvas link.

### Symptom
`make test` (or `make canvas`) fails *only* with `ld: cannot find <split>.o`
for the exact files the split just produced — no `undefined reference`, just a
missing object. `make <name>` works if a prior build left the `.o` around.

### Fix (verified green)
1. Add the new `.o` (as `$(DIR)/foo_a.c` — the `$(DIR)/%.o: $(DIR)/%.c`
   pattern rule compiles a `.c` listed on a link line; OR as `$(DIR)/foo_a.o`
   if you also want it built by `make <dir>`) to the object-list variable the
   target uses (`GUI_OBJS` for gui/tests that consume `$(GUI_OBJS)`,
   `APP_RT_OBJS` for `canvas`/`apps`).
2. **Also list them as prerequisites on every `test_*` target whose recipe
   link line references them** (after the `target:` line, before the first
   `\t` recipe line). This forces make to compile them even on a clean tree.
   `_OBJS` vars are not automatically prerequisites of `test_*` targets that
   inline their link objects.
3. For `canvas`/`apps`, add the missing RT fragments to `APP_RT_OBJS`
   (NOT `RT_OBJS` — that collides with `HOSTED_OBJS`; see dedup nuance above).

### Reusable detection (run after ANY split)
```sh
# Per test target: does its link line reference a .o that no rule builds?
for t in test_wm test_hosted test_control test_gui_screenshot test_apps; do
  make -n $t 2>/dev/null | grep -oE 'src/[a-z/]+\.o' | sort -u | while read o; do
    [ -f "$o" ] || echo "MISSING-BUILD: $t needs $o (no rule/prereq builds it)"
  done
done
# Clean-tree proof (the real bar, never skip):
make clean && make test   # must EXIT 0
make clean && make canvas # must EXIT 0 (canvas was red here)
```
A warm-cache `make test` PASS is NOT proof — `make clean` is what exposes this
class. After a split, ALWAYS `make clean && make test` before declaring done. CRITICAL ADDITION (2026-07-22): `make test` is a curated tier aggregator and does NOT run every `test_*` target — a split can leave `test_screenshot`/`test_gui_screenshot`/etc. broken while the gate stays green. After ANY split, ALSO explicitly run the split's direct-consumer targets (`make test_<base>` plus any target the `grep -n "<base>" Makefile` flags). See the "RECOVERING A HALF-COMMITTED SPLIT AFTER A CRASH" section above.

### SYSTEMIC fix (preferred over per-target whack-a-mole)
The 2026-07-15 session found ~22 missing `.o` on a clean tree across MANY
targets (wm_input/window, wubu_settings_defaults/io, styxfs_*,
wubu_archd_loop, wubu_container, wubu_snapshot*, wubu_ns_*, wubu_pkg,
wubu_proton_dxvk, wubu_bottle_serialize, wubu_holyd_repl, …). Adding a
prereq to each `test_*` target individually is fragile. The robust fix:
**make the tier AGGREGATOR targets depend on `runtime` / `gui` / `hosted`** —
the phony targets that build the full `RT_OBJS` / `GUI_OBJS` / `HOSTED_OBJS`
lists. Verified green:
```makefile
test_critical_runtime: runtime test_oci test_network ...
test_high_bridge:      runtime test_bridge test_bridge_flip test_syscall
test_high_gui:         gui runtime test_wm test_startmenu ...
test_medium_other:     runtime gui test_worldsim test_audio ...
```
This guarantees every split-module `.o` is compiled (by `make runtime` /
`make gui`) BEFORE the inline-linking `test_*` leaf targets run, closing all
clean-tree gaps in one edit. Keep the leaf-target-specific prereqs too (they
help incremental builds), but the aggregator prereqs are the safety net.
Caveat: `runtime` + `gui` add build time to `make test`, but correctness >
speed. `hosted` is NOT needed as an aggregator prereq (hosted tests already
prereq `$(HOSTED)/*.o` explicitly and don't link full RT_OBJS).
Do NOT add `$(RT_OBJS)` to a `hosted`-env link (multiple-definition trap
above) — `runtime` as a prereq only *builds* the objects, it doesn't link
them.

## RECOVERING A HALF-COMMITTED SPLIT AFTER A CRASH (verified 2026-07-22)

A crash mid-split leaves a distinct tree state from a clean working tree:
`git status --short` shows BOTH modified tracked files (the base module being
split, e.g. `M src/gui/wubu_wm.c`) AND untracked NEW files (the split products,
e.g. `?? src/gui/wubu_wm_desktop.c`). The in-flight build usually only PARTIALLY
wired the new files, so the next `make test` fails on the first unwired link line.
This is the "crash reconciliation" case for a split (vs the boot-stub stash case
elsewhere in this skill).

### Symptom shape
- `make test` fails at a specific target with `undefined reference to <sym>`
  where `<sym>` is a `const` table/array the split moved into a NEW file.
- The defining file EXISTS (untracked) but is NOT on the failing target's link
  line. Example (2026-07-22): the macOS syscall split moved `mac_bsd_table[512]` /
  `mac_trap_table[96]` into `vsl_syscall_mac_bsd.c` / `vsl_syscall_mac_mach.c`, but
  `test_syscall`'s link line only listed `vsl_syscall_mac.c` (the dispatch file
  that *references* the tables). `ld` reported `undefined reference to
  mac_trap_table` / `mac_bsd_table`.

### Recovery recipe (run in order)
1. **Enumerate the damage.** `git status --short` (modified base + untracked split
   files) and `git diff --stat` (what the in-flight edit touched). Note every
   `<base>.c` that lost lines and every new `<base>_<sub>.c`.
2. **Find which link lines reference the base module.** `grep -n "<base>" Makefile`
   (e.g. `wubu_wm`). Every target whose recipe mentions `<base>.c`/`<base>.o` may
   ALSO need the new split files — not just the gate target.
3. **Map the undefined symbol to its DEFINING file** (not just any file):
   `grep -rn "<sym>" src` -> the `const <type> <sym>[...] = {` definition lives in
   the split file you forgot to wire. Add THAT file to the link line.
4. **Wire the split files into EVERY link line that references the base.** For the
   WM split (2026-07-22) that meant adding `wubu_wm_desktop.c wubu_wm_input.c
   wubu_wm_render.c` to both `test_screenshot` and `test_gui_screenshot`, not just
   `test_wubu_wm` (already covered by the in-flight edit). For the macOS split it
   meant adding `vsl_syscall_mac_bsd.c vsl_syscall_mac_mach.c` to `test_syscall`.
5. **Add the split files to the object-list variable too** (`GUI_OBJS`, `RT_OBJS`)
   so `make gui`/`make runtime` build them; verify with
   `make -s --eval='p:; @echo $(GUI_OBJS)' p | grep wubu_wm_desktop`.
6. **Re-run the GATE, then the DIRECT consumers** (see pitfall below).

### PITFALL — `make test` green is NOT sufficient after a split
`make test` is a curated tier aggregator; it does NOT run every `test_*` target.
After the 2026-07-22 WM split, `make test` was GREEN (all tiers PASS) even though
`test_screenshot` and `test_gui_screenshot` referenced `wubu_wm.c` WITHOUT the new
split files and would have failed with undefined refs — the gate simply never
invoked them. **Rule:** after ANY split, explicitly run the targets that DIRECTLY
consume the split module — `make test_<base>` AND any other target the step-2 grep
flagged (e.g. `make test_screenshot`, `make test_gui_screenshot`, `make test_vsl_mac`,
`make test_vsl_macho`). Do NOT trust "all tiers PASS" alone.

### Triage pre-existing vs crash-introduced breakage during recovery
A crash-recovery pass surfaces broken targets that are NOT your fault. The
2026-07-22 session found `test_gui_screenshot` ALSO broken by a PRE-EXISTING defect
(unrelated to the split): it links `hosted.c` (own `main()` at hosted.c:208)
alongside `wubu_screenshot_test.c` (also `main()`) -> `multiple definition of main`,
AND references `hosted_wayland_surface.o` / `xdg-shell-private.o` /
`primary-selection-private.o` — three Wayland-codegen `.o` files with NO `.c`
sources. This was already broken before the crash. **Judgment call:** during a
crash recovery, do NOT scope-creep into pre-existing defects unless (a) they're in
the `make test` gate, or (b) the user explicitly directs. Note them, leave them,
finish the recovery commit, and flag them in the handoff. The split-induced break
(`undefined reference` to the moved symbol) is the priority; the pre-existing
`main()`-collision + missing-codegen `.o` is a separate rabbit hole.

### Reference-dump hygiene
A split that pulled in external reference material (e.g. a `darling-ref/`
144M macOS-XNU reference dump) must NOT be committed. The repo `.gitignore` already
excludes `reference/*/` study dirs — add the new dump following that convention
(`darling-ref/`) and keep it local. A regenerated test binary (e.g.
`src/runtime/wubu_dos_emu_smoke`, tracked) shows as modified after a build — it's a
build artifact; exclude it from the recovery commit (stage the sources; `git add`
the binary only if intentionally refreshing it).

See `references/recover-half-committed-split.md` for the exact command transcript.

## Memory-constrained linker: OOM segfault + stack-overflow (NEW failure class, 2026-07-13)

This WSL box has a HARD per-`cc`/linker memory ceiling. A `cc` invocation that
compiles+links **~20-30 translation units at once** (the original `test_ns_bridge`
monolith, or any test that links snapshot+bottles+archd+styx together) will
**segfault** — `make: *** [Makefile:N: target] Segmentation fault (core dumped)`
or a `collect2: error: ld returned 139` / the test binary dumps core at *runtime*
(exit 139). This is NOT a code bug; it is `cc1`/`collect2` exhausting the cgroup
memory while holding all TUs' debug info in RAM. Symptom triage:

- Link line builds MANY `.c` (or MANY debug `-g` `.o`) in one `$(CC)` call → OOM.
- Even `-Wl,--reduce-memory-overheads -Wl,--no-keep-memory` does NOT save you here
  when the combined object set (e.g. `wubu_snapshot.c` ~88KB `.o` but huge in-core)
  is large. `ld` still reads everything before linking.
- A test binary that **segfaults at runtime with exit 139** but links fine is
  usually a **stack overflow**, not heap — see below.

### Recovery recipe (verified, in order)

1. **Reduce TU count per link, hard.** The budget that demonstrably works is
   ~30 files for the *original* bridge test; adding even 3 large snapshot
   objects broke it. Split a new test that needs heavy modules into its OWN
   small binary:
   - `test_ns_snap` links ONLY `wubu_ns_fs.c + wubu_ns_snap.c + wubu_snapshot.c
     + wubu_snapshot_fs.c + wubu_snapshot_copy.c + wubu_fs_util.c + <test>.c`
     (7 files) and got **16/16 green**. Keep each test binary under ~10-12 files.
2. **Prefer linking PREBUILT `.o` over recompiling from `.c` in the recipe.**
   `make runtime` compiles each `.o` in its own `cc` process (low peak memory).
   Then a test recipe does `$(CC) -no-pie *.o -o bin` (link only). This avoids the
   giant combined compile. Pattern:
   ```
   test_x:
   	$(CC) -O0 -std=c11 ... -c $(RT)/x_test.c -o /tmp/x_test.o
   	$(CC) -O0 -no-pie $(RT)/wubu_ns_fs.o $(RT)/wubu_ns_snap.o ... /tmp/x_test.o -o $(RT)/x_test
   ```
3. **Drop `-g` from the test compile** (`-O0` without `-g`). Debug info is what
   bloats in-core link memory; tests don't need it. This alone let larger links
   through.
4. **`make` itself can segfault on a specific target** (transient process crash,
   not the recipe). If the binary builds+links fine when you run the `$(CC)`
   commands by hand but `make test_x` reports `Segmentation fault`, it's the
   `make` process — bypass it: run the link command directly in `terminal`, then
   run the binary. The recipe is still correct for a healthy runner.
5. **RUNTIME stack-overflow (exit 139, gdb shows crash at a function's opening
   brace):** WuBuOS has GIGANTIC structs. `WubuSnapshotManager` is **~56 MB** —
   it MUST be `calloc(1, sizeof(...))` on the heap, never a stack local
   (`WubuSnapshotManager mgr;`). Likewise `WubuSnapshot snaps[WUBU_MAX_SNAPSHOTS]`
   (1024) is too big for the 8MB stack — heap-allocate `calloc(SNAP_CAP, ...)`
   with a sane cap (256). The real `wubu_snapshot_test.c` uses exactly this
   `smgr()` heap helper. Any new test touching these structs must heap-allocate.
   Find the size fast: `cat >/tmp/sz.c <<'EOF' ... sizeof(WubuSnapshotManager) ...`\n   or run under AddressSanitizer (`-fsanitize=address`) to get `stack-overflow`\n   at the exact frame.\n\n### Validated template (2026-07-13, shipped green)\n\nWhen a `/n` subtree needs a heavy module (snapshot/bottles), give it its OWN\nbinary instead of bolting onto `test_ns_bridge`. This template worked for\n`test_ns_snap` (16/16), `test_ns_pkg` (13/13), `test_ns_kernel` (13/13):\n```makefile\ntest_ns_x:\n\t$(CC) -O0 -std=c11 -D_POSIX_C_SOURCE=200809L -Wno-format-truncation -I$(RT) \\\n\t    -c $(RT)/wubu_ns_x_test.c -o /tmp/wubu_ns_x_test.o\n\t$(CC) -O0 -no-pie $(RT)/wubu_ns_fs.o $(RT)/wubu_ns_x.o <prebuilt deps> \\\n\t    /tmp/wubu_ns_x_test.o -o $(RT)/wubu_ns_x_test\n\t$(RT)/wubu_ns_x_test\n```\n- Compile ONLY the test `.c` fresh (`-c` to `/tmp`); link PREBUILT runtime `.o`.\n- NO `-g` on the compile (debug info bloats the link). `-O0` is fine.\n- Heap-allocate any struct the test instantiates that is >~1MB (see step 5).\n- Add `test_ns_x` to the `test_medium_other` gate line.\n- After adding a target, run `make -n test_ns_x` and confirm it does NOT list\n  any source from an UNRELATED subtree (catches the orphaned-target trap).\n
### Why this is its own recipe, not "just add the .o"
The instinct "add the missing object to the link" is right for `undefined
reference`, but here the link SUCCEEDS and then either the linker or the binary
crashes on memory. The fix is structural (fewer/smaller objects, heap structs),
not symbol-level. Spent most of a session re-learning this — encode it.

## Stray in-test `outb` serial markers → ring-3 SIGSEGV (NEW failure class, 2026-07-15)

A hosted/test build that links `vbe.c` or `memory.c` can **SIGSEGV at the first
statement of an init function** — gdb shows the crash inside `vbe_init` /
`mem_init` at a line that is JUST an `__asm__ __volatile__("... outb %%al,%%dx")`.
This is a privileged-instruction fault, not a code bug:

- Prior sessions sprinkled `outb 0x3F8` serial-debug markers ("M","L","N","O","P"
  / "v","w","x","y") into functions that ALSO compile into ring-3 test binaries.
  `vbe.c` is linked by `test_bridge` / `test_explorer` / `test_startmenu`;
  `memory.c` by `test_memory`. `outb` to COM1 (0x3F8) in ring-3 → `#GP` → SIGSEGV.
- **Detection:** `grep -rn 'outb %%al' src/` to find raw port I/O. If a test
  target SEGVs at init and the top frame is an `outb`, that's it.
- **Fix:** delete the stray `outb` markers in any file compiled into a user-space
  test. Route the trace through the existing `VBE_LOG(...)` (hosted → stderr,
  bare-metal → `klog_printf`) or `klog_printf` instead. NO code logic lives in
  those markers — they are pure debug noise.
- **DO NOT blindly strip all `outb`.** `src/kernel/metal_main.c` (`kernel_main`,
  never in a test target) and `src/kernel/interrupt.c`'s `ILOG` macro are
  *legitimate* bare-metal serial logging and must stay — removing them breaks
  real-hardware debug output. Rule of thumb: only remove `outb` from files that a
  `test_*` target actually compiles AND executes in ring-3. Empirically this
  session: `vbe.c` + `memory.c` removed (gate red→green); `metal_main.c` /
  `interrupt.c` left (gate already green — `ILOG` doesn't fire in ring-3).
- **Verify:** `make test` green; also confirm the bare-metal path still compiles:
  `gcc -c -std=c11 -DMYSEED_METAL -I src/kernel src/kernel/memory.c -o /tmp/m.o`.

## Test Suite Verification - All Tiers Green (2026-07-21)

```bash
make test  # run for the live target/assertion count (do not cite a fixed total)
```

**Critical fixes this session:**
- NT syscall transliteration: ReactOS ordinal mapping wired to 100% parity (run `build_nt_test_lite.sh` for the live count)
- `test_control` 20/20 pass (orb double-buffer + user_data fix)
- `test_calc` linker errors fixed (removed duplicate `calc_test_stub.c`, compile all WM sources)
- `test_trash` target added to Makefile (was missing from `test_medium_other`)
- All tier targets green: `test_critical_runtime`, `test_critical_kernel`, `test_high_bridge`, `test_high_gui`, `test_high_bear`, `test_medium_other`

### Control Panel Two-Pane Render Test Fixed (2026-07-21)
**Symptom:** `test_control` failed on "Control Panel orb (red quadrant) drawn in left rail" — the XP orb's 4 colored quadrants weren't detected in the framebuffer.

**Root causes (multiple):**
1. **Double-buffer confusion** — VBE drawing functions write to `g_vbe.back` (back buffer), but test read from `g_vbe.fb` (front buffer) before `vbe_swap()`
2. **Test called `chrome_draw_window()` twice** — first call inside `control_draw()` draws chrome+content; second call in test redraws chrome OVER the orb, erasing it
3. **Test used local `DosGuiWindow` without `user_data = c`** — `control_draw_content()` reads `win->user_data` for `ControlState*`, which was NULL

**Fix applied:**
- `control_draw()` now explicitly passes `vbe_state()->back` to chrome/content drawing
- Test calls `vbe_swap()` then reads from `vbe_framebuffer()` (front buffer)
- Test does NOT call `chrome_draw_window()` again — computes content rect from window geometry
- Test sets `win.user_data = c` before calling `control_draw()`

**Result:** `test_control` now passes 20/20 (was 19/20).

## Stray in-test `outb` serial markers → ring-3 SIGSEGV (NEW failure class, 2026-07-15)

A hosted/test build that links `vbe.c` or `memory.c` can **SIGSEGV at the first
statement of an init function** — gdb shows the crash inside `vbe_init` /
`mem_init` at a line that is JUST an `__asm__ __volatile__("... outb %%al,%%dx")`.
This is a privileged-instruction fault, not a code bug:

- Prior sessions sprinkled `outb 0x3F8` serial-debug markers ("M","L","N","O","P"
  / "v","w","x","y") into functions that ALSO compile into ring-3 test binaries.
  `vbe.c` is linked by `test_bridge` / `test_explorer` / `test_startmenu`;
  `memory.c` by `test_memory`. `outb` to COM1 (0x3F8) in ring-3 → `#GP` → SIGSEGV.
- **Detection:** `grep -rn 'outb %%al' src/` to find raw port I/O. If a test
  target SEGVs at init and the top frame is an `outb`, that's it.
- **Fix:** delete the stray `outb` markers in any file compiled into a user-space
  test. Route the trace through the existing `VBE_LOG(...)` (hosted → stderr,
  bare-metal → `klog_printf`) or `klog_printf` instead. NO code logic lives in
  those markers — they are pure debug noise.
- **DO NOT blindly strip all `outb`.** `src/kernel/metal_main.c` (`kernel_main`,
  never in a test target) and `src/kernel/interrupt.c`'s `ILOG` macro are
  *legitimate* bare-metal serial logging and must stay — removing them breaks
  real-hardware debug output. Rule of thumb: only remove `outb` from files that a
  `test_*` target actually compiles AND executes in ring-3. Empirically this
  session: `vbe.c` + `memory.c` removed (gate red→green); `metal_main.c` /
  `interrupt.c` left (gate already green — `ILOG` doesn't fire in ring-3).
- **Verify:** `make test` green; also confirm the bare-metal path still compiles:
  `gcc -c -std=c11 -DMYSEED_METAL -I src/kernel src/kernel/memory.c -o /tmp/m.o`.

## Verification gate (must pass before declaring done)

```
make runtime && make hosted && make apps && make canvas   # all exit 0
make test                                                # GATE exits 0, "All tests passed"
```
`doom` was **deleted** (Wolfenstein-3D raycaster clone — not the accepted
FreeDoom impl `wubu_freedoom.c`). `paint` was **deleted** (MS-Paint toy) and
replaced by `canvas` (real `wubu_canvas` engine; `make canvas` builds
`src/apps/canvas_standalone.c`). If a target you expect is missing, check
`git log` — target names change when clones are purged.
`make hosted` is the integration canary: if it goes red after a Makefile edit,
you almost certainly duplicated or dropped an object in `HOSTED_OBJS`.
`make test` is the final authority — never skip it.

## HOSTED_OBJS + full RT_OBJS = dozens of `multiple definition` (NEW, 2026-07-14)

A `test_*` target that needs the **hosted** environment (GUI + kernel-in-process +
Styx) is tempted to link `$(HOSTED_OBJS) $(RT_OBJS)` (or `HOSTED_TEST_OBJS + RT_OBJS`).
**Do not.** `HOSTED_OBJS` and `RT_OBJS` share many objects — `styx`, `styxfs_*`,
`wubu_exec*`, `wubu_container.o`, `oci/oci_http_client.o`, `wubu_fs_util.o`,
`wubu_archd_*`, `wubu_ramdisk*`, … Linking both lists together feeds **two distinct
`.o` files** (one from each list) that define the same globals →
`ld: multiple definition of <sym>; <same .o>: first defined here` on *every* shared
symbol. This is exactly what broke `test_hosted` in the 2026-07-14 session.

### The `ld` dedup nuance — CORRECTED (verified 2026-07-22)
- **Listing the same `.o` path twice on a link line is NOT benign in this toolchain.** It causes `multiple definition of <sym>` (verified: `HOSTED_OBJS` listed `ct_iso_seccomp.o ct_iso_cgroup.o ct_iso_ns.o` **twice** and `RT_OBJS` listed them once more; the `hosted` recipe concatenates `HOSTED_OBJS` + `RT_OBJS`, so `$(RT)/ct_iso_seccomp.o` appeared 3× and broke the link with `multiple definition of runtime_to_seccomp`). The old claim "gcc a.o a.o links fine" does NOT hold for GNU ld with loose relocatable objects — dedupe applies to **archive members**, not loose `.o` on the command line. **Never list an object path more than once across the concatenated link inputs.**
- `multiple definition` fires whenever the same global symbol is pulled from two inclusions of an object — whether the duplicate is the SAME path listed twice (within one variable, or across `HOSTED_OBJS`+`RT_OBJS`) or two DIFFERENT objects. "The object is listed twice" IS the right mental model for this repo's hand-maintained lists.
- Consequence: `HOSTED_OBJS` (pristine) *already* contains `oci_http_client.o` AND `RT_OBJS` *also* contains `oci_http_client.o` — yet `make hosted` links fine ONLY because the `hosted` recipe links `HOSTED_OBJS` + only a **few explicit RT fragments** (`styxfs_vfs.o styxfs_callbacks.o styxfs_posix.o wubu_fs_util.o wubu_archd_fs.o wubu_archd_svc.o`), NOT full `$(RT_OBJS)`. The overlap in the *variables* is harmless as long as you never link both lists in full AND no single variable lists an object twice.

 **`hosted`/`test_*` targets must LIST their literal link objects as PREREQS (2026-07-22).** A link recipe that names `$(RT)/wubu_holyc_agi.o` / `$(RT)/holyd_lifecycle_app.o` on the `$(CC)` line but does NOT list them on the `target:` prereq line has a latent build-break: on a warm tree the `.o` already exists (built by `make runtime`), so it links; after `make clean` it's gone and `ld` reports `cannot find .../wubu_holyc_agi.o`. This bit the `hosted` target this session. **Fix:** add every object that appears on the link line to the target's prereq line (or to the owning `*_OBJS` variable the target depends on). The same trap hit the two new VSL personalities: `test_vsl_cpm` / `test_vsl_macclassic` were standalone-only targets that `make test` (the tier aggregator) never invoked — they were only green because nothing ran them. **Fold any new `test_*` target into the top-level `test:` aggregator** (`test: test_critical_runtime ... test_vsl_cpm test_vsl_macclassic`) so the gate actually exercises it; otherwise it's a false-green.

 **Verify a crashed/Makefile-edited tree with the canonical 4-step gate (not piecemeal):**
 ```bash
 make clean && make runtime && make hosted && make test   # ALL four must exit 0
 ```
 `make runtime` + `make hosted` + `make test` were the verified bar this session; `make hosted` was the canary that caught the `ct_iso_*` dup + missing prereqs. A `make test` green alone is NOT sufficient (gate doesn't run every `test_*`, and `hosted` isn't in the gate).

**`make hosted` broken at HEAD despite a green slate (verified 2026-07-22).** The slate/index claimed `make hosted` exited 0, but that was STALE — at HEAD `make hosted` was actually broken (the author never ran a fresh `make clean && make hosted`; a stale `.o` cache masked it). A session crash forced a clean rebuild and exposed it. Two distinct defects: (a) the within-`HOSTED_OBJS` `ct_iso_*` duplicate above; (b) the `hosted` link referenced `wubu_holyc_agi.o` / `holyd_lifecycle_app.o` that were never prerequisites → `cannot find` after `make clean`. **Rule: never trust a handoff/slate build-status line — run `make clean && make runtime && make hosted` for ground truth after any crash.** A warm-cache `make hosted` PASS is NOT proof.

### Fix (verified green)
Mirror the working `hosted` link model. For a hosted-env test:
```
test_x: $(HOSTED)/xdg-shell-private.o $(HOSTED)/primary-selection-private.o
	$(CC) ... -I... \
		$(HOSTED_TEST_OBJS) $(RT)/styxfs_vfs.o $(RT)/styxfs_callbacks.o \
		$(RT)/styxfs_posix.o $(RT)/wubu_fs_util.o $(RT)/wubu_archd_fs.o \
		$(RT)/wubu_archd_svc.o \
		$(HOSTED)/test_x.c $(HOSTED)/hosted.c \
		-lwayland-client -lxkbcommon -lm -lsqlite3 -lzstd -lz -ldl -lpthread -ljson-c -lvulkan \
		-o $(HOSTED)/test_x
```
where `HOSTED_TEST_OBJS = $(HOSTED_OBJS:$(HOSTED)/hosted.o=)` (drops the one-true
`main`, replaced by the test's `main` via `hosted_test.c`/`hosted.c` recompiled as a
source with `-DWUBU_HOSTED_TEST`). **Never** add `$(RT_OBJS)` to a hosted-env link.
Need archd/wubucontainer/json/vulkan symbols? Add the specific RT fragment(s) the
`hosted` recipe already pulls, plus `-ljson-c -lvulkan` (those libs are NOT in the
`hosted` link line and must be added for tests that touch `wubucontainer.c` /
`vsl_gpu_vulkan.o`).

### C11 Ring Attention Module (wubu_ring_attn) — Verified 2026-07-31

WuBuOS now has a built-in ring attention module (`include/wubu_ring_attn.h`, `src/wubu_ring_attn.c`) that implements chunked scan with LSE for 1M+ token contexts. Key patterns:

**Per-token architecture:** `ring_token_attention()` computes full-context Q·K softmax + weighted V for ONE query token. The hot loop calls it per token. This is the correct model — do NOT reuse a per-chunk output buffer across tokens; each token needs its own output.

**No INFINITY sentinel — use RING_LSE_MIN = -1e30f.** `-ffast-math` breaks `INFINITY` comparisons. Use finite sentinels (`-1e30f`, `-1e29f`).

**`wubu_ring_attn_init()` pre-allocates score_scratch for `max_ctx` tokens** (full context, not chunk_size). The score buffer holds one float per token. A common bug is allocating only chunk_size entries, causing out-of-bounds writes.

**`wubu_ring_attn_forward()` is the main entry point.** It computes per-chunk local attention then merges outputs. The chunk loop runs in parallel via OpenMP. Each chunk is independent (no cross-chunk dependency in single-process mode; cross-chunk LSE merge is optional).

**Star Attention pattern:** Anchor blocks get full-context attention; periodic blocks get sparse attention via `ring_token_attention_sparse()` with a `k_slice_end` limit.

**Test target:** `make test_ring_attn` — verifies ring attention produces non-degenerate output (norm > 0) on a 256-token, 4-chunk, 2-head, dim=64 test.

**Known pitfall (FIXED):** The original `ring_chunk_local()` used a score buffer sized for chunk_size but iterated over all `max_ctx` tokens — buffer overflow → segfault. Fixed by switching to per-token `ring_token_attention()` with per-token output, and by sizing `score_scratch` for `max_ctx` entries in the context struct. Do NOT revert to the per-chunk buffer model.

### Test targets that link a prebuilt `.o` directly (the `test_ns_pkg` trap)
A test recipe that links `src/runtime/wubu_ns_pkg.o` (or any `<mod>.o`) as a direct
dependency **will fail** with `ld: cannot find <mod>.o` if that object is not built by
`make runtime`/`make apps` — i.e. it isn't in `RT_OBJS` (or `APP_RT_OBJS`). The
`test_ns_pkg` target broke this way in the 2026-07-14 session: `wubu_ns_pkg.o` existed
as a source but was missing from `RT_OBJS`, so `make runtime` never produced it.
**Fix:** add `$(RT)/wubu_ns_pkg.o` to `RT_OBJS` (it then builds under `make runtime`
and is available to both the hosted link and the test). Before assuming a missing
`.o` is "bit-rot", check `make -s --eval='p:; @echo $(filter %/<mod>.o,$(RT_OBJS))' p`
— empty output means it's simply not in the object list.

### Reusable verification (catches this class before the link)
See `scripts/check_link_dupdef.sh <target>` — expands the target's link objects via
`make -n`, extracts each `.o`, runs `nm --defined-only -g` on the built ones, and
reports any global symbol defined in 2+ objects (the precise predictor of
`multiple definition`). Run it after any Makefile object-list edit that touches
`HOSTED_OBJS`/`RT_OBJS`.

## Freestanding kernel link break (`make kernel`) — DISTINCT failure class

`make kernel` links with `-ffreestanding -nostdlib -nostartfiles -fno-pie
-mno-red-zone -mcmodel=kernel`. This REJECTS things the hosted/RT builds accept,
and is unrelated to the multiple-def / missing-`.o` / OOM classes above. Verified
2026-07-14. Full cookbook in `references/kernel-freestanding-recovery.md`.

### Trigger / triage
`make kernel 2>&1 | grep -oE 'undefined reference to \`[^']+\'' | sort -u` —
if you see `__fprintf_chk`, `__memcpy_chk`, `__memset_chk`, `__printf_chk`,
`__snprintf_chk`, `__sysv_signal`, `stderr`, `abs`, `gmtime`, `time`,
`__ctype_toupper_loc`, `_setjmp`, `__longjmp_chk` → freestanding gap, NOT a
Makefile object-list bug. If you see `relocation truncated to fit: R_X86_64_32`
→ boot-stub/higher-half VA problem.

### Three root causes + fixes (one-liners; details in the reference)
1. **`R_X86_64_32` relocation truncated** (crt0.S references higher-half VAs in
   32-bit `.code32`): split VMA(higher-half) from LMA(physical 1MB) via
   `PHDRS`+`AT()` in `kernel.ld`; define **absolute low-physical** scratch
   symbols (`page_table_base = 0x90000` etc.) for the boot stub; make crt0
   **position-independent** for the long-mode jump (`call .get_eip; pop %ebx`,
   then `leal (label - .get_eip)(%ebx), %eax`). Never `movl $_higher_half_sym`.
   `ld` also errors on referencing input-object/`.rodata`/`.text` symbols inside
   `= expr` assignments ("undefined symbol … in expression") — use only
   `ABSOLUTE(_kernel_start) - _physical_offset` form.
   **CONCRETE 2026-07-16 INSTANCE — `.data` boot scratch:** a crash left
   `boot_magic:` declared via `.section .data` / `.long 0` inside crt0.S, then
   `movl $boot_magic, %edx`. `.data` is linked higher-half, so this emits
   `R_X86_64_32 against '.data'` and fails the kernel link. The FIX is NOT the
   `movl` syntax — it is to move the scratch OUT of `.data` into an **ABSOLUTE
   low-physical linker symbol** (`boot_magic = 0x90040;` in kernel.ld, mirroring
   `page_table_base`), which assembles to a literal 32-bit immediate (no
   relocation). See `references/kernel-freestanding-recovery.md` Symptom 1b for
   the exact error text + fix. RULE: never reference a `.data`/`.bss`/higher-half
   symbol with a 32-bit absolute in the boot stub — use `sym = 0x900xx;` or
   position-independent `call .get_eip; pop %ebx`.
2. **`_setjmp`/`__longjmp_chk` undefined**: kernel built with `MYSEED_METAL` but
   `tasking.c` gates the real asm switch on `WUBU_BAREMETAL`. Build kernel objects
   with `-DWUBU_BAREMETAL=1` (a `KERNEL_CFLAGS` var) so it uses `task_switch_asm`
   instead of the hosted setjmp path (which doesn't exist under `-nostdlib`).
3. **missing freestanding libc**: complete `src/kernel/libc.c` with `abs`/`labs`,
   `time`/`gmtime` (static `struct tm`, fixed epoch), `sigaction`/`signal`/
   `__sysv_signal` no-ops, `__ctype_toupper_loc`, `__memcpy_chk`/`__memset_chk`
   wrappers, and `fprintf`/`printf`/`snprintf`+`__*_chk` routed to a serial
   `klog`. Add `klog.c`/`klog.h` to `KERNEL_OBJS`; route `memory.c` diagnostics
   via `#ifdef MYSEED_METAL … klog_printf … #else fprintf(stderr,…)`.
   **Gotchas:** `struct tm`/`time_t` are ALREADY typedef'd at the top of libc.c
   — do NOT redeclare (redefinition error). Do NOT add setjmp/longjmp in libc.c
   (clashes with libc.h's `jmp_buf`).

### Verification
`make kernel` → `✅ Bare-metal kernel.elf built`, exit 0. `make all` → exit 0.
Caveat: the ELF *links*; runtime boot needs QEMU (unavailable in this WSL env) —
link success is the verified bar. Also add `make shell` + `make test_shell` to the
gate when touching the shell subtree (`shell` target was previously missing
entirely; BATTLESHIP 228-231 now real, 9/9).

## Bare-metal bootsector (`src/kernel/boot.S`) — assembly + QEMU validation

`boot.S` is a 16-bit real-mode bootsector (NOT kernel-model code). It assembles
to a 512-byte image via `make boot`, and `make qemu` packs it + `kernel.elf`
into a 1.44MB floppy and boots under QEMU. Two non-obvious traps consumed a
full debug session and are encoded in `references/baremetal-qemu-boot.md`:

1. **SeaBIOS loads a raw sector at LINEAR 0, not 0x7C00.** Using `.org 0x7C00`
   makes every symbol VMA wrong (strings/data unreachable → `serial_puts` emits
   nothing, machine triple-faults into a reboot loop while a raw `outb` still
   works). **Always `.org 0`** so VMA == file offset == linear load address.
2. **`cld` is mandatory** before `lodsb`/`stosb` (BIOS leaves DF set → walks
   backward through memory, reads garbage).
3. Assemble with **plain `-m16 -ffreestanding -nostdlib`** — never the kernel
   `-mcmodel=kernel -fno-pie` flags (they corrupt 16-bit code).
4. ELF entry formula: physical entry = `e_entry & 0xffffffff - 0x80000000`
   (do NOT also add 0x100000 — that double-counts the LMA).
5. **QEMU capture:** use `-nographic` + `-device isa-debug-exit,iobase=0xf4`
   for clean flush; capture to a FILE not a pipe. Raw `outb` of a literal char
   is the ground-truth "reached here" probe.
6. **KNOWN SANDBOX LIMITATION:** `int 0x13` disk reads HANG in this WSL/QEMU
   (both LBA `ah=0x42` and CHS `ah=0x02`, floppy + HDD). The bootsector logic
   is correct; full kernel boot can't be validated here. Verified bar:
   `make kernel` links + `make boot` yields a 512-byte `boot.bin` with AA55 at
   offset 510. On real hardware / unrestricted QEMU it boots and prints
   for this — the `NNN|` line prefix defeats naive `startswith` re-TAB logic.

   ### Mode F — object on a recipe link but ABSENT from RT_OBJS (stale/missing `.o`)
   A recipe (e.g. `hosted:`) lists `$(RT)/wubu_holyd_input.o` on its link line, but if
   that object is NOT in `RT_OBJS` (or `HOSTED_OBJS`/`GUI_OBJS` as appropriate), `make
   runtime`/`make gui` never treat it as a prereq, so the `$(RT)/%.o: $(RT)/%.c` pattern
   rule never fires. Two failure modes result:
   - **`cannot find src/runtime/<x>.o`** — the object is stale/deleted and nothing rebuilds it.
   - **Silent STALE `.o`** — make links a pre-built `.o` from a prior edit, so your new
   symbol reports `undefined reference` even though the source defines it.
   This bites when a prior session added modules to a recipe link line but forgot the
   object-list variable. (Distinct from the mid-token *truncation* class — here the var
   entry is simply missing, not cut off.)
   **Diagnose (trust the expanded var, not the recipe line):**
   `make -s --eval='p:; @echo $(RT_OBJS)' p 2>/dev/null | tr ' ' '\n' | grep <module>`
   — empty output = the object is not in the list. Corroborate with
   `nm <module>.o 2>/dev/null | grep <newsymbol>` (a stale `.o` won't define it).
   **Fix:** add `$(RT)/<module>.o` to `RT_OBJS` (so `make runtime` builds it) AND keep it
   on the recipe link line. Then `make clean && make runtime && make hosted`.

   ### Mode G — LAYERING VIOLATION: a non-GUI module calls a GUI symbol (NEW, 2026-07-20)
   A runtime/daemon module (e.g. `src/runtime/wubu_holyd_input.c`) that calls a
   GUI-only function (e.g. `wm_handle_mouse`) forces the ENTIRE WM graph
   into every daemon/test link that compiles the caller — which then fails with
   `undefined reference to wm_handle_mouse` AND drags in half the desktop.
   This is NOT a missing-`.o` problem; it's a dependency-direction violation.
   **Fix (DI, same pattern as the HolyC-terminal injector):** decouple via an
   injected callback, do NOT pull the GUI into the runtime module:
   - In the public header (`wubu_holyd.h`): typedef a handler pointer
     `typedef void (*wubu_holyd_pointer_fn)(int x,int y,int btn,int kind);` and a
     setter `void wubu_holyd_set_pointer_handler(wubu_holyd_pointer_fn fn);`.
   - In the module (`wubu_holyd_input.c`): add a `static wubu_holyd_pointer_fn
     g_pointer_handler = NULL;`; the setter stores it; every call site does
     `if (g_pointer_handler) g_pointer_handler(x, y, btn, kind);` (no-op when
     unset). The daemon-only build stays decoupled — no `wm_*` reference.
   - In the hosted COMPOSITION ROOT (`hosted.c`, next to `holyc_term_set_eval`):
     `wubu_holyd_set_pointer_handler(wm_handle_mouse);` — the only place
     the real GUI symbol is wired. Mirror the terminal-eval injector there.
   **Detect fast (before the link):** after editing a runtime/daemon module,
   `nm -u $(RT)/wubu_holyd_input.o | grep -vE 'free|malloc|calloc|memcpy|...'`
   — if it shows a GUI symbol (`wm_*`), you've introduced a layering
   violation. Every runtime/daemon `.o` must list ZERO `wm_*` /
   `wubu_gui_*` undefineds. The decoupled-callback pattern is the canonical fix
   (also used for the HolyC eval injector and the EDR dashboard's
   separate-flagged object).

   ### Mode H — NEW SYMBOL in a SHARED translation unit → re-link sweep (NEW, 2026-07-22)
   Adding a function call inside a heavily-shared module (e.g. a new
   `hc_register_holyc_runtime()` call inside `hc_eval` in `holyc_codegen_api.c`)
   that references a brand-new object (`holyc_runtime.o`) breaks EVERY link recipe
   that compiles that shared TU — not just the one target you were working on.
   The first failure (e.g. `test_era_apps`) is fixed, but the gate then dies at
   `test_holyd`, `test_holyc`, `test_wubu`, `test_syscall`, `test_styxfs`,
   `test_wm`, `test_startmenu`, `test_edr_agent`, `canvas`, … — each
   with `undefined reference to hc_register_holyc_runtime`. This is WHACK-A-MOLE
   unless you sweep the WHOLE Makefile. **Systematic fix (verified):**
   1. **`COMP_OBJS` is the shared list** — add the new `.o` there first
      (`COMP_OBJS = ... holyc_codegen_api.o $(COMP)/holyc_runtime.o ...`) so any
      target using `$(COMP_OBJS)` picks it up.
   2. **Find every OTHER link line that inlines the shared TU's `.c`/`.o`** (these
      don't use `COMP_OBJS` and will miss the new symbol):
      ```sh
      grep -n 'holyc_codegen_api' Makefile | grep -v 'COMP_OBJS'
      ```
      For a new `holyc_runtime.o`, the hit lines are the `$(CC) ...` link recipes
      (not `%.o:` rules). Add `$(COMP)/holyc_runtime.c` to EACH such link line.
   3. **Also fix `hosted`** if it links the shared TU's callers: `hosted` links
      `wubu_holyd*.o` (which call `hc_eval`) but did NOT list the compiler objects;
      add `$(COMP)/holyc_lexer.c … $(COMP)/holyc_runtime.c` to the `hosted` link
      line (do NOT also add them if `hosted` already compiles them — that causes
      `multiple definition`; see dedup nuance). Verify with `make hosted`.
   4. **Run the FULL gate after each Makefile sweep** (`make test`); repeat steps
      2-3 until `gate_exit=0`. Do NOT declare done after the first target passes.
   This also applies when a new `.c` is added to any shared module (VSL syscall
   router, `wubu_exec.c`, `holyc_codegen_api.c`, `wm.c`): grep for every
   link line that names that module and add the new object there. The dedicated
   `test_*` you were debugging will pass first; the shared-TU breakage shows up
   only at the gate.

   ### SIGKILL (137) on a test that dies at runtime = OOM-MASKED LOGIC BUG
   A daemon/compiler test that exits **137 with no output** (dies during execution, not at
   load) is easy to misread as the WSL cgroup OOM segfault. But 137 is ALSO what an
   **infinite loop that allocates AST/parse nodes forever** yields: the loop never
   returns, RSS climbs until the cgroup SIGKILLs the process. This session's
   `wubu_holyd_eval("garbage")` crash was exactly that — `parse_block` spun on an
   unparseable token, `hc_ast_new()` eventually returned NULL, and `n->child = expr`
   deref'd it. Wrapped in a `ulimit -v` memory cap the same bug reports 137 and HIDES the
   real cause; **run the repro under `gdb` with NO `ulimit` cap** to get the true
   backtrace (a clean `SIGSEGV` at the NULL deref, not 137). Recipe:
   `gdb -batch -ex run -ex bt --args ./repro_bin` → read the crashing line, add the loop
   progress guard, re-verify. (Contrast with the *link-time* OOM class: that segfaults at
   `cc1`/`collect2`, this dies inside the running test binary.)

   (invalid hex `0xNT`/`0xHC`, missing `g_program_db` decl, not in any target) —
   see the "Orphan subclass — BROKEN-and-UNREFERENCED" note under Mode D.

   ### Make recipe BLANK-LINE terminator trap (verified 2026-07-25)
   A **blank line inside a recipe body terminates the recipe** in GNU Make — recipes
   are paragraph-delimited, not brace-delimited. If a `\`-continued prereq/link line is
   immediately followed by a blank line, Make ends the recipe there and treats the NEXT
   real line (e.g. `\t\t-o $(RT)/bin -lpthread`) as a NEW target whose name is the first
   token (`-o`). Symptom: `make: o: No such file or directory` / `make: <bin>: No such
   file`. This bit `test_archd` after a Python splice appended ` $(RT)/<new>.c` to a line
   that already ended with ` \`, leaving `<old>.c \` + blank line + `-o ...`.
   **Cause:** a `sed`/`python` edit that appends to a ` \`-terminated line can slip a
   blank line between the continuation and the next recipe line.
   **Detect** (the Makefile transport strips TABs, so visualize them):
   ```bash
   sed -n 'Np' Makefile | cat -A | sed 's/\t/>>TAB<</g'
   ```
   A blank line (just `>>TAB<<` or empty) between two recipe lines inside the target
   block is the bug.
   **Fix:** delete the blank line so the ` \`-continued line directly precedes `-o` /
   `$(CC)`. Verify: `make -n <target> 2>/dev/null | grep -oE 'src/[a-z/]+\.o' | head`
   runs the real link (no `make: o:` error). Rule of thumb: never append to a
   ` \`-terminated line; insert the new token BEFORE the trailing ` \`.

   ### `--as-needed` + inline-compiled `.c` link-order trap (verified 2026-07-25)
   When a `test_*` recipe compiles a `.c` INLINE on the link line (not via a prebuilt
   `.o`), `make` compiles it to a **temp `/tmp/ccXXXX.o`** and links that. Debian/Ubuntu
   `gcc` links with default `--as-needed`, which DROPS a `-l<lib>` if no symbol
   referenced by objects processed *so far* needs it. So if `-lssl -lcrypto` appears
   BEFORE the inline-compiled temp object that references OpenSSL, the linker drops the
   lib → `undefined reference to TLS_client_method` / `SSL_CTX_new` / `BIO_new_ssl_connect`
   even though the lib is right there.
   **Two verified fixes (either works):**
   1. **Order** — put `-lssl -lcrypto` AFTER every object, including the inline-compiled
    temp `.o` (list libs last on the link line).
   2. **Force-link** — `-Wl,--no-as-needed -lssl -lcrypto` so the lib is linked
    regardless of command-line order (works even when the temp `.o` lands after the
    libs).
   **Verified 2026-07-25:** `test_archd` compiled `wubu_archd_svc.c` (fresh, OpenSSL)
   inline; `-lssl` before the temp object → undefined refs; adding
   `-Wl,--no-as-needed` resolved it. Confirm the SOURCE is clean first with
   `gcc -c ... -o /tmp/x.o && nm /tmp/x.o | grep TLS_client_method` — a stale prebuilt
   `.o` from `make runtime` can otherwise mask a real source fix (the linker's
   `wubu_archd_svc.c:N` attribution is just the debug symbol's file, not proof the object
   is fresh).

   ### OpenSSL-avoidance technique (verified 2026-07-25)
   If a network fetch (AUR RPC, index.json) doesn't strictly require TLS, implement it
   with a **self-contained POSIX-socket HTTP/1.1 GET** (`socket()` + `getaddrinfo()` +
   `connect()` + `write()` + `read()`, strip the header block at `\r\n\r\n`). This removes
   the `-lssl -lcrypto` dependency entirely — no `--as-needed` games, smaller link, no
   OpenSSL version-symbol risk. The architecture rule "no third party if we can write it"
   favors this.
   **Gotcha — compat macro emits an absent symbol:** under `OPENSSL_API_COMPAT`,
   `SSL_library_init()` macro-expands to `OPENSSL_init_ssl(...)`, and
   `OPENSSL_init_ssl` / `OPENSSL_init_crypto` may be absent in the linked lib (the header
   declares them, the lib is older). If you DO use OpenSSL, **don't call the init
   Keep any TLS path behind
   `#ifdef WUBU_USE_OPENSSL` so the default build links without it.

   > **See also `references/link-regression-rt-objs-and-137.md`** for stale-`.o` link
   > regressions and the `--as-needed`/temp-object interaction is the 2026-07-25
   > addition above.

   ## NEW 2026-07-25 — Hermes transport + execute_code pitfalls

Three reusable lessons from the Mega-OS operator build that are NOT
Makefile-object-list bugs (they are the agent's OWN tooling limits):

### write_file / patch >~8K tokens = silent stream timeout
A single `write_file` (or a `patch` whose `new_string` is very
large) returns a **stream timeout before delivery** — the file is
NOT written and no error surfaces to the next turn. Verified: writing a
~180-line `.md` doc in one call timed out silently.
**Rule (verified):** create the file once (header + first section), then
APPEND each remaining section with `patch` (unique `old_string` anchor +
`new_string` = anchor + block). Each call stays well under ~8K tokens.
This is a Hermes transport limit, not a WuBuOS quirk — applies to ANY
large artifact (docs, generated `.c`).

### execute_code naive `replace` matches the WRONG occurrence
`execute_code` doing `s.replace(anchor, new)` where `anchor`
appears TWICE in the Makefile inserts `new` at BOTH spots —
this session it produced a DUPLICATE `wubu_trace.c` line in `RT_OBJS`,
then the `test_archd` link died with `multiple definition of
wubu_selfimprove_cycle` (the `.c` got compiled twice).
**Rule (verified):** (a) make anchors UNIQUE by including surrounding
context lines; (b) after any bulk replace, `grep -c '<token>' Makefile`
to assert the EXPECTED count (1 in `RT_OBJS`, 1 in `test_archd`);
(c) `replace(anchor, new, 1)` caps to one occurrence — use it when unsure.

### Function defined INSIDE main() from a bad patch
Patching a `static fn(...) { ... }` block with an `old_string` anchor
that sat inside `main()` (e.g. before a `printf(...)`) produces a
NESTED function definition → `invalid storage class for function
'test_mega_os_loop'` / `expected declaration or statement at end of input`
(unbalanced braces). Verified this session.
**Rule (verified):** keep ALL `static fn` definitions ABOVE the
`/* Main --- */` marker; only CALLS go inside `main()`. After any
insert, `grep -nE 'static .*\(.*\) \{|int main' file.c` should show
defs above `main`, with exactly one `}` after the last test call.

### Stale binary masks the real link failure (recurring, 2026-07-25)
`make test_X` recipes are `gcc … -o bin && ./bin`. When the LINK
fails, `make` returns non-zero but the PREVIOUS good `bin` stays on
disk. If you debug by running `./bin` directly, you get STALE green
results that mask the real link error and send debug the wrong way.
**Rule (verified):** (1) trust the `make` EXIT code (`echo "EXIT=$?"`),
NOT the binary's stdout; (2) grep the actual diagnostics —
`make test_X 2>&1 | grep -iE 'error:|undefined ref'`; (3) only after
`make` exits 0 do you run `./bin`; (4) `make` exit 2 with ONLY
warnings (implicit-function-declaration, missing-declaration) is a warning,
not a link error — confirm via the grep, don't assume failure from the
exit code alone.

### NEW MODULE NAME COLLISION
A `multiple definition` naming a file you never touched means a name is
already taken, not that an object is missing. Two signatures (silent
overwrite of a committed module vs. struct/function collision), and the
two-command pre-flight that catches both — see
`references/new-module-name-collisions.md`.

## References
- `references/kernel-freestanding-recovery.md` — full `make kernel` freestanding
  link-break recipe.
  missing freestanding libc, klog). Read this when `make kernel` fails with
  `relocation truncated to fit` or `undefined reference to _setjmp/__fprintf_chk/...`.
- `references/baremetal-qemu-boot.md` — bootsector assembly pitfalls (`.org 0`
  not 0x7C00, mandatory `cld`, plain `-m16` flags, ELF entry formula) and the
  QEMU serial-capture recipe. Read this when `boot.S` won't assemble cleanly or
  - `references/link-triage-recipe.md` — copy-paste command cookbook for steps 1-5.
  - `references/link-regression-rt-objs-and-137.md` — RT_OBJS-missing-object
    stale/`.o` link regression + SIGKILL(137) as OOM-masked infinite loop (gdb
    WITHOUT a `ulimit` cap to see the real NULL-deref). Read when a test dies with
    137 mid-run or a recipe-linked object fails to build.
  - `references/makefile-object-map.md` — which WuBuOS objects carry `main()`,
  which are hosted-only, the `APP_RT_OBJS` curation rule, the proton
  duplicate-definition map, and required wayland protocol objects.
- `references/gui-shot-stale-object-trap.md` — three new failure classes added
  2026-07-20: (1) gui-shot / test-harness stale-object trap (target prereqs omit
  linked objects); (2) Control Panel app launch matches title not registry key;
  (3) overlapping-window layout in GUI harness makes visual verification
  impossible. Read when `wubu_gui_shot` or similar harness crashes/misbehaves
  despite correct-looking code.
- `references/link-triage-recipe.md` — copy-paste command cookbook for steps 1-5.
- `references/link-regression-rt-objs-and-137.md` — RT_OBJS-missing-object
  stale/`.o` link regression + SIGKILL(137) as OOM-masked infinite loop (gdb
  WITHOUT a `ulimit` cap to see the real NULL-deref). Read when a test dies with
  137 mid-run or a recipe-linked object fails to build.
- `references/makefile-object-map.md` — which WuBuOS objects carry `main()`,
  `src/**/*.c` against the Makefile's `.c`/`.o` tokens and prints truly-unwired
  modules (the scalable orphan sweep, Pass 1). Pair with the Pass-2 per-symbol
  caller/test grep in Mode D.
- `scripts/fix_makefile_tabs.py` — deterministic re-TAB recovery for recipe lines
  a `patch` edit stripped of TABs (2026-07-13). Pass 1-indexed recipe-body line
  numbers; it re-prefixes each with `\t\t`. Do NOT use `execute_code`+`read_file`
  for this — the `NNN|` line prefix defeats naive `startswith` re-TAB logic.
- `references/recover-half-committed-split.md` — command transcript for recovering
  a half-committed monolith split left by a crashed session (2026-07-22): the
  `git status` damage pattern, the `const`-table-defining-file variant of
  undefined-reference, the "gate doesn't run direct consumers" pitfall, and the
  pre-existing-defect triage. Read when `make test` is green but a split-related
  `test_*` target still fails, or after any session crash mid-split.
- `references/crash-vsl-dispatch-fanout.md` — 2026-07-22 recovery of a HALF-WIRED
  dispatch-router extension: `vsl_syscall_dispatch()` gained CP/M (0xC0) +
  Classic Mac (0xB0) callees wired only into their dedicated `test_vsl_*` target,
  breaking the SHARED link sites that compile the router. Read when a central
  fan-out dispatcher (switch/route table) gained a new callee personality and
  every target compiling the router now fails with undefined reference — the
  dedicated test passing is a false-green.
  **INVERSE case (same session, also 2026-07-22):** the opposite failure — a
  dedicated `test_vsl_cpm` / `test_vsl_macclassic` target existed but was NOT
  folded into the top-level `test:` aggregator, so `make test` (the tier gate)
  never ran it (false-green). Fix: add every new `test_*` target to the `test:`
  line. And `make clean && make hosted` caught a `ct_iso_*` triple-listing +
  missing-`hosted`-prereq break — see the corrected "ld dedup nuance" and the
  "`hosted`/`test_*` targets must LIST their literal link objects as PREREQS"
  pitfalls above. The `era_apps.c` orphan was BROKEN-and-UNREFERENCED
  (invalid hex `0xNT`/`0xHC`, missing `g_program_db` decl, not in any target) —
  see the "Orphan subclass — BROKEN-and-UNREFERENCED" note under Mode D.
