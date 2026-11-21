# Reusable-Leaf Extraction: B5 Batch (mime desktop parser + gamelib scanners)

Concrete recipe used in commit `d1dafb7` that extends the reusable-leaf pattern from
`references/reusable-leaf-extraction.md` with two new wrinkles:

1. the leaf's TYPES/GLOBALS are defined IN the host `.c` (not a public header), and
2. the parent→submodule family needs blanket wiring across MANY test recipes.

## A. When the leaf's types/globals live in the host `.c`

Extracted `wubu_json.c` (JSON parser) from `wubu_settings.c`. The `JsonToken` struct,
`JsonType` enum, and the static token-arena globals (`g_json_tokens[JSON_MAX_TOKENS]`,
`g_json_token_count`, `g_json_parse_error`) were ALL defined inside `wubu_settings.c`.

**Wrong:** `extern`-declare `g_json_tokens` in `wubu_json.h` while the struct stays in the `.c`
→ `redefinition of typedef` / `unknown type name JsonToken` in the module.

**Right:** move the DEFINITIONS into the shared header:

```c
// wubu_json.h
#define JSON_MAX_TOKENS 512
typedef enum { JSON_TYPE_OBJECT, JSON_TYPE_ARRAY, JSON_TYPE_STRING,
               JSON_TYPE_NUMBER, JSON_TYPE_BOOL, JSON_TYPE_NULL } JsonType;
typedef struct JsonToken_s JsonToken;
struct JsonToken_s { JsonType type; char *key; char *str_value; int int_value;
                     bool bool_value; JsonToken *children; int child_count; int child_capacity; };
extern JsonToken g_json_tokens[JSON_MAX_TOKENS];
extern int g_json_token_count;
extern int g_json_parse_error;
JsonToken *json_parse_value(const char **p);
JsonToken *json_find(JsonToken *obj, const char *key);
void       json_free(JsonToken *root);
```

Then BOTH `wubu_settings.c` and `wubu_json.c` do `#include "wubu_json.h"` and the module
DEFINES the globals (non-extern). The host file drops its local copies.

## B. Dedup-aware blanket Makefile wiring

After splitting `wubu_mime.c`→`_desktop` and `wubu_gamelib.c`→`_scan`, EVERY recipe that
compiles the parent `.c` directly (not just `GUI_OBJS` + hosted link) must also compile the
submodule `.c`, or you get `undefined reference to parse_desktop_file` / `get_dir_size`.

Single Python pass (run on the Makefile text):

```python
pairs = {
    "$(GUI)/wubu_proton.c":   ["$(GUI)/wubu_proton_util.c", "$(GUI)/wubu_proton_dxvk.c",
                                "$(GUI)/wubu_proton_exec.c", "$(GUI)/wubu_proton_config.c"],
    "$(GUI)/wubu_mime.c":      ["$(GUI)/wubu_mime_desktop.c"],
    "$(GUI)/wubu_gamelib.c":   ["$(GUI)/wubu_gamelib_scan.c"],
    "$(GUI)/wubu_deploy.c":    ["$(GUI)/wubu_deploy_util.c", "$(GUI)/wubu_deploy_gen.c"],
    "$(GUI)/wubu_settings.c":  ["$(GUI)/wubu_json.c"],
    "$(GUI)/explorer.c":["$(GUI)/explorer_zip.c", "$(GUI)/explorer_render.c",
                                 "$(GUI)/explorer_fs.c", "$(GUI)/explorer_fsops.c"],
}
for parent, subs in pairs.items():
    idx = 0
    while True:
        p = content.find(parent + " ", idx)
        if p == -1: break
        line_end = content.find("\n", p)
        line = content[p:line_end]
        missing = [s for s in subs if s not in line]
        if missing:
            insert_at = p + len(parent) + 1
            content = content[:insert_at] + " ".join(missing) + " " + content[insert_at:]
        idx = p + len(parent) + 1
```

The `if s not in line` guard prevents duplicating submodules that are ALREADY present on
`GUI_OBJS` (so `make clean && make hosted` and `grep` for dup `.o` stay clean). After the pass,
`wc -l` each parent `.c` and confirm no 10x shrink (forward-decl trap), then
`make clean && make hosted` + the affected `test_*`.

## C. Verify order that catches the most in one pass

1. `gcc -c` the new module standalone (catch include/extern/`static follows` in isolation).
2. `make clean && make hosted` (catches cross-module link errors: collisions, missing submodules).
3. Run the broad `test_*` smoke for every recipe that compiles a parent. A single pre-existing
   broken recipe (e.g. `test_gui_screenshot` double-`main`) is NOT your regression — read the
   recipe before "fixing" it.
