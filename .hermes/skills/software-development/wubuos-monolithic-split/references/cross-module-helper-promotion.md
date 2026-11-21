# Cross-Module Helper Promotion & Sibling-Convention Matching

Concrete technique distilled from the 2026-07-15 `wubu_editor.c` split
(814 → 468 core + `wubu_editor_undo.c` / `_selection.c` / `_find.c`). Read
this when a monolith you are splitting has a `static` helper that more than
one resulting module needs, or when you are unsure what module style to use.

## 1. When a `static` helper is needed by 2+ split modules → promote it

A helper that lives in module A but is also called by the core file AND by a
sibling module B cannot stay `static` in A — B won't see it, and you'll get
`undefined reference`. The fix is to make it a public seam:

- Define it once (in the module that owns the concern — here `undo_push`
  became `wubu_ed_undo_push` in `wubu_editor_undo.c`).
- Declare it in the **public** header (`wubu_editor.h`), not an internal
  header, so every module that `#include "wubu_editor.h"` can call it.
- Rename all call sites (core + sibling) to the public name.

```c
/* wubu_editor.h */
void wubu_ed_undo_push(WubuEdTab *tab, WubuUndoKind kind, int line, int col,
                       const char *text, int text_len);

/* wubu_editor_undo.c — single definition */
void wubu_ed_undo_push(WubuEdTab *tab, ...) { ... }

/* core wubu_editor.c + wubu_editor_find.c both call wubu_ed_undo_push(...) */
```

The canvas subsystem uses the analogous convention with a double-underscore
"internal seam" name (`wubu_cv__undo_push`, declared in
`wubu_canvas_internal.h`) — see `references/dedup-shared-core-patterns.md` §8.
**Pick the convention already in use for the file you are splitting; do not
impose a foreign style.** For `wubu_editor.c` the existing siblings
(`wubu_editor_bookmark.c`, `wubu_editor_macro.c`) use plain public `wubu_ed_*`
names, so that is what we matched.

## 2. Match the subsystem's existing sibling convention

Before splitting, list the file's existing sibling modules:

```
grep -nE "^(static )?[A-Za-z_].*\(" src/apps/wubu_editor_*.c
```

If `wubu_editor_bookmark.c` / `wubu_editor_macro.c` already exist and each is a
standalone `.c` that `#include "wubu_editor.h"` and implements `wubu_ed_*`
functions directly, mirror THAT: new module = one `.c` + the public header,
no new internal header, no opaque-struct gymnastics (the public header is
already the API surface). This keeps the diff minimal and the gate green.

## 3. Extract large contiguous blocks by line range (safer than `patch`)

For deleting a 100+ line block, `patch` fuzzy-matching on a giant single line
is fragile. Use a short Python script via `terminal` (bare `open()`, NOT
`hermes_tools` — the tools truncate large files, see `wubuos-build-recovery`):

```python
p="src/apps/wubu_editor.c"
lines=open(p).read().split('\n')          # 1-indexed externally
keep=[ln for i,ln in enumerate(lines,1) if not (317<=i<=444) and not (445<=i<=559)]
open(p,'w').write('\n'.join(keep))
```

Then rename call sites (`undo_push(` → `wubu_ed_undo_push(`) with targeted
`patch` edits. Verify each new module compiles standalone before wiring:

```
gcc -Wall -Wextra -std=c11 -O2 -g -D_POSIX_C_SOURCE=200809L -I src/apps \
    -c src/apps/wubu_editor_undo.c -o /tmp/x.o
```

## 4. Wire the new modules (the part that breaks the gate)

After extracting, add each new `.o` to the object-list variable the consumers
use AND to every inline-linking `test_*` recipe. For `wubu_editor`:

```
APP_OBJS += wubu_editor_undo.o wubu_editor_selection.o wubu_editor_find.o
# test_apps2 links wubu_editor.c inline → also add the 3 .c there
```

Then run `make clean && make test` (the REAL bar — a warm-cache pass hides
missing-`.o` gaps; see `wubuos-build-recovery` "THE MONOLITH-SPLIT LINK GAP").

## 5. Verification (this session, green)

- `make test_apps2` → 19/19 (editor split links + passes).
- `make clean && make test` → EXIT=0, all tiers, 42 groups.
