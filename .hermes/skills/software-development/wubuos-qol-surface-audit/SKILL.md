---
name: wubuos-qol-surface-audit
description: Use when auditing OS quality-of-life / human-felt gaps.
version: 1.0.0
author: WaefreBeorn
license: MIT
metadata:
  hermes:
    tags: [wubuos, gui, desktop, audit, qol]
    related_skills: [wubuos-wm, wubuos-test-suite, wubuos-desktop-capture-harness, wubuos-battleship-gaps]
category: software-development
---

# WuBuOS quality-of-life / human-felt surface audit

## When to use
- Asked to "assess the gaps for the OS quality of life", "how good does the desktop
  feel", or to prioritize user-facing work.
- Asked to "assess the gaps left for the OS" against a product vision, a
  roadmap, or an outside description of what the system is for -- run step 12
  (the product legs) FIRST, then the surface pass.
- Before planning a GUI/app sweep, to separate what is thin from what only looks thin.
- After a gate goes green, to check the green is earned.

## Core principle
A green gate is NOT evidence that the surface works. Measure each surface
independently and report the measurements separately; a gap in any one is a real
finding.

## Procedure

### 1. Count what the gate ACTUALLY asserts
A tier that prints "complete" can be running stubs. For each target in the tier,
count its assertions:
```bash
grep -n '^test_high_gui:' mk/tests.mk          # the tier's member list
# then for each linked test TU:
grep -c 'TEST(\|CHECK(\|ASSERT(' <tu>.c
```
A test TU wired into a green tier with 0-2 assertions is the top finding: the gate
certifies a surface nobody verifies. Report file + line count + assertion count.

**CRITICAL -- distinguish the TEST TU from its SHIM TU.** Recipes commonly link
BOTH `<x>_test.c` (the real assertions) AND `<x>_test_stub.c` / `<x>_test_stubs.c`
(a dependency shim supplying no-op definitions of symbols the real test does not
exercise). Counting the shim reports 0 assertions and produces a FALSE "the gate
lies" finding -- the single most expensive misreading in this audit.
Rule: the TU ending `_test.c` (not `_test_stub.c`) is the test; the `_stub` TU is
plumbing. When a recipe links several `_test*.c` files, count each separately.

Verify a suspicious count by RUNNING the target and reading its summary line
(`make <target> | grep -oE '[0-9]+/[0-9]+ passed'`), not by trusting the grep.

**A recipe with NO `<x>_test.c` is not an empty test.** Some targets link only
objects and run a binary whose test `main()` is compiled into an object via a
`-D<TEST_MAIN>` flag (`test_vsl` links `$(VSL_OBJS)` and nothing else). No
`_test.c` file means you have not found where the test lives, NOT that the gate
asserts nothing. Grep-based assertion counting has two independent false-positive
modes -- macro variance, and a test main compiled into an object -- so NEVER
report a "green tier asserts nothing" finding from counts alone. Run the target;
the run is the truth.

### 2. Run the capture harness and LOOK at the frames
`make desktop_shot` (26 frames) is the honest visual evidence and it builds.
Convert PPM→PNG with PIL (`Image.open(p).save(png)`); view frames with the
vision tool. Read the harness's own behaviour prints (`[lasso] icons selected: N/3`,
`[clock] menu open after click: N`) as the real gates. Cross-reference
`wubuos-desktop-capture-harness` before trusting a frame — a harness can measure a stub.

`make gui_shot` is currently RED and it is not a gate target: its recipe
compiles `src/gui/lua/wubu_lua_gui.c`, which includes `wb_lv.h`, and that
vendored header is not on the recipe's include path. Do not treat a gui_shot
failure as a regression from your change — check whether you touched its
include path before chasing it, and use desktop_shot for visual evidence.

**A capture harness is not the product -- diff its init sequence against the
real boot before believing either.** The harnesses call `wubu_theme_set()`,
`icon_add_ex()` and `wubu_a11y_set_enabled()` directly and never call
`desktop_init()` or load settings, so they can render a desktop the real boot
path does not produce. When a surface is present in a frame but missing in the
product, compare the harness's init calls one by one against `hosted_init()`;
every call present in one and absent in the other is a candidate root cause
(theme never applied, icons never seeded, a11y never enabled). The product's own
evidence is `./src/hosted/wubu --screenshot <path>` -- use it for any
product-side claim, and the harness only for WM/composite behaviour.

### 3. Trace launch wiring — find real code the desktop cannot reach
The app registry is the source of truth. For each entry, read the launcher body:
```bash
grep -n -A8 '<launcher>' src/apps/apps.c
```
A launcher that calls a SIBLING app's launcher (`launch_editor` →
`launch_notepad`) means a real engine is unreachable from the desktop.
Confirm the engine is real and built, then check whether anything references it:
```bash
grep -rn '<engine_symbol>' src/ --include=*.c --include=*.h \
  | grep -vE '^src/(apps|runtime|gui)/<engine>\.(c|h)|_test\.c'
grep -o '<engine>\.o' mk/objects.mk      # is it linked at all?
```
Zero external references + a linked object = dead capability. **Exclude the
module's OWN test from the grep** — a `*_test.c` that is the only caller is not
a consumer, it is the gate certifying itself; a fully green module with no
non-test caller is still unreachable. Also read the engine's handlers for no-op
bodies (`(void)x;`, empty draw) — a registered app whose draw voids every
parameter opens a blank window.

**A launcher that binds NOTHING is the other blank-window shape.** It calls
`wm_create(...)` and returns without assigning `on_draw`/`on_key`/`on_mouse`,
so the app opens as an empty frame -- and its test can still be green because it
asserts only `win != NULL`. Read the launcher body for the three callback
assignments, not just for a sibling call. The engine usually already has a
`*_draw`/`*_draw_content` function the launcher forgot to bind: the fix is the
three assignments, not a rewrite.

**The fix is an adapter, not a rewrite.** See
`references/gui-engine-adapter.md` for the full pattern: one TU owns the engine
handle, binds it to `on_draw`/`on_key`/`on_mouse`, draws inside the chrome rect,
and exposes an opaque accessor so a test can assert the buffer keystrokes reach.
It also covers the weak-reference pattern for optional cross-layer calls and the
include-guard collision check.

To ADD a new shell surface (overlay, panel, OSD, lock/saver, hotkey) rather than
wire an existing engine, use the `wubuos-wm` skill -- it carries the six-step
wiring order and the render layering.

### 4. Measure per-app input coverage
An app with a draw handler but no input handler is a screenshot, not an app:
```bash
for d in src/apps/*/; do
  printf '%-22s draw=%s key=%s mouse=%s\n' "$d" \
    "$(grep -rl 'on_draw\|_draw(' $d --include='*.c' | wc -l)" \
    "$(grep -rl 'on_key\|_key('   $d --include='*.c' | wc -l)" \
    "$(grep -rl 'on_mouse\|_mouse(' $d --include='*.c' | wc -l)"
done
```
Report thin apps with LOC so the finding is actionable.

### 5. Check the first-boot surface
The onboarding stream (persisted sentinel → GREETER vs DESKTOP) and the visible
greeter dialog are separate things — one can exist without the other. Check both:
`src/runtime/wubu_onboarding.*` (the decision) and
`src/gui/shell/wubu_shell_greeter.*` (the visible dialog). A third failure is the
dialog being created and never appearing: creation order IS the z-order, so a
greeter created before the initial windows is painted underneath them (see
`wubuos-wm`). Verify on the PRODUCT with a fresh `$HOME`, not on a harness --
the sentinel and the window stack are both boot-path behaviour.

### 6. Settings that save but never apply ("write-only settings")
A settings panel can be a complete JSON round-trip and still do nothing. Check
whether the values are CONSUMED, not whether they are stored:
```bash
# every helper with zero external callers = the setting is inert
for sym in $(grep -oE '^#define|^[a-z]+ [a-z_]+\(' src/gui/wubu_settings.h | grep -oE 'wubu_settings_[a-z_]+' | sort -u); do
  n=$(grep -rn "$sym" src/ --include='*.c' | grep -v 'wubu_settings' | wc -l)
  [ "$n" = 0 ] && echo "INERT: $sym"
done
```
Then read the "apply" function itself -- a comment like "X would apply here"
is an admission, not a plan. The classic shape is an apply function that
contains only the theme setter: every other category is persisted and nothing
consumes it, so the settings panel is a JSON round-trip with no effect on the
running UI.

**Read the apply function BEFORE calling a setting write-only.** A setting can
be applied by direct struct access (`g_settings.a11y.high_contrast`) in the apply
body while its typed getter (`wubu_settings_high_contrast()`) has zero callers:
the getter is dead API, not a dead setting. Report those separately -- a dead
getter is cleanup, an unconsumed setting is a user-facing lie.

**Scope the caller grep to the DEFINING file.** Excluding every path containing
the module name (`grep -v wubu_settings`) discards the implementing files
(`wubu_settings_io.c`, `wubu_settings_defaults.c`) and marks the whole API inert
-- a guaranteed false positive.
**The cheapest real fix is often a global multiplier in the primitive layer**
(one `vbe_set_text_scale` rescales all ~201 `vbe_draw_text` call sites and, if
`vbe_text_width` scales too, layout maths stays coherent).

**A key absent from the saved file must keep its DEFAULT, not zero.** The JSON
loader overrides only the keys it finds, so `settings_apply_defaults()` must
run BEFORE `wubu_settings_load()`; otherwise a settings file written by an
older build -- or one that simply lacks a newer key -- leaves that key at its
zero value. And every key needs a deliberate default: `show_desktop_icons` had
none, so it read false and the product hid every desktop icon while the harness
(which never loads settings) showed them. When a whole surface is missing from
the PRODUCT but present in the harness, suspect a settings default (theme,
icons, a11y) before suspecting the renderer.

### 7. Duplicate implementations of the same subsystem
Two window managers, two clipboard backends, two editors: grep the header of
each and check which one the LIVE desktop actually links (`desktop_shot`'s
recipe is the truth). A second implementation reachable only from an orphan
test target is drift waiting to happen.

**The recurring shape in this tree** (met three times: a REPL, a text editor,
a window manager):
```
src/apps/<name>.c          <- the REAL implementation
src/apps/<name>/<name>.c   <- a parallel STUB, same basename, in a subdir
```
Its tell-tales:
- the stub's header owns an include guard **identical** to the real one, so a
  TU including both silently gets only one of them;
- the stub exposes a **parallel no-op API** (`notepad_create` / `_new_tab` /
  `_insert_char` as `(void)x;` bodies) alongside the real API
  (`notepad_state_get` / `np_new_tab` / ...);
- the **live desktop binds the real callbacks**, but the **test recipe and
  `APP_OBJS` bind the stub** -- so the real code is built, referenced by
  nothing live, and unverified, while the gate asserts the stub's no-op API.

Detection -- every nested `src/apps/<name>/<name>.c` is a candidate:
```bash
for f in src/apps/*/*.c; do
  b=$(basename "$f" .c); d=$(dirname "$f")
  [ "$d" = "src/apps/$b" ] && echo "nested duplicate? $f  vs  src/apps/$b.c"
done
```
Then confirm which one the recipe links and whether the other has any external
references. Resolve by **deleting the stub** and sweeping it out of `APP_OBJS`,
the test recipe and any `-I$(APPS)/<name>` include path; then point the test at
the real API, adding inspection accessors where the real state is
module-static so its behaviour is assertable.

### 8. "Feature X is missing" -- prove it by grepping the API, not by vibes
Before reporting a missing desktop feature, search for its API in the headers.
A feature can be fully implemented, gated and wired while having no string that
matches your first guess. 2026-11-08: this audit reported "no notification
center -- only systray count badges"; `notif_center_add/mark_read/clear/
render/is_open/toggle` were all implemented in `wm_systray.c`, rendered
from `wm_render.c` and toggled from `wm_input.c`.
Search several names (`quick_settings`, `tray_menu`, `systray_menu`; `lock`,
`lockscreen`; `emoji`; `overview`, `expo`) AND check the WM's header for a
declared-but-unfamiliar API before declaring a gap.

### 9. Input paths that can never fire (dead shortcuts)
A shortcut can be fully written, bound and still unreachable. Two failure
shapes, both invisible to a green gate because no test drives the dispatcher:

- **Hardcoded bitmasks that disagree with the platform's defines.** A
  dispatcher testing `mods & 0x08` for Alt while the platform header defines
  `MOD_ALT 0x04` means the shortcut can never fire -- and a neighbouring
  `mods & 0x04` "Ctrl" test silently fires on Alt instead.
- **A modifier the input layer never sets.** `MOD_WIN` can be defined and
  tested for, but if no backend ever ORs it in, every Win+ shortcut is dead.

Check both:
```bash
grep -n 'mods & 0x' <dispatcher>.c      # every raw mask must match a MOD_* define
grep -rn 'MOD_WIN' src/ --include='*.c'  # is the bit ever SET, not just tested?
```
Fix: include the platform's input header and use its `MOD_*` names; wire any
missing modifier at the input layer (e.g. map the Super keys to `MOD_WIN`).
Then add a test that drives the dispatcher with the real modifier values --
without one, the whole shortcut layer stays unverified.

**A binding that is a superset of another swallows it.** Adding Win+Ctrl+D does
not work if Win+D is tested first as `mods & MOD_WIN` alone: it matches, fires,
and returns, so the new shortcut is unreachable and the old one fires instead.
Ordering is not sufficient -- the broader binding must require the extra
modifiers to be ABSENT (`(mods & MOD_WIN) && !(mods & MOD_CTRL)`), and the more
specific binding must be dispatched first. A new hotkey is only proven when the
test drives BOTH combinations through the dispatcher.

### 10. Selector state that is never mutated (a feature with one reachable branch)
A subsystem can implement N options, expose a switch among them, and still be
stuck on the first: the count or index is set once at init and nothing ever
writes it again. The tell is a setter that validates against a constant no
caller can raise:
```bash
grep -rn '<count_or_index_field>' src/gui/ --include='*.c' --include='*.h'
```
If every write is inside the init function, all but one branch is dead --
virtual desktops you can switch to but never create, a taskbar pager showing
one page, a zone list of length 1. Report it as "present, one branch reachable"
and look for the missing creator/destroyer API rather than the missing UI.

### 11. A module whose only callers are its own tests (dead capability cluster)
A whole subsystem can be linked into the build and still be unreachable. For
each module added recently, grep its public symbols outside its own files and
its own `_test.c`:
```bash
for sym in <module_symbols>; do
  grep -rn "$sym" src --include=*.c --include=*.h \
    | grep -v "<module>" | grep -v "_test\.c"
done
```
Zero hits while the object sits in `RT_OBJS` / `GUI_OBJS` = a dead cluster.
Report it as a PROCESS gap (module-after-module with no integration step),
not only a code gap -- the fix is a caller, not a rewrite. The cheapest real
caller is the surface that already owns the geometry: the WM for anything that
lives on a window or the screen edge.

Also look for the same scaffold copied across two modules (calloc + add +
step + hit with the same shape). Two copies of one concern is drift; extract
the shared owner rather than fixing each copy.

### 12. The product legs (when the ask is "gaps", not "how does it feel")
A green QoL pass can coexist with a product that does not exist. When the ask is
a gap assessment against a product vision, audit these legs FIRST -- each is one
command, and a false claim here outranks twenty UI findings:
- **Hosted leg:** is there a runnable binary AND a target that builds it? Settle
  the README's build claim with `make -n <target>`; sources plus a
  `-DWUBU_HOSTED_TEST` capture harness are NOT a product.
- **Metal leg:** does the booted kernel bring up the desktop, or only the
  kernel/supervisor? `grep -rn 'wm_init\|desktop_init' src/kernel/` -- zero hits
  means the GUI is hosted-only.
- **Self-host leg:** `nm -u <kernel.elf>` empty? An on-target build gate? A
  ladder doc that exists?
- **Ecosystem leg:** grep the tree for the external layers by name (federation,
  AID, WID, sponsor, WorldSpace). Zero hits outside submodules = no bridge.
  That bridge EXISTS now (`src/runtime/wubu_agent.c` +
  `src/runtime/wubu_ns_worldspace.c`, published at `/n/agent` and
  `/n/worldspace`) — re-grep before reporting this leg open, and judge it by
  whether the surfaces PUBLISH live state, not by whether the files exist.
- **AGI-loop leg:** for every write path, find the read path. A publisher with
  zero callers, or a flat file published where a directory is required, is an
  open loop regardless of how green its own test is.

Report these as Tier 0 -- they gate the meaning of every QoL finding beneath
them, and they are what a "the product is done" claim rests on.

### 13. Menus and dialogs that are DRAWN but never DISPATCHED
A context menu, toolbar or dialog can render every item correctly and have ZERO click
handling: the pointer lands, nothing happens, or the whole menu just closes. This is
the menu-shaped twin of step 9's dead shortcuts and it is invisible to any gate that
only checks the draw path.

Detection -- compare the renderer's origin/state variables against the input handler:
```bash
# 1. what the renderer uses to place items
grep -n 'menu_x\|context_menu_x\|_y' <surface>_render.c | head
# 2. whether the input handler EVER reads the same variable for a hit-test
grep -rn 'menu_x\|context_menu_x' <surface>*.c | grep -v _render.c
```
If the only use outside the renderer is "clicked anywhere -> hide", every item is
cosmetic. A menu's drawn item count must be matched by a dispatch branch per item;
read the handler, do not infer it from the drawing code.

Worked shape (WuBuOS Explorer): the renderer drew eight items from
`ex->context_menu_x/y`, and the mouse handler closed the menu on any left click inside
it and returned -- no index maths, no switch, nothing. The underlying operations were
already implemented (`explorer_copy`/`cut`/`paste`/`delete`/`rename`/
`show_properties`), so the fix was a hit-test plus a switch, not a rewrite. Worse,
this surface also had NO open action at all, so a selected file could not be acted on by
any gesture.

**Sibling shape, found in the SAME menu: a `continue` that draws a separator INSTEAD
of an item silently drops one label.** The item array held eight entries while the
draw loop ran `if (i == 5) { draw separator; continue; }`, overwriting position 5 -- so
the menu rendered SEVEN labels while the code claimed eight, with no error and no
warning. Detection: compare the renderer's DRAWN ROW COUNT against the length of the
ITEMS array, and prefer INSERTING a separator row (`iy += row_h`) over replacing an
item slot. A `continue` inside a draw loop always costs the caller a row; ask whether
that row is a separator or a missing feature.

**Geometry read by BOTH the renderer and the hit-test must live in ONE header.** Here
the hit-test helper defined its own row constants while the renderer kept local copies
-- the setup for a silent divergence. Move them to the shared internal header and pin
the mapping in a test that calls the hit-test at EVERY row, asserts the separator row is
refused, and asserts a closed/hidden menu refuses everything. A comment saying "must
mirror the renderer" is not protection: a drifted menu is simply unclickable again.

Fix order: hit-test + dispatch the items whose operations already exist, then add the
missing primary action (open/activate), then wire extension-specific handlers. Report
the count of dead items and which operations were already available -- it is what makes
the finding cheap to close.

### Reporting shape
Report in tiers by human impact, each carrying the evidence that produced it:
1. **A green tier whose test TUs assert little** — with file + assertion count,
   and only after ruling out the shim-TU misreading in step 1.
2. **Real capability unreachable** — registry entry → launcher → engine.
3. **Apps with no input** — LOC + which handlers are missing.
4. **Unverified surfaces** — what exists but no test asserts.

Close with "what's genuinely good — don't rebuild" so the next session does not
re-implement working code, then a recommended order. Split the remainder into
**not yet built** (UI can be written today) and **blocked on missing
infrastructure** (no input path reports the data, no driver setter exists, the
data model cannot express it) -- the second cannot be closed by writing UI and
must be reported as a prerequisite, not a TODO.

### Writing the durable work list (when the ask includes "save it so we can continue")
When the user expects the context to be compacted and work to resume later, the
findings must live IN THE REPO, not in the chat transcript:

- Put them in one document under `docs/`, named for what it is, and REGISTER it
  in `mk/tests.mk`'s `test_docs` path list. A gated doc cannot rot silently; an
  unregistered one will.
- Every item carries four things: **owner file**, **acceptance test**,
  **priority tier**, and the **proving file** behind the claim. An item with no
  acceptance test is a wish, not a task.
- Keep a **Progress** section at the top and update it in the SAME commit that
  lands an item (mark it done, name the commit, name the verification). A stale
  list is worse than none: the next session trusts it over its own reading of the
  tree.
- Anything you could not confirm goes in an explicit **Open questions** section,
  never as a finding. Asserting an unverified gap costs the next session real
  time chasing something that already works.
- When a prior audit claimed something is missing, re-verify before repeating
  it -- and say in the doc which older claims turned out to be wrong. This is how
  the list stays honest across sessions.

## Auditing against a reference OS surface
When the ask is "find the gaps versus Windows 11 / Linux Mint / <reference OS>"
rather than "how does this feel", use
`references/reference-surface-gap-audit.md`: build a (feature -> implementing
regex) checklist, ship a re-runnable scanner (`tools/gap_audit.py` is the worked
example), report present/absent with a priority order, and split "not yet built"
from "blocked on infrastructure".

## Pitfalls
- **The theme's live colours are only seeded by `wubu_theme_set()`, and the
  only non-test caller is `wubu_settings_init()`.** A product/boot path that
  never calls `wubu_settings_init()` renders a BLACK taskbar, borderless
  windows and invisible desktop icons (`tc()->btn_face` / `icon_text` stay
  zero). Capture harnesses look fine because they call `wubu_theme_set()`
  directly and never load settings -- so a green capture proves nothing about
  the product. Call `wubu_settings_init()` before the first render.
- **`wubu_settings_load()` overrides only the keys it finds.** Defaults must
  be applied FIRST (`settings_apply_defaults()`), then the file overrides on
  top; otherwise any key missing from a saved file silently stays at its zero
  value. This is how `show_desktop_icons` ended up false and a fresh install
  surfaced an empty desktop.
- **A default of `false` for a visibility flag is a desktop-killer.**
  `show_desktop_icons` was never set anywhere, so it defaulted to false and
  `desktop_init()` hid every icon. Visibility flags default to true; the user
  hides things, the code does not.
- **The icon label owns the column pitch, not the glyph.** `max_label_w` must
  track `DOSGUI_ICON_COL_PITCH`, and the grid<->pixel maths must use the
  `DOSGUI_ICON_COL_PITCH` / `DOSGUI_ICON_ROW_PITCH` macros in EVERY place
  (icon_add_ex, shortcut_create, wm_restore_icon_layout, the arrange reflow,
  the grid helpers and the tests) -- a literal `SIZE + GAP` in one forgotten
  spot re-breaks the layout. Widening the column pitch means updating the
  test that clicks an icon by its old pixel position.
- **A RENDERED symptom is not a STORED symptom -- prove which one you have
  before filing it.** "Typed text arrives upper-case" was filed as an input bug
  and was wrong: the input bytes were correct (a lower-case command executed and
  produced output), and the shared 8x8 font simply had no lower-case glyphs, so
  everything rendered in capitals. A symptom seen on screen can originate in the
  producer, the transport, or the renderer; only the renderer explains a symptom
  that ALSO affects constant strings nobody typed. When code reading cannot
  separate them, RUN the product and compare a constant against typed input.
  Shipping a wrong root cause into a durable document costs the next session
  real time chasing a layer that is fine.
- **A missing CALLER is not a missing CAPABILITY -- apply steps 8 and 11 to
  your OWN first-draft findings before they reach the report.** "There is no way
  to run a command from the GUI" is false when a fork+exec layer exists and only
  the Run dialog fails to call it; the fix is a wire-up, not a build, and the
  estimate differs by an order of magnitude. Grep the implementing module under
  several names AND check whether anything wires it. The same discipline that
  stops a false gap finding stops a false gap CLAIM.
- **Do not trust a roadmap/plan doc for current state.** In-repo `*_PLAN.md` /
  `BATTLESHIP.md` claims about what is missing are routinely stale. Read the
  function bodies the doc names before acting.
- **A header comment saying "minimal stub" is not proof.** Verify by reading the
  body — and conversely, a file with no stub banner may still be a no-op.
- **Assertion counting must match the suite's macros.** `grep -c 'TEST('` misses
  suites using `CHECK(` / `ASSERT(` / `PASS(` / custom macros. Count all of them,
  or read `main()` to see which helpers exist.
- **LOC alone is not thinness.** A 200-line app can be complete; a 20-line app can
  be a shell. Pair LOC with handler coverage and a body read.
- **A capture harness can measure a stub** — verify which definition binds before
  believing a frame (`wubuos-desktop-capture-harness` pitfall 1).
- **A capture harness is not the product.** It bypasses the real boot (no
  settings load, no `desktop_init`), so a frame can certify a desktop the
  product never produces. Diff the harness's init against `hosted_init()`;
  missing theme/icon/a11y setup is the usual cause.
- **Distinguish "unwired" from "unused".** Real code with zero external references
  may be a library entry point called only from a path you have not grepped (e.g. a
  function-pointer table). Check the table before declaring it dead.
- **Check that a header's include guard is unique before writing it.** Two headers
  sharing a guard silently skip the second in any TU that includes both -- the
  build succeeds with declarations missing and the error surfaces in an unrelated
  TU as `unknown type name`. The check is one grep (see the adapter reference).
- **A "first member" embedding is not an array-of-structs stride.** Passing
  `&array[0].first` to code that indexes `ptr[i]` is only correct when the
  element type IS the struct. For an array of larger structs the stride is
  `sizeof(Element)`, not `sizeof(TheStruct)`, and the field silently walks into
  the next element's neighbours (observed: NaN in an unrelated field after ten
  steps, because 28-byte `WubuBlob` steps were applied to 40-byte islands).
  Pass the stride explicitly.
- **An undeclared or MIS-CALLED function is UB that compiles clean -- and it can look
  exactly like a logic bug.** Two shapes:
  (a) a test TU calls a new module without including its header -> implicit
  declaration, a WARNING not an error, so the gate stays green while the real
  prototype is never checked;
  (b) a DECLARED function is called with the WRONG NUMBER OF ARGUMENTS (two args
  against a four-parameter helper) -> the missing parameters receive garbage, so
  assertions fail while an adjacent debug loop using the correct form prints the right
  values moments earlier.
  Fix: add the `#include` in the same edit as the test that exercises the module, and
  keep every call site's argument count uniform. When observed values contradict your
  reading of the arithmetic, PRINT the actual return value instead of reasoning about
  operator precedence -- precedence reasoning is precisely how this one stayed hidden
  for several debugging rounds.
- **A feature->module mapping table is a CLAIM, not an inventory.** The
  `os-studies/README.md` "QUICK REFERENCE: KEY GAPS BY OS" table maps
  reference-OS features to module filenames, and a large share of those files do
  not exist -- the names were written down as targets. Re-verify every entry
  against the tree before reporting a gap or planning a graft:
  ```bash
  for m in <module>; do ls src/*/*$m*.c src/*/*/*$m*.c 2>/dev/null; done
  ```
  Use an INFIX glob (`*$m*.c`), not a prefix glob (`$m*.c`) -- `wubu_proton_dxvk.c`
  does not match `dxvk*.c`, so a prefix miss reads as "missing" when the module
  exists under another name. Also try name variants (`*gamescope*`, `*flatpak*`,
  `*bus*` for D-Bus) before concluding a subsystem is absent.
