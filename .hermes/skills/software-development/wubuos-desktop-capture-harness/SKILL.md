---
name: wubuos-desktop-capture-harness
description: "Verify desktop_shot without measuring a stub."
version: 1.0.0
author: WaefreBeorn
license: MIT
metadata:
  hermes:
    tags: [wubuos, gui, desktop, capture, verification, a11y]
    related_skills: [wubuos-win32k-backbone, wubuos-test-suite, wubuos-architecture]
---

## When to Use
- You are about to trust a `desktop_shot` / `a11y_shot` frame or its console prints.
- A GUI interaction "doesn't show up" in a captured frame.
- You are extending the capture harness or adding a new frame.
- A shot harness builds but appears to no-op.

# WuBuOS desktop capture harnesses (desktop_shot, a11y_shot)

The human-felt desktop is measured by PPM frame capture, not by unit tests. Two
harnesses live at the repo root: `wubu_desktop_shot.c` (26 frames: a11y cluster,
window move/minimize/restore/rotate/resize/close, lasso, balloon, clock popup,
start menu, companion toggle, cursor easing, typer) and `wubu_a11y_shot.c`.

Targets: `make desktop_shot`, `make a11y_shot` (recipes in `mk/tests.mk`). Frames
land in `/tmp/wubu_desktop_shots/*.ppm`. Convert with PIL (`Image.open(ppmp).save(png)`)
and view; diff two frames pixel-wise to prove a UI element appeared.

## PITFALL 1 — a shot harness can silently measure a STUB (cost real time)
`desktop_shot` linked `wm_test_stub.c`, whose STRONG `startmenu_*`
definitions won the link. The Start button toggled a dead `tsm_open`; the captured
"menu open" frame was empty while the harness reported success. The stub's own
comment claimed sibling binaries link the real TU too — false: the recipe omitted
`startmenu.c`.

**Rule: when a capture harness shows a no-op, verify WHICH definition binds.**
- `nm -C <bin> | grep <symbol>` shows the address; `gdb -ex 'break <sym>' -ex run -ex 'bt 3'`
  shows the file:line that actually executes.
- Fix: make stub definitions `__attribute__((weak))` (the stub file already uses this
  for `wubu_bonzi_*`) so the real module wins wherever it is linked, and add the real
  sources to the recipe.
- A harness must also INITIALISE what it measures: `desktop_shot` never called
  `startmenu_init()`, so `g_main_count==0` and the open menu was a 4px sliver.

## PITFALL 2 — duplicated layout constants drift
`desktop_shot.c` hardcoded `a_center`/`b_center` offsets that drifted from the
product's `orb_a_center`/`orb_b_center` in `wubu_a11y.c`. The stale "red B" offset
landed on the green A orb (r=31) -> click-A = MAXIMIZE, so frame 7 maximized the
window instead of closing it; the maximized window then covered the desktop and broke
the later lasso (0/3) and typer tests.

**Rule: never hardcode a second copy of product geometry. Expose an accessor.**
`wubu_a11y_orb_centers(win, &gx,&gy, &bx,&by, &yx,&yy, &pl_x,&pl_y, &pr_x,&pr_y)` returns
the real on-screen centers (NULL = don't need). Harnesses call it.

## PITFALL 3 — input priority: taskbar outranks window a11y orbs
A maximized window's a11y rotate orb sits at the bottom-right corner and overlapped
the taskbar clock well (999,754). The a11y check ran BEFORE the taskbar block, so the
clock popup could never open. In `wm_handle_mouse` the order must be:
startmenu -> clock-popup-outside-close -> **taskbar** -> a11y -> bonzi -> windows.
The taskbar is the topmost strip; it keeps priority.

## PITFALL 4 — text truncation must reserve the ellipsis
Icon labels: the loop cut the name to `max_label_w` then appended `"..."`, pushing
the label back past the slot, so adjacent selection plates merged into one
unreadable bar. Reserve `vbe_text_width("...",1)` BEFORE truncating.
Icon grid spacing is `DOSGUI_ICON_SIZE + DOSGUI_ICON_GAP` = 40px, so
`max_label_w = DOSGUI_ICON_SIZE + 4` = 36px is correctly sized.

## PITFALL 5 — declare what you link
`test_era_apps` linked ~20 objects (OCI, styxfs, archd, kvfs, wasm ISA, tgemm_avx512)
without declaring them as prerequisites; it only built because they existed on disk.
A `find src -name '*.o' -delete` clean broke it. Every object on a link line must be a
target prerequisite.

## Recipe discipline
Per-.c compile + a separate run line; commands start with a real TAB (verify `cat -A`,
`^I`). Prefer splicing whole regions over patching recipe lines. `desktop_shot` needs
`-DVBE_HOSTED` (else vbe.c runs kernel-mode and segfaults on NULL buffers).

## PITFALL 6 — driving the LIVE compositor: never guess coordinates
When you point xdotool at the running session instead of capturing a harness frame,
two things go wrong repeatedly:

- **Hit-tests are gated by state.** The modern taskbar's click handler returns
  immediately unless the theme is DARK, and the bar is CENTRED (`bar_x = (fb_w -
  bar_w)/2`, Start at `bar_x + MODERN_PAD`), NOT left-aligned. Clicking where the
  classic shell puts Start lands on a desktop icon instead and opens some unrelated
  app — which reads exactly like "the menu is broken". Read the layout function
  (`taskbar_modern_layout`) and compute the rect; do not assume a corner.
- **`xdotool ... --window <wid>` mis-targets** and drops events when the surface
  has not been mapped/focused. Prefer absolute display coordinates after an explicit
  `mousemove` + settle delay.

## PITFALL 7 — do not trust a vision read of a CROPPED screenshot
A cropped image's own boundary is easy to mistake for clipping. One measurement
reported the mascot as "clipped by the screen edge"; a numeric scan of the full
frame showed 11 px of margin on the right and 40 px above the bottom. **Compute the
bounding box from pixels** (scan the region for the object's colour range, print
min/max x/y) before believing or denying a clipping claim. Same discipline for any
"is it fully visible / is anything overlapping" question: numbers, not impressions.

**When automation cannot get the shot, say so.** Fall back to the behaviour gate
(the unit target that drives the real code path), report exactly which half is
unverified, and do not narrate the feature as visually confirmed. Repeated failed
attempts cost more than an honest limit.

## Re-measure after any GUI change
`make desktop_shot` then inspect the frames + the harness's own prints
(`[lasso] icons selected: N/3`, `[clock] menu open after click: N`, `[typer] ... busy=`).
These prints are the behaviour gates; the PPMs are the evidence.
