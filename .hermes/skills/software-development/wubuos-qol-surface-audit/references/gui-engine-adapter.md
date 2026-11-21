# Wiring a real engine into the desktop (GUI adapter pattern)

Remediation for the audit's step-3 finding: a built, tested engine that the
registry cannot reach. The fix is a thin adapter TU -- never a rewrite of the
engine, and never a second copy of it.

## The pattern

One TU (e.g. `src/apps/<app>/<app>.c`) owns the engine handle and binds it to a
`DosGuiWindow`:

```c
EditorState *editor_create(void) { return (EditorState *)wubu_ed_create(); }

static void editor_win_draw(DosGuiWindow *win, uint32_t *fb, int w, int h) {
    editor_draw(win, fb, w, h, (EditorState *)win->user_data);
}

DosGuiWindow *editor_launch(void) {
    EditorState *ed = editor_create();
    if (!ed) return NULL;
    DosGuiWindow *win = wm_create(x, y, w, h, "Title");
    if (!win) { editor_destroy(ed); return NULL; }
    win->user_data = ed;
    win->on_draw   = editor_win_draw;
    win->on_key    = editor_key;
    win->on_mouse  = editor_mouse;
    engine_new_file(...);   /* start usable, not a blank surface */
    return win;
}
```

Rules:
- **Draw inside the chrome rect.** Call `chrome_draw_window(win, fb, w, h)`
  and render only within the returned `ChromeContentRect`. Anything drawn
  outside it is overdrawn by the frame on the next pass.
- **Keep the engine free of rendering types.** The engine stays a pure core
  (buffer, undo stack, find state); the adapter translates framebuffer and
  key codes into engine calls. Do not let `vbe_*` or `DosGuiWindow` leak into
  the engine header.
- **Key codes are the WM's, not ASCII.** `8` = Backspace, `127` = Delete,
  `'\r'`/`'\n'` = Enter, `28/29/30/31` = left/right/up/down, printable is
  `key >= 32 && key < 127`. Read the existing app adapter rather than guessing
  -- they all agree.
- **Modifier bits are NOT the same numbers as those key codes, and they are
  easy to swap.** The platform defines them in `src/kernel/input.h`:
  `MOD_SHIFT 0x01`, `MOD_CTRL 0x02`, `MOD_ALT 0x04`, `MOD_WIN 0x08`.
  Include that header and use the names -- never a raw hex mask. A dispatcher
  that hardcodes `mods & 0x08` for Alt (it is `MOD_WIN`) and `mods & 0x04` for
  Ctrl (it is `MOD_ALT`) compiles, passes its tests, and has every shortcut
  permanently dead, because the input layer sets `MOD_ALT`/`MOD_CTRL` from the
  real key map and never sets the bit the dispatcher is waiting for. Check
  whether each modifier bit is actually SET anywhere, not just tested.
- **Mouse is window-relative.** Subtract the chrome content origin before
  mapping a click to a line/column, and clamp the column to the line length.
- **Start in a usable state.** A newly launched app that shows an empty
  surface until the user finds the right keypress is a bad first run; create
  the initial document/tab in the launcher.

## Testing the adapter without the window struct

A test TU may deliberately forward-declare the WM API instead of including
`wm.h` (to avoid colliding with its own stubs), so it cannot read
`win->user_data`. Expose an opaque accessor from the adapter:

```c
void *editor_engine_of_window(DosGuiWindow *win);   /* returns user_data */
```

The test casts to the engine type. This keeps the window struct opaque and
still lets the gate assert the buffer a keystroke actually reached -- which is
the only proof that the adapter is wired at all.

## Optional cross-layer dependencies

When a module must call into a layer that not every consumer links (settings
→ kernel framebuffer, theme → kernel node API), use a weak reference:

```c
extern __attribute__((weak)) void vbe_set_text_scale(int);
...
if (vbe_set_text_scale) vbe_set_text_scale(ts);   /* NULL when not linked */
```

A hard reference breaks every recipe that links the caller without the callee.
Check the recipes first: `grep -n '<caller>.c' mk/tests.mk` and compare
against `grep -n '<callee>.c' mk/tests.mk`.

## Include guards

Check a header's guard is unique before writing it. Two headers sharing a
guard means any TU including both silently skips the second -- the build
succeeds with half the declarations missing, which surfaces later as
`unknown type name` in an unrelated TU:

```bash
grep -rhn '^#ifndef [A-Z_]*_H' src/ | awk '{print $2}' | sort | uniq -d
```

Any duplicate listed is a live collision.
