# Touchpad gesture input in the dosgui WM

See `src/kernel/wubu_gesture.[ch]` (engine + evdev adapter) and
`wm_gesture_dispatch()` in `src/gui/wm_input.c`.

## Shape: semantic contact reports, not raw evdev

The engine takes `(id, x, y, down, now_ms)` -- a CONTACT report, not an
evdev byte stream. That split is deliberate: the recogniser is then testable
with synthetic contact sequences (a selftest with no touchpad), and the
evdev reader stays a thin adapter that can degrade to "no touchpad".

Keep that split when extending. Do not let `struct input_event` leak into
the engine, or the recogniser becomes untestable.

## Wiring

1. `wm_gesture_poll()` is called once per frame from
   `wm_render.c` (before the lock screen -- gestures should not fire
   while locked).
2. It calls `wubu_gesture_tick()` to feed the device, then
   `wm_gesture_dispatch()` to drain the engine's pending queue.
3. The dispatch maps gestures to the SAME actions as the hotkeys:
   swipe up = Win+Tab overview, swipe left/right = virtual desktop,
   pinch in = overview.

## Weak reference is mandatory

The WM links into targets with no driver raft. `wubu_gesture_tick` must be
reached weakly:

```c
extern __attribute__((weak)) int wubu_gesture_tick(WubuGesture *out);
if (!wubu_gesture_tick) return;   /* headless target: no engine linked */
```

`wm_gesture_dispatch()` calls `wubu_gesture_poll()` directly, so the
WM test recipes must link the engine object (`$(CACHE)/wubu_gesture.o`) --
sweep every recipe that links the WM, exactly as for any other new module.

## Recogniser pitfalls (each one cost a test round)

- **The baseline and the evaluation must order the same contact pair the same
  way.** The pinch/rotate baseline was built when the second finger landed
  (pair ordered by arrival), while the lift evaluation ordered by slot index.
  For a horizontal pair those orderings are opposite, so a plain two-finger
  horizontal swipe read as a 180-degree rotation. Sort the pair by a stable key
  (slot index) in BOTH places.
- **The release report carries the final position.** Ignoring it means the
  last move position is used, and a fast flick never reaches the swipe
  threshold. Update x/y on lift before evaluating.
- **Dominance must exclude the diagonal.** A 45-degree drag has a dominant-axis
  ratio of 0.707, so a 0.70 threshold accepts it as a swipe. Use 0.80.
- **Conservative over eager.** A false gesture is worse than a missed one;
  every threshold should err toward not firing.

## Testing

`test_hw_gesture` drives the engine with synthetic sequences: tap, double tap
and its time window, four-way swipes, the diagonal rejection, pinch in/out,
rotation, the live pinch scale, and the slow-press non-tap. `test_wm`
feeds real contact sequences through `wm_gesture_dispatch()` and
asserts the WM reacts.

There is no touchpad on a VM -- `wubu_gesture_open_touchpad()` returns -1 and
the whole path is a clean no-op. That is the expected behaviour, not a bug.
