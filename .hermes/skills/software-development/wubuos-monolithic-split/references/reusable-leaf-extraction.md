# Reusable Leaf Extraction (zero-dep parser / encoder / crypto)

Pattern for pulling a generically-useful, self-contained subsystem out of a
feature `.c` where it currently lives embedded. Concrete case: the JSON parser
in `wubu_settings.c` (581->415) became `wubu_json.c` + `wubu_json.h`
(commit `b9a9699`).

## When this pattern fits
- The block has ZERO external deps beyond libc (only calls its own fns).
  Grep the block and confirm cross-references are all self-named. If the only
  matches are its own `json_*`, it's a clean leaf.
- The code is GENERICALLY USEFUL (parser, encoder, hash), not a feature-private
  helper. If >1 TU will want it, promote to a PUBLIC header. The JSON parser
  qualifies because settings load/save AND any future caller can reuse it.

## Wrinkle vs. "parse-only" extraction
In parse-only extraction the helper only needs INCLUDES bundled. Here the leaf
DEPENDS ON TYPES/ENUMS/GLOBALS DEFINED IN THE HOST `.c`. Relocate those
definitions into the new header so both TUs share them.

## Steps
1. Inspect what the block pulls from the host: type defs (`JsonToken`,
   `JsonType`), the enum, and any module-global *state* (`g_json_tokens[]`,
   `g_json_token_count`, `g_json_parse_error`).
2. Create `module.h` owning:
   - `#define JSON_MAX_TOKENS 512`
   - the `JsonType` enum
   - the `JsonToken` struct
   - `extern JsonToken g_json_tokens[JSON_MAX_TOKENS];`   // arena state
   - `extern int g_json_token_count;`
   - `extern int g_json_parse_error;`
   - the PUBLIC API prototypes (`json_parse_value`, `json_find`, `json_free`)
3. Create `module.c`:
   - `#include "module.h"` + minimal libc includes
   - DEFINE the arena globals (non-extern): `JsonToken g_json_tokens[...] = {0};`
     etc. — exactly ONE definition, in this `.c`.
   - paste the parser block, making the API fns NON-static (were static in host;
     now cross-TU -> strip `static`).
4. In the host `.c`: delete the type/enum/globals block AND the parser block;
   add `#include "module.h"` near the top (after feature macros). Host calls to
   `json_find`/`json_free`/`json_parse_value` now resolve via the header.
5. Compile the new module STANDALONE first (catches errors in isolation):
   `gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM \
      -Isrc/gui -Isrc/kernel -Isrc/runtime -c src/gui/wubu_json.c -o /tmp/j.o`
6. Makefile BLANKET REPLACE so EVERY recipe that compiles the parent also
   compiles the new module:
   ```python
   c = open("Makefile").read()
   c = c.replace("$(GUI)/wubu_settings.c ", "$(GUI)/wubu_settings.c $(GUI)/wubu_json.c ")
   open("Makefile", "w").write(c)
   ```
   This catches GUI_OBJS, the hosted link, AND every `test_*` recipe that pulls
   the parent `.c` directly (test_pkgmgr/test_deploy/test_wm all needed
   it). A targeted grep-and-patch misses these and fails at link with
   `undefined reference to json_find`.

## Gotchas
- Arena globals MUST be `extern` in the header and DEFINED in exactly one `.c`
  (the new module). Defined in both -> `multiple definition`; only declared ->
  `undefined reference`.
- Don't leave the type/enum in the host `.c` AND redeclare in the header ->
  `redefinition of typedef`. Move them out entirely into `module.h`.
- After extraction, sanity-check `wc -l host.c` — a sudden large shrink means
  you matched a forward declaration instead of the definition (see brace-counting
  Pitfall). Restore via `git checkout <commit> -- host.c` and re-run.

## Verification
`make clean && make hosted` (links the new module) + the parent's test targets.
All must pass before committing.
