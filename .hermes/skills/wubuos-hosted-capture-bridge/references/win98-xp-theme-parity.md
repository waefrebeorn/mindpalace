# Windows 98 / XP Theme Parity in the DosGui Chrome Layer

How to make a chrome surface read as authentic Win98 Classic vs XP Luna,
and how to verify each change visually. Applies to the DosGui chrome
files: `src/gui/window_chrome.c`, `src/gui/wm_taskbar.c`,
`src/gui/wubu_theme.c`.

## Theme Gate: one flag drives the whole era split
`th->Luna_start_button` (a bool on `WubuTheme`, set true for every
post-98 theme: Luna/Zune/Media/WuBu) is the era switch. Rule: **never
branch on the theme ID enum; branch on the flag**, so a new post-98
theme inherits XP behavior automatically.

`tc()` returns `const WubuThemeColors *`; `theme()` returns
`const WubuTheme *` — both are declared in
`src/gui/wm_internal.h`, no extra include needed.

## Scope: complete parity, every sub-surface
The assignment is COMPLETE Windows XP user-experience parity — every
button, pane, hover state, and flyout, not a representative sample. A
surface that renders but is missing its sub-surfaces (sidebar present,
username banner absent) is half-done: finish the remaining sub-surfaces
before opening a new one. The banner name comes from a cached accessor
(`startmenu_user_name()`: `$USER` → `$LOGNAME` → `"User"`,
declared in `startmenu.h`) — add the accessor, don't inline
getenv in the render path.

## Per-Surface Rules (post-98 vs Win98 Classic)

| Surface | Win98 Classic | XP Luna / post-98 |
|---|---|---|
| Close button | silver 3D raised, black X | **RED rounded rect, WHITE bold X**, 18px wide |
| Min/Max buttons | silver 3D raised, black glyph | FLAT translucent pale rect over the title bar, soft rounded edge, black glyph |
| Taskbar buttons | 3D sunken(active)/raised(inactive) | FLAT: active = pale-blue face + 1px Luna-blue edge; inactive = near-white + soft edge; **minimized == inactive** (XP never sunkens) |
| Start orb | flat silver, flag, black "Start" | GREEN pill, soft vertical gradient (lighter top), 3D edge, flag left-of-center, bold white "start" |
| Title bar | flat `win_title_active` fill | **VERTICAL gradient**: dark saturated color at BOTTOM, lighter at TOP ("lit from above") |
| Title text | flat color, no shadow | WHITE + 1px drop shadow offset (+1,+1) in a darkened gradient color |
| Start menu right pane | flat list on gray | username banner at top: bold dark name + two-tone circular avatar at the pane's right + 2-tone divider below; program list shifts down by the banner height (Luna only) |
| Menu-item icons (main pane + flyout) | none | 16×16 rounded colored square + 1px dark border, left of the label; label shifts past it |

## Hover States (distinct from static chrome — don't reuse select_bg)
A hovered Luna menu item is a **LIGHT blue tint, FLAT** — never the
saturated `tc()->select_bg` and never a 3D-raised edge (both read as
Win95 selection). Rule: hover bg `0xB4D0F5`, hover edge `0x316AC5`
(a 1px `vbe_rect_rounded`), hover fg black. Applies to BOTH the
main-pane items and the flyout rows. Win98 Classic keeps its original
`select_bg` + raised treatment untouched in the else-arm.

## VBE primitive to use
- `vbe_vgradient(x, y, w, h, top_color, bottom_color)` — vertical
- `vbe_hgradient(x, y, w, h, start, end)` — horizontal (legacy)
- `vbe_fill_rect_rounded(x, y, w, h, radius, color)` +
  `vbe_rect_rounded(...)` — rounded edges
- All declared in `src/kernel/vbe.h`.

## Title-Gradient Trap
Theme tables store `title_gradient = {darker, lighter, true}` (start =
darker). The vertical gradient must run **lighter(top) -> darker(bottom)**:
pass `vbe_vgradient(..., lighter, darker)`. Passing them in table order
inverts XP's lighting and reads as "lit from below".

When a window has rounded corners (`rad > 0`), the gradient pass must
re-fill the rounded rect first (`vbe_fill_rect_rounded(win_face)`) then
re-apply the gradient for the corner rows, then the rounded border —
otherwise the corner pixels keep the client-area color.

## XP Color Constants (when the theme lacks a slot)
Close-button face `0xE0431E` (active) / `0xC03A1A`, highlight edge
`0xF0855E`, outline `0x8C2A10`. Flat taskbar/button face `0xD6E4F7`
(active) / `0xF1EFE8` (inactive), edges `0x316AC5` / `0xB8B4A8`.
Title shadow `0x002850` (active) / `0x606060` (inactive).

## Verify Every Change with the Capture Harness
Never ship a chrome change on code review alone — the whole point of
this layer is pixels. Run the harness and look at the frames:
```
make gui_shot            # EXIT=0 + frames in /tmp/wubu_gui_shots
make test_wm      # chrome regression suite must stay green
```
The `gui_shot` harness cycles themes (Win98 -> XP Luna -> WuBu), so one
run shows both eras of every surface you touched.

## Theme-Reactivity Round-Trip (surfaces follow the theme, not stale state)
Every XP surface reads `theme()` flags at render time, so a Win98<->XP toggle
must not leave stale state. Add a round-trip test that: sets Win98 -> asserts
the era flag (`Luna_start_button`) OFF; sets XP Luna -> asserts the flag ON;
renders after each switch (no crash). Then cycles through all `THEME_COUNT`
themes via `wubu_theme_cycle()`, re-rendering the full desktop+taskbar+chrome
each time, and asserts a full cycle returns to the starting theme
(`wubu_theme_current()`). Finally round-trips back to Win98 -> flag OFF again
with no leftover XP state. Accessors live in `wubu_theme.h`
(`wubu_theme_current`, `wubu_theme_cycle`, `THEME_COUNT`). This locks the
theme-reactivity of every surface at once.

## Pitfalls
- **Draw the glyph, don't use the font:** XP glyphs are 1-2px bold
  strokes drawn with `vbe_set_pixel` loops at fixed offsets — never
  8x8-font characters. A double-width diagonal (`i` and `i+1`) reads as
  "bold" at 14px.
- **Rounded-rect buttons eat width:** the XP close button is 18px where
  the others are 14px; lay out from the right edge with the wider
  button accounted for, or the glyph drifts off-center.
- **Drop shadow before, not after:** draw the shadow pass at
  `(text_x+1, text_y+1)` FIRST, then the glyph pass, or the shadow
  covers the text.
- **Win98 Classic must not regress:** every branch keeps the original
  silver-3D path verbatim in the `else` arm. Users run both themes.
- **Menu-icon glyph needs a layout offset helper:** draw the 16×16 icon,
  then shift the label past it. `draw_menu_icon()` returns the label
  offset (icon width + padding, ~20px); pass the shifted x and the
  reduced width to the item renderer so truncation math stays correct.
- **New struct fields must be explicitly zeroed:** adding `icon_color` to
  `SmMenuItem`/`MainMenuItem` means every construction site needs it set.
  Convert positional initializers (`(T){A,"","",0}`) to **designated
  initializers** (`.field = v`) so the new field is `0` (no icon) rather
  than inheriting a stale array value — a positional initializer silently
  leaves the new trailing field unset.

## XP Interaction Semantics (behavior, not paint)
Parity is also how icons respond to input, not just how they look:
- **Desktop icons: single-click SELECTS, double-click LAUNCHES.** Any
  click firing the launch handler is a bug — a plain click must highlight
  (the navy translucent `wm_draw_icon_selection` already renders
  from `icon->selected`). Selection is exclusive: selecting one clears
  all others, like XP.
- **Double-click detection needs a clock.** No OS tick exists; derive a
  monotonic frame-clock from the render loop (`render_frame_count * 16`
  via `wm_ticks_ms()`), and a ~500ms window on the same icon index
  (`last_click_icon`/`last_click_ms`) distinguishes single from double.
  Initialize `last_click_icon = -1` in `wm_init` alongside the
  other id fields. Add a regression test that single-click sets
  `selected`, and a second click >500ms later is NOT a double-click.
- **Selection highlight already exists — wire the input to it.** Before
  writing a highlight renderer, grep for the existing
  `wm_draw_icon_selection` and the `icon->selected` flag; the gap
  is usually the input path never setting the flag, not a missing painter.

## XP Reusable Control Primitives (scrollbar, push-button, app-layer button)
Build these ONCE as theme-gated primitives and route every app through them —
do not per-app patch. Signature: `draw_button(x,y,w,h,label,state,is_default)`
(state 0/1/2 = normal/hover/pressed) and
`draw_vscrollbar(x,y,w,h,scroll,visible,total)` (content model).
- **Luna scrollbar:** beige sunken track + white right highlight; flat up/down
  arrow buttons; the thumb is a rounded BLUE-gradient pill (lighter `0x8FB8E8`
  top → `0x3A6EA5` bottom, dark `0x24486E` edge). Win98 keeps raised silver 3D.
- **Luna button:** flat + rounded, NO 3D bevel. Normal = soft light gradient +
  1px outline + black label. **Default/primary = Luna blue gradient + WHITE
  label** (the OK/Apply action). Pressed shifts content down 1px and darkens.
- **App-layer button is the lever:** `chrome_draw_button` (used by the
  Calculator keypad and dialogs) is shared — make IT theme-aware (delegate to
  `draw_button` under Luna, `pressed→state 2`) and every consumer
  inherits XP parity with zero per-app change.
- `vbe_3d_raised_colors`/`vbe_3d_sunken_colors` take `(x,y,w,h,light,face,
  dark,darkest)` — 8 args, NO bevel-width param. Passing a 9th arg is a compile
  error.

## XP Start-Menu Nested Cascades (All Programs → category → app)
XP's Programs is a CASCADE of categories, not a flat app list. Model it with a
static submenu registry so any flyout can open a nested flyout:
- Registry: `SmSubmenu g_sm_registry[SM_MAX_SUBMENUS]` + `int g_sm_parent[]`,
  with `sm_register(id, sub, parent_id)` / `sm_get(id)`. Register
  top-level flyouts (Programs/Accessories/WuBuOS/System) at init with
  `parent=-1`. This REPLACES any hardcoded `switch (submenu_id)` in the
  click/hover/render paths — a hardcoded switch caps nesting at the cases you
  wrote.
- Programs (id 0) leads with `SM_ITEM_SUBMENU` category items (each with an
  `icon_color`); preserve any MIME apps already bucketed into `g_programs` as
  leading app entries shifted under the categories (cap so they never overwrite
  the category rows).
- **XP opens a flyout on HOVER, not on click.** `startmenu_track_hover`
  must SET `g_submenu_open = item->submenu_id` when the hovered item is a
  submenu item (main item `type == 1`, or `SM_ITEM_SUBMENU` inside a flyout),
  not merely set `g_sub_hovered`. A tracker that only highlights leaves the
  whole cascade click-to-open — that is Win95 behavior, not XP: you sweep the
  mouse across Programs and the flyout appears, then across a category and its
  nested flyout cascades open. Keep the click path too (toggle), but hover is
  the primary affordance. Regression test hovers the chain and asserts
  `g_submenu_open == 0` after Programs then `>= 1` after a category.
- **Route hover through the WM path, not just the hosted input layer.** Only
  `hosted_wayland_input.c` called `startmenu_track_hover`; the WM's own
  `wm_handle_mouse` mouse-move branch (`kind == 0`) never did, so
  hover-to-open worked in one build path and silently not the other. Add
  `if (startmenu_is_open()) startmenu_track_hover(x, y);` at the
  top of that branch — and remember every new WM-input symbol needs a no-op
  stub in `apps_test.c` or the apps test fails to LINK (symptom:
  `undefined reference to 'startmenu_track_hover'` from the apps test
  only, since the WM test links the real engine).
- Clicking an `SM_ITEM_SUBMENU` item opens/toggles its nested cascade
  (`g_submenu_open = item->submenu_id`); nested items draw the XP right-pointing
  triangle affordance (`vbe_vline` fan at the row's right edge).
- Geometry (must match the renderer for click hit-tests): `MENU_X=4`,
  `sidebar_w=48`, `content_x=56`, `menu_w=200`, `submenu_w=180`, `mh=24`;
  submenu drawn at `sx = MENU_X + menu_w = 204`, `sy = menu_y + 2 + open*mh`.
- Verify the chain in the startmenu test harness (real sources linked): open →
  click Programs (`g_submenu_open==0`) → click Accessories category
  (`g_submenu_open==1`). The capture harness links the start-menu STUB and
  cascade cannot render cascades — see the capture skill.

## Derive the repo path from a variable; never retype the transposable root
The two repo roots differ by one easily-transposed letter. Retyping a
believed-correct path that is actually the wrong root loops: the patch tool
returns 'Failed to read file', the terminal returns 'No such file' or
'No rule to make target', and two identical failures in a row means you
retyped the wrong root, not that the path needs a nudge. Derive it from a
shell discovery command and pass the VARIABLE to every later call:
`OSDIR=$(for d in /home/wubu/wubu*; do [ -f "$d/mk/tests.mk" ] && echo "$d"; done | head -1)`
then `cd "$OSDIR"` / `"$OSDIR/..."`. Verify a Makefile target lives in a repo
with `grep -rl '<target>:' <candidate>/mk/tests.mk` before `cd`-ing there to
build it.

## Functional Parity: an app that draws but ignores the mouse is broken, not done
Visual parity (paint) and functional parity (input→behavior) are separate
gates. A control that renders but doesn't respond to clicks is "drawn but
dead" — the audit method:
- **Grep the launch path for `on_mouse`.** `launch_*` / `*_launch()`
  bind `on_draw`+`on_key` but omit `on_mouse` → the app is keyboard-only and
  its mouse-driven UI (keypad, tabs, tiles) is decoration. Binding `on_mouse`
  is the fix; the draw geometry already tells you the hit-regions.
- **Then check draw-coords vs input-coords alignment** (the coordinate-space
  bug below) — a bound handler that hit-tests the wrong space is still dead.

### The coordinate-space bug (breaks ALL mouse input silently)
The WM delivers **window-relative** coords to `on_mouse` (`x - w->x`,
`y - w->y` — see both call sites in `wm_input.c`). Apps that draw in
**absolute** screen space (`win->x + ...`, a stored `content_x` set from the
window origin, `screen_to_canvas` subtracting an absolute `content_x`) but
compare the window-relative input against those absolute positions miss every
click by the window offset. Tests pass because they call the handler directly
with fullscreen coords — the bug only shows in the real WM.
**Fix (one line, top of the handler):** `x += win->x; y += win->y;` so all
hit-tests and any `screen_to_*` run in one absolute space. Compute the content
rect directly, not via the draw call: `bw=border_width(); tbh=title_bar_height();
cx=win->x+bw; cy=win->y+bw+tbh; cw=win->w-2*bw; ch=win->h-tbh-bw;`
(`border_width`/`title_bar_height` are in `wm_internal.h`). Hit-test
against the draw's EXACT geometry (same cell/row metrics) and invoke the
app's existing action (e.g. `calc_do_action`, `control_set_tab`).
Affected this session: Explorer (render loop also ignored `list_scroll_y`),
Canvas (`screen_to_canvas`), plus Notepad/Calculator/Control-Panel missing
`on_mouse` entirely. Terminal's `on_mouse` is an intentional no-op (pty is
keyboard-only); Notepad-before-fix had no `on_mouse` (absent, not mis-wired).

### Adding an `on_mouse` handler — the link footprint
- Declare it in the app's public `.h`; bind it in EVERY launch path
  (`notepad_open` AND `launch_notepad`; `control_launch` is also
  reached via `launch_settings`).
- **The apps-test links STUBS, not the real engine** (`test_apps` links
  `notepad/notepad.c`, a stub). A new real-engine symbol the launch path
  references (`notepad_mouse`, `app_explorer_scroll`) goes undefined at
  link time unless you add a matching stub to BOTH `apps_test.c` and
  `apps_test_stubs.c`. Symptom: `undefined reference to '<new_fn>'`
  from the apps test only.
- **A symbol the WM input references must exist in EVERY binary that links
  `wm_input.c`.** Wiring `wm_handle_key` to call a real-engine
  function (`startmenu_handle_key`) breaks the WM test, the apps test,
  and `a11y_shot` at once — those link the start-menu STUB
  (`wm_test_stub.c` / inline in `apps_test.c`), which never had
  that symbol. Add a no-op stub wherever `startmenu_is_open` is already
  stubbed. Symptom: `undefined reference` from several unrelated targets after
  one `wm_input.c` edit.
- A widget primitive the app render calls (`draw_vscrollbar`,
  `draw_button` — both live in `wm_render.c`) needs a stand-in
  in the explorer test stub if that test doesn't link `wm_render.c`.
- **Never link the real chrome into the apps test to satisfy a new symbol.**
  `window_chrome.c` collides with the test's own inline chrome stubs
  (`multiple definition of 'chrome_draw_window'`). Add just the two
  needed functions as stubs instead; a test that stubs a subsystem cannot
  absorb that subsystem's real TU.

### Scroll must move the list, not just the thumb
A scrollbar whose render loop starts at entry 0 and ignores the scroll offset
is decoration: the thumb moves, the content doesn't. Fix the render to start
at `list_scroll_y` (clamp so the last page is reachable, write the clamp back),
AND make selection map the visible row to `list_scroll_y + row` (not `row`).
Wheel events: the Wayland layer already captures `ev.scroll` but
`hosted_input_dispatch` dropped it — forward it (`wm_scroll(delta)`,
add an `on_scroll` window hook) and implement thumb-drag + track page-jump in
the app's mouse handler with `sb_dragging`/`sb_drag_off` state.

### Title-bar buttons: hit-test BEFORE starting a drag
The chrome already ships `chrome_hit_test_button(win,mx,my)` (returns
3=close/2=max/1=min) and `chrome_handle_button_click(win,btn)` (both
declared in `wm.h`). The WM's title-bar click branch must call the
hit-test FIRST and dispatch the action on a left-press; a branch that
unconditionally sets `drag_id` makes the drawn close/min/max buttons dead
(any title-bar click just drags). Regression test clicks each button via
`wm_handle_mouse` and asserts the state change — **and recomputes the
button's screen position from the post-action geometry for the second click**:
after maximize the window fills the screen, so the old coordinates miss.

### Verify clicks drive STATE, not just "no crash"
A no-crash assertion proves the handler ran, not that it worked. For each
wired interaction assert the observable state transition the user would see:
`calc_get_display()` changes after a keypad click, `control_get_tab()`
changes after a category-tile click, window count drops after close. When such
an assertion fails, check WHICH state object the handler mutates vs the one the
test reads: `*_launch()` functions create their OWN state bound to
`win->user_data`, so read `win->user_data`, not a separately-created state.

## When a diagnostic stops yielding information, switch verification path
If a full-desktop harness (`gui_shot`) reports success but its output dir
is empty and two probe iterations (gdb register dumps, breakpoint
addresses) return nothing new, STOP iterating and verify the chrome
through `make a11y_shot` — it exercises the same `screenshot.c` writer and
persists its frames, so it confirms the visual change while the harness
startup quirk is left for later. Don't burn the turn chasing a harness
persistence bug when the unit-test gate (`make test_wm`) and the
a11y capture already prove the pixels.

## The wheel-event chain (4 links — find which one is broken)
When the mouse wheel does nothing, trace the chain end-to-end before editing;
each link was independently broken at some point:
1. **Capture** — the Wayland `pointer_axis` handler pushes a `MouseEvent` with
   `ev.scroll = wl_fixed_to_int(value)` into `input_mouse_push`.
2. **Dispatch** — `hosted_input_dispatch` polls `mev` but only forwarded
   `mev.buttons`; it ignored `mev.scroll` entirely. Forward it (normalize to
   rows, route on press-less scroll events).
3. **WM hook** — needs a `wm_scroll(delta)` that delivers to the focused
   window's `on_scroll`; add the `on_scroll` field to `DosGuiWindow`.
4. **App** — an `on_scroll` binding that adjusts the app's scroll state
   (`wubu_cmd_scroll`, `explorer_scroll`).
Grep for `input_mouse_poll` to find the dispatcher; a missing link anywhere in
the chain reads as "wheel does nothing" with no error.

## Dead duplicate implementations: consolidate before adding features
Parallel "real + stub" copies of the same app are the dominant structural
confusion. Detect with: for each app, count implementations
(`wc -l src/apps/<x>.c src/apps/<x>/<x>.c`), then `grep -c '<file>' mk/tests.mk`
to see which is linked into a SHIPPED target vs only a test. A file linked only
into its own test (or only into a stub-using test) is dead code; a file whose
draw says "Would render X here - simplified" is a stub masquerading as the
shipped app. Removing a dead stub means: delete the files, drop their tests
(they test behavior no shipped app has), drop their link-line entries in BOTH
`mk/tests.mk` AND `mk/objects.mk`, and remove leftover `.o`/`.d` artifacts — a
stale `.d` re-triggers the deleted source (`No rule to make target '<gone>.c',
needed by '<gone>.o'`). Two implementations with NO symbol overlap are separate
APIs, so the stub's tests are the only consumer — safe to remove wholesale.
Per OS_BIBLE.md "Honesty Over Inflation": don't ship a stub while a complete
implementation sits orphaned in a test-only link.

### Make it self-enforcing: `make check_dupes`
Consolidating once does not stop the bug class recurring — it returns the next
time someone adds an app. Build the detector instead of relying on an audit;
`tools/dev/find_orphan_sources.py` + a `check_dupes` target in `mk/clean.mk`
runs it in CI (exit 1 on a hit). Five traps, each of which silently produced
either a useless gate or a gate everyone learned to ignore:
- **A detector that reports clean on a planted instance of what it detects is
  not working — verify with the probe.** Plant the exact bug (`mkdir -p
  src/apps/<x>`; write a same-named `.c`), confirm the gate flags it, then
  remove it. For an untracked probe use `git add -N <file>` so a
  git-ls-files-based walk sees it. Without this check a scanner that matches
  nothing looks identical to a clean tree.
- **Count directory levels for the repo root.** For `tools/dev/x.py` the repo
  root is THREE `dirname`s up (`tools/dev` → `tools` → root); two levels lands
  in `tools/`, so `mk/vars.mk` never loads, the variable map is empty, and the
  reference set is empty — every file looks orphaned.
- **A regex that captures a source path STRIPS its extension.**
  `\$\(VAR\)/file\.c` captures `file`, but the filesystem walk yields
  `file.c`. Comparing the two directly matches NOTHING, so the scanner reports
  every file orphaned. Normalize both sides extension-less (`.c` and its `.o`
  are the same key).
- **Scan the repo's OWN makefiles only.** Walking all makefiles under the tree
  pulls vendored third-party checkouts (`vendor/`, `os-studies/`) whose
  thousands of makefiles flood the reference set with foreign paths and produce
  wild false positives. Restrict to `Makefile` + `mk/*.mk`.
- **Walk git-tracked files, not the filesystem.** `src/compiler/` may be a
  stale sibling checkout with ZERO tracked files; its stray copies
  (`src/compiler/tools/<x>.c` shadowing a real `tools/<x>.c`) read as duplicates
  of this repo's own sources. Use `git ls-files src` and scope to the
  mk-governed subtrees.
- **Make the default signal high-confidence, and keep the noisy one opt-in.** A
  raw orphan count is mostly false positives here, because the build uses
  wildcard and per-directory rules a token scanner cannot model (a naive count
  reported ~1800 "orphans"). A gate that cries wolf that often trains everyone
  to ignore it, which is worse than no gate. Default to the DUPLICATE signal —
  an unreferenced `.c` whose BASENAME is also built from a different directory,
  the exact shape of the Notepad/Editor/Terminal bug — and put the full list
  behind `--all` as review-only output that never fails.
