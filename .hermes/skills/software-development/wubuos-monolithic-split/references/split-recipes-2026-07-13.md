# Split Recipes & Pitfalls — 2026-07-13 session

Condensed from a live monolith-busting session (container handler registry +
`hosted_wayland.c`, 844 lines). Companion to SKILL.md; the pitfalls below are the
ones the general workflow does NOT call out explicitly.

## Pitfall A — global definitions dropped by function-only extraction

Brace-aware extraction grabs *functions* but silently drops strong **global
definitions** that lived in the monolith body (file-scope `type var;` lines that
are NOT inside a function). Example: original `hosted_wayland.c` had
`wayland_state_t g_wl;` at file scope. The extractor only pulled functions, so
`g_wl` vanished → `undefined reference to 'g_wl'` at the final `make hosted` link
(even though every module `-fsyntax-only`'d clean, because each saw it as `extern`
from the header).

**Fix:** choose ONE owning module (the facade is safest — it is always linked into
the hosted binary) to hold each strong definition. Siblings reference it via
`extern` in the internal header. After extraction, grep the original file for
file-scope defs that are neither static functions nor typedef/struct, and make sure
each now has exactly one strong definition somewhere.

## Pitfall B — public entry points not in the extraction list

The extraction list enumerated connect/dispatch/disconnect but NOT
`hosted_wl_frame_render` (declared in the public `hosted_internal.h` and called by
`hosted.c`'s render loop). It compiled fine in isolation yet linked as
`undefined reference to 'hosted_wl_frame_render'`.

**Fix:** before extracting, grep the public header for the module's declared API and
tick off every symbol: either extract its body, or re-point the facade to call a
sub-module hook that now owns it. Here `hosted_wl_frame_render` was moved into the
SHM module (it blits into the SHM buffer) and the facade's `hosted_wl_*` entry
points were re-pointed to call `wl_shm_init/term`, `wl_input_init/term`,
`wl_surface_init/term`.

## Pitfall C — cross-module coupling needs an `extern` in the internal header

When the split puts a global/function referenced by TWO sub-modules into only one
of them, the other fails to compile:
- `touch_listener` (const, referenced by `seat_capabilities` in the input module)
  → declare `extern const struct wl_touch_listener touch_listener;` in
  `hosted_internal.h`; make its definition **non-static** in its owning module.
- `shm_buffer_create/destroy` + `g_shm_bufs`/`g_cur_buf` (owned by SHM module, used
  by the surface `xdg_toplevel_configure` resize path) → declare `extern` in the
  header; drop `static` from the SHM definitions.

Symptom pattern: `undeclared (first use in this function)` for a symbol that looks
"local" but is actually defined in a sibling module.

## Pitfall D — making a heavy external dependency optional (angel-coder)

`wubu_container_init` hard-required `fork()`+`execl("bun run src/main.ts …")` even
for the in-memory **handler registry** test, so the test `assert(rc==0)` died with
`SIGABRT` whenever `bun` was absent. Root cause class: pure in-memory logic gated
behind a heavy external subprocess.

**Fix:** split the pure registry into `wubucontainer_registry.c` (no json-c, no IPC,
self-contained). Make `wubu_container_init` best-effort: spawn the engine, set
`engine_up = (spawn == OK)`, else `fprintf(stderr, …)` and continue. Add an
`engine_up` guard in `wubu_ctr_send_request` so live conversion fails fast with
`WUBU_CTR_ERR_ENGINE` instead of writing to a closed fd. The registry test now
passes with no `bun` present.

## Verification gate (run BEFORE editing the Makefile)

Catches Pitfalls A/B/C per-module, cheaply, before the full link:

```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
for m in shm input surface; do
  echo "=== hosted_wayland_$m.c ==="
  gcc -fsyntax-only -std=c11 -D_POSIX_C_SOURCE=200809L \
    -I src/hosted -I src/kernel -I src/runtime -I src/gui -I src/bridge \
    -I src/compiler -I src/jit -I src/apps src/hosted/hosted_wayland_$m.c 2>&1 | head
done
```

Then wire the new `.o` files into **every** recipe that previously compiled the
monolith. A module linked into `hosted` but not `test_hosted`/`test_gui_screenshot`
yields duplicate or unresolved symbols. Use a Python splice (preserves TABs) to
append `$(HOSTED)/hosted_wayland_shm.o …` after the monolith's `.o` token in each
recipe, rather than `patch` (which corrupts Makefile TABs).

## Final authority

After wiring: `make clean && make runtime && make hosted` green, then full
`make test` (GATE_EXIT=0, "All tests passed (all tiers)"). Both splits this session
landed green and were committed.
