---
name: wubuos-lua-scripting
description: Use when embedding slerm-Lua as a WuBuOS GUI layer.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wubuos, lua, slerm-lua, gui, scripting, c11]
    related_skills: [wubuos-wet-framework, wubuos-dosgui-wm, wubuos-architecture, waefrebeorn-repo-creation]
---

# Embedding slerm-Lua in WuBuOS

## When to use

- Adding a Lua-driven GUI surface, tool or game script to WuBuOS.
- Wiring a C11 host that exposes WuBuOS primitives to Lua.
- Debugging a script that loads but its calls do nothing.
- Replacing an SDL/third-party GUI path with Lua (the standing direction:
  the GUI layer is Lua, the substrate is C11).

## The boundary -- decide it before writing any code

| Lua owns | C11 owns |
|---|---|
| layout, labels, reactive behaviour, iteration | the framebuffer, input routing, the filesystem, memory |

A script must never reach a driver handle, a raw framebuffer pointer or a
kernel structure. It calls `gui.*` / `fs.*` and the host does the work. Keep
the binding table SMALL and batched: one call per primitive, not one call per
pixel. A hot path moves into C and is re-exposed as a single function.

## Where the interpreter lives

slerm-Lua was rewritten to the full Lua 5.4 surface and moved to its own
repository, **Wua**. WWW pulls it in as a NESTED submodule, so the sources
sit one level deeper than you would guess:

```
src/lua/www/~WuBu~/src/lv/src/wb_lv.h          public API
src/lua/www/~WuBu~/src/lv/src/wb_lv_arena.c    allocator
src/lua/www/~WuBu~/src/lv/src/wb_lv_eval.c     evaluator + tables + globals
src/lua/www/~WuBu~/src/lv/src/wb_lv_host.c     state, register_global, call, builtins, openlibs
src/lua/www/~WuBu~/src/lv/src/wb_lv_lex.c      lexer
src/lua/www/~WuBu~/src/lv/src/wb_lv_parse.c    parser
src/lua/www/~WuBu~/src/lv/src/wb_lv_stdlib.c   base + table + math + os + io registration
src/lua/www/~WuBu~/src/lv/src/wb_lv_string.c   string library + Lua-pattern matcher
src/lua/www/~WuBu~/src/lv/src/wb_lv_value.c    values, interning, equality
```

Both WWW and Wua are separate repos with their own owners. **Do not edit the
interpreter from a WuBuOS session** -- consume it, and report gaps upstream.
Declare a missing prototype locally rather than patching the submodule.

**Nested submodule: init recursively.** `git submodule update --init` at the
top level does NOT populate `~WuBu~/src/lv`; run `--init --recursive`, and
after any `git submodule update --remote` on `src/lua/www`.

**WWW declares Wua over SSH** (`git@github.com:waefrebeorn/Wua.git`). On a box
without SSH keys the recursive init fails with "Could not read from remote
repository". Either add a host rewrite once --
`git config --global url."https://github.com/".insteadOf "git@github.com:"` --
or set the submodule URL to HTTPS locally before recursing.

## Wiring a host module

1. **One state per surface.** `wb_lv_new()` per window/app; `wb_lv_free()` on
   destroy. Never share a state across surfaces.
2. **Register a table, not flat names.** Build `wb_lv_table_new()`, fill it
   with `wb_lv_table_set()`, then `wb_lv_set_global(L, "gui", table_value(t))`.
   A flat `wb_lv_register_global(L, "gui.text", ...)` creates a global whose
   NAME contains a dot -- `gui.text` reads as nil.
3. **Intern every table key.** `wb_lv_str(wb_lv_intern(L, "text", 4))`. The
   interpreter hashes by string identity; an uninterned literal never matches
   the script's own `"text"`. This is the single most common reason a binding
   is silently nil.
4. **Call the script's hooks by global name**: `wb_lv_get_global(L, "draw")`
   then `wb_lv_call(L, fn, args, nargs)`. Check `fn.t` is
   `WB_LV_FUNCTION`/`WB_LV_CFUNCTION` before calling.
5. **Build**: add the host `.c` to `GUI_OBJS` in `mk/objects.mk`, and give the
   test recipe an explicit source list (the slerm-Lua `.c` files plus
   `$(KERNEL)/vbe.c` if the host draws). Define the interpreter dir once:
   `LUAWWW := $(LUA)/www/~WuBu~/src/lv/src` in `mk/tests.mk` -- note the
   trailing `src`. Link ALL of the interpreter's `.c` files: `wb_lv_openlibs`
   lives in `wb_lv_host.c` and calls registration functions defined in
   `wb_lv_stdlib.c` / `wb_lv_string.c`, so omitting those two is a link error.
6. **Gate**: add the test target to the right tier in `mk/tests.mk`.

## When the interpreter does not build on this host

A submodule may not compile on every platform. Supply the missing symbol with
a **weak** definition in ONE file, and name the upstream fix in a comment:

```c
__attribute__((weak)) void wb_lv_register_coro(wb_lv *L) { /* ... */ }
```

The strong definition wins the moment upstream builds, so the shim needs no
removal. Give it its own file -- one owner -- and link that file into every
host that opens the libraries. Do not copy the shim per host; two copies drift.

## Pitfalls

- **Table keys must be interned.** See step 3. Symptom: the table HAS the
  field (`wb_lv_table_get` returns the right type) but `gui.text` in a script
  is nil.
- **Register a table, not a dotted global.** See step 2.
- **`wb_lv_tonumber` / `wb_lv_tostring` take the value BY VALUE**, not a
  pointer: `wb_lv_tonumber(*v, &ok)`. Passing `v` is a compile error that
  looks like an API mismatch. `wb_lv_equal` now takes the state as its first
  argument: `wb_lv_equal(L, a, b)`.
- **`wb_lv_new()` already opens EVERY library.** It is `wb_lv_alloc()` (bare
  state, nothing registered) followed by `wb_lv_openlibs(L)`. Calling
  `wb_lv_openlibs()` again on the same state re-initialises it. Reach for
  `wb_lv_alloc()` when you want to register libraries yourself, not for a
  "faster" `wb_lv_new()`.
- **`wb_lv_get_global` takes a FLAT name, not a path.** `"wet.clicks"` is a
  global literally named `wet.clicks`, which does not exist -- it reads as nil.
  To read a field, get the table then index it:
  `wb_lv_get_global(L, "wet")` -> `wb_lv_table_get(L, t, k(L, "clicks"))`.
  This is the most common way a host-side test reports a false nil.
- **`wb_lv_pcall` leaves `nout` at 0 on error and does NOT fill `out[]`.** The
  message is stashed in the global `__lv_last_error`. Reading `out[0]` after a
  failed call reads uninitialised memory.
- **`wb_lv_setmetatable` takes a table POINTER**, not a value:
  `wb_lv_setmetatable(L, t, meta)`.
- **A table literal with a hash key BEFORE its array items loses the array
  part.** `{spacing=6, 'a','b','c'}` has length 0 and `[1] == nil`, while
  `{'a','b','c', spacing=6}` is correct. Any embeddable description format must
  use an explicit array field (`children = { ... }`) rather than relying on
  numeric keys.
- **Check `references/slerm-lua-subset.md` before concluding a host bug.** It
  carries the current upstream gap list with workarounds, and the list changes
  as Wua is fixed -- read it rather than assuming a behaviour from memory.
- **`wb_lv_register_builtins` IS declared in `wb_lv.h` now.** Older hosts may
  carry a local `extern` for it; that is harmless but no longer needed.
- **The surface is full Lua 5.4** -- integers and floats, the complete
  operator set (`# ^ // & | ~ << >> ..`), multiple returns, varargs,
  metamethods, `do`/`end`, `break`, `repeat`/`until`, `goto`, `elseif`,
  method definitions, `pcall`/`xpcall` with line numbers in error messages,
  hex literals, string escapes, long strings/comments, and the standard
  libraries. A construct outside it is a parse error, not a runtime error --
  check the script, not the host, when a binding "does nothing". Full detail
  in `references/slerm-lua-subset.md`.
- **A script that only draws is not a feature.** Gate the input path too -- a
  surface whose callbacks are never invoked passes a render-only test.

## Gate

`make -k -j24 test` -> RC=0, 0 errors, 0 segfaults; `make -j24` clean;
`make desktop_shot` still writes its frames. Run the Lua host's own test
binary directly as well -- it reports its own pass/fail line.
