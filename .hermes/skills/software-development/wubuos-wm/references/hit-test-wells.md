# Hit-test wells: the renderer publishes, the input consumes

Lesson proven three times in one session (2026-11-19, wubuos batches 4-5):
every WM hit-test bug found was the SAME class — the input path re-derived
geometry that the renderer already computed, and the two disagreed.

## The bugs

1. Modern tray: taskbar_modern_handle swallowed every click inside the
   floating island without testing tray icons at all — icons drawn, dead.
2. Classic tray: input walked right-to-left from screen_w-10-clock_w-10
   while the renderer drew from clock_x - EDGE_PAD — a SIZE+GAP offset.
3. Classic pager: input guessed desk_x = screen_w-150 while the renderer
   drew at tray_x - PAGER_RESERVE — offset by the whole clock+tray reserve.

## The rule

The renderer PUBLISHES its layout wells into g_dwm (clock_well_*,
tray_well_*); the input path hit-tests THOSE, never a parallel formula.
One hit-test owner per surface (e.g. systray_icon_at in wm_systray.c)
called by every input path (classic walk AND taskbar_modern_handle).
Visible-icon compaction must match: both eras skip invisible icons
without consuming pitch, so slot i = i-th VISIBLE icon, not array index i.

## The gate pattern

Render, then fire a real wm_handle_mouse press at the published well's
icon centre and assert the callback ran — in BOTH themes. Absolute pixel
colour assertions are fragile (wallpaper, screensaver); callback counters
and well arithmetic are not. Disable the screensaver around render tests.
See test_tray_hit_test / test_pager_hit_test in src/gui/wm_test.c.

## Audit markers vocabulary (tools/std_audit.py)

brand-art, icon-identity, glyph-art (deliberate art constants),
percent-math (ratio math, not layout), btn-id (hit-test return codes),
format-mask (printf colour masks like & 0xFFFFFF). R11 catches both
0xRRGGBB and 0x00RRGGBB / 0xFFRRGGBB forms. Ratchet identity: long/fat
key by FILE (line-count drift is not growth), hits by file:value.
