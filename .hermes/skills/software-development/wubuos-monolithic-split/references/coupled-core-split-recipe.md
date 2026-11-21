# Coupled-Core Split Recipe (override of the ">5 shared helpers → drop" rule)

The user may direct you to IGNORE the "if extraction needs >~5 shared static
helpers, drop that subsystem" rule and split the coupled core anyway. The
correct technique is **promote the shared helpers into the internal header
first**, then extract. This is what was done for `explorer` (tree
subsystem, B9) and `wm` (taskbar, B10).

## When to use

- The file is a genuine monolith (>1000 lines) AND the user explicitly wants it
  split despite coupling. Otherwise prefer the skill's decision rule (drop it).
- You have already done the clean-leaf splits; only the coupled core remains.

## Steps

1. **Survey.** Identify the target subsystem block + every `static` helper it
   calls that lives in the host (e.g. `ex_get_extension`, `ex_file_compare`,
   `ex_sort_entries`, `ex_populate_tree`, `ex_tree_find`, `ex_tree_free`,
   `g_sort_ctx`). Also list the shared GLOBALS it touches (`g_explorer`,
   `g_dwm` — usually already `extern` in the internal header).

2. **Extract via brace-counting with FULL signatures** (see
   `brace-counting-extractor.md` — use the complete signature string
   `name(params)`, not a short prefix; short prefixes mis-match forward
   declarations and corrupt the host). Extract the subsystem block AND the
   needed helpers into one new module.

3. **Promote to the internal header.** For each moved helper, declare it
   non-static in `module_internal.h` (e.g. `void ex_sort_entries(...);`). For a
   shared global that moved OUT of the host, declare it `extern` in the header
   and define it exactly once (in the module or the host — pick one, never
   both). Example: `g_sort_ctx` moved from `static` in host → `extern
   ExExplorerState *g_sort_ctx;` in header + non-static def in host.

4. **De-static in BOTH TUs.** Remove `static` from the forward declaration AND
   the definition in the host, AND from the definition in the new module. A
   `static` left anywhere contradicts the non-static header decl →
   "static declaration follows non-static declaration".

5. **Grep for stale duplicate copies.** After promoting, grep ALL sibling
   `.c` files for each promoted name (`grep -rln ' ex_file_compare(' src/gui/*.c`).
   If another file has its own `static` copy, delete it (keep one canonical
   impl) — else link fails with `multiple definition`.

6. **Remove stale forward declarations from the host.** The host's old forward
   decls of the moved fns now conflict with the header's non-static decls —
   delete the exact lines.

7. **Wire into THREE places** (not one):
   - `GUI_OBJS` (feeds `make runtime`) — add `module.o`.
   - The **inline hosted link** line (the `hosted:` target compiles `.c`/`.o`
     inline; `GUI_OBJS` does NOT reach it) — add `module.o`.
   - Any `test_*` recipe that compiles the parent `.c` directly — add `module.c`.

8. **Verify from clean.** `make clean && make hosted` + `make clean && make
   test_<t>`. Stale `.o` files mask missing symbols.

## Concrete results (B8–B10)

- `explorer_tree.c`: `ex_get_extension` / `ex_strcasecmp` /
  `ex_sort_entries` / `ex_file_compare` / `ex_populate_tree` / `ex_tree_find` /
  `ex_tree_free` promoted non-static to `explorer_internal.h`; `g_sort_ctx`
  promoted `extern`. Host 1462→1261.
- `wm_taskbar.c`: taskbar render + height; `g_dwm` already extern; added
  `taskbar_get_clock_str` decl (defined in `wm_ctxmenu.c`,
  cross-module). Host 1405→1138.

Both verified green (explorer 74/74, wm 19/19) after clean rebuild.
