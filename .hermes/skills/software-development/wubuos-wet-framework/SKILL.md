---
name: wubuos-wet-framework
description: Use when building or extending the .WET applet framework.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wubuos, wet, lua, gui, framework, c11, widgets]
    related_skills: [wubuos-lua-scripting, wubuos-dosgui-wm, waefrebeorn-repo-creation, vws-form-designer]
---

# The .WET Framework

## When to use

- Adding a control, panel, event or binding to `.WET`.
- Debugging a `.wet` applet that builds but does not lay out, draw or respond.
- Wiring a new consumer (a second OS, a hosted test harness) to the framework.
- Keeping the framework repo and its WuBuOS submodule in sync.

## What it is

".WET" is WuBu's .net: a declarative applet stack. A `.wet` file is a Lua
script that builds a widget tree; the C11 framework runs a real
**measure/arrange** pass (the WPF model) and renders through the VBE, so a
`.wet` applet composites with the same Win98 shell as a C app.

The layout rule that matters: **a control never positions itself.** A panel
asks each child how big it wants to be, then hands out rects. That is what lets
one script reflow at any window size, and it is why a control's `measure()`
must derive its desired size from its own text/state -- never from its current
`rect`.

**Exception: a canvas child with an explicit size.** `wet_canvas_set_size()`
sets a `size_set` slot flag; the Lua builder reads `w`/`h` for it. Without that
flag a canvas sizes a child from its measured `desired`, which is right for a
flowing layout and wrong for a form designer that places a button at exactly
100x28. A designer MUST set the explicit size or the control's own content
metrics win.

## Repos and how they connect

`.WET` is its own repository (a WaefreBeorn umbrella repo, `main` branch,
WaefreBeorn Umbrella License v3.0). WuBuOS consumes it as a **submodule** at
`src/gui/wet` -- it is not a subdirectory of WuBuOS and must not be vendored a
second time.

```
WET repo                        WuBuOS
externals/wua  (submodule)      src/gui/wet          (submodule -> WET)
hosted/vbe_shim.c               src/kernel/vbe.c     (the real VBE)
```

- Wua is a submodule of WET, so `git submodule update --init --recursive`
  inside `src/gui/wet` is required after cloning.
- `hosted/vbe_shim.c` exists only so WET's own suites run without a kernel.
  **Never compile it into WuBuOS** -- the OS links the real `vbe.c`.
- When a framework change lands, commit in the WET repo, push, then bump the
  submodule pointer in WuBuOS and commit that separately.

### Consumers

| Consumer | Where | What it needs |
|---|---|---|
| WuBuOS | `src/gui/wet`, launcher `src/apps/wet_applet.c` | the whole framework + the real `vbe.c` |
| VWS | `externals/wet` | the tree-walking read accessors only; no VBE, no render backend |

A consumer that walks the tree (a designer, a test harness) uses the read
accessors, never `wet_internal.h`: `wet_app_root_get`, `wet_app_width` /
`wet_app_height`, `wet_widget_child` / `nchildren`, `wet_widget_rect`,
`wet_widget_class_name`, and the per-class `*_text` / `*_checked` /
`*_value` getters. Reaching into `WetWidget` internals from another repo breaks
silently the moment the struct changes.

The VWS row is a real consumer with its own workflow -- see the
`vws-form-designer` skill before touching it.

## Build and gate

In the WET repo:

```bash
git submodule update --init --recursive
make test          # builds and runs both suites
```

Two suites, both must pass:

- `test_wet` -- framework only, no interpreter: geometry, the four panels,
  input routing, render calls, lifecycle.
- `test_wet_lua` -- script-driven build, proxies, handlers, error isolation.

In WuBuOS the framework is built by `mk/tests.mk` (`WET`/`WET_SRCS`) and gated
by `make -k -j24 test` -> RC=0, 0 errors, 0 segfaults. The recipes carry an
explicit source list; when a file is added to the framework, add it to
`WET_SRCS` there too.

**A framework change is not done until both suites pass in the WET repo AND
the WuBuOS gate is green.** The submodule pointer is the last step, not the
first.

## Architecture -- which file owns what

| File | Owns |
|---|---|
| `wet.h` / `wet_internal.h` / `wet_lua.h` | the three public faces; internals are not includable outside the repo |
| `wet_widget.c` | the widget tree, class registry, text metrics, the theme |
| `wet_layout.c` | the panels: `stack`, `dock`, `canvas`, `grid` |
| `wet_render.c` | clipped drawing primitives -- no backend knowledge |
| `wet_backend_vbe.c` | the ONLY file that knows the VBE |
| `wet_controls.c` | the leaf controls and their typed accessors |
| `wet_input.c` | hit-testing, focus, routed events |
| `wet_lua.c` | the Lua binding: constructors, builder, proxies, handlers |
| `wet_app.c` | the application: layout pass, render pass, error sink |

> `wubu_lua_compat.c` (a weak `wb_lv_register_coro` shim) was **deleted** once
> Wua's `wb_lv_coro.c` built on non-Windows hosts. Do not reintroduce it.

Two seams are deliberate and must stay:

- **`wet_render.c` never includes a kernel header.** A backend supplies the
  `WetRender` function table; the framework only clips and calls through it.
- **The Lua binding is optional at link time.** `WetApp` carries a
  `lua_dispatch` function pointer plus a `lua_ctx`; when both are NULL the
  framework is pure C. Do not add a hard Lua dependency to the framework core.

## Adding a control

1. Add the payload struct to `wet_internal.h` and the class id to `wet.h`.
2. Add the typed accessors to `wet.h` + `wet_controls.c`, each type-checked
   against `w->cls->id` and returning a safe default otherwise.
3. Add the class to `wet_controls_register()` with all six ops. A leaf control
   has a no-op `arrange` and does its own drawing in `render`.
4. `measure()` derives the desired size from the control's own state. Add a
   check to `wet_selftest.c` that reads the desired size -- not the final rect.
5. If it is interactive, give it an `input` op and add a click/key check.
6. Expose its properties in `wet_lua.c`: a row in the builder's property list,
   a branch in `proxy_index_fn` / `proxy_newindex_fn`, and a name in the
   `class_from_name` table.

## The WuBuOS launcher

`src/apps/wet_applet.c` is the seam that puts a `.wet` applet in a
`DosGuiWindow`; the registry entry is `launch_wet()` in
`src/apps/apps.c`. It routes only:

- **draw** -- chrome first, then `wet_app_set_origin` to the content rect and
  `wet_app_resize` + `wet_app_render`. The applet's coordinate space IS its
  content rect, so a script never learns whether it is fullscreen or in a panel.
- **key** -- WuBuOS sends `8` for backspace; the framework wants `'\b'`. Translate.
- **mouse** -- WuBuOS `kind` is `0=move, 1=down, 2=up`; map to MOUSE{MOVE,DOWN,UP}.
- **resize** -- the next draw reflows from the content rect, so the callback is
  deliberately empty.

`launch_wet()` opens the built-in demo (no path), so the menu item works
before any script exists. `wet_applet_open(path, ...)` loads a real file.

## Pitfalls

- **`wb_lv_new()` already calls `wb_lv_openlibs()`.** Calling it again
  re-initialises the state and empties the intern table; the first script then
  dies with SIGFPE in `wb_lv_intern` (`nbuckets == 0`).
- **`wb_lv_pcall` leaves `nout == 0` on error** and stashes the message in the
  global `__lv_last_error`. Read it there -- `out[0]` is unset. Wua now fills
  it correctly (was empty); the handler-error check asserts the text.
- **`wb_lv_call_multi(L, fn, args, nargs, &out)` returns the COUNT and sets
  `*out` to the result array** (fixed as of Wua `bf39a26`). Prefer it over
  `wb_lv_pcall` when a handler returns values.
- **Coroutines build on non-Windows** (Wua `bf39a26`). Link the real
  `wb_lv_coro.c`; the old weak `wb_lv_register_coro` shim is gone and must not
  be reintroduced.
- **`wet_lua_dispatch` takes `const void *ev`**, not `const WetEvent *` --
  `WetEvent` lives in `wet_internal.h`, so naming it in `wet_lua.h` breaks every
  includer.

- **Intern every key you look up in a script table.** The interpreter hashes by
  string identity. A host-side lookup with a plain `wb_lv_str("text")` returns
  nil even though the script's own `"text"` is right there. See
  `wubuos-lua-scripting` for the full embedding rules.
- **`wet.find` returns a proxy table, and the app stores the PUBLIC handle.**
  `app->lua_ctx` must hold the `WetLua*`, not the internal ctx -- the dispatch
  hook and `wet_lua_run` both take the public handle. Storing the internal one
  makes the dispatcher read a Lua state as if it were a handle, and the crash
  looks like heap corruption.
- **Children are an explicit `children = { ... }` array.** Numeric keys
  (`wet.stack { child, child }`) also work; Wua fixed the table-constructor
  bug that used to drop the array part when a keyed field came first, so both
  forms are reliable now. `children` still wins if both are present.
- **Handler keys are `on` + the event name**: `onclick`, `onchange`,
  `ontextchanged`. Matching the bare event name (`click`) silently registers
  nothing.
- **A panel's fill child is the one with `dock == WET_DOCK_FILL` OR
  `WET_DOCK_NONE`.** Treating `NONE` as "not docked" leaves the last child
  with a zero rect.
- **A real click is press then release.** `wet_app_pointer` synthesises the
  `CLICK` from a `MOUSEUP` over the widget that took the `MOUSEDOWN`; a test
  that sends only `MOUSEDOWN` will never reach a control's click handler.
- **Stack spacing 0 means no gap.** Do not treat 0 as "unset" and fall back to
  the default -- that inserts phantom pixels between every child.
- **Report a raising handler through the app's error sink, never let it
  propagate.** A script error must not take the shell down.
- **A function defined in a `.c` but missing from the `.h` is implicitly
  declared `int` at every call site.** A pointer return comes back truncated to
  32 bits and sign-extended -- `0xffffffffa393c8e0` -- and the crash surfaces in
  the callee as a wild pointer, nowhere near the missing prototype. When a
  pointer looks like `0xffffffff...` or a bare low value, grep the headers for
  the declaration before suspecting the heap or a struct-layout mismatch.
  **The usual cause is a missing feature-test macro, not a missing prototype.**
  `strdup`/`opendir`/`readdir` are POSIX, not C11: a link whose recipe does not
  define `_POSIX_C_SOURCE` gets them implicitly declared and `strdup`'s pointer
  comes back truncated to 32 bits -- a garbage heap address that segfaults in
  the first `strcmp`. A file that uses them must `#define _POSIX_C_SOURCE
  200809L` itself, before any include; do not rely on the caller's command line
  (one test recipe had it, another did not, so the bug was invisible until the
  second link).
- **`wb_lv_table_set` stores the string POINTER, not the bytes.** Setting a
  global to a stack buffer with `wb_lv_set_global(L, "__wet_err", wb_lv_str(buf))`
  leaves it pointing at a dead frame -- the reader sees an EMPTY message, which
  looks like the error path never ran. Intern first:
  `wb_lv_str(wb_lv_intern(L, buf, strlen(buf)))`. String literals are static and
  safe; any `snprintf`'d buffer is not. This bit `wet_create`'s unknown-class
  error too (it reported empty).
- **`wet_lua_run` CONSUMES `__wet_err`.** After the chunk runs it reads the
  global and, if it is a string, clears it and returns it as the run error. So
  a script can read `__wet_err` itself AND the caller gets it as the return
  value -- but a test asserting `err == NULL` after a handled error will fail,
  and so will one expecting `__wet_err` to survive the run.
- **`wet_theme_set(NULL)` resets to the default; an unnamed hand-built theme
  reports "custom".** The theme is GLOBAL state, so a test that switches it
  must restore it or every later test in the process sees the wrong palette.

## Templates, themes and effects (2026-11-10)

- **VWS is the studio; every program is created from a template.** The
  template library lives in `src/gui/vws/vws_templates.{c,h}` as DATA (one
  control table + one handler-stub table + one generic emitter), and it is
  PURE C11 over stdlib -- no Lua, no WET. That is what lets W-CODE link the
  same file and emit byte-identical text to the designer: one owner, no second
  copy. The `vws` CLI (`--list`/`--template`/`--new`) links only that file; the
  IDE shells out to it rather than linking VWS.
- **`vws_form_set_handler` must be matched by the emitter.** A handler name
  stored by the designer but never written to the `.wet` output is silently
  dropped on every save -- the designer's wiring does nothing. The emitter
  writes `onclick=<name>`.
- **A `WetTheme` is a palette; `wet.theme(name)` / `wet.themes()` reach it from
  Lua.** Named themes: light, win98, xp, wubu, dark.
- **Surface effects are NOT a WET concern -- but an applet can effect its own.**
  WET renders through the narrow `vbe_interface.h` and has no framebuffer, so a
  post-process pass belongs outside the framework. The engine is
  `src/runtime/wubu_effect.{c,h}` (pure C11, no GUI includes) and the GPU leg is
  `src/hosted/wubu_vk_effect.{c,h}`. The desktop applies the `/n/effect` stack
  to the compositor's double buffer; a `.wet` applet applies its OWN stack to
  its own surface (see below). Never inside `gui_dbuf_flip` -- a pass is not
  idempotent and a flip can run more than once per frame.
- **`wet.effect(name [, strength [, colour]])` -- the script's own call.**
  Registered by the applet host (`src/apps/wet_applet.c`) into the framework's
  `wet` table through `wet_lua_state()`, so the WET submodule needs NO change
  and no pointer bump: WuBuOS adds a host capability to the state it owns.
  Follow the `wubu_tutorial.c` pattern -- `wb_lv_get_global(L, "wet")`, then
  `wb_lv_table_set` with an INTERNED key. An unknown pass name is refused
  (false + `__wet_err`), never silently ignored.
- **An applet's surface is a copy, because the VBE has no retargetable fb.**
  `wet_applet_draw` copies the content rect into an applet-owned buffer, applies
  the stack, and blits back. Two copies, no framework change. With no effects
  requested the pass is skipped entirely, so a NULL fb in a test harness still
  works.
- **A program is a FILE: the desktop discovers `.wet` applets.** `app_scan_wet_dir`
  registers every `.wet` in the applet dir (`$WUBU_APPLET_DIR`, else
  `$HOME/.wubu/applets`) as a desktop program at boot -- no C change, no
  rebuild.  `DosGuiAppDef.path` (a new trailing field) makes a discovered
  applet launch through `launch_wet_applet(path)` instead of a C launcher;
  the path rides in a file-static because `launch` takes no arguments.  The
  scan is idempotent per path, so a per-boot rescan does not duplicate.  This
  is the closure of the template loop: VWS creates the file, W-CODE edits it,
  the registry discovers it.
- **One owner for discovery: `src/apps/apps_wet.c`.** The scan, the directory,
  the accessors and the lookups over the discovered set live there, NOT in
  `apps.c` (which owns `g_app_defs`, the launchers, and the terminal/notepad
  code). The split is what lets the START MENU ask "what applets exist?"
  without linking the whole compiled-in registry and launcher set -- two
  program sources was the bug it fixed. `app_find` / `app_find_by_name`
  DELEGATE to `app_find_wet` / `app_find_wet_by_name`; do not inline a second
  walk over the array.
- **The start menu resolves by NAME, not by path.** It builds its submenus
  from MIME `.desktop` entries, so a discovered applet is appended by name and
  `launch_app(name)` resolves it through the registry -- there is no second
  launch path. The accessor is declared weak in `startmenu_db.c` and TESTED
  before use, so a GUI-only link with no applet runtime still builds.

## References

- `references/element-reference.md` -- the elements, their properties, the
  events and the proxy fields, as a lookup table.
