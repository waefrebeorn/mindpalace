---
name: wubuos-build-integrity
description: How WuBuOS Makefile header-dependency tracking was added (-MMD -MP + .d include) to kill the "edit a header, stale .o linked into test, phantom test failures" trap. Use whenever a header change (struct layout, #define) causes tests to fail in ways that don't match the source, or when test binaries mix prebuilt .o with fresh .c.
---

# WuBuOS build-integrity: header-dep tracking

## Symptom
You edit a header (`wm.h` changed `DOSGUI_MAX_ICONS` 16->64, which
reshaped the `DosGuiWM` struct in memory). Source code looks correct, but a
bunch of tests fail — often ALL routing through one accessor
(`icon_get` returning NULL, `wm_get_icon_count` wrong). The
failing tests are not actually broken; the **linked binary is built from
stale `.o` objects** compiled against the old header.

## Root cause
The Makefile pattern rules (`$(GUI)/%.o: $(GUI)/%.c` etc.) compiled with
`$(CC) $(CFLAGS) ... -c $< -o $@` and NO `-MMD`. So object files did not
record which headers they included. When a header changed, `make` saw the
`.c` unchanged (newer than its `.o`) and did NOT rebuild dependent `.o`s.
Test recipes that listed *some* sources as prebuilt `.o` and *some* as `.c`
then linked a mix of new + old objects → struct-layout mismatch → fields
read at the wrong offset.

## The fix (applied 2026-07-19, commit 7e7b19c)
1. Add `-MMD -MP` to EVERY `$(CC) ... -c $< -o $@` recipe line in the
   pattern rules (kernel/runtime/jit/gui/bridge/apps/comp/vsl/...). This
   emits a `<src>.d` file listing the headers each object depends on.
   Script used (safe: only touches recipe lines containing `-c $< -o $@`):
   ```python
   lines=open("Makefile").read().split("\n"); out=[]
   for ln in lines:
       if ln.startswith("\t$(CC)") and "-c $< -o $@" in ln and "-MMD" not in ln:
           out.append(ln.replace(" -c $< -o $@", " -MMD -MP -c $< -o $@", 1))
       else: out.append(ln)
   open("Makefile","w").write("\n".join(out))
   ```
2. After the `.PHONY:` block, add:
   ```
   # Header dependency tracking: every .c compile emits a .d (via -MMD -MP).
   # Including them rebuilds an object when any header it includes changes.
   -include $(shell find src -name '*.d' 2>/dev/null)
   ```
   Use `-include` (not `include`) so the first build with no `.d` files is
   silent, not an error.
3. Add `*.d` to `.gitignore` (generated artifacts, never commit).
4. Convert test recipes that mix prebuilt `.o` + fresh `.c` to ALL `.c`
   (self-contained, cannot link stale objects). Example `test_wm`
   had `wm_window.o wm_input.o wubu_settings_defaults.o
   wubu_settings_io.o` in its link line — changed those to `.c`.

## When you see phantom failures
- Before assuming source is broken, check object freshness:
  `find src/gui -name '*.o' -older src/gui/<edited_header>.h`
  If any are older than the header you just edited, that's the bug.
- `ls -la --time-style=+%H:%M:%S <file>.o <header>` to compare mtimes.
- Fast unblock: `find src -name '*.o' -delete` then rebuild (forces consistent).
- NEVER trust "the code looks right" — the binary is the source of truth.

## Gotchas
- The `-include $(shell find ...)` re-scans every `make` invocation; cheap
  for this repo. If it ever slows down, scope the find to the active dir.
- Some test recipes legitimately use `$(JIT_SRCS)` / `$(COMP)/holyc_*.o`
  macros — those expand to `.c`, not literal `.o`; only literal `path.o`
  tokens in a test link line are the trap.
- Always re-run the SPECIFIC failing test after a header edit, not just the
  umbrella, to catch stale-object issues early.
- **`-MMD` tracks header deps, NOT new link deps.** Adding `-MMD` fixes
  stale-object rebuilds, but it does NOT auto-add a *new* `.c`/`.o` you start
  calling to a test recipe's link line. If you make a module call a function
  from a file it didn't previously link (e.g. `wm_ctxmenu.c` now calls
  `wubu_trash_move` from `wubu_trash.c`, which pulls `wubu_arch.c` →
  `wubu_arch_mkdir_p`), you get `undefined reference` at LINK time even though
  every object rebuilt fresh. You must still hand-add the new source(s) to
  every recipe that compiles the calling file. `grep` the tree for other
  recipes compiling the calling `.c` and add the dep to each. Affected by the
  trash change (2026-07-19): `test_wm` + `test_control` both needed
  `wubu_trash.c` + `wubu_arch.c` added to their link lines.

## Hosted test recipes link a SUBSET of kernel objects

The hosted/GUI tests compile `src/kernel/interrupt.c` DIRECTLY, without linking
`interrupt_apic.c`. So new kernel code that calls `lapic_*` / `apic_*` links fine
in `make hosted` and in the full `make test`, but breaks `test_first_run`,
`test_wet_applet`, `test_vsw_designer` and `test_tutorial` with
`undefined reference to 'lapic_eoi'`.

Rule: wrap new kernel code that needs APIC symbols in `#ifdef MYSEED_METAL`
the way the boot path already does, and re-run those hosted tests after touching
interrupt/timer code. Symptom shape: the full suite passes while an individual
target dies at link -- always compare per-target link sets, not just the umbrella.

## The egojar room: POSIX lives in two headers, not in the tree

The goal is to build this tree with wubunos instead of gcc. What blocks that
is not logic -- it is 520 `#include <unistd.h>` lines and 366 scattered
`-D_POSIX_C_SOURCE` flags across the makefiles.

The fix is a ROOM of jar headers -- a trojan-horse suit: they look like
ordinary headers and carry the POSIX world inside.

    src/egojar.h       core: feature-test macros + files, processes, threads,
                       memory, signals, mounts, inotify, epoll
    src/egojar_net.h   network: sockets, addresses, net devices

Rules:
- **Include the jar FIRST** in any file that needs POSIX. Feature-test macros
  only take effect before the first system header, so a jar included after
  `<time.h>` silently does nothing.
- **Standard C headers are NOT in the jar** (`<stdio.h>`, `<string.h>`,
  `<stdint.h>`). Any compiler has them; they are not the portability seam.
- **Why a room and not one jar:** `<sys/socket.h>` drags in `<net/if.h>`, which
  redefines `struct ifreq` / `ifmap` / `IFF_*` and collides with
  `<linux/if.h>` -- and half the tree legitimately includes `<linux/if.h>`.
  Shelves let a file pay only for what it uses.
- **A header whose struct crosses a TU boundary must include the jar.** When
  the library TU has the jar and the test TU does not, the two see different
  feature macros and compute different struct layouts -- the test reads a
  garbage pointer out of the shared global and dies in a call far away
  (`wubu_clipboard_internal.h` / `ClipboardState` segfaulted in `strcmp`).
  Give the HEADER the jar, not each caller.
- **A name the jar makes visible can collide with the project's own.**
  Including `<sys/socket.h>` declares `shutdown()`, which clashed with the
  project's OS `shutdown()`. Rename the project's function
  (`wubu_shutdown()`) -- bind BOTH sides (definition, declaration, callers)
  and verify no bare `shutdown(` remains. The socket name keeps its meaning.
- Dropping the 366 `-D_POSIX_C_SOURCE` makefile flags is only safe once every
  TU gets the macros from a jar. Sweep the includes first, then the flags.
- **A bulk include sweep will run into the submodules.** They are separate
  repos with their own uncommitted work, and a tree-wide `grep -rl ... | xargs`
  rewrites them too. Either skip the submodule paths in the sweep pattern, or
  revert precisely afterwards: for each modified file, if the diff contains
  ONLY your added include and removed system includes, `git checkout -- <path>`;
  if the diff has anything else, LEAVE IT (that is the user's work). A
  wholesale `git checkout .` inside a submodule destroys pre-existing edits.

## Makefile whitespace: never collapse it

A bulk regex that collapses `[ \t]+` to a single space DESTROYS makefiles --
recipe lines are tab-indented, and a space-indented recipe line is
`*** missing separator`. When removing flag tokens (`-D_POSIX_C_SOURCE=...`)
from `mk/*.mk`, delete the token and at most ONE following space, never a run:

```python
re.sub(r'-D\s*_POSIX_C_SOURCE=\S+ ?', '', line)   # never re.sub(r'[ \t]+', ' ')
```

Verify after any bulk edit: `make -n <target>` parses the file without
complaining about separators.

## A FAILED link leaves the OLD binary, and the guest boots it

**Symptom:** a kernel change has no effect — log lines from code you deleted
still appear, or a new object you added is simply never called. Nothing errors
at boot because boot is fine; the artifact is old.

**Mechanism:** when a source file is missing from `KERNEL_OBJS`, or a symbol is
unresolved, `make kernel` exits non-zero and **`kernel.elf` keeps its previous
contents**. Any `run-*.sh` that packages the existing image then boots code from
an earlier session. This hides for as long as nobody compares mtimes, and it
silently invalidates every measurement taken through that script.

**Rules:**
- After editing anything the kernel links, check the artifact moved:
  `ls -l --time-style=+%H:%M:%S src/kernel/kernel.elf` before trusting a boot log.
- The link line is the source of truth: a new `.c` needs both an object rule AND
  an entry in `KERNEL_OBJS` (e.g. `timer_wheel.o`, later `ramfb.o`). Linking
  fails silently in a script that pipes `make` through `grep` — capture the
  exit status or the tail, never just the matches.
- A boot script that reports milestones can still pass while running a stale
  image: milestone greps match OLD log text too. Rebuild inside the script (or
  require a fresh mtime) before it asserts anything.

## Boot path truth: `-kernel` is not a boot test

`kernel.elf` is a higher-half 64-bit image with **no multiboot header**, so
`qemu-system-x86_64 -kernel kernel.elf` is not a boot attempt: QEMU's Linux
loader prints a few probe bytes (`0102…`) and stops. Do not diagnose that output
or add a multiboot header to "fix" it.

The supported path is **WuBuFW**, our own C11 UEFI firmware in `src/firmware/`:
`bash src/firmware/build.sh` then `bash src/firmware/qemu-boot-verify.sh`. That
script is the authoritative gate (secureboot policy, signed/unsigned payload,
TPM PCR, allocator, ESP listing, interactive shell) and prints
`ALL MILESTONES PASSED` when the guest really boots.

Rules:
- A boot claim must name the path it tests. `tools/boot_audit.sh` only proves the
  artifact is freestanding; it says nothing about execution.
- Gate the firmware path (`tools/boot_gate.sh`), keep `--kernel` behind a flag as
  a diagnostic, and let the gate print each PASS milestone.
- Firmware scripts use `bash`, not `sh`: `build.sh` sets `pipefail` and dies with
  `Illegal option -o pipefail` under dash.
- The firmware shell reads its console, not COM1 — piping `help` into
  `-nographic` does not drive it. Verify via `qemu-boot-verify.sh`, which knows
  how to observe it.

## Declared test targets are not reachable test targets

`mk/tests.mk` declares hundreds of `test_*` targets, but `make test` only reaches
the dependency closure of its first target. Audit by building the full list and
aggregating it (`mk/tests_all.mk`: `ALL_TESTS = …` + `test_all: $(ALL_TESTS)`,
included after `mk/tests.mk`), then `make -k test_all`.

- Reachability is a property, not a policy: generate the aggregate list from the
  declared targets so a new test cannot be silently omitted.
- Most `test_all` failures are **missing link inputs**, not broken tests. Fix the
  recipe/list (`HOLYD_SRC`, `VSL_NT_OBJS`, …) — one shared source list can repair
  ten targets at once.
- Per-target hand-written source lists of 100+ entries are the defect shape: each
  fix exposes the next undefined symbol. Prefer shared object-set variables over
  appending single files.

## Orphan recipe lines in `mk/*.mk`

Symptom: a target runs a command with no input (`gcc: fatal error: no input
files`) or executes another target's recipe. Cause: an interrupted edit left
tab-indented lines with no rule header, so make attaches them to the previous
target. Detect with `sed -n 'N,Mp' mk/tests.mk | cat -A` — bare `^I` lines after a
blank line and before the next comment are orphans. Delete the header-less
duplicate block rather than adding a new rule above it.

## Freestanding artifact audit (proving the kernel has no host)

A kernel can boot and still be a host process: if it carries a dynamic loader,
a `NEEDED` library, or undefined libc symbols, its "independence" is an
assumption. Audit the ARTIFACT, not the intent — `readelf`/`nm` answer in
seconds what a boot log cannot:

```bash
readelf -d kernel.elf | grep -q NEEDED   && echo "FAIL: shared libs"
readelf -l kernel.elf | grep -q INTERP   && echo "FAIL: PT_INTERP"
readelf -l kernel.elf | grep -q DYNAMIC  && echo "FAIL: PT_DYNAMIC"
[ "$(nm -u kernel.elf | wc -l)" -eq 0 ]  || echo "FAIL: undefined symbols"
readelf -h kernel.elf | grep -q 'Type:.*EXEC' || echo "FAIL: not EXEC"
```

Pass criteria: no `NEEDED`, no `PT_INTERP`, no `PT_DYNAMIC`, `nm -u` empty,
`Type: EXEC`, non-zero entry point. Ship it as `tools/boot_audit.sh` +
`make boot-audit` so the claim is re-checkable, and print the size and entry
address on success — those are the two facts a reviewer can compare between
builds.

Caveats that keep the audit honest:
- **An audit of a stale binary proves the old build, not the current source.**
  Check the artifact's mtime against `src/kernel/*.c` before quoting it, or
  rebuild first. `nm -u` empty on a two-week-old `kernel.elf` means the tree
  used to be freestanding.
- **Absence of `INTERP` is not presence of a loader.** BIOS bootsector boot and
a UEFI path are different artifacts; `grep -r efi_main` returning nothing means
there is no EFI entry point in the tree, not that UEFI "probably works".
- Keep it separate from `make test`: it inspects a build product, and a missing
  `kernel.elf` should report "build first", not fail the unit suite.

## Docs and onboarding must execute

A guide nobody runs is a hypothesis. When adding or repairing a README/quickstart,
ship a `tools/onboard_check.sh` that runs exactly the documented commands
(prerequisites, build, audit, one test, aggregate, boot) and fails when a
step documented as passing does not. Keep known-failing steps listed explicitly
and have the check say when one starts passing, so the doc cannot go stale.

## Pitfalls from desktop-gap work (2026-07-19)
Reproducible recipes + the exact C gotchas are in `references/build-traps-2026-07-19.md`. Summary of the recurring traps:

## Gui-shot / test-harness stale-object trap (2026-07-20)
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

## A `.o` beside a `.c` in the link line is not evidence of a stale build

**Symptom:** you edit `src/gui/wm_render.c`, `make hosted` relinks, but
`src/gui/wm_render.o` still carries its old mtime -- so it looks like your
change never compiled. It did.

**Mechanism:** `GUI_OBJS` in `mk/objects.mk` lists a MIX of `.o` and `.c`
tokens (`$(GUI)/wm_render.c` beside `$(GUI)/wm_input.o`, and so on). The `.c`
entries are compiled directly in the hosted link line, so the stale `.o` sitting
next to them is never read; the link recompiles the `.c` entry every time.

**Rule:** before concluding a change is missing from a binary, check the LINK
LINE, not the `.o` mtimes: `make -n hosted | grep <file>`. A `.c` token there
means the source is compiled fresh at every link. `.o` mtimes only matter for
the literal `.o` tokens.

## An object named only in a link recipe is never built

Symptom: `make clean && make` dies at LINK time with
`cannot find src/foo/bar.o: No such file or directory`, while every incremental
build succeeds. Cause: the objects appear in the recipe's link line but nowhere in
the target's **prerequisite list**, so make never puts them in the dependency graph.
A normal build works only because stale `.o` files from an earlier configuration are
still on disk -- the tree was quietly unbuildable from clean and nobody noticed,
because every workflow rebuilds incrementally.

Rule: **every token in a link recipe must also be a prerequisite** (directly, or via
a variable that expands to the full set). Same failure shape for a recipe referencing
a literal `path.o` that no rule builds: compile the `.c` in the recipe like the
neighbouring entries do.

Consequence: any verification done without a `make clean` first measures a tree
that may not be reproducible. Run one clean build per session that touches link
lines in `mk/*.mk`, and treat "it built" as meaningless until then.

## Compile-time config flags need a config stamp prerequisite

`-MMD -MP` tracks HEADERS, not make-variable state. When a recipe compiles
an object with flags derived from a build config (`HOSTED_TLS`,
`WUBU_MBEDTLS_ROOT`, backend selection), a later build with a different
config reuses the object compiled with the old flags and the link fails
with undefined symbols from the missing backend (e.g. `mbedtls_*`).

Rule: encode every flag-changing variable into a small, content-checked
stamp file and make the affected objects depend on it:

```make
HOSTED_TLS_STATE := build/hosted_tls.state
.PHONY: FORCE_HOSTED_TLS_STATE
FORCE_HOSTED_TLS_STATE:
$(HOSTED_TLS_STATE): FORCE_HOSTED_TLS_STATE
	@mkdir -p build
	@printf '%s|%s' '$(HOSTED_TLS)' '$(WUBU_MBEDTLS_ROOT)' > $@.new
	@cmp -s $@.new $@ || mv $@.new $@
	@rm -f $@.new

$(RT)/oci/%.o: $(RT)/oci/%.c $(HOSTED_TLS_STATE)
```

The FORCE prerequisite runs the recipe every time but rewrites the stamp
only when the state actually changes, so unrelated builds do not recompile
everything. Verify BOTH transitions (with root, then without root) with
`make hosted` RC=0 — a one-way green proves only the cached state.

**A backend flag is not proof of the selected backend.** After enabling a
compile-time backend (`-DWUBU_EDDSA_FIXED_LADDER`, a TLS/crypto path), inspect
the EMITTED OBJECT, not just `make -n` or the macro: `nm <object> | grep -c
<banned-symbol>` must be 0 for the disabled backend. `#if` precedence can
let an auto-detected alternative backend win even when the new flag is
present, so a product can still link the old implementation while every
gate that compiles the new branch goes green. Also check that each new leaf
`.c` is in the product object list, not merely in the test gate's source
list. Why: the gates prove the new source compiles; only the product's
object symbols prove the shipped binary uses it.

## A target named through a variable BELOW the rule is silently dropped

Symptom: a target added to a `test_*:` prerequisite list fails once with
"<binary>: not found", then passes on retry after something else builds the
artifact. Looks like a flake; it is a silent dependency drop.

Mechanism: **GNU make expands a rule's prerequisite list at PARSE time.** If the
target is spelled through a variable defined further down the makefile, the
expansion yields the EMPTY STRING at that point -- so the prerequisite simply does
not exist. The recipe body is expanded later and produces the correct path, which
is why the run executes a binary that was never built. Existing targets named
literally look fine, which hides the defect until someone adds a new one.

```make
# BROKEN: FOO_SAN is defined below, so $(FOO_SAN) vanishes here
.PHONY: test_all
test_all: test_a $(FOO_SAN)
	$(FOO_SAN)            # expands correctly at run time -> "not found"

FOO_SAN = src/foo.san  # too late
```

Rule: **define every target-naming variable ABOVE the rule that lists it**, and say
why in a comment. Verify with `make -qp | grep '^<target>:'` -- if the prerequisite
is missing from that line, it will not be built. Diagnose a suspect gate by checking
whether the same variable appears in the dep line at all before assuming a race.

## Implicit declarations and include-guard collisions

Full procedure, enumeration commands and the ABI-collision variant:
`references/implicit-declarations-and-guard-collisions.md`. Summary: an
`-Wimplicit-function-declaration` warning is a correctness defect (a call through a
missing prototype reads the return value out of garbage and passes or fails
depending on stack layout); sweep them with a clean build; gate them with
`-Werror=implicit-function-declaration`; two headers sharing an include guard shadow
each other, and renaming guards can expose either duplicate code or a genuine ABI
collision.

## Theme application order trap (2026-07-21)
**Symptom:** Captured frames show an orange Control Panel window / orange title bars that shouldn't exist. The orange matches `THEME_XP_MEDIA_ORANGE` (`win_title_active = 0xE86C00`) but the intended theme is Win98 Classic (navy).

**Root cause:** `wubu_theme_set(THEME_WIN98_CLASSIC)` was called **BEFORE** `desktop_init()`. But `desktop_init()` calls `wubu_settings_init()` which loads saved settings from disk and calls `wubu_theme_set(g_settings.theme.theme_id)` — overwriting the manual theme with whatever you just set.

**Fix:** Move `wubu_theme_set(THEME_WIN98_CLASSIC)` to **AFTER** `desktop_init()` completes, so the saved settings are loaded first, then your explicit override applies last.

```c
wm_init(SHOT_W, SHOT_H);
desktop_init();
wubu_theme_set(THEME_WIN98_CLASSIC);  /* AFTER init - survives settings load */
```

**Verification:** After the fix, all 5 fresh frames (`01_desktop_win98` through `05_apps_wubu`) had **0 orange pixels**. The cycle is now: Win98 → Win98 Apps → Win98 Control Panel → XP Luna Blue → WuBu Green. No orange frames.

**Debugging tip:** If a theme "doesn't stick" in a harness or test binary, check the call order of `wubu_theme_set()` vs any `*_init()` that might call `wubu_settings_init()` → `wubu_theme_set()`. The last call wins.
`references/build-traps-2026-07-19.md`. Summary of the recurring traps:

- **New call → new link dep (the #1 repeat offender).** Adding a function
  call from module A into a symbol defined in module B that itself needs
  module C (transitively) produces `undefined reference` at LINK time even
  though every `.o` rebuilt fresh via `-MMD`. You must hand-add B (+C...) to
  EVERY recipe that compiles A. There is no auto-detection. `grep -rn` the
  tree for other recipes compiling A's `.c` and patch each.
- **Don't call the full boot initializer inside a unit test.** A test that
  calls `desktop_init()` dragged in the DOS-emulator subsystem
  (`g_app_defs` → `dos_window.h` → `wubu_dos_proc.h`) — a deep cascade.
  Instead, test the *exact restore line* the initializer runs (e.g.
  `wm_set_auto_arrange(wubu_settings_get()->theme.auto_arrange)`)
  directly. Keeps the test link minimal.
- **Test-fixture naming collides with guard logic.** A fixture named
  `Trash.desktop` matched the trash dir prefix `.../Trash`, so
  `wubu_trash_move`'s "can't trash trash" guard rejected it and the test
  failed for a non-bug reason. Never name fixtures with a prefix that matches
  a substring/guard check in the code under test.
- **C declaration gotchas when adding functions:** (1) calling a `static`
  fn before its definition → implicit non-static decl → "static declaration
  follows non-static declaration"; fix with a forward `static void fn(void);`.
  (2) `bool` params in a header lacking `#include <stdbool.h>` → "unknown
  type name 'bool'". (3) prefer promoting an internal fn to the public header
  over reaching into `wm_internal.h` from another module.

## Edit-tool pitfalls (session part 5-6, 2026-07-19)
- **NEVER use the `patch` tool on a Makefile rule body.** The tool re-escapes
  backslashes: a line-continuation `\` becomes `\\` and leading tabs are
  mangled, so a multi-line `$(CC) ... \` recipe comes back corrupted — make
  then reports nonsense like `No rule to make target 'gcc'` (the recipe line
  got merged into the prerequisite list). It also silently over-escapes on
  each retry, compounding the damage.
  - **Rule:** edit `mk/*.mk` / `Makefile` rule bodies with `execute_code`
    Python using exact line-index surgery: `lines = f.readlines()`,
    `lines[i] = "\t\t$(RT)/foo.c \\n"`, `f.writelines(lines)`. Verify with a
    byte-level check (`open(p,'rb').read().split(b'\n')`, confirm each
    continuation line ends with exactly one `\`).
  - When you must keep a Makefile rule intact, prefer replacing a single
    self-contained line (no trailing backslash) over a block.
  - A quick global repair if backslashes already got doubled in continuation
    lines: `content.replace(' \\\\n', ' \\n')` — but re-inspect before
    trusting it, since it can touch legitimately-escaped content.
- **`patch` replace_all on multi-block C struct initializers CORRUPTS the
  file.** When several theme/struct blocks share IDENTICAL lines (e.g. all
  5 WuBuOS themes have `select_bg = RGB(0xE8,0x6C,0x00),` for the
  orange ones, or `select_text = RGB(0xFF,0xFF,0xFF),`), a
  `replace_all` that matches an anchored pair will (a) re-match the SAME
  pair repeatedly and (b) re-order fields, producing garbled duplicates
  like `...select_hover = X, .win_shadow = Y, select_hover = X,` and
  even overwriting Win98's field with XP's value. SEEN TWICE this
  session — both times had to `git checkout` the file and redo.
  - **Rule:** for repeated struct blocks, NEVER `replace_all`. Either (1) anchor
    each insertion on a UNIQUE preceding line (the line above the target must
    differ per block — e.g. the theme's `startmenu_bg = ...` value, or its
    `.id = THEME_*` line), or (2) do it with a script that splits the
    file on `.id =` markers and inserts once per block (see below).
  - **Deterministic script pattern** (used to add `win_shadow` to all 5
    themes without corruption):
    ```python
    import re
    text = open("src/gui/wubu_theme.c").read()
    parts = re.split(r"(\.id\s*=\s*THEME_\w+,)", text)
    out = [parts[0]]
    shadow = {"THEME_WIN98_CLASSIC":"0x000000", "THEME_XP_LUNA_BLUE":"0x14141E", ...}
    for i in range(1, len(parts), 2):
        marker, block = parts[i], parts[i+1]
        tid = re.search(r"THEME_\w+", marker).group(0)
        block = block.replace("        .select_text       = RGB(0xFF,0xFF,0xFF),\n",
            f"        .select_text       = RGB(0xFF,0xFF,0xFF),\n        .win_shadow        = {shadow[tid]},\n", 1)
        out.append(marker + block)
    open("src/gui/wubu_theme.c","w").write("".join(out))
    ```
    (If a block uses a different select_text colour, match `.select_text\s*=`
    with any value via `re.sub(..., count=1)`.)
- **Makefile phony-test-target naming is NOT the binary path.** The start-menu
  test recipe `test_startmenu:` builds `$(GUI)/startmenu_test`.
  Running `make test_startmenu` -> "No rule to make target". Running
  `make src/gui/startmenu_test` -> Make uses the BUILTIN linker
  (wrong flags, missing sources, link error) instead of the recipe.
  - **Rule:** invoke the PHONY target name exactly as declared
    (`make test_startmenu`). To discover it:
    `grep -nE "test_[a-z_]+:" Makefile | grep <keyword>`.
  - Same trap as the stale-`.o` one: the binary on disk may be a PREVIOUS
    build, so running `./src/gui/startmenu_test` directly can report
    stale pass/fail. Always rebuild via the phony target first.
- **Theme struct ABI edits (adding a field) require recompiling EVERY consumer.**
  Adding `win_shadow` / `startmenu_sidebar_grad_end` to `wubu_theme.h`
  reshaped `WubuTheme`. All 5 theme blocks in `wubu_theme.c` MUST get
  the new field (or field offsets shift and you get silent garbage / wrong
  colours). `vbe.h` adding `vbe_blend_rect` is safe (append-only API).
  After any `wubu_theme.h` field add: rebuild `make runtime` + `make hosted`
  + the GUI test umbrella, not just the one test you touched.
