---
name: vws-form-designer
description: Use when building or extending the VWS form designer.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [vws, wet, lua, gui, designer, rad, forms, wubuos]
    related_skills: [wubuos-wet-framework, waefrebeorn-repo-creation, wubuos-lua-scripting]
---

# VWS -- Visual WuBu System

## When to use

- Adding a designer feature (palette item, property, event picker) to VWS.
- Changing the `.vws` file format or the emitter.
- Debugging a form that loads in the designer but runs differently.
- Wiring VWS into a host (a second OS, a test harness).

## What it is

WuBu's Visual Basic: a form designer and code-behind editor over the
[.WET](https://github.com/waefrebeorn/WET) applet framework.

The thing being slermed is NOT the Basic language -- it is the **loop**: drag a
control onto a form, double-click it, write the handler, run it. The code is
Lua, because Lua is already the .WET surface. Do not invent a Basic dialect.

## The file model (the important decision)

**A `.vws` file IS a `.wet` Lua script.** One representation, runnable and
editable -- VB's `.frm` model.

```lua
function Button1_Click(self)
  wet.messagebox('hi', 'Form1')
end

wet.applet {
  title = 'Form1', width = 400, height = 300,
  content = wet.canvas {
    children = {
      wet.button { id='Button1', left=24, top=40, w=100, h=28, text='OK' },
    }
  }
}
```

Because the file is Lua, **the designer's view and the running app cannot
drift**: loading runs the file through .WET and walks the built widget tree;
saving emits Lua. There is no `.vrx` to deserialise and no second format to keep
in sync. A change to the file format is a change to the emitter and the walker,
and both are covered by one round-trip test.

## Repos

`VWS` is its own WaefreBeorn repo (`main`, WaefreBeorn Umbrella License v3.0),
consumed by nothing yet. It consumes WET as a submodule at `externals/wet`
(which brings Wua). VWS needs only the tree-walking read accessors from WET --
no VBE, no render backend, so `make test` in VWS never links a kernel.

## External references -- NOT ours, do not build them

The WWW (world-space) maintainer is **learning from** two upstream projects.
They are references, not deliverables, and no WaefreBeorn repo should be
created for them:

- **REDOT** -- a fork of **Godot**. Studied for engine/ECS/scene/render ideas.
  Not a WuBu project; never `git init` it or claim it.
- **MuJoCo4** -- physics. Also studied, not built.

WWW's own GUI is built from **VWS + WUA + WET** -- that is the in-house stack.
The circularity is the point: the OS builds its GUI tools from its own GUI
framework, and those tools build the world space that hosts them.

## Architecture -- which file owns what

| File | Owns |
|---|---|
| `vws_form.c` | the document (`VwsForm` + `VwsControl`) and the designer edits: add / find / hit-test / move / resize / set text / set handler / remove / bring-front, the palette, the error sink |
| `vws_emit.c` | turning a document into Lua (including string escaping) |
| `vws_load.c` | running a file through .WET, walking the tree back into a document, and scanning handler bodies |
| `vws_lua.c` | the `vws.*` Lua face of the SAME document, plus `vws_lua_open` for sharing a host's state |
| `designer.wet` | the designer applet itself -- Lua over .WET, using `vws.*` |
| `vws_selftest.c` | the round trip and the designer edits |
| `vws_designer_test.c` | the designer applet, run for real |

## The designer is circular by construction

`designer.wet` is a `.wet` applet that drives the same `VwsForm` the loader and
emitter use. The tool that builds the GUI is built from the GUI framework -- that
is the point of the stack, so never fork a second document model for the
designer.

It builds its chrome at runtime with `wet.create` / `wet.attach` (a `.wet`
constructor outside `wet.applet{...}` returns a TABLE, not a widget -- only
`wet.create` makes a live one). The form's controls go on a `wet.canvas`
surface, so the designer previews exactly what will run.

`vws_lua_open(L, ...)` wraps an EXISTING interpreter state (does not own it), so
a host that already runs .WET gets the document model in the same state.
`vws_lua_new` creates and owns one.

## The designer document

`VwsForm` is an ordered singly-linked list of `VwsControl`. **List order IS
z-order**: the last control paints on top, and `vws_form_at` returns the LAST
match. `vws_form_bring_front` moves a control to the tail. Never sort the list;
order is the design.

A control carries: `id` (unique -- a duplicate add is rejected), `cls` (a
.WET element name), `left`/`top`/`w`/`h` (absolute, VB's model), `text`, and
`handler` (the Lua function name for its primary event, empty until set).

Position is absolute, so a form emits a `wet.canvas` with `left`/`top` and an
explicit `w`/`h` per child. **Set the explicit size** -- a canvas otherwise
sizes a child from its measured content (see `wubuos-wet-framework`).

## The round trip (the contract)

`vws_form_emit` -> Lua text -> `vws_form_load` -> `VwsForm`. The test asserts
size, control count, id, class, position, size and caption all survive.

**The `.frm` guarantee:** handler bodies are recovered from the SOURCE, not the
tree, and re-emitted verbatim. The tree only knows that a control has a handler
function, not its text -- re-emitting from the tree alone would silently delete
user code. The loader scans for top-level `function NAME(` and captures each
body to its matching `end`; the emitter writes them out unchanged.

A loaded form leaves `handler` empty: the tree does not carry the NAME, only
the function value. That is correct -- the designer sets it.

## The designer in WuBuOS

`src/apps/vws_designer.c` in WuBuOS launches the designer as a window.  It
builds the same stack the designer designs for -- a `WetApp` for the tree,
WET's Lua binding for `wet.*`, and VWS's document binding for `vws.*`, both in
ONE interpreter -- then routes draw/key/mouse into it.

Reachable from **Programs > Development > VWS Designer**, and from the first-boot
greeter's offers row (`src/gui/shell/wubu_shell_greeter.c`).  The greeter's
offers are weak references, so a build without the app registry still links.

WuBuOS carries VWS as a submodule at `src/gui/vws` (which brings WET, which
brings Wua).  The designer script is read from `src/gui/vws/designer.wet` in a
-tree build and `/usr/share/wubuos/designer.wet` when installed.

## The first-run surface

A new user boots into a working desktop with no map.  The greeter's offers row
answers "where do I start" in three clicks:

- **Getting Started** -> `src/apps/getting_started.c`, an in-shell document:
  the terminal, the in-tree HolyD compiler, a Lua `.wet` applet, the designer,
  and where the source lives.  Scrollable, reachable from Help and the greeter.
- **GUI Designer** -> VWS.
- **Terminal** -> the shell.

## Pitfalls

- **`putf()` must not use a fixed stack buffer.** It formats one piece at a
  time; a piece longer than the buffer is silently clamped and the truncated
  bytes are written, producing a script that will not parse. The fix is a
  two-pass `vsnprintf` (length, then write) straight into the destination,
  which `reserve()` already sizes for the NUL. Any emitter that formats a
  variable-length body (a handler, a control table) is exposed to this -- a
  short sample set hides it.
- **A LAYOUT template and a PROGRAM template are different claims.** The 8
  original templates emit a form with inert stubs; a PROGRAM template must
  emit something that actually WORKS. Round-tripping the script through the
  loader proves it only loads. Gate it by driving it: emit -> load as a real
  applet -> click -> read a value back. The calculator template
  (`vws_template_emit("calculator")`, then click 2 3 + 4 =) reads `27`.
- **Buttons share one handler and are told apart by `self.text`** -- the proxy
  exposes `text`/`value`/`checked`/`dock`, NOT `id`. So `wet.button { text="7",
  onclick=Key }` and `function Key(self) local k = self.text ...`.
- **A handler body is emitted inside `function <name>(self) ... end`,** so a
  helper must be a NESTED local function inside that body; there is nowhere
  else to put one in a template.

- **The emitter must escape Lua string literals.** Text goes into a
  double-quoted Lua string, so `"`, `\`, and control characters must be
  escaped. A caption containing a quote otherwise produces a file that does not
  parse, and the failure surfaces far from the emitter.
- **`vws_form_load` runs the file through .WET, so a script error is a load
  error.** Report it through the error sink; do not return a half-built form.
- **A file with no `wet.applet` still loads** -- it yields an empty form. Only a
  read failure or a script error is a load failure.
- **The z-order test must match the list rule.** After moving control B onto
  control A, the hit test returns whichever was added LAST. Write the
  assertion to the list order, not to a mental picture of the form.
- **Do not reach into `WetWidget` internals from VWS.** Use the read
  accessors; the struct is private to the WET repo.

## Gate

```bash
cd VWS && git submodule update --init --recursive && make test
```

The suite covers the document model, hit-testing and z-order, the palette, the
emitter (including escaping), the round trip, handler preservation, and the
failure paths. **A designer change is not done until `make test` is green.**
