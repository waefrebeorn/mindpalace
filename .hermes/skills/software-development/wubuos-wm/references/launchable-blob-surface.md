# Glue for a WM-owned surface of launchable blobs

Use when a runtime module already owns the geometry or physics of a surface and
the WM must make it reachable: blobs on a window rim, blobs on a screen edge,
tiles on a dock. Two instances of this shape exist (`wm_rim` wraps the focused
window's frame, `wm_slime` wraps the screen). A third should copy the shape.

## Shape

One module under `src/gui/shell/` (`wm_<surface>.{h,c}`):

- `static Wubu<Thing> g_<thing>;` plus a **parallel meta array** for the
  per-item data the runtime module does not own (face colour, launch command):
  `static struct { uint32_t color; char exec[160]; } g_meta[CAP];`
  Index it with the SAME index the runtime module returned from its `add()`.
- `wm_<s>_init(screen_w, screen_h)` / `wm_<s>_shutdown()` -- call from
  `wm_init` / `wm_shutdown`.
- `wm_<s>_add(...)` -- call the runtime module's `add()`, then fill `g_meta[i]`.
- `wm_<s>_tick()` -- step the physics; call from `wm_render` beside the other
  per-frame ticks.
- `wm_<s>_render(fb,w,h)` -- draw; call from `wm_render` at the right layer.
- `wm_<s>_handle_pointer(x,y,btn,kind)` -> bool; call from `wm_handle_mouse`
  BEFORE window and taskbar handling so the surface wins the pointer.
- `wm_<s>_count()` + `wm_<s>_island_pos(i,&x,&y,&r)` -- an inspection pair so a
  test can assert geometry without reaching into module-static state.

## The real caller

A surface with only a public API is still unreachable. Cheapest real caller:
mirror an existing persisted model into it. For a launcher surface that is the
taskbar pins:

```c
int n = wubu_taskbar_count();
for (int i = 0; i < n; i++) {
    const WubuTask *t = wubu_taskbar_get(i);
    if (!t->pinned) continue;
    float slot = (float)(shown + 1) / (float)(n + 1);   /* spread, not piled */
    wm_<s>_add(edge_or_t, slot, 9.0f, colour, t->exec[0] ? t->exec : t->title);
    shown++;
}
```

Call it from `wm_init` immediately after `wubu_taskbar_init()`. With no pins
the surface stays empty and the default desktop renders byte-identical.

## Click vs drag

Track the down position; a press-release that moved more than a few pixels is a
drag and must NOT fire the launch:

```c
int dx = x - g_down_x, dy = y - g_down_y;
if (dx*dx + dy*dy > SLOP*SLOP) return true;   /* consumed, but not a click */
```

## Launch through the weak path

```c
__attribute__((weak)) void launch_app(const char *name);
...
if (g_meta[i].exec[0] && launch_app) launch_app(g_meta[i].exec);
```

A test or minimal build does not link `src/apps`, so a hard reference breaks
every WM recipe.

## clear() must re-initialise

Freeing the backing module without re-initialising it leaves capacity 0: every
later `add()` returns -1 and the surface silently refuses input. Free then
init, or keep the allocation and reset the count.
