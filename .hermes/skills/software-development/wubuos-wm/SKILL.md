---
name: wubuos-wm
description: Use when adding a WuBuOS shell/WM overlay, panel or hotkey.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wubuos, gui, wm, shell, desktop]
    related_skills: [wubuos-qol-surface-audit, wubuos-test-suite, wubuos-desktop-capture-harness]
---

# Adding a shell feature to the WuBuOS WM

## When to use
- Adding a desktop overlay, panel, OSD, lock screen, saver, overview or quick
  settings surface.
- Putting real artwork on a surface (a mascot, an icon set, a splash) in a tree
  with no image decoder: bake it to an RGBA table and blit it through `vbe_*`.
  See `references/baked-art-assets.md` for the pose-extraction pipeline, the
  isolation pitfalls and the multi-pose state pattern.
- Adding or repairing a WM hotkey.
- Wiring a setting into live behaviour.
- Adding or repairing touchpad gesture input -- see
  `references/gesture-input.md` for the engine shape, the weak-reference rule
  and the recogniser pitfalls.
- Adding a Lua-driven GUI surface (a script that draws through `gui.*` onto the
  VBE surface) -- that is a scripting layer, not a WM overlay; see the
  `wubuos-lua-scripting` skill for the boundary, the host wiring order and the
  interning/table pitfalls.
- Making an existing runtime module reachable from the desktop -- a surface
  that already has a gate and no caller. See
  `references/launchable-blob-surface.md` for the glue shape and the real
  caller.

The audit skill (`wubuos-qol-surface-audit`) finds the gap; this skill closes it.

## The wiring order -- all six steps, every time

Skipping a step produces a link error or a surface that never appears.

1. **Declare it.** Public API in `src/gui/wm.h`; module-static state
   stays in the module. Only cross-module state goes in
   `wm_internal.h`.
2. **`mk/objects.mk`** -- add the `.c` to `GUI_OBJS`.
3. **`mk/tests.mk` -- add it to EVERY recipe that links the WM.** This is the
   step that costs time. Find the recipe lines by grepping for an existing WM
   source and append the new file to each:
   ```bash
   grep -n 'wm_taskbar.c' mk/tests.mk
   ```
   A single edit with `str.replace(old, old + ' $(GUI)/shell/<new>.c')` covers
   them all. Missing one target = `undefined reference` only in that target.
   **Add the module's transitive sources on the same lines.** A surface backed
   by a runtime module (rim islands, the slime seam) calls that module's
   functions, so every recipe line also needs `$(RT)/wubu_<dep>.c` -- and the
   dependency's own dependency. Adding only the surface's `.c` links the one
   target you happened to build first and fails with `undefined reference to
   <dep>_*` everywhere else.
   **When the WM gains a new call into a module, enumerate the targets that
   link the WM WITHOUT that module and add weak stubs to their test TUs.**
   Those TUs usually already stub a sibling symbol from the same module (e.g.
   `startmenu_is_open`); a new `startmenu_handle_key()` call then fails only in
   them, one `undefined reference` per target. Find the set by recipe, not by
   guessing:
   ```bash
   python3 - <<'PY'
   import re
   rules = re.split(r'\n(?=\S)', open('mk/tests.mk').read())
   for r in rules:
       if 'wm_input.c' in r and 'startmenu.c' not in r:
           m = re.match(r'^([^\s:]+):', r)
           if m: print(m.group(1))
   PY
   ```
   Add `__attribute__((weak))` stubs to each named test file. Weak matters: a
   strong stub collides with the real definition in the targets that DO link
   the module.
4. **Render hook** in `src/gui/wm_render.c`, at the right layer (below).
5. **Input routing** in `src/gui/wm_input.c` -- keys first, then pointer.
6. **Test** in `src/gui/wm_test.c`, and include the new module's header.

## Render layering (later calls draw on top)

The current top of the stack, in call order inside `wm_render`:

```
windows -> slime seam -> rim islands -> a11y cluster -> bonzi buddy
        -> taskbar -> systray / notification center -> clock menu
        -> Win+Tab overview -> Win+W widgets board -> Win+Z snap flyout
        -> lock screen -> screen saver
        -> Win+A quick settings -> volume/brightness OSD -> cursor
        -> surface effects (/n/effect)
```

Pick the slot by what must stay visible above it. A lock screen goes above
everything but the cursor; an OSD goes above panels but below the cursor. Read
`wm_render.c` before inserting -- the order is the file's call order.

## Cross-layer calls: weak references, always

The WM links into targets that do not link the app or driver layers (the
headless WM tests link no driver raft at all). A hard reference breaks every
such recipe:

```c
extern __attribute__((weak)) void music_apply_system_volume(float v);
...
if (music_apply_system_volume) music_apply_system_volume(vol);
```

Same for kernel driver probes: a missing driver reads as "off", never as a
link failure. Check the recipes before choosing: `grep -n '<callee>.c' mk/tests.mk`.

**An OPTIONAL shell layer is reached through a weak hook module, not called
directly.** If `wm_render.c`/`wm_input.c` call `win11_snap_render()` directly,
every test recipe that links the WM must also link `win11_snap.c` and its deps
-- miss one and that target fails with `undefined reference`. Instead declare a
few weak hooks in a header (`win11_shell_render` / `_key` / `_click`), call
them guarded, and define them in one `win11_shell.c` that pulls in the layer
modules. Minimal test builds then link with no Win11 code at all, and the
product links the strong definitions. Same shape as the weak `launch_app` /
`music_apply_system_volume` pattern above.

## Shared state lives in ONE module

When several surfaces show the same value (an OSD and a quick-settings panel
both showing volume), the value lives in one module (`wubu_osd.c`) and every
consumer reads it. Never let each surface keep its own copy -- they drift and
the user sees two different numbers for the same setting.

## Naming: the shell is `wm_*`, not `dosgui_*`

The stale `dosgui_` prefix (104 files, a "DOS GUI" layer that no longer
exists) was dropped in 2026-11.  The first token names the layer now:

- `wm_*` -- window manager (`wm.c`, `wm.h`, `wm_input.c`, `wm_render.c`,
  `wm_window.c`, `wm_layout.c`, `wm_window_state.c`)
- `startmenu_*`, `explorer_*`, `term_*`, `controlpanel_*`, `cp_*`, `bpm_*`,
  `daemon_panel`, `service_mgr`, `dos_window`, `era_apps`, `quick_settings`,
  `window_chrome`, `desktop`, `taskbar_tasks`

`wm.h` is the real header and still carries the legacy NanoShell aliases
(`WmWindow`, `WinFlags`, `wm_create_window`, `wm_destroy_window`), so old apps
build against the live implementation.  Never add `dosgui_` back.

Two latent bugs that a rename like this exposes, both fixed:
- `term.c` carried stale local forward declarations that used to differ from the
  real API by name and so never collided; they now collide.  Removed.
- the screenshot harnesses declared a static `tick()` that collided with the
  now-public `wm tick()`; renamed to `shot_tick()`.

## Doing a safe bulk relabel (the sequence that worked)

When the user says a prefix is noise and the files must be reassessed, do it
in this order or a recipe breaks in a way you will spend a session chasing:

1. **Survey first.** List every file with the prefix; check for post-strip
   filename collisions (the one existing header `wm.h` absorbed the aliases);
   grep the prefix inside string literals -- a global strip is only safe where
   it appears nowhere the user sees.
2. **Rename files with `git mv` BEFORE stripping content.** Then strip the
   prefix across `.c/.h/.mk/Makefile/.sh` with one `s/prefix//`. The strip also
   rewrites TEST stubs and recipes, so do not stop at "no refs left" -- that is
   the easy half.
3. **Iterate the linker, not your assumptions.** Build `make test_<t>` and
   grep for `undefined reference to \`X'` and `multiple definition of \`X'`;
   fix each and repeat in a loop. The strip silently renames stub definitions
   whose old name happened to contain the prefix (e.g. a stub `agi_kernel_*`
   binds to nothing because the real symbols are `wubu_agi_kernel_*` and do NOT
   contain the stripped prefix, and a real-defined symbol your stub duplicates
   hits `multiple definition`). Verify by SYMBOL, never by believing the rename
   was total.
4. **Reconcile every collision the merge creates.** A rename that merges two
   formerly-distinct names into one makes the compiler surface latent,
   divergent declarations that used to coexist silently (stale `term.c` forward
   decls; a public `wm tick()` now colliding with a test TU's `static tick()`).
   Fix the declarations, do not rename around them.
5. **Check the file-owner boundary before reorganizing.** Files inside other
   repos' submodules (wubuwizard `lfm2/crnn/train`, wubuoffice build dirs) are
   not yours to rename -- leave them. An intentional brand codename (`src/bear`
   = the sovereign BearRL stack) is not noise; do not strip it.
6. **When a test includes a real header transitively** (a `_test.c` that pulls
   `wm.h` through an app header), its stubs must match the EXACT real types
   (`DosGuiWindow *`, `bool`) -- a permissive `void *`/`int` stub only compiles
   while the declaration is out of scope; once the real header is visible it is
   a hard type-conflict error. Match real signatures from the start.

## The taskbar pin model

`src/gui/shell/taskbar_tasks.{h,c}` -- a TASK is an APP, not a window (identity
key, title, launch command, pinned flag, running window).  Pins persist to
`~/.config/wubuos/taskbar` (atomic write, `pin key|title|exec` per line,
comment-readable).  `wm_init` loads them, `wm_shutdown` saves them.  Pinned
tasks render in the taskbar even with no running window; clicking launches via
`dosgui_launch_app`-equivalent `launch_app` (weak, guarded).

## Tutorials

`src/apps/wubu_tutorial.c` + `src/apps/tutorials/*.wet`: interactive tutorials
that ARE `.wet` applets.  `tut.action(name)` opens the real tool.  See the
`vws-form-designer` skill.

`src/apps/wubu_walkthrough.c` is the FIRST-RUN walkthrough: a clicked,
stepped window (Back / Next / Finish, step dots, a baked clipart pose per step)
that teaches the real path -- terminal, HolyD, the VWS designer, the buddy.
`gs_launch()` in `getting_started.c` opens it, and the greeter's "Getting
Started" offer reaches it through `launch_getting_started`. Steps must describe
things that EXIST and are reachable; the walkthrough is a claim about the
product, so a step naming a tool that moved is a bug.

## Geometry has ONE owner: `include/wubu_gui_metrics.h`

Every shell surface reads layout numbers from the metric system; nothing may
hardcode a margin, gap, radius, control size or chrome height. When the audit
reports "incorrect margins and bad design", the cause is almost never taste --
it was that there was NO shared scale: `window_chrome.c` carried title bar 20 /
buttons 14 / icon padding 6 / text padding 8 while the taskbar, Start menu,
systray and context menus each carried their own literals (4/6/7/8/10/12/20
all appearing independently), and `wm.h` disagreed with the tokens on the same
concepts (caption 20 vs 32, taskbar 28 vs 48).

One decision point, two shapes:

- `include/wubu_gui_metrics.h` holds the canonical compile-time `WUBU_METRIC_*`
  values AND the runtime `struct`; `wubu_gui_metrics_default()` copies the
  defines, so a number changes in exactly one place.
- `src/gui/wubu_tokens.h` ALIASES those defines (`WUBU_SPACE_XS` ->
  `WUBU_METRIC_GAP_XS`, `WUBU_TITLE_BAR_H` -> `WUBU_METRIC_TITLEBAR_H`,
  `WUBU_TASKBAR_H` -> `WUBU_METRIC_TASKBAR_H`) instead of restating them, and
  `wm.h` consumes them too.

Canonical values: unit 4; gaps 4/8/12/16; margins 4/8/16/24; row 24,
control 32, touch 40; window caption 32, taskbar 48; hairline border 2.
Radii are ELEMENT-CLASS tokens, not drift: `WUBU_METRIC_RADIUS_CONTROL` 4 /
`WUBU_METRIC_RADIUS_WINDOW` 8 (a button corner and a window corner genuinely
differ; two truths only appear when a class is unnamed).

`src/gui/wubu_tokens.h` therefore keeps only the token-specific extras
(`SPACE_2XS/XL/2XL`, glyph/type sizes) plus the aliases.

Migration recipe, value-mapping table and dead-duplicate sweep:
`references/gui-metrics-migration.md`.

Windows 11 caption treatment (`THEME_DARK`): buttons run the full 32px
caption height, are 46px wide, touch the frame corner and carry no gap.
Classic keeps square inset buttons. Both paths derive from the same tokens,
and `chrome_caption_metrics()` is the single answer to "how big is the
caption" for any surface that must align with it (a snap flyout, a tooltip).

**When a metric changes, expose it through an accessor and assert THAT in a
gate.** A test asserting `bar_h == WUBU_TITLE_BAR_H` and that Close touches the
frame edge survives a later redesign; a pixel estimate read off a rendered
frame does not. See `wubuos-hosted-product` for why a screenshot description
cannot be trusted as a measurement at all.

## Pitfalls

- **A new shell file's bare integers are a second geometry owner.** Grep a
  freshly written surface for literal offsets in rect arithmetic
  (`rect(... + 8)`, `* 20`) and replace them with tokens as you write it.
  Refactoring later means every surface has drifted to its own incompatible
  set, which is how "the margins are wrong everywhere" happens at all.
- **Off-grid spacing values are accidents, not taste.** 6/10/22/26/30/34
  show up where 8/12/24/32 was meant; replace with the nearest canonical
  `WUBU_METRIC_*` token and say what it was in the comment. Genuinely
  non-spacing numbers (glyph cell sizes, item counts, physics offsets) are
  false positives -- leave them.
- **Centre text with `vbe_text_width(label, scale)`, never `strlen(label)*8`.**
  The font advances 6px per cell and honours the global text scale; a hardcoded
  8px cell sits every label off-centre and breaks harder under scaling. The
  measurement API is the owner of "how wide is this string" — a second estimate
  in a draw path is a geometry owner you did not intend.
- **An unused enum or constant table that contradicts the live convention is a
  trap, not documentation.** A hit-test enum ordered close=1/min=3 while the live
  hit-test/handler pair used min=1/close=3 reads as authoritative to the first
  caller that trusts it, and wires Close to Minimize. When a census or review
  finds a dead table disagreeing with live code: align it to the live numbering
  AND use it in both producer and consumer (or kill it) — never leave two
  conventions coexisting.
- **A dead duplicate chrome constant contradicts a live one silently.**
  `wm.h` once carried `WM_TITLE_HEIGHT` / `WM_BORDER_WIDTH` /
  `DOSGUI_TASKBAR_H`, each referenced ONLY by its own definition and each
  disagreeing with the `DOSGUI_*` name that IS used. Before adding a token,
  grep its stem for an existing define; if a copy is unused, delete it rather
  than reconciling both.
- **Gate the owners against each other.** `make test_gui_metrics` asserts the
  canonical defines equal the runtime defaults, that `wubu_tokens.h` and
  `wm.h` agree with them, and that WM chrome heights stay on the 4px grid.
  Run it after touching ANY spacing value, plus the affected surface's suite
  and the full gate.
- **A desktop icon's `DESK_ICON_COUNT + N` index must be UNIQUE.** The app
  registry holds one entry per index, so a new icon that reuses an existing
  `+N` silently REPLACES that icon: the new one never appears in the column
  and the displaced one is gone, with no error and no test failure. Before
  adding an icon, `grep -n 'DESK_ICON_COUNT +' src/apps/apps.c` and pick the
  first index nothing else claims. Indexes are a sparse hand-allocated space,
  not a sequence -- always survey, never assume `+1` past the last one is
  free.
- **An app window whose `user_data` is never attached opens BLANK, and every
  render test stays green.** `wm_create()` returns a window with
  `user_data == NULL`; the app's draw path correctly bails out on NULL, so the
  window renders an empty frame and nothing crashes. The launcher must create
  the state and attach it (`win->user_data = state`, the `edr_dash`/`apps.c`
  convention) and then prime it (refresh the list the draw shows). A capture
  harness proves nothing here -- it draws the desktop, never launches the app.
  When a window is blank, check the state attachment FIRST, then the draw.
- **A taskbar layout lives in exactly one function.** THEME_DARK draws a
  floating centred bar; classic themes draw the full-width one.
  `taskbar_modern_layout()` is called by BOTH the renderer and the pointer
  path, so the bar cannot be drawn in one place and clicked in another.  When
  adding a surface that has both a draw and a hit-test (taskbar, dock, panel),
  compute the rects once and share them -- a second copy of the arithmetic is
  how you get a click that lands N px off. For tray/pager-style strips the
  renderer PUBLISHES its wells into `g_dwm` (`tray_well_*`, `clock_well_*`) and
  one hit-test owner (`systray_icon_at`) consumes them from EVERY input path —
  including `taskbar_modern_handle`, which otherwise swallows the whole island
  and leaves drawn controls dead. Gate by firing a real `wm_handle_mouse` press
  at the published well and asserting the callback ran, in BOTH themes.
  Mechanism + the three-bug pattern: `references/hit-test-wells.md`.
- **Window-chrome button geometry has one owner too, and the WM is a second
  consumer.** The renderer, `chrome_hit_test_button()` and the WM's pointer
  path each carried their own copy of the min/max/close rect arithmetic and all
  three drifted: the WM's Close sat 4px left of the drawn button (clicking
  Close did nothing), the chrome hit-test omitted the border-width offset and
  sat 2px high, and max/min were gated behind `Luna_start_button`, so on the
  dark theme they were drawn but inert. Expose `chrome_button_rects()` and
  call it from the renderer and both hit-tests. Then check whether a button is
  gated behind a theme flag the renderer does not consult -- a drawn button
  that is never hit-tested is a silent dead control.
- **A synthetic/interactive title-bar drag that does not move the window is
  almost always swallowed by a CHROME button, not lost in drag logic.** On a
  narrow window the close/max/min buttons are laid out FROM THE RIGHT at their
  full width, so their x-range reaches well toward centre (a 200px window:
  buttons span ~[x+182, x+w]). A grab at centre-x (`x + w/2`) IS the minimize
  button -- the press returns at the chrome-button hit-test (run BEFORE the
  window drag path), the window turns up MINIMIZED (`flags & DOSGUI_WIN_MINIMIZED`,
  which makes it invisible to hit_test), nothing moves, and the drag falls to
  empty desktop (lasso). Resize still works because it grabs an EDGE, not the
  title bar. To isolate: bisect the pre-hit_test pointer handlers
  (`win11_shell_click`, slime, rim, bonzi, a11y, modern/classic taskbar) by
  guarding each with `if (0 && ...)`, then instrument `hit_test()` to dump every
  alive window's rect + MINIMIZED flag -- a freshly-created window showing `m`
  proves the grab hit its minimize button. FIX the grab, not the WM: in
  synthetic-drag tests grab the title bar LEFT of the buttons (e.g. `x + 30`),
  never centre-x on narrow windows.
- **The taskbar's top edge is `taskbar_top()`, never `screen_h - task_h`.**
  It folds in `g_dwm.taskbar_offset` (always 0 now -- the auto-hide is gone for
  Windows 11 parity -- but keep going through the helper), so the render, the
  window clip, the hit region, the Start/clock/systray/pager geometry, the
  maximize height and the icon-drag clamp all agree.  A sixth copy of the
  arithmetic is how you get a bar drawn one place and clicked in another.
  When adding a new taskbar-adjacent surface, use the helper.
- **Draw through `vbe_*`, never through the caller's `fb` pointer.** The WM
  can pass `fb == NULL` to `on_draw` (it does, on the path where a surface is
  created mid-frame), so a direct `fb[y * w + x]` segfaults on the new
  surface's first frame while every older surface keeps rendering and the gate
  stays green. `vbe_set_pixel`/`vbe_get_pixel` write the real back buffer, are
  the single drawing path, and honour clipping. The existing rule about
  ASSERTING pixels through `vbe_get_pixel` is the read half of this; the write
  half crashes rather than misleads.
- **Window creation order IS the z-order.** `wm_create` appends to `zorder`, so
  a dialog created before the windows it must cover is drawn UNDERNEATH them and
  simply never appears -- no error, no test failure. Create the topmost surface
  LAST, or raise it explicitly. The first-boot greeter was invisible for exactly
  this reason: it was created before the initial file-manager and terminal
  windows, which then painted straight over it.
- **A dialog whose action opens a window must close itself.** If the handler
  launches something and leaves the dialog up, the dialog hides what it just
  launched and the user sees nothing happen. Close it in the same handler.
- **The taskbar auto-hide is gone; do not reintroduce it.** The modern theme
  used to slide the bar off-screen whenever the pointer left the bottom band
  (`taskbar_offset -> th`), which put the Start button below the screen edge --
  a click at its old position hit nothing and the bar "disappeared". Windows
  11's bar is always revealed, so `wm_render` pins `taskbar_offset = 0`. A
  taskbar-adjacent surface must not assume the bar can hide.
- **A hotkey that is a superset of another swallows it.** Win+D tested as
  `mods & MOD_WIN` matches Win+Ctrl+D first, so the new shortcut never fires.
  The broader binding must require the extra modifiers ABSENT
  (`(mods & MOD_WIN) && !(mods & MOD_CTRL)`), and the specific binding must be
  dispatched first. Test BOTH combinations through the dispatcher.
- **Include the new module's header in the test TU.** An implicit declaration
  is a warning, not an error: the gate stays green while the prototype is never
  checked, and a signature drift surfaces as a runtime crash.
- **A surface that only renders is not a feature.** Gate the input path too --
  a panel whose rows do nothing, or a lock screen that does not swallow the
  pointer, passes a render-only test. And a surface with no real caller is not
  reachable however green its gate: mirror an existing persisted model into it
  (`references/launchable-blob-surface.md`).
- **Verify by running the target**, not by reading the recipe: `./src/gui/wm_test`.
- **Pixel assertions read the VBE back buffer, not the `fb` you passed.**
  `wm_render(fb, w, h)` takes a framebuffer argument but the `vbe_*` primitives
  write to the global VBE buffer, so scanning a malloc'd `fb` always finds
  nothing. Use the WM test convention: `vbe_init(w, h)` +
  `wm_render(NULL, w, h)` + `vbe_get_pixel(x, y)`.
- **Assert a tolerance band on animation-derived positions, never equality.**
  A spring settles within a fraction of a pixel and the `(int)` cast truncates,
  so `x == 200` fails on 199.99. Use `x >= 198 && x <= 202`.
- **A `clear()` that frees the backing module must re-initialise it.** Freeing
  without re-init leaves capacity 0, so every later `add()` returns -1 and the
  surface silently refuses input while a count-based test still passes.
- **A gesture recogniser's baseline and its evaluation must order the same
  contact pair the same way.** Ordering the pair by arrival at touch-down and
  by slot index at lift makes a symmetric gesture (a horizontal two-finger
  swipe) read as its opposite (a 180-degree rotation). Sort by a stable key in
  both places. Details and the other recogniser thresholds are in
  `references/gesture-input.md`.
- **Verify a geometry defect by MEASURING pixels, never by reading a vision
  pass over a crop.** A vision model reading a resized crop routinely reports
  "clipped by the screen edge" where the subject is fully on-screen with room to
  spare — what it saw was the crop boundary or the resize, not the screen edge.
  Scan the framebuffer numerically for the surface's distinctive colour range,
  print min/max x/y plus the gap to each screen edge, and only then claim a
  clipping or layering defect. The same caution runs in reverse: do not call a
  placement fix verified because a crop looks tidier.
- **An always-on desktop surface goes against a region nothing else owns.**
  Hardcoding one corner overlaps whatever lives there: the mascot sat at x=8,
  which is exactly where the desktop icon column begins (icons start at x=20),
  so it covered their labels; butting it against the taskbar with no margin let
  the idle bob push its base under the bar. Before placing a permanent overlay,
  find where the icons, taskbar (`taskbar_top()`), tray and clock live, use the
  empty corner, take spacing from `wubu_tokens.h`, and CLAMP so odd screen sizes
  cannot push it off-screen. If the position is computed at init AND on resize,
  update both call sites — otherwise a resize strands it where the old size put
  it.

## Gate

`make -k -j24 test` -> RC=0, 0 errors, 0 segfaults; `make -j24` clean;
`make desktop_shot` still writes its frames.
