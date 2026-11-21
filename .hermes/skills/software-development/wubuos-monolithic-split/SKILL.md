---
name: wubuos-monolithic-split
category: software-development
description: Systematic workflow for splitting monolithic C files in WuBuOS into self-contained modules with internal headers. Opaque struct pattern + Makefile updates + test verification.
---

# WuBuOS Monolithic File Splitting Workflow

> **Ring-0 hardware concerns:** when the monolith folds in raw port I/O or
> APIC/MSR pokes, extract them into a host-testable sibling by gating ONLY the
> hardware call under `#ifdef MYSEED_METAL` and keeping the bookkeeping
> mode-agnostic. See [`references/ring0-hardware-extract.md`](references/ring0-hardware-extract.md)
> (used for the `interrupt.c` → `interrupt_pic.c` PIC/IRQ-routing split).

> **Session detail / cross-build patterns:** [`references/dedup-shared-core-patterns.md`](references/dedup-shared-core-patterns.md) — collision-with-existing-def handling, wiring a shared core into RT_OBJS/GUI_OBJS/HOSTED_OBJS + direct-compile test recipes, cold-build-race fixes, multi-function extraction, the standalone verification harness + `\n`-as-line-start parser bug, AND the **divergent-dupe → canonical-core + resolver/state-hook pattern** (§8) plus the **REAL_GAP override** (§11: a divergent duplicate is authorized work, not a stop-and-ask). See [`references/monolith-b50-b67-status.md`](references/monolith-b50-b67-status.md) for the CLOSED dedup list (commits `8cbd776`, `62b5738`).
> **WIP recovery (resuming a half-finished split):** [`references/split-wip-recovery.md`](references/split-wip-recovery.md) — phantom-module detection, the `.o`-vs-`.c` link-vs-test-recipe trap, `_legacy_bak` relocation breaking `test_*` recipes, and shared-global promotion.

## Trigger Conditions
- User says "split up", "monolithic files", "refactor monolithic", "break apart", or similar
- A file exceeds 1000 lines and has clear internal boundaries (section markers, `static` function groups, `typedef` structs for subsystems)
- Building on the VSL modular refactor pattern already applied to `wubu_vsl.c` → `src/runtime/vsl/`

## Principles (C11 Opaque Refactoring)
1. **Opaque structs in headers** — forward declare in public .h, define in private/internal headers
2. **Minimal includes** — headers include only what they need for types/function signatures
3. **No god headers** — no single header pulls in entire subsystem
4. **Self-contained modules** — .c files include their internal header first
5. **C11 only** — no GNU extensions, no C++

## Workflow

### Step 0: Scoping — is it worth splitting?

Before any extraction, confirm the file is actually on the **build hot path** and that its
bulk is **separable subsystems**, not one cohesive function:

1. **Is it in the build graph?** `grep -n 'filename' Makefile`. If NO recipe references it
   (no `OBJS` entry, no direct-compile line), splitting gives **zero rebuild benefit** — the
   file is never recompiled, so its size doesn't slow anything. Skip it (e.g. `src/apps/explorer.c`,
   `wubu_compositor_standalone.c` in WuBuOS are orphaned — left as-is). Only split files a
   recipe compiles.
2. **Is the bulk separable subsystems, or one giant function?** If the file is ~one function
   body (a dispatch / parse / codegen / RPC handler), splitting it across files is **artificial
   fragmentation**, not monolith-busting — and it forces you to extern a pile of statics for no
   cohesion gain. Leave single-cohesive-function files (e.g. `holyc_codegen_expr.c`'s ~846-line
   `gen_expr`, `wubucontainer.c`'s ~415-line `wubu_ctr_send_request`). The user's goal is
   *separable subsystems*, not *fewer lines per file*.
3. **Out-of-scope per project constraints:** kernel freestanding, ML, GL, hosted glue, generated
   tables. Don't force those.

If it passes all three, proceed to Step 1.

### Step 1: Survey the Target File
```bash
cd /home/wubu/wubuos/src

# Check file size
wc -l <path_to_file>.c

# Identify section markers
grep -n '^/[*]====\|^/[*] ---\|^// ===\|^// ---\|^/\* --' <path_to_file>.c | head -30

# Identify function boundaries - which are static (candidates for extraction) vs public API
grep -n '^static.*(' <path_to_file>.c | head -40

# Identify struct typedefs (are they in .c or .h?)
grep -n '^typedef struct\|^struct.*{' <path_to_file>.c | head -10
```

### Step 2: Identify Extractable Modules
Look for sections that:
- **Are self-contained**: use their own data, don't access the big global state directly (or access it through well-defined public API)
- **Have clear boundaries**: section comment markers, the functions all relate to one subsystem
- **Are not tightly coupled**: don't access internal fields of the main global state struct directly

Good candidates:
- HolyC terminal (has its own struct, only uses `g_dwm` via public API)
- Context menus (uses extern `g_ctx_stack`, self-contained)
- System tray + notification center (accesses `g_dwm.systray_icons[]` directly)
- Desktop icons grid (tightly coupled to `g_dwm.icons[]` — harder but doable)

### Step 3: Create Internal Header
Create `wm_internal.h` (or `module_internal.h` for other modules):

```c
#ifndef WUBU_DOSGUI_WM_INTERNAL_H
#define WUBU_DOSGUI_WM_INTERNAL_H

#include "public_header.h"          // For public types (DosGuiWindow, etc.)
#include <all_needed_system_headers.h>
#include "../other_module/dep.h"     // Cross-module deps

/* -- Safe String Macros (shared) -- */
#define WUBU_STRCPY(...) ...

/* -- Global State (was static in .c, now extern) -- */
typedef struct { ... } GlobalState;
extern GlobalState g_state;  // Definition lives in the .c

/* -- Forward declarations for functions shared across sub-modules -- */
void internal_fn1(void);
void internal_fn2(int param);
// These are NOT static — they're called from other sub-module .c files

#endif
```

**Key rules for internal headers:**
- **Do NOT redefine types that the public header already declares.** This is the #1 compile error when splitting. `wm.h` already defines `DosGuiIcon`, `DosGuiContextMenu`, `CTX_ITEM_*` enum, `DOSGUI_ICON_SIZE`, `DOSGUI_MAX_ICONS`, `g_ctx_stack` — internal header must NOT repeat these.
- **Include the public header in the internal header** (it's already there). Then add only what the public header doesn't have: private structs like `HolycTerm`, the internal `DosGuiWM` struct with ALL members matching the original, and forward declarations for shared internal functions.
- **Match the original struct member names exactly.** The internal header's `DosGuiWM` must have `drag_id` (not `drag_win`), `wallpaper_mode`, etc. — whatever the original `.c` uses.
- **`static` on function declarations in .h is wrong** — functions declared in .h cannot be static.
- **Compilation error: `conflicting types` / `redefinition of typedef`** — This means the internal header redefines something that `wm.h` already declares. Fix: remove the duplicate from the internal header (it gets it via the `#include wm.h`).

### Step 4: Extract to New Files
### Step 4: Extract to New Files — PREFER BRACE-COUNTING, NOT LINE RANGES

**⚠️ Primary method: locate function bodies by signature + depth-matched braces, not by
1-indexed line ranges.** Line-index slicing (`raw[19:62] + raw[68:214]`) SHIFTS indices
after a multi-range deletion and silently corrupts the host file. This burned multiple
iterations on `wubu_proton.c` and `term.c` — `g_proton` got deleted, functions got
truncated. Use a Python `execute_code` script instead:

```python
lines = open("src/gui/wubu_proton.c").read().split("\n")
def fn_end(start):
    depth = 0; started = False
    for i in range(start, len(lines)):
        for ch in lines[i]:
            if ch == '{': depth += 1; started = True
            elif ch == '}':
                depth -= 1
                if started and depth == 0: return i
    return len(lines) - 1
def extract(sig):
    for i, l in enumerate(lines):
        # Require '{' on the SAME line as the signature: matches the FUNCTION
        # DEFINITION, never a forward declaration (which ends in ';'). Without
        # this guard, extract() grabs the forward decl (e.g. line 66
        # "static void ex_worker_copy(...)") instead of the definition at 1516,
        # and the remove-mask then deletes everything in between — silently
        # nuking ~1500 lines of the host (burned explorer.c in the
        # 2026-07-09 batch; the file dropped to 125 lines and had to be
        # restored from git). ALWAYS require '{' on the signature line.
        if sig in l and '{' in l:
            return i, fn_end(i)
    raise RuntimeError(sig)
ranges = [extract(s) for s in sigs]          # sigs = list of "static int fn_name" etc.
mask = [False]*len(lines)
for s, e in ranges:
    for i in range(s, e+1): mask[i] = True
block = "\n\n".join("\n".join(lines[s:e+1]) for s, e in ranges)
new_src = [l for i, l in enumerate(lines) if not mask[i]]
```
A paste-ready, complete implementation (disjoint ranges, keeps globals outside the mask,
de-statics declared helpers, writes the new module + trimmed host atomically) is in
`references/brace-counting-extractor.md`. **Use it for every file >1000 lines / >10
functions to remove.** Reserve the `patch` tool for tiny (<40 line) single-block moves.

Create `module_subsection.c`:
```c
#include "module_internal.h"
// ... extracted code ...
```

**Things to change when extracting:**
1. Remove `#include` lines — the internal header covers them
2. Remove `static` from functions that need to be called from other modules (if any)
3. Remove `#define`s and `typedef`s that are already in the internal header
4. Keep the function implementations identical — **don't fix bugs during refactoring**

### Step 5: Remove Extracted Code from Original .c

Use `patch` tool to remove the extracted section. The old_string should include surrounding context for uniqueness.

**After removal:**
- Original .c should still compile on its own
- Forward declarations (if any stayed) must match the actual function definitions

### Step 6: Update Makefile

1. Add new `.o` files to `MODULE_OBJS` variable
2. Add new `.c` files to ALL recipe lines that compile the original .c directly (grep for all occurrences)
3. Add any missing `-I` flags to the pattern rule

```makefile
# Find all references:
grep -n 'old_file\.c' Makefile

# For each, add new files right after the old .c reference
```

4. **How many Makefile places to update depends on file location:**
   - **GUI files** (`src/gui/`): 4 places — `GUI_OBJS` + hosted binary (line ~166) + hosted_test binary (line ~469) + test target direct-compile.
   - **Runtime files** (`src/runtime/`): typically 2 places — `RT_OBJS` + test target direct-compile. The hosted binary may not include the file at all. Check with `grep -n 'old_file\.c' Makefile` — never assume 4.
   - **Kernel/JIT/Compiler**: 1 place (their OBJS variable) unless a test compiles directly.

5. If new headers need include paths not already in the pattern rule, add `-I` flags:
```makefile
$(GUI)/%.o: $(GUI)/%.c
	$(CC) $(CFLAGS) -I$(GUI) -I$(KERNEL) -I$(NEW_DEP) ... -c $< -o $@
```

**⚠️ Test target recipes compile `.c` files directly — never put `.o` files there.**
Test targets like `test_vsl`, `test_syscall`, `test_holyc` compile source files in a single `$(CC)` invocation. The recipe lists `.c` files, not `.o` files. Adding `$(RT)/vsl/vsl_memory.o` to a test target recipe produces a link failure or silently ignores the `.o` file. Always use the `.c` source path. The `OBJS` variables (e.g., `RT_OBJS`) for `make runtime` DO use `.o` files — that's the correct place for `.o` additions.

**⚠️ Critical: Hosted/main binary targets are distinct from `OBJS` variables.**
`OBJS` lists `.o` files for the pattern-rule build; **legacy** hosted/main binary recipes compile `.c` files *directly* in one big `$(CC)` invocation. Adding to `GUI_OBJS` is NOT sufficient for the hosted binary. `grep -n 'old_file\\\\.c' Makefile` will find BOTH types — you must update every hit, including the hosted build recipe, the test targets, the GUI build, and the screenshot tool.

**⚠️ The inline hosted recipe is itself the #1 rebuild-speed killer — convert it, don't extend it.**
If the `hosted:` (or `main:`) link line lists dozens of `.c` paths inline, it recompiles the whole TU on *every* `make hosted` even when you edited one file — this is the usual cause of "rebuilding takes too long." Prefer converting it to **incremental object linking** (see Variant: Convert Hosted/Main Inline-Recompile Recipe to Incremental Object Linking) BEFORE adding more files to it. After conversion, you only add the new `.o` to `HOSTED_OBJS` — one grep hit, not four.

**⚠️ Stale `.o` files mask missing-link errors.**
After splitting, old `.o` files from before the split sit on disk and provide symbols that would otherwise fail to link. New clone or `make clean` surfaces the missing symbols. Always run `make clean && make hosted` (or `make clean && make <affected-test>`) to catch missing-link deps before committing.

**⚠️ "Use-before-declare" in callback-heavy files.**
When you expose a `static` helper as non-static and declare it in the internal header, the host .c may still have the function definition physically *after* its callers. If a new split module is compiled independently (its own .c), that's fine — the header declaration is enough. But if the host .c itself uses the newly-exposed function, C still requires the declaration or definition to appear before the first use. Add the `#include "internal.h"` at the top of the host file, or add a forward declaration above the caller.

### Step 7: Verify

```bash
make test_<target>
# All tests must pass — if not, fix the forward declaration / static mismatch first
```

**Compilation error: `static declaration follows non-static declaration`** — This is the most common error when splitting. It happens because:
1. The **internal header** declares `void fn(void);` (non-static, correct)
2. The **original .c** still has `static void fn(void);` in its forward declarations AND `static void fn(void) { ... }` in its definitions

**Fix in sequence** (both places must be changed):
1. Remove `static` from forward declarations in .c → matches internal .h
2. Remove `static` from function DEFINITIONS in .c → matches its own forward decl
Both `.h` forward decl and `.c` forward decl + definition must agree: all non-static. Missing step (2) is the #1 gotcha — the definition's `static` contradicts the non-static forward decl and the compiler catches it.

**Common errors and fixes:**
| Error | Fix |
|-------|-----|
| `static declaration follows non-static declaration` | Remove `static` from the forward declaration in .c, OR remove the declaration from internal header |
| `undefined reference to 'fn_name'` | Forward declare + remove `static` from function definition |
| `conflicting types for 'fn_name'` | Function signature mismatch between .h declaration and .c definition |
| `redefinition of typedef` | Don't redefine what's already in the included header |
| `redeclaration of enumerator` | Enum values defined twice in the same enum — check for duplicates after merge |
| `implicit declaration of function 'parse_block'` | Function used before declaration — add proper declaration in header, or include parser.h |
| `assignment to 'HCASTNode *' from 'int' makes pointer from integer without a cast` | Implicit int return from undeclared function — declare function in header |

## Compiler Refactor Session Learnings (2026-07-05)

### HolyC Modular Refactor: Key Fixes Applied

**1. Modular header structure established:**
- `holyc_types.h` — Core types, enums, struct definitions (token types, AST kinds, symbols, etc.)
- `holyc_lexer.h` — Lexer API (HCTokenType hc_lex_init, hc_lex_next, hc_lex_peek, hc_lex_expect)
- `holyc_parser.h` — Parser API (hc_parse_init, hc_parse_expr, hc_parse_stmt, hc_parse_decl, hc_parse_compilation_unit, hc_parse_block, hc_parse_peek)
- `holyc_codegen.h` — Codegen API (hc_gen_init, hc_gen_node, hc_gen_function, gen_expr, gen_stmt, emit_prologue, emit_epilogue, jit_alloc_exec, jit_free_exec, hc_compile, hc_eval)
- `holyc_ast.h` — AST node struct + utilities
- `holyc.h` — Facade including all of the above

**2. Parser.c corruption recovery:**
The original `holyc_parse.c` was corrupted during the split (all functions became `parse_block`). Restored by:
- Reverting to clean forward declarations at top: `static HCASTNode *parse_expr(HCParser *p);` etc.
- Making `parse_block` non-static and declaring in `holyc_parser.h`
- Fixing `HC_KWBool` → `HC_KW_BOOL` mismatch
- Fixing `HC_TOK_PLUS_EQ` → `HC_TOK_PLUS_ASSIGN` token name mismatches

**3. Codegen.c fixes:**
- Added `#include "holyc_parser.h"` for `hc_parse_block` declaration
- Changed `parse_block(&parse)` → `hc_parse_block(&parse)` in `hc_eval` and `hc_compile`
- Fixed `HC_AST_BOOL_LIT` missing from enum (added to HCASTKind)
- Fixed `HC_AST_DEREF`, `HC_AST_ADDR` missing from enum

**4. Lexer.c fixes:**
- Added `#include <stdarg.h>` for `hc_lex_error` variadic
- Fixed token names: `HC_TOK_PLUS_EQ` → `HC_TOK_PLUS_ASSIGN`, `HC_TOK_MINUS_EQ` → `HC_TOK_MINUS_ASSIGN`, etc.
- Fixed `HC_KWBool` → `HC_KW_BOOL` in keyword table

**5. Token type enum cleanup:**
- Added `HC_TOK_SHL`, `HC_TOK_SHR` separate from `HC_TOK_LSHIFT`/`HC_TOK_RSHIFT` (parser uses both)
- Added `HC_TOK_PLUS_PLUS`, `HC_TOK_MINUS_MINUS` for pre/post inc/dec
- Added `HC_TOK_SHL_ASSIGN`, `HC_TOK_SHR_ASSIGN`
- Removed duplicate `HC_AST_POST_INC`/`HC_AST_POST_DEC`/`HC_AST_BITXOR` from HCASTKind

**6. Type system fixes:**
- Added `name` field to `HCType` struct for struct/enum/typedef names
- Added `array_size` to `HCType` for arrays
- Fixed `HC_KWBool` → `HC_KW_BOOL` in keyword enum

**7. Parser token name consistency:**
- `HC_TOK_PLUS_EQ` → `HC_TOK_PLUS_ASSIGN` throughout parser.c
- `HC_TOK_MINUS_EQ` → `HC_TOK_MINUS_ASSIGN`
- `HC_TOK_STAR_EQ` → `HC_TOK_STAR_ASSIGN`
- `HC_TOK_SLASH_EQ` → `HC_TOK_SLASH_ASSIGN`
- `HC_KWBool` → `HC_KW_BOOL` in parse_type

### Pattern: When Modular Refactor Breaks Build

1. **Enum duplication**: After merging split headers, check for duplicate enum values (especially AST kinds, token types)
2. **Function declaration mismatch**: Ensure internal header declares functions as `extern` (not static), .c file definitions match (non-static)
3. **Token name drift**: Parser uses specific names — ensure lexer.h enum and lexer.c both use identical names
3. **Missing includes**: After modular split, each .c must include all needed headers (parser.h for parse_block, etc.)
4. **stdarg.h**: Add to any file using va_list/va_start/va_end
4. **Forward declarations**: Ensure all non-static functions called across modules are declared in a public header

### Step 8: Create Tests (Optional — Second Pass)

Add a test file for the extracted module:

```makefile
test_holyc_term:
	$(CC) -O0 -g -DVBE_HOSTED -I$(GUI) -I$(KERNEL) -I$(COMP) -I$(JIT) \
		$(GUI)/wm_holyc_term.c $(GUI)/wubu_theme.c \
		...test_stubs... \
		$(GUI)/holyc_term_test.c -o $(GUI)/holyc_term_test -lm
	$(GUI)/holyc_term_test
```

## Example: wm.c (2288→1965 lines) Split

| New File | Lines | Content |
|----------|-------|---------|
| `wm.c` | 1965 | WM core (state, lifecycle, z-order, input, render, taskbar, icons, ctx menu + dialogs) |
| `wm_holyc_term.c` | 152 | HolyC REPL terminal (draw, key, eval, spawn) |
| `wm_ctx_menu.c` | placeholder | Context menu API stays in main .c for now — too coupled to dialog actions |
| `wm_internal.h` | 109 | Internal struct + function declarations |
| **Total** | **~2226** | Cleaner organization, 16/16 tests pass |

**Key learning:** Functions that are static in the original .c and accessed by the new modules must be declared non-static in the internal header. Remove `static` from both the forward declaration AND the function definition in the original .c.

## Variant: Reusable Leaf Extraction (parser / encoder / crypto)

When the monolith embeds a **generically-useful, zero-dependency subsystem** (a JSON parser,
a PNG encoder, a hash) that >1 TU will want, extract it to its own `.c` + **PUBLIC** header and
promote the API there (not just an internal header). Unlike parse-only extraction, the leaf
depends on types/enum/globals defined in the host `.c` — those move into the new header, the
arena globals become `extern` there and are DEFINED once in the new `.c`. Because the module is
pulled in by many recipes, wire it with a **blanket Makefile replace** (see Pitfalls). Full
recipe + gotchas in `references/reusable-leaf-extraction.md`.

## Variant: Header-Only Utility Library (static inline pattern)

For pure utility code (crypto, hash, string helpers) that doesn't depend on global state:

**Create a `.h` with `static` functions** instead of splitting into `.c` + `.h`:

```c
// wubu_crypto.h  —  Self-contained, no .c file needed
#ifndef WUBU_CRYPTO_H
#define WUBU_CRYPTO_H
#include <stdint.h>
#include <string.h>

static uint32_t wubu_crc32(const void *data, size_t size) { /* ... */ }
static void wubu_sha256_digest(const void *data, size_t size,
                                char *out_hex, size_t out_size) { /* ... */ }
#endif
```

**When to use:**
- Pure functions with no global/mutable state
- Under ~200 lines (beyond that, a `.c` + `.h` is cleaner)
- Only `stdint.h`/`string.h`/`stdio.h` deps

**Migrating:**
1. Create `module_crypto.h` with `static` function definitions
2. `#include` in the originating `.c` file
3. Add `#define` backward-compat aliases for old names:
   ```c
   #define SHA256_CTX    wubu_SHA256_CTX
   #define sha256_digest wubu_sha256_digest
   #define sha256_file   wubu_sha256_file
   ```
4. Delete duplicate function bodies from `.c`
5. If same code also lives in ANOTHER `.c` (e.g., CRC32 duplicated in `wubu_container.c`), delete there too and add the same `#include`

**Caveat:** If another header already declares the same function as `extern` (non-static), the `static` definition in the header causes `static declaration follows non-static declaration`. Remove the `extern` declaration from the other header.

## Variant: Gut Old Monolith to Shim

When sub-module `.c` files already exist in a subdirectory but the old monolith still has all the duplicate code:

1. **Shim** — replace old monolith with just global state:
   ```c
   // old_monolith.c  —  was 2175 lines, now 3 lines
   #include "subdir/module_internal.h"
   **Deferred:** If a module calls ~5+ static helpers from the host (like `ex_update_breadcrumbs`, `ex_add_to_history`, `ex_sort_entries` for explorer), extract those helpers to the internal header FIRST before extracting the module itself.

## Variant: Extract Render Layer as Separate Module

| File | Lines | Sections | Difficulty | Notes |
|------|-------|----------|------------|-------|
| `wubu_image.c` | 1516 → ~1220 after parse extraction | tar writer, manifest JSON, layer cache, build engine | Medium | Parse extracted; next: tar writer or manifest JSON |
| `wubu_audio.c` | ~1990 | device enum, stream routing, mixer, PipeWire/PulseAudio | High | Coupled to platform audio APIs |
| `wubu_network.c` | 1271 | netlink helpers, profile management, endpoint connect | Medium | Some coupling to state |
| `wubu_snapshot.c` | 1222 | fs ops (btrfs/zfs), nftw copy, snapshot/branch/tag | Medium | |
| `wubu_holyd.c` | 1467 | HolyC daemon, compiler state, sessions | Medium | Coupled to HolyC runtime |

## Example: wubu_image.c → wubu_image_parse.c (Parse-Only Extraction)

| File | Lines | Content |
|------|-------|---------|
| `wubu_image.c` | 1516 → (TBD after full split) | Build engine, tar writer, layer cache, manifest ops, tags, push/pull |
| `wubu_image_parse.c` | 293 | WuBuFile parser (`parse_instruction`, `wubu_parse_wubufile`, `wubu_parse_wubufile_str`) |
| `wubu_image_internal.h` | 85 | Shared helpers (`str_trim`, `str_dup`, `str_startswith` as `static inline`), crypto wrappers, forward declarations |

**Key pattern difference from prior splits:** This module has NO global state. No `extern` vars, no shared mutable data — the parser only takes `WubuBuildContext*` as output and reads files. The internal header is purely an **include consolidation**: it bundles the public header, all system headers, crypto wrappers, and string helpers so both `wubu_image.c` and `wubu_image_parse.c` have one `#include "wubu_image_internal.h"` line where they previously had ~30 lines of duplicate includes, `#define` aliases, and `static` helpers.

**When to use this pattern:** the extracted module only calls 2–4 small `static` helpers from the parent file. Move those helpers to the internal header as `static inline`, then the module gets them for free with zero coupling. No need to externalize, no `extern` gymnastics.

**Internal header structure for parse-only extraction:**
```c
// wubu_image_internal.h  —  shared helpers + consolidated includes
#include "wubu_image.h"          // public types
#include <stdlib.h>              // all system headers the subsystems need
#include <string.h>
#include <stdio.h>
#include <ctype.h>
#include "wubu_crypto.h"          // shared crypto
#define sha256_digest wubu_sha256_digest  // backward-compat aliases
#define sha256_file   wubu_sha256_file

static inline void str_trim(char *s) { /* ... */ }   // moved from parent
static inline char *str_dup(const char *s) { /* ... */ }

```c
int parse_instruction(const char *line, WubuInstruction *inst, int line_num);
int wubu_parse_wubufile(const char *path, WubuBuildContext *ctx);
int wubu_parse_wubufile_str(const char *content, WubuBuildContext *ctx);
```

**Existing files to update:**
- `explorer_render.c` (was already split) — this `static inline` helper pattern was used there too (theme helpers in `explorer_internal.h`). Verify no stale duplication.

## Cumulative Split Status (OUTDATED — see Pitfalls "Status was wrong" + references/monolith-backlog-2026-07-11.md)

> ⚠️ The block below was written 2026-07-10 claiming the work was DONE. A 2026-07-11
> build-graph audit proved that FALSE: the B-series extracted only ONE separable
> subsystem per file, but most parents are still large and separable. The goal is NOT
> complete. Authoritative state + ordered backlog: `references/monolith-backlog-2026-07-11.md`.

**39 monolith splits (B11–B39) committed + pushed to `origin/master`.** Every in-scope

**39 monolith splits (B11–B39) committed + pushed to `origin/master`.** Every in-scope
separable subsystem across GUI / runtime / apps / compiler / jit / bridge is now its own
self-contained leaf file (`*.c` + internal header, opaque-struct discipline, minimal
includes). `make hosted` is incremental `.o` linking. Push no longer blocked (PAT via
`~/.git-credentials`, NOT memory).

**Modules extracted this batch (B11–B39):**
- GUI: `startmenu`→`_power`; `explorer`→`_preview`; `wm`→`_icons`;
  `term`→`_tabs`; `wubu_pkgmgr`→`_db`; `wubu_clipboard`→`_mime`; `wubu_screenshot`→`_draw`.
- Runtime: `styxfs`→`_util`; `wubu_network`→`_svc`+`_fw`; `wubu_archd`→`_util`; `wubu_snapshot`→`_tag`+`_diff`;
  `wubu_proton`→`_pe`+`_dll`; `wubu_ct_isolate`→`_cgroup`; `wubu_bottles`→`_json`; `wubu_proton2`→`_gpu`;
  `wubu_exec`→`_format`; `styx`→`_fid`; `wubu_image`→`_cache`.
- Apps/Compiler/JIT: `wubu_editor`→`_bookmark`; `wubu_canvas`→`_blend`; `wubu_canvas_io`→`_ppm`;
  `jit`→`_encode`; `jit_minic`→`_token`; `holyc_parse`→`_ast`; `calc`→`_math`.
- Bridge: `wubu_syscall`→`_vbe`.

**Hosted build + all affected tests green after each split** (test_explorer 74/74,
test_wubu, test_styxfs, test_proton/proton2/gamelib, test_snapshot/system, test_oci,
test_calc, test_jit, test_holyc, test_syscall, test_screenshot*, test_archd,
test_daemon_panel, test_editor/apps2, test_bottles, test_network all PASS).

**Deliberately LEFT (do NOT force-split):**
- Files that are ONE large cohesive function, not separable subsystems:
  `holyc_codegen_expr.c` (one ~846-line `gen_expr` dispatcher),
  `src/runtime/container/wubucontainer.c` (one ~415-line `wubu_ctr_send_request` RPC handler).
  Splitting a single function across files is artificial fragmentation, not monolith-busting.
- Out-of-scope per original constraints: kernel (`interrupt.c`/`fat32.c`), ML (`bear/*`),
  GL (`wubu_vulkan.c`/`wubu_metal.c`), hosted glue (`hosted.c`/`wubu_metal.c`),
  generated (`vsl_syscall_table.c`).
- Not in the build graph at all: `src/apps/explorer.c`, `wubu_compositor_standalone.c`
  (splitting files no recipe compiles gives zero rebuild benefit).

**Pre-existing failures (NOT regressions — left as-is):** (see org-session notes below)
- `test_container_registry`: test `.c` references `WubuContainerHandler.handler` (member
  doesn't exist; it's `name`) — test-source bug, untouched by splits.
- `test_apps`: **recipe rot FIXED** (paths `paint/paint.c`→`paint.c`, `wm.c`→`wm.c`,
  include `paint/paint.h`→`paint.h`, restored `wubu_freedoom.c`), but the test still fails to
  *compile* on ~57 opaque-struct field reads (CalcState/NotepadState/TaskManagerState/
  RegeditState/FileManagerState/ControlState) — a pre-existing test-source contract
  violation, scoped as a separate accessor-refactor pass. Do NOT fix by exposing the structs
  (cascades into missing enum/macro deps).

## Build-Graph Audit & Legacy Mining (2026-07-10 org session)

> **Live backlog:** `references/monolith-backlog-2026-07-11.md` holds the current
> post-audit state + ordered candidate list. Re-read it at the start of every
> monolith-busting session — do NOT trust the "Cumulative Split Status" block below it.

When the user asks to "organize the build graph" / "fix exclusions" / "rebuild from
legacy", the work is: (1) **audit** which `.c` files are actually compiled/linked,
(2) **relocate** excluded files into a graveyard (`src/_legacy_bak/`) with a README
categorizing each, (3) **mine the graveyard** for declared-but-unimplemented
subsystems to rebuild into the new org.

### Build-graph audit (the correct way)
A naive `grep "src/foo.c" Makefile` gives false negatives because the Makefile uses
`$(VAR)/foo.c` / `$(VAR)/foo.o` tokens and `os.path.relpath` may keep the `src/`
prefix. Correct scan: map `src/<dir>` → the Makefile `$(VAR)`, then for each `.c`
check BOTH the `.o` form and `.c` form as tokens. Reusable script in
`references/build-graph-audit.md`. Two bugs that burned a turn: (a) stripping the
`src/` prefix before mapping (then `top` never matched the varmap), and (b) checking
only `.c` (OBJS vars list `.o`). Either yields a bogus "27 files not in build" — verify
against a known-in-build file (e.g. `explorer.c`) before trusting the list.

### Relocation pattern
`git mv` each excluded file into `src/_legacy_bak/` with a flattened name
(`gui/wubu_compositor.c` → `gui__wubu_compositor.c`) so nested dirs don't collide.
For untracked files use `mv` + `rmdir -p`. Add `src/_legacy_bak/README.md` with an
inventory table: reason per file (superseded dup / needs-deps / orphan-demo) and, for
anything later restored, its commit + status. Keeps the layout self-documenting.

### Gap analysis — what to rebuild
The legacy reveals **declared-but-unimplemented subsystems**: a header still in the
build graph whose `.c` impl was orphaned. Find them:
```bash
for h in wubu_compositor.h wubu_display.h wubu_codec.h; do
  echo "$h:"; grep -rln "$h" src --include=*.c | grep -v _legacy_bak
done
```
Then rebuild the impl: restore from `_legacy_bak/`, compile-standalone, wire into the
relevant test recipe + (if needed) `HOSTED_OBJS`. Keep the working impl (e.g.
`wubu_drm_direct.o` already provides `wubu_display_init`) and have the restored
standalone impl be exercised by its OWN test, to avoid duplicate-symbol collisions.

### Use git to not blast ourselves
For org refactors, work on a **feature branch** and **commit per logical step**
(relocate → rebuild-A → rebuild-B → fix-recipes), pushing the branch so nothing is
lost. Each step is a revert point — don't do one giant squash.

### Pitfalls (org/rebuild session)
- ❌ **Don't expose opaque structs to fix a test's internal field access.**
  `apps_test.c` poked into 6 opaque app-state structs (≈57 sites). Moving the
  struct defs into the public headers cascaded into missing enum/macro deps
  (`NP_MAX_TABS`, `TM_MAX_PROCESSES`, `FM_MAX_ENTRIES`, …) and broke compilation.
  Reverted. The clean fix is accessors (a dedicated test-refactor pass), NOT struct
  exposure. Document the test as known-broken instead of blasting the codebase.
- ✅ **A codec that shells out to the `ffmpeg` BINARY at runtime needs NO
  `libavcodec` headers to compile.** `wubu_codec.c` (`wubu_codec_detect_type`/
  `wubu_codec_available` are pure; decode/encode/transcode shell out) rebuilds fine
  without ffmpeg dev packages. Don't assume a codec needs ffmpeg headers — check
  whether it links the lib or execs it.
- ❌ **Status was wrong — don't trust a "DONE" Cumulative Split Status line.** The
  2026-07-10 status claimed "39 splits, every separable subsystem is now its own leaf,
  make hosted incremental, work complete." A 2026-07-11 build-graph audit disproved
  it: 111 build-graph `.c` files were still ≥300 lines, and the B-series had extracted
  only ONE separable subsystem per parent (most parents stayed large). Concrete remaining
  work + an ordered backlog lives in `references/monolith-backlog-2026-07-11.md`. Rule:
  when you return to a long-running refactor, **re-audit the build graph** (line counts +
  grep for separable sections) instead of trusting the skill's own "complete" status. The
  status block is a historical note, not a guarantee.
- ❌ **When the HOST still CALLS an extracted function, that function must be NON-STATIC
  and declared in the internal header — or the link fails.** (B40 lesson, 2026-07-11.)
  Extracting `wubu_image_tar.c` from `wubu_image.c`: the tar module defined `rmtree` and
  `tar_write_dir` as `static`, but `wubu_image.c`'s `wubu_image_build` calls both. Result:
  `undefined reference to rmtree` / `tar_write_dir` at link. Fix: promote every extracted
  function the host (or any other TU) calls to non-static and declare it in the internal
  header (`create_layer_tar`/`rmtree`/`tar_write_dir` all got promoted; only the purely
  internal `tar_write_header`/`tar_write_file`/`remove_cb` stayed static). General rule:
  BEFORE cutting the block, grep the host for calls to each candidate function; if the host
  calls it, it's a cross-TU symbol, not a leaf-private one.
- ❌ **The opaque-struct anti-pattern was VIOLATED in 2026-07-11 and must not recur.**
  Commit `303de7e` (test_apps green) promoted all 7 app state structs
  (`CalcState`/`NotepadState`/`PaintState`/`TaskManagerState`/`RegeditState`/`FileManagerState`/
  `ControlState`) into PUBLIC headers and added a Paint instance API + stubbed `wm_create`.
  That contradicts this skill's hard rule ("Don't expose opaque structs to fix a test ...
  document the test as known-broken instead of blasting the codebase") and the project's
  "opaque structs + minimal includes" discipline. The test went green ONLY because internals
  were leaked. The prescribed fix is an ACCESSOR-REFACTOR PASS (add `calc_get_mode()`,
  `notepad_*()`, `paint_get_shape_count()`, `regedit_get_key()`, … to the app APIs and rewrite
  the test to use them), NOT struct exposure. If you find `303de7e` already merged, treat it as
  tech debt to unwind: revert the struct promotions, keep only the genuinely-correct parts
  (container_registry accessors, WM-recipe wiring, the `reg_search` brace fix), and re-document
  `test_apps` as known-broken pending the accessor pass.
- ❌ **`git mv` from `execute_code` needs ABSOLUTE paths** when the sandbox cwd is
  `/home/wubu`, not the repo root. `os.path.exists("src/foo.c")` (relative) returns
  False → "MISSING" and the move is skipped. Use `os.path.join(repo_root, ...)` for
  both src and dst, and pass `cwd=repo_root` to `subprocess`.
- ❌ **A restore can surface a `static`/macro collision** in the orphaned file.
  `apps/doom.c` defined `static float fabsf(float)` which conflicted with
  `wubu_math.h`'s `#define fabsf wubu_fabsf` + `float wubu_fabsf(float)` decl. Deleting
  the static def let the calls route to the math.h impl. Check for name clashes
  before restoring.
- ❌ **`wubu_doom_*` API lives in `wubu_freedoom.c`, NOT `doom.c`.** `doom.c` is a
  separate raycaster demo. Restoring the wrong file wastes a cycle — `grep` for the
  actual symbol definition before restoring.
- ❌ **apt install needs sudo; in a non-interactive shell it fails**
  (`sudo: a password is required`). Compositor rebuild (`libgbm-dev`/`libpixmin-1-dev`)
  was blocked here — document as FUTURE REBUILD rather than forcing.
- ✅ **Build-graph scan must check BOTH `.o` (OBJS vars) and `.c` (direct-compile
  recipes).** Checking only one form mis-classifies in-build files as excluded.

See `references/build-graph-audit.md` for the scan script.

## Dead/Build-Blocking File Protocol

## Variant: Syscall-Table-Driven Monolith (Dispatch Table at Bottom)

When the monolithic file is a syscall handler collection where the last section is a lookup table (`static const vsl_syscall_fn vsl_syscall_table[] = { ... }`) that references every handler by name:

1. **Must extract ALL handlers referenced by the table** — partial extraction leaves the table pointing at functions that no longer exist in any translation unit. Either extract all ~90 handlers to split modules in one pass, or leave them all in the original.
2. **Count handlers first**: `grep -c '^static int64_t vsl_sys_' <file>.c` — this is your extraction scope.
3. **Group by category**: process mgmt (~12), file I/O (~20), memory (~15), identity/credential (~20), socket/net (~15), signals/timers (~20), *at family (~12), io_uring/namespace/security (~10).
4. **The syscall table stays in the original** — it's the facade. Gut the original to: includes → table → bridge dispatch → helper functions. Everything else moves out.
5. **Internal header must forward-declare EVERY handler** the table references. Missing one = `undefined reference` at link.

**Files created**: `vsl_syscall_proc.c`, `vsl_syscall_fileio.c`, `vsl_syscall_memory.c`, `vsl_syscall_net.c` (socket/signal/timer/poll/*at/namespace). Depends on file size; 1664 lines → 4-5 modules of ~300-400 lines each.

**Common pitfall specific to this pattern**: the test target (`test_syscall` / `test_vsl`) compiles `.c` files DIRECTLY (not via `.o` objects). Do NOT put `.o` files in test target recipes — only `.c` source files.

## Pitfalls to Avoid
- ❌ Don't try to split everything at once — do 1 file per session
- ❌ Don't put `.o` files in test target recipes — test targets compile `.c` files directly, not link `.o` files. `$(RT)/vsl/vsl_memory.o` in a test target recipe is wrong; use `$(RT)/vsl/vsl_memory.c` instead.
- ❌ Don't fix bugs or refactor logic during extraction — keep implementations identical
- ❌ Don't forget to remove `static` from both forward decl AND definition
- ❌ Don't put `static` declarations in header files
- ❌ Don't redefine types in internal headers that the public header already declares
- ❌ Don't forget the `grep` for ALL Makefile references to the old .c file — OBJS variables AND direct-compilation lines (hosted binary, test targets, GUI build, screenshot tool) are all separate grep targets
- ❌ Don't extract context menus if they share dialog/action code with the main file — the menu API functions (_create, _add_item, _show, _hide) are usually coupled to dialog callbacks (_rename, _delete, _properties) that live in the same TU. Extract those action handlers FIRST, then the menu layer
- ❌ Don't put placeholder or stub extracted modules in the build — if the new .c file is empty or only includes the header, it doesn't belong in the Makefile yet
- ❌ Don't trust stale `.o` files — after splitting, old `.o` files from before the split sit on disk and provide symbols that mask missing-link errors. Run `make clean && make <target>` before declaring the split complete.
- ❌ Don't forget use-before-declare in C — when you expose a `static` helper as non-static, the host file's callers may be physically above the function definition. Add `#include "internal.h"` at the top of the host file (it has the forward declaration) to fix.
- ❌ **Don't leave a split half-wired — wire the new helpers to their call sites too.** A recurring failure mode: add the real implementation + opaque struct + Makefile edits, but leave the *call site* invoking an empty stub / fake notify. The build passes but the feature is still form≠function (a REAL_GAP). After a split meant to close a gap, grep the call sites and confirm they now invoke the real function, not a `wubu_notify_simple("...", "TODO")` placeholder. Concrete case: desktop Stream-3 — WM-side helpers (`reflow_icons_column`, `write_desktop_shortcut`, `auto_arrange` field) were added to `wm.c`, but the four ctxmenu stubs (`ctx_action_sort_by_name`, `ctx_action_create_shortcut`, `ctx_action_view_desktop`, `ctx_action_refresh`) were never rewired to call them, so the context menu still did nothing until the next session.
- ❌ **Makefile double-backslash continuation breaks `make hosted`.** Adding a `.c` to the inline hosted link recipe (line ~166) can leave a SECOND backslash at line end (`...wallpaper.c \\` + newline): the extra `\` escapes the newline, so `cc1` gets ` src/gui/wallpaper.c` (leading space) and fails with "No such file or directory" — while `make -n` dry-run looks fine and `make runtime` passes. Diagnose with `sed -n '169p' Makefile | tail -c 16 | od -c` (TWO `\` = broken, ONE `\` = good); fix with a byte-exact Python replace. Full recipe + fix in `references/makefile-line-continuation-bug.md`.
- ❌ Don't miss stale static duplicates across split modules — after extracting helpers to the internal header, sibling .c files may still have their own `static` copies of the same function. When the internal header declares them non-static (as it should), these collide at link time. Audit ALL sibling files for identically-named `static` functions, keep ONE canonical implementation, remove the rest. Example: after the VSL split, `vsl_process.c` and `vsl.c` each had `static` copies of `register_child_pid`, `find_free_vsl_pid`, and `vsl_openat` — all duplicates of the implementations in `vsl_syscall.c`.

## Pitfalls Added 2026-07-09 (monolith-split batch 2)

- ❌ **Don't split by 1-indexed line ranges via `raw[start:end]`.** Multi-range deletion
  shifts indices and corrupts the host (this cost several iterations on `wubu_proton.c` /
  `term.c` — `g_proton` got deleted, functions truncated). Use the brace-counting
  extractor (Step 4) which finds bodies by signature + depth-matched `{}` and builds a single
  remove-mask. Reserving `patch` for tiny (<40 line) single-block moves.
- ❌ **A `static` global state struct can't satisfy an `extern` from another TU.** When a
  submodule references the host's global (`g_proton`), the host must define it **non-static**
  (`ProtonState g_proton = {0};`). The internal header's `extern` then resolves; leaving it
  `static` surfaces `undefined reference to g_proton` only after the referencing code moves out.
- ❌ **Render modules hold draw functions only — state-mutating handlers stay in the host.**
  `term_render.c` grabbed `term_handle_mouse_content` (a mouse *handler*) and it had to
  be moved back because `term.c` calls it. Keep render modules to `fb`-drawing fns; keep
  input/handler fns in the host. Make a cross-TU handler non-static + declare in internal header.
- ❌ **Internal headers exposing `static inline` theme helpers MUST `#include "wubu_theme.h"`.**
  `term_internal.h` declared `tc()/th()` returning `WubuThemeColors`/`WubuTheme` but
  omitted the theme include → "unknown type name" for every render fn. Add the include.
- ❌ **`_XOPEN_SOURCE` must precede ALL system headers for `FTW_*` constants.** For `rm_rf`/
  `nftw` code using `FTW_DEPTH`/`FTW_PHYS`, put `#define _XOPEN_SOURCE 700` as the FIRST line
  of the new module. The older `#ifndef FTW_*` redefinition workaround is inferior — a clean
  `#define` before includes is the real fix and avoids redefinition warnings.
- ❌ **Don't `#include "wubu_metal_internal.h"` from a new metal submodule.** It pulls
  `<math.h>` AFTER `WUBU_NO_LIBM` defines `log`/`exp` as macros → "mathcalls.h: expected ';'
  before 'extern'" parse break. Mirror `wubu_metal.c`'s discipline: `#include "wubu_metal.h"` +
  local `extern` decls of shared globals + only subsystem headers. (`wubu_metal.c` DRM split
  was abandoned this session as too fragile — it is off the hosted hot path; revisit only with
  a dedicated metal internal-header pass.)
- ❌ **Nested `#ifdef WUBU_USE_DRM` blocks don't survive naive copy-extraction.** Copying
  "content between outer #ifdef/#endif" leaves unbalanced directives (inner nested guards).
  Wrap the extracted file in ONE outer `#ifdef WUBU_USE_DRM` and strip the inner/duplicate guards.
- ❌ **Brace-counting `extract(sig)` MUST require `'{'` on the signature line.** A monolith's
  forward-declaration block (e.g. lines 64-68 `static void ex_worker_copy(...);`) contains the
  same signature substring as the real definition (line 1516, with `{`). A locator that matches
  `sig in l and '(' in l` returns the *first* hit = the forward decl, and the remove-mask then
  deletes everything from there to the definition — silently wiping ~1500 lines of host. The
  brace-counting extractor (Step 4) and its reference `references/brace-counting-extractor.md`
  both require `'{' in l`. If you hand-roll a locator, copy that guard. After extraction, sanity
  check `wc -l host.c` — a sudden 10x shrink means you matched a forward decl, not a definition.
  Restore via `git checkout <commit> -- host.c` and re-run with the `{`-guard.

- ❌ **A clean leaf that touches >5 shared `static` helpers is NOT a clean leaf.** When the
  candidate block calls host-defined statics that the rest of the host ALSO uses
  (`ex_file_compare`, `ex_sort_entries`, `ex_get_extension`, `ex_tree_find`, `ex_tree_free`,
  `ex_strcasecmp`, …), extracting it forces promoting all of them to the internal header and
  de-static-ing both definition and every caller. That's high-risk churn for little gain.
  **Decision rule:** if extraction requires externalizing >~5 shared static helpers, drop that
  subsystem and pick a genuinely self-contained one instead (file-op workers, 9P backend, PNG
  encoder, config generators, util/fs subs). The parent stays a bit larger — that's fine.
- ❌ **When a helper is needed by >1 TU AND is generically useful, promote it to the PUBLIC
  header, not just the internal one.** `png_encode_rgba` lived in `wubu_screenshot.c`; after the
  PNG encoder moved out, BOTH the new `wubu_screenshot_png.c` and the host's
  `wubu_screenshot_to_clipboard` needed it. Promote it to `wubu_screenshot.h` as a reusable API
  (`size_t png_encode_rgba(const uint32_t*, int, int, uint8_t**)`) — it's a real, reusable PNG
  encoder, not a private detail. Internal header = cross-TU of one module; public header =
  cross-module reusable capability.
- ❌ **Extraction can pull in a NEW link library — keep the link line's LIBS in sync.** Moving the
  PNG encoder out brought `zlib` (`compress`/`deflate`) into `wubu_screenshot_png.c`. The hosted
  link already had `-lz`, so `hosted` built — but a test recipe that links the screenshot files
  WITHOUT `-lz` will fail with `undefined reference to compress`. Rule: grep the new module for
  library calls (`zlib`, `sqlite3`, `xkbcommon`, …) and confirm every link target that compiles
  it carries the matching `-l<lib>`. The hosted link is NOT the only place that matters.
- ❌ **A test FAIL after a split is not automatically your regression — check for a pre-existing
  broken recipe first.** `test_gui_screenshot` links `hosted.c` (which has a `main`) AND the
  test file (which also has a `main`) → `multiple definition of 'main'`. That recipe was broken
  before any split and fails identically on the prior commit. Before "fixing" a failing test,
  confirm it's caused by YOUR change: `git stash` your Makefile/module edits (or `git show
  HEAD~1:Makefile`) and rebuild the test, or read the recipe to see if it double-links a `main`.
  Don't mask a pre-existing defect by hacking the recipe to suit your split.
- ✅ **Compile each new module standalone BEFORE wiring the Makefile.** After extracting, run
  `gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM -I<dirs> -c new_module.c -o /tmp/x.o`
  (mirror the flags the pattern rule uses) and fix include/static issues in isolation. Only then
  add it to `GUI_OBJS` / hosted link / test recipes. This catches `unknown type`, missing
  `extern` global, and `static follows non-static` errors ~10× faster than a full `make hosted`.

- ❌ **When the new module is a SHARED leaf (parser/encoder/crypto), blanket-replace the parent
  `.c` in the Makefile instead of grep-and-patch.** A reusable leaf (e.g. `wubu_json.c` split
  from `wubu_settings.c`) is pulled in by MANY recipes — `GUI_OBJS`, the hosted link, AND every
  `test_*` recipe that compiles the parent `.c` directly (`test_pkgmgr`, `test_deploy`,
  `test_wm` all needed it). A targeted "add after the GUI_OBJS line" patch misses those
  and fails at link with `undefined reference to json_find`. Do a single
  `content.replace("$(GUI)/wubu_settings.c ", "$(GUI)/wubu_settings.c $(GUI)/wubu_json.c ")`
  across the whole Makefile (Python, not `patch`) — then `grep -c` to confirm all expected
  hits moved. See `references/reusable-leaf-extraction.md`. The B5 batch (mime desktop parser +
gamelib scanners, commit `d1dafb7`) adds two wrinkles — when the leaf's types/globals live in
the host `.c`, and a dedup-aware blanket Makefile wiring script — in `references/reusable-leaf-b5-recipe.md`.

- ❌ **Cross-module SYMBOL COLLISION is distinct from "static follows non-static".** After
  extraction the link may fail with `multiple definition of 'get_dir_size'` even when each TU
  compiles fine — because the SAME function name was defined in 2-3 OTHER `.c` files
  (`wubu_proton_util.c` AND `wubu_trash.c` both had `get_dir_size`; the gamelib copy collided).
  This only surfaces at link time, after move, so: before promoting/renaming a helper, grep the
  whole tree for the name (`grep -rln ' get_dir_size(' src/gui/*.c`). If it already exists
  elsewhere, RENAME the extracted copy (e.g. `gamelib_get_dir_size`) in the module, its internal
  header decl, AND the host's caller — don't leave a triplicated symbol. Caught this on the
  `wubu_gamelib_scan.c` split (commit `d1dafb7`).

- ❌ **When a reusable leaf's TYPES/GLOBALS live IN the host `.c`, the new PUBLIC header must
  carry them and BOTH files include it.** Extracting `wubu_json.c` from `wubu_settings.c`: the
  `JsonToken` struct, `JsonType` enum, and the static token-arena globals (`g_json_tokens`,
  `g_json_token_count`, `g_json_parse_error`) were all DEFINED in `wubu_settings.c`. The fix was
  to move those definitions into `wubu_json.h` (globals as `extern`), making `wubu_json.h` the
  single source of truth that both `wubu_settings.c` and `wubu_json.c` `#include`. If you leave
  the type in the host and `extern`-declare it in the new header, you get `redefinition of
  typedef` / `unknown type name` — move the DEFINITION into the shared header instead.

- ✅ **Dedup-aware blanket Makefile wiring for a whole parent→submodule family.** Once several
  parents each have submodules, doing per-recipe patches is fragile (you miss the recipe that
  compiles the parent inline, e.g. `test_explorer` compiling `wubu_mime.c` without
  `wubu_mime_desktop.c`). Use ONE Python pass that, for each `parent.c -> [sub1.c, sub2.c, ...]`
  mapping, finds every recipe line containing `parent.c ` and appends the missing submodules
  (skip any already present on that line → no duplication in `GUI_OBJS`). Full script in
  `references/reusable-leaf-extraction.md`. This is what made the B5 batch (mime + gamelib)
  verify green across ALL test targets in one pass.

- ✅ **WuBuGrep monolith → module split (separate compile units, 2026-08-21).** When
  the goal is *both* legibility AND a speed win, split into separate `.c` TUs
  (NOT the `#include` shim) joined by one `wubre_internal.h` that carries shared
  struct DEFINITIONS + cross-module function bridges. Two non-obvious wins:
  (a) **whole-buffer single-pass NFA** — re-admit `re->start` into the active
  set at EVERY step (unconditional, when `re->start>=0`) so an unanchored match
  can begin anywhere in the buffer; gating re-admit on an `unanchored` flag
  alone breaks `^`-anchored mid-buffer restarts. (b) **SIMD literal prefilter +
  2-literal `.*` window** as a fast reject (`wub_simd_has_window`), built in-house
  (no vectorscan). Always gate the split with the 281/281 GNU-grep parity diff +
  unit + ASan, and diff on a **fixed-seed corpus** (a re-randomized corpus
  between grep and wubugrep runs looks like an engine bug but isn't). Full recipe
  in [`references/wubugrep-module-split-2026-08-21.md`](references/wubugrep-module-split-2026-08-21.md).

- ✅ **Compile each new module standalone BEFORE wiring the Makefile.** After extracting, run
  `gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM -I<dirs> -c new_module.c -o /tmp/x.o`
  (mirror the flags the pattern rule uses) and fix include/static issues in isolation. Only then
  add it to `GUI_OBJS` / hosted link / test recipes. This catches `unknown type`, missing
  `extern` global, and `static follows non-static` errors ~10× faster than a full `make hosted`.


## Orphaned-Declaration Trap (WuBuOS `-Wno-implicit-function-declaration` hides it)

When you extract functions from the monolith into a new module, the **public
header's declaration set can drift from the module's definition set** in TWO silent
ways that the build will NOT catch (WuBuOS compiles with `-Wno-implicit-function-declaration`,
so implicit decls compile, and with `-Wno-unused-function`, so an unreferenced
definition is silent):

1. **Declared but undefined** — the header declares `wubu_cv_save_ppm(...)` but the
   function body was dropped during extraction and never re-added to the new module
   (or any other TU). The header looks complete; the linker disagrees only if a
   test/main actually *calls* it. Catch it by grepping for the definition across the
   tree and adding a real implementation (don't leave an orphaned decl).
2. **Called but undeclared** — the test (or another TU) calls `wubu_cv_load_png(...)`
   directly, the new module *defines* it, but the public header never *declares* it.
   The compiler treats it as an implicit `int` decl — compiles, links (the def is
   present), but it is a latent type-safety gap and a real defect. After moving a
   function set into a module, **diff the header's decl list against the module's
   def list** and add every missing `wubu_*_load_*` / `wubu_*_save_*` declaration to
   the header. (Concrete case 2026-07-09: `wubu_canvas_io.c` defined 4 `wubu_cv_load_*`
   + `save_ppm`; the header declared `save_ppm` but not the loaders, and had
   `save_ppm` with no definition — fixed by declaring the loaders and implementing
   `save_ppm`.)

**Rule:** after an extraction, run `grep -nE '^int wubu_X_|^static int wubu_X_' module.c`
and `grep -nE 'wubu_X_' public.h`, then reconcile both lists by hand. Don't rely on
the build to surface the mismatch — WuBuOS' warning flags suppress the usual signal.

## Pitfalls Added 2026-07-10 (B5 mime/gamelib + B6 startmenu splits)

- ❌ **A submodule that calls a `static` helper defined ONLY in the host `.c` is an
  implicit-int trap, not a clean split.** When the extracted module calls `tc()`
  (`static const WubuThemeColors *tc(void)` private to `startmenu.c`), the
  new `.c` has no declaration → C compiles it as an **implicit `int`** (WuBuOS
  builds with `-Wno-implicit-function-declaration`), so `tc()->win_title_text`
  becomes `int->win_title_text` → `invalid type argument of '->' (have 'int')`.
  Two fixes, pick by intent:
  (a) **Replace the private helper with the public API** it wraps — `tc()` just
      returns `wubu_theme_colors()`, so the module calls `wubu_theme_colors()`
      directly (and `#include "wubu_theme.h"`). Preferred when the private helper
      is a one-line wrapper over a public fn.
  (b) If the helper is non-trivial, promote it to the internal header as non-static
      and `#include` the internal header in BOTH the host and the module.
  Either way, the module MUST `#include` the header that declares what it calls
  (e.g. it needs `wubu_theme.h` for `wubu_theme_colors()`).

- ❌ **`hermes_tools.read_file` / `read_file` on a ~700-line file can return a dict
  WITHOUT a `content` key** (size-truncation / pagination notice) — a Python
  `read_file(...)["content"]` then `KeyError`s and aborts the extractor mid-way.
  For files you're going to parse with `split("\n")`, **read them via terminal
  `cat file > /tmp/x.c` first, then `open()` with plain Python** — or read the REAL
  file (not a `/tmp` copy) for the surgical deletion pass. Burned once on
  `wubu_gamelib.c` (~700 lines) during B5; the `/tmp` copy + real-file two-source
  approach resolved it.

- ❌ **A `*/` inside a block comment prematurely closes it.** Writing
  `* the vbe_*/theme APIs.` in a `/** ... */` comment ends the comment at `vbe_*/`,
  then `theme APIs.` is parsed as code → "unknown type name 'theme'". Write
  `vbe_* and theme` (no slash-star). Burned on `wm_taskbar.c` (B10).

- ❌ **GUI_OBJS feeds `make runtime`, NOT the hosted binary.** The `hosted:` target
  links an INLINE recipe (dozens of `.c`/`.o` on one line, e.g. line ~173) — adding a
  new `.o` to `GUI_OBJS` does NOT make it appear in `hosted`. You must ALSO add it to the
  inline hosted link line. Conversely, test targets that compile `.c` directly need the
  new `.c` too. Three distinct places: GUI_OBJS + hosted inline link + test recipe.
  (The "Convert Hosted/Main Inline-Recompile Recipe to Incremental Object Linking"
  variant moves hosted to `HOSTED_OBJS` so only ONE place needs the `.o` — preferred.)

- ✅ **Promote shared helpers to the internal header (non-static) to prevent double-coding.**
  When a `static` helper is used by >1 submodule (or by the host + a module), declare it
  `extern`/non-static in the module's internal header and remove `static` from both the
  forward declaration AND the definition in every TU. This is the explicit alternative to
  the ">5 shared helpers → drop" rule: the user may direct you to IGNORE that rule and
  split the coupled core anyway — in which case promoting helpers is the correct path
  (done for `explorer` tree + `wm` taskbar, B8-B10). After promoting, grep
  ALL sibling files for the name to catch stale `static` copies (see symbol-collision pitfall).
  move the globals' DECLARATIONS into the internal header as `extern` and add
  `#include "module_internal.h"` to the host.** `startmenu.c` kept its
  `g_open / g_program_db / g_search / g_recent / g_tree_*` definitions in the host
  (lines 84-98) and the new `startmenu_internal.h` declared them `extern`;
  both `startmenu_search.c` and `startmenu_tree.c` `#include` the
  header and reach the shared state. The host still OWNS the definitions (no
  duplicate), so there is exactly one copy — no `multiple definition`. This is the
  canonical "shared global state across sub-modules" pattern; prefer it over
  passing every global as a parameter.

- ❌ **Brace-counting `extract(sig)` must handle signatures WRAPPED across two
  lines.** `static int scan_steam_appmanifest(const char *manifest_path, char
  *appid, size_t aid_len, \n  <continuation>) {` has `{` on the NEXT line, so a
  locator requiring `sig in l and '{' in l` never matches and raises
  `def not found`. Fix (now in `references/brace-counting-extractor.md`): match
  ALL signature WORDS, then walk forward to the line containing `{`. Forward
  declarations are still skipped because they end in `;` (no `{` on any following
  line) and the walk never closes on them.

- ✅ **Dedup-aware blanket Makefile wiring is REQUIRED once ≥3 parents have
  submodules.** The B5 batch revealed that a targeted "add after GUI_OBJS" patch
  misses the recipe that compiles the parent `.c` inline (e.g. `test_explorer`
  compiling `wubu_mime.c` WITHOUT `wubu_mime_desktop.c` → `undefined reference to
  parse_desktop_file`). The single Python `content.replace("parent.c ", "parent.c
  sub1.c sub2.c ")` pass (dedup-guarded, so `GUI_OBJS` isn't double-patched) is the
  fix — see the existing "Dedup-aware blanket Makefile wiring" pitfall. After
  running it, `grep -c` the parent string to confirm every recipe line got the
  submodules (8 hits in B5 across `wubu_proton/mime/gamelib/deploy/settings/
  explorer`).

- ❌ **TWIN-BASENAME FILES break the blanket-dedup Makefile replace.** When the
  SAME basename exists in two dirs (e.g. `src/gui/wubu_session.c` AND
  `src/runtime/wubu_session.c` — the runtime one a small unrelated stub), a
  blanket `content.replace("$(GUI)/wubu_session.c ", ...)` only matches the GUI
  occurrences; the `$(RT)/` recipes are untouched (correct — they compile a
  DIFFERENT file). BUT verify with `grep -c` you didn't need to patch the `$(RT)/`
  side. Concrete B7 case: the brace-counting extractor pulled `wubu_session_autostart.c`
  from `src/gui/wubu_session.c`; the 4 recipes using `$(RT)/wubu_session.c` were
  correctly left alone because that file is a distinct stub. Rule: when splitting a
  file that shares a basename with another file in a different dir, grep BOTH
  `$(GUI)/` and `$(RT)/` (and any other prefix) and reason about each independently
  — don't assume one replace covers all.

- ❌ **Statics/buffers declared ABOVE the extracted block get STRANDED in the
  host.** The brace-counting extractor matches a function *signature* and walks to
  its `{`; any `static` globals/buffers declared on lines BEFORE the first extracted
  function stay in the host while the function that uses them moves to the module →
  `undeclared (first use in this function)`. Concrete B7 case: `wubu_session.c` had
  `g_autostart_path[512]` / `g_session_path[512]` buffers at lines 11-12, ABOVE
  `session_autostart_path()` (line 33, the extract start). The extractor took the
  function but left the buffers in `wubu_session.c`; the module then failed with
  `g_autostart_path undeclared`. Fix: before extracting, scan the lines immediately
  above the first function you'll extract for `static` globals/buffers that the
  extracted functions reference, and move them into the new module (together with
  the function definitions). Same trap for the state array `g_autostart[]
  `/`g_autostart_count` — they lived above the extracted block too and had to be
  relocated. General rule: the extractor's remove-mask is function-bounded, so
  NON-function declarations in the same region must be handled separately (manually
  moved, not masked). See `references/stranded-statics-above-block.md`. Repro +
  extraction-script guard in `references/stranded-statics-above-block.md`.

## Pitfalls Added 2026-07-06 Learnings: wubu_metal.c Audio Split

A separate trap from the "stale `.o`" one: if you fix a bug in the extracted module
but `make test_<t>` still reports the OLD failure identically, the **test binary
itself may be stale** — e.g. a previous run of `make test_<t>` hung or segfaulted
before the link completed, so `make` considers the binary newer than the sources and
skips relinking, or the cached binary predates your edit. This is distinct from stale
`.o` masking *missing symbols*; here a *valid* binary is cached with the old behavior.
Fix: `rm -f src/.../test_<t>; make test_<t>` (or `make clean`). Suspect this whenever
"the code is fixed but the test output didn't change at all."

## Variant: Gut Monolith to Shim (Too-Coupled Module)

When a subsystem accesses too many `static` globals and helpers in the host file to extract cleanly:

1. **Shim** — leave the host `.c` as a thin shell: just the global state + `#include` of the new module's internal header
2. **Sub-module** — extract the *least* coupled subsystem first (preview pane, not zip; HTTP client, not OCI core). Don't fight tight coupling — shim around it.
3. **Externalize globals** — move the global state typedef into the internal header. The host `.c` defines it, sub-modules get `extern` access via `#include "module_internal.h"`.

```c
// main_monolith.c  —  was 2598 lines, now stub
#include "module_internal.h"
// Global state definition lives here
ExExplorerState g_explorer = {0};
```

```c
// module_internal.h
#include "public_header.h"
#define WUBU_STRCPY(...) ...
extern ExExplorerState g_explorer;
void ex_update_breadcrumbs(ExExplorerState *ex);
void ex_add_to_history(ExExplorerState *ex, const char *path);
```

```c
// module_preview.c
#include "module_internal.h"
void ex_render_preview(ExExplorerState *ex, ...) {
    /* accesses g_explorer via parameter or extern */
}
```

**Deferred:** If a module calls ~5+ static helpers from the host (like `ex_update_breadcrumbs`, `ex_add_to_history`, `ex_sort_entries` for explorer), extract those helpers to the internal header FIRST before extracting the module itself.

## Variant: Extract Render Layer as Separate Module

When a large GUI file has a cleanly-separated rendering layer (functions that take `uint32_t *fb, int fb_w, int fb_h` params and only draw, never mutate state):

1. **Move theme helpers to internal header** — Since both the main .c and the render module need `tc()`, `th()`, `ex_row_h()`, etc., move them to the internal header as `static inline`:
   ```c
   static inline const WubuThemeColors *tc(void) { return wubu_theme_colors(); }
   static inline int ex_row_h(void) { return th()->rounded_buttons ? 24 : EX_ROW_H; }
   ```
   This gives each TU its own copy with zero overhead and no symbol clash.

2. **Move small shared utilities too** — `ex_dirname_safe` is also a good candidate for `static inline` in the internal header since it's used by both the main .c and modules like the zip handler.

3. **Move render forward declarations** — Remove `static` from render function forward declarations in the main .c, declare them in the internal header.

4. **Create render module** — The render .c just needs `explorer_internal.h` (which gives it `explorer.h` types, theme helpers, VBE interface includes, and the `g_explorer` extern). It includes `../kernel/vbe.h` and `wm.h` for VBE functions and taskbar height.

5. **Keep `ex_draw_tree_node` static** — It's only called from other render functions in the same module. No need to expose it.

6. **Makefile: FOUR places to update** (not two):
   - `GUI_OBJS`: add `.o` file
   - **hosted binary** (line ~166): add `.c` file to direct-compile list
   - **test binary** (test_explorer line ~452): add `.c` file
   - **hosted_test binary** (line ~469): add `.c` file
   
   Missing any ONE of these causes a link failure from a stale- or fresh-build scenario.

7. **Verify from clean** — Always `make clean && make test_<target>` and `make clean && make runtime` to catch stale `.o` masking.

## Variant: Dedup-First Extraction (Multiple Inline Duplicates)

When a monolithic file contains the same algorithm duplicated inline in multiple functions (e.g., VT100/ANSI parser copied in both `term_process_pty_output` and `term_process_container_output`):

1. **Identify the superset** — One version is usually the superset (PTY had 256-color SGR, full ED/EL modes, DECSC/DECRC). Use that as the canonical implementation.

2. **Create polymorphic abstraction** — Define a struct (e.g., `TermScreen`) with flat pointers to the common fields shared by both backing structs (both `TermPtySession` and `TermContainerSession` have identical `screen`, `attrs`, `cursor_x`, `cursor_y`, `cur_attr`, `cur_fg`, `cur_bg`, `saved_cursor_x/y` layouts).

3. **Binder functions** — Add `term_screen_bind_pty()` and `term_screen_bind_container()` that populate the `TermScreen` pointers into the respective structs.

4. **Shared parser module** — Move the canonical parser to a new `.c` (e.g., `term_ansi.c`) that operates on `TermScreen*`. No globals — state is per-call or bound to the screen.

4. **Thin wrappers in host** — Replace both inline copies with wrappers that:
   - Read from the FD
   - Bind the appropriate screen
   - Call `term_ansi_parse()`

5. **Per-call parser state** — Don't try to share parse state across calls (the originals used buggy `static` state shared across all tabs). Per-call state is a correctness improvement and a prerequisite for dedup.

**Benefits**: Eliminates ~410 lines of duplicate code, gains full feature parity for container sessions, single source of truth.

## Variant: Convert Hosted/Main Inline-Recompile Recipe to Incremental Object Linking

**Session 2026-07-09 — the "rebuilding takes too long" root cause + fix.**

When the user reports slow rebuilds, monolithic `.c` files are only half the story.
A bigger, silent waste is a **link recipe that recompiles every `.c` inline** instead of
linking the `.o` objects the pattern rules already built. This is the single highest-leverage
restructure for rebuild speed — do it *before* or alongside splitting the monoliths.

**Detection:** open the `hosted:` (or `main:`) target. If its `$(CC) …` link line lists
`$(GUI)/x.c $(RT)/y.c $(KERNEL)/z.c …` directly (dozens of `.c` paths), it recompiles the
whole TU on every `make hosted` even when you touched one file. Confirm with timing:
`make clean && time make hosted` vs `touch src/gui/one.c && time make hosted`.
Before the fix both were ~9s; after, clean 9s but incremental **0.5s** (one `.o` + relink).

**Fix pattern:**
1. Build a `HOSTED_OBJS` list of `.o` paths the directory pattern rules already produce
   (e.g. `$(GUI)/wm.o`, `$(RT)/styx.o`). Drop the `.c` paths from the link line.
2. Make `hosted:` a **link-only** target: `hosted: $(HOSTED_OBJS)` then
   `$(CC) $(CFLAGS) $(HOSTED_OBJS) -l… -o $(HOSTED)/wubu`. Editing one `.c` now recompiles
   only that one `.o` (via the pattern rule) and relinks.
3. Watch for **flag mismatches the old inline recipe was masking** — converting to object
   linking surfaces these as link errors:

| Symptom (post-conversion link error) | Cause | Fix |
|---|---|---|
| `multiple definition of 'main'` (e.g. `wubu_archd.c` / `wubu_holyd_lifecycle.c`) | Those `.c` gate a daemon `main` behind `#ifndef WUBD_TEST_MAIN`; the inline recipe compiled everything with `-DWUBD_TEST_MAIN`, suppressing them. Your pattern-rule `.o` lacks it. | Variant rule `$(HOSTED)/archd_hosted.o: $(RT)/wubu_archd.c` → compile with `-DWUBD_TEST_MAIN`. Link `archd_hosted.o`, not `wubu_archd.o`. |
| `relocation R_X86_64_32S against '.rodata' can not be used when making a PIE object` | Kernel `.c` built by the kernel pattern rule with `-fno-pie -mcmodel=kernel`; inline recipe recompiled them with default (PIE) `CFLAGS`. | Variant rules `$(HOSTED)/%_khosted.o: $(KERNEL)/%.c` compiling with default `CFLAGS` (PIE-capable). Link the `_khosted.o` variants, not the kernel `.o`. |
| `undefined reference to 'oci_http_connect'` etc. | The feature's real dependency (e.g. `oci_http_client.c`) was never in the inline recipe either — the feature was silently broken (form≠function). | Add the dependency `.o` (e.g. `$(RT)/oci/oci_http_client.o`) to `HOSTED_OBJS`. |
| Only `src/kernel/vbe.c` needs `-DVBE_HOSTED` | Inline recipe compiled ALL files with `-DVBE_HOSTED` (wasteful); bare-metal `kernel.elf` must keep the real VGA path. | Rule `$(HOSTED)/vbe_hosted.o: $(KERNEL)/vbe.c` with `-DVBE_HOSTED`; link `vbe_hosted.o`. |

4. **Stale/conflicting object trap:** the original `HOSTED_OBJS` may list kernel `.o` from the
   *kernel* pattern rule (built `-fno-pie`) — unusable for the PIE hosted link, which is *why*
   the inline recipe recompiled them. After conversion, point the hosted link at the
   `*_khosted.o` variants and remove the bare-metal kernel `.o` from `HOSTED_OBJS`.

**Verification:** `make clean && make hosted` (must succeed), then
`touch src/gui/<one>.c && make hosted` (must recompile exactly ONE `.o` + relink, fast).
Run `test_hosted` + affected GUI tests to confirm runtime parity.

**Apparent "hang" in networking tests (form≠function, not a real hang):** tests that spawn a
background HTTP server (python `http.server`) and call real fetch code can *look* hung because
(a) `stdout` is fully buffered so `RUN_TEST` prints don't flush, and (b) a **lingering server
child from a prior interrupted run** holds the port. Always run with `stdbuf -oL -eL ./test_bin`
to see progress, and `pkill -f http.server` stale children before re-running. The test almost
always *completes* — the "hang" was a buffering + port-collision artifact.

**`db_query(sql, NULL, out)` gotcha:** a NULL callback never copies rows into `out`. If a
search returns a positive count but callers find empty structs, add a real sqlite3 callback
that `strncpy`s each column into the `out` array (see `wubu_pkgmgr.c` `cb_search`).

See `references/hosted-incremental-link.md` for the exact before/after Makefile recipe.

## Authoritative backlog / status

- `references/monolith-backlog-2026-07-11.md` — START HERE each session: ordered candidate list + the "status was wrong" warning.
- `references/monolith-b50-b67-status.md` — post-third-pass (B41–B67) authoritative state: every extracted leaf, parent line counts, the one remaining cross-dir `wubu_proton_dxvk_*` duplicate (dedup task). Re-read before extracting anything — the separable leaves are DONE; do not re-extract them.

## Post-Extraction Verification: Dedup Scan

After extracting shared utility code to a header (crypto, hash, string), CHECK sibling files for stale duplicates:

```bash
# After creating wubu_crypto.h, find stale SHA256/CRC32 copies
grep -rn 'sha256_digest\|sha256_file\|wubu_crc32' src/runtime/*.c | grep -v 'wubu_crypto\|wubu_image'
# If hits appear, the sibling file has its own copy → replace with #include + thin wrapper
```

```bash
# General dedup: find duplicated function bodies across sibling .c files
grep -rn 'static void sha256\|static uint32_t crc32\|static.*sha256_digest' src/*.c | grep -v test
# Any output = stale duplicate → migrate to shared header
```

## Session 2026-07-06 Learnings: wubu_metal.c Audio Split (Monolithic → Modular)

**Task**: Split audio engine from wubu_metal.c into dedicated src/audio/ module

**Changes made**:
- Removed ~400 lines of ALSA/PulseAudio/PipeWire backend code from wubu_metal.c
- Delegated to existing `src/audio/wubu_audio.c` (DAW + Furnace tracker + SF2 synth + AI plugins + MIDI)
- Kept wubu_metal.c audio API as simple stubs returning -1 (audio not configured)
- Removed Vulkan surface creation code (future wubu_vulkan.c module)
- Fixed broken test_metal build: missing `../shell/wubu_shell.h` → added weak forward declaration for `wubu_shell_run`
- Updated BATTLESHIP.md: wubu_metal.c gap count reduced 55 → **25** (audio gaps moved to proper module)
- Updated slate.md, STATE.md, README.md with audio engine module info

**Key learnings**:
1. **Check existing modules first** — src/audio/ already had full engine (1990 lines). Don't rewrite — delegate!
2. **Keep API surface identical** — wubu_audio_init/shutdown/submit/cpu_load signatures unchanged; callers outside don't care
3. **Weak symbol pattern for test stubs** — `__attribute__((weak)) int wubu_shell_run(int w, int h)` lets test build override with stub while metal build links real impl
4. **Stale .o files mask missing symbols** — Always `make clean && make test_<target>` after splitting
5. **Documentation updates must be atomic** — BATTLESHIP.md, slate.md, STATE.md, README.md all updated in same commit

**Verification**: All tests pass — holyd 33/33, vsl 83/83, metal 5/5, audio 14/14, runtime clean build

---

## Session 2026-07-06 Learnings: HolyC REPL Persistent Variable Fix

**Problem**: HolyC REPL persistent variable across evals failed — `I64 x = 123;` in first eval, then `x + 10` in second eval returned garbage instead of `133`.

**Root Cause (3 bugs in `holyc_codegen.c` and `wubu_holyd.c`):**
1. **Global var load check**: First global variable gets `stack_offset = -0 = 0`. HC_AST_IDENT check `if (off < 0)` treated offset 0 as local (stack-relative), not global (RIP-relative). Fix: `if (off <= 0)`.
2. **Missing runtime patches for IDENT loads**: HC_AST_VAR_DECL (stores) recorded `global_patches` for runtime fixup, but HC_AST_IDENT (loads) did not. First eval's disp32 baked in, second eval used wrong offset. Fix: IDENT global loads now record patch info (patch_pos, global_offset).
3. **Stale `global_patches` preserved across compilations**: `hc_gen_init` saved/restored `global_patches`, but these are per-compilation ephemeral data. Second eval inherited first eval's patches pointing to wrong instruction offsets. Fix: `hc_gen_init` clears `n_global_patches = 0` (don't preserve).

**Pattern for JIT runtime patching:**
- Compiler emits placeholder disp32 for RIP-relative global accesses
- Records patch positions in `global_patches[]` with `code_patch_pos` (disp32 location) and `global_offset` (data section offset)
- At runtime after final `code_size` known: `disp32 = code_size + global_offset - patch_pos - 4` (RIP after instruction = exec + patch_pos + 4)
- Patch both STORE (VAR_DECL) and LOAD (IDENT) instructions
- Never preserve patches across compilations — they're tied to specific code layout

**Files modified**: `src/compiler/holyc_codegen.c` (HC_AST_IDENT patch recording, hc_gen_init clear), `src/runtime/wubu_holyd.c` (patch formula fix)

**Verification**: `make clean && make test_holyd` → 33/33 tests pass (was 31/32)

---

## OCI Split Session Learnings (2026-07-05)

### 1. JSON Helpers as `static inline` in Internal Header
For pure utility functions (JSON parsing, string helpers) used across multiple submodules, declare them as `static inline` in the internal header instead of a separate `.c` file. This:
- Avoids extra compilation unit
- Zero overhead (inlined at call site)
- Self-contained — no forward declaration needed
- Example: `oci_json_find_string`, `oci_json_copy_string_value`, `oci_json_find_int`

### 2. SHA256 Wrapper Pattern
When crypto lives in a shared header (`wubu_crypto.h`) with different API (`wubu_sha256_digest` vs old `sha256_digest`), add a wrapper in the internal header:
```c
static inline void sha256_digest(const void *data, size_t size, char *out_hex) {
    wubu_sha256_digest(data, size, out_hex, 65);
}
```
All submodules include the internal header and get the compat wrapper automatically — no code changes in extracted modules.

### 3. Test Target: Compile All Modules Directly
Follow EDR pattern: in `test_oci` target, list all `.c` files explicitly instead of relying on object files:
```makefile
test_oci:
	$(CC) ... -I$(RT)/oci \
		$(RT)/oci/oci_http_client.c $(RT)/oci/oci_image_config.c ... \
		$(RT)/wubu_image.c $(RT)/wubu_container.c $(RT)/wubu_oci_test.c \
		-o $(RT)/wubu_oci_test -lm
```
This ensures **no stale `.o` files can mask missing symbols**. Always run `make clean && make test_oci` before declaring success.

### 4. Pattern Rule Required for `make runtime`
Even with `RT_OBJS` listing all `.o` files, `make runtime` uses pattern rules to build objects. Add subdirectory pattern rule:
```makefile
$(RT)/oci/%.o: $(RT)/oci/%.c
	$(CC) $(CFLAGS) -I$(RT) -I$(RT)/oci -I$(COMP) -I$(JIT) -c $< -o $@
```

### 5. HTTP Client + Registry Dependency Order
In test target compilation, order matters: HTTP client must be compiled before registry client (which uses it). List dependencies in dependency order.

### 6. Largest Module First
HTTP client (360 lines) was the largest due to mbedTLS conditional compilation. Extract largest/most self-contained first to reduce coupling pressure on remaining code.

### 7. Clean → Test → Remove Original
Workflow:
1. Create all modules + internal header + Makefile updates
2. `make clean && make test_oci` — verify from fresh
3. `make runtime` — verify production build
4. Remove original `wubu_oci.c` only after all pass

**Reference:** `references/oci-split-2026-07-05.md` — full session transcript with file list, test results, and Makefile diffs.

**Reference:** `references/holyc-repl-persistent-var-fix-2026-07-06.md` — HolyC REPL persistent variable bug fix across multiple evals. Root cause: global var loads with stack_offset==0 treated as locals, missing runtime patches for IDENT loads, stale global_patches preserved across compilations.

Fix pattern for a duplicate in `wubu_oci.c`:
1. Add `#include "wubu_crypto.h"` up top with other includes
2. Replace the 60-line SHA256 body with: `static void sha256_digest(const void *data, size_t size, char *out_hex) { wubu_sha256_digest(data, size, out_hex, 65); }`
3. Update `sha256_file` to call `wubu_sha256_digest` directly
4. Remove the stale `#include "wubu_crypto.h"` from the middle of the file if present

**Real example:** `references/oci-crypto-dedup-2026-07-02.md` — full transcript of the wubu_oci.c → wubu_crypto.h migration.

## Pitfalls Added 2026-07-10 (B19–B39 batch)

- ❌ **`RT_OBJS` feeds `make runtime`, NOT `make hosted` — `wubu_archd.c` is special.**
  `wubu_archd.c` is compiled to `archd_hosted.o` by a dedicated rule
  (`$(HOSTED)/archd_hosted.o: $(RT)/wubu_archd.c … -DWUBD_TEST_MAIN`), and the hosted
  link uses that object, NOT `wubu_archd.o`. So when you extract `wubu_archd_util.c`,
  adding `wubu_archd_util.o` to `RT_OBJS` does NOTHING for `make hosted` — you must add
  `$(RT)/wubu_archd_util.o` to `HOSTED_OBJS`. Generic rule: after ANY split, check BOTH
  the parent's `OBJS` var AND `HOSTED_OBJS`; if the parent is compiled to a `*_hosted.o`
  variant, its submodules go into `HOSTED_OBJS` too.
- ❌ **An implicit-shared symbol (defined in a DIFFERENT `.c`, no header decl) is a
  double-coding hazard.** `wubu_detect_payload_type` lived in `wubu_container.c` with NO
  declaration anywhere; `wubu_exec_format.c` (new module) called it and linked "by
  coincidence" — until the symbol set changed and broke. Fix: create/extend the relevant
  internal header and DECLARE the shared symbol (`WUBU_PAYLOAD_TYPE wubu_detect_payload_type(
  const void*, size_t);`), so all consumers link the SAME impl. Same pattern for any
  cross-module helper with no header decl.
- ✅ **Compile each new module STANDALONE before wiring** (re-confirmed across B19–B39):
  `gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM -I<dirs> -c new.c -o /tmp/x.o`.
  Catches missing system includes (the silent SEGFAULT trap: omitting `<stdlib.h>` makes
  `getenv` implicitly `int`, returns garbage → crash only at runtime, NOT link) and unknown
  types ~10× faster than a full `make hosted`.
- ❌ **A `static` CALLBACK duplicated across submodules = double-coding (kill it).** B15:
  `cb_list_installed` was copy-pasted verbatim into `wubu_pkgmgr_install.c` AND defined in
  `wubu_pkgmgr_db.c`. After extraction, keep ONE canonical copy (in the db module), promote it
  non-static + declare in the internal header, and route ALL callers (including the installer)
  through it. If you see an identical function body in two files, that's the smell.
- ✅ **One internal header CAN carry multiple sub-module families** when they share a prefix.
  `jit_internal.h` holds both `jit_encode.c`'s `enc_*` decls AND `jit_minic.c`'s Mini-C lexer
  types + `minic_*` decls (the tokenizer types `MinicLexer`/`MinicToken`/`MinicTokType` moved
  OUT of `jit_minic.c` into this shared header). Merge, don't multiply headers per leaf.

- ❌ **Concurrent sibling sub-agents editing the SAME Makefile will shift line numbers under
  you.** In a multi-agent session, a sibling may rewrite the Makefile (e.g. add a `.o` to
  of a `patch` reports "modified by
  sibling subagent", or your expected line (e.g. the `wubu_archd.o` line in `HOSTED_OBJS`) is
  no longer where you last saw it. **Mitigations:** (a) prefer idempotent Python
  `content.replace(...)` (dedup-guarded) over line-numbered `patch` — a blanket replace re-applies
  correctly even if the neighbors changed; (b) re-`read` the Makefile (or `grep` the live line)
  immediately before editing when you've done other work in between; (c) after the final write,
  `grep -c` the new token to confirm it actually landed (the B19 debacle: `RT_OBJS` edit
  "applied" but the hosted link used `HOSTED_OBJS`, so the symbol stayed undefined until a
  re-read revealed the real target).

## Pitfalls Added 2026-07-11 (B40–B49 batch — second monolith-busting pass)

- ❌ **`FTW_DEPTH`/`FTW_PHYS` need `_GNU_SOURCE`, not merely `_XOPEN_SOURCE 700`.** The older
  "put `#define _XOPEN_SOURCE 700` first" rule is INSUFFICIENT for `nftw` code using
  `FTW_DEPTH`/`FTW_PHYS` (and `FTW_MOUNT`). On this toolchain, `_XOPEN_SOURCE 700` exposes the
  `nftw()` prototype but NOT the `FTW_DEPTH`/`FTW_PHYS` *flag* macros — they need `_GNU_SOURCE`
  (which subsumes the X/POSIX feature set). Concrete B42/B43 case: new `wubu_archd_fs.c` /
  `wubu_bottles_fs.c` (`rm_rf` via `nftw`) failed `FTW_DEPTH undeclared` until `#define _GNU_SOURCE`
  led the module. Rule: for any ftw-based module, lead with `#define _GNU_SOURCE` (plus
  `#define _POSIX_C_SOURCE 200809L`) before includes. Keep the `_XOPEN_SOURCE 700` redefinition
  workaround only as a fallback when `_GNU_SOURCE` isn't viable.

- ❌ **A THREE-WAY `static` duplicate needs RENAME-TO-CANONICAL, not just promotion.** `rm_rf`
  is defined `static` in THREE files: `wubu_archd.c`, `wubu_bottles.c`, AND
  `src/gui/wubu_proton_util.c`. Extracting it non-static from one collides at link with the
  others (`multiple definition of rm_rf`). Fix: name the extracted helper with a module prefix
  so it can never collide — `archd_rm_rf` / `bottles_rm_rf` — and update the host caller. Leave
  the third copy (`wubu_proton_util.c`) alone (different module, out of scope for the archd/bottles
  split). This is a sharper form of the symbol-collision pitfall: when the same name exists in 3+
  TUs, renaming the new copy is safer than unifying all three at once (which would touch GUI code
  and its callers and risk regressions).

- ✅ **Established STOP CONDITION for monolith busting.** When every leaf that is *self-contained*
  (uses only declared public/internal API, no file-local shared statics) has been extracted, the
  remaining large files are **cohesive single-responsibility managers** whose only further
  "leaves" couple to >5 file-local shared statics (`find_snapshot`, `snapshot_now`, `net_cmd`,
  `find_network`, `g_clipboard`, `g_library`, …). Promoting those shared helpers to satisfy one
  extraction is a broader refactor, not a clean leaf split — and the ">5 shared helpers → drop"
  rule already says so. At that point the goal ("separable subsystems extracted; no monoliths
  remain") is MET for cleanly-separable leaves. **Do NOT force fragmentation.** The B40–B49 batch
  (snapshot/archd/bottles/deploy/pkgmgr/editor/explorer/proton2/ramdisk leaves) reached exactly
  this point: clean `make hosted`, 39/40 real tests PASS, and the only remaining large files are
  cohesive managers left intentionally (the 40th test, `test_apps`, is the documented
  known-broken opaque-discipline test — not a regression).

- ❌ **A true cross-directory DUPLICATE is a DEDUP task, not a monolith split.** `wubu_proton_dxvk_*`
  (22+ fns: `wubu_proton_dxvk_config_write`/`set_hud`/`set_async`/…) is defined in BOTH
  `src/runtime/wubu_proton.c` AND `src/gui/wubu_proton_dxvk.c`. They live in different dirs and are
  never linked together (runtime → `test_proton`; GUI → hosted), so it's latent — but it's
  double-coding violating "no double-coding." Flag it as separate tech debt; do NOT try to split it
  as part of monolith busting (that would mean rewiring `test_proton` onto the GUI module and
  risking that test). The correct fix is one canonical `wubu_proton_dxvk.c` that BOTH builds compile
  — a focused dedup pass, separate from leaf extraction.

- ❌ **Never re-run the brace-counting extractor against an ALREADY-TRIMMED host.** If a run fails
  or is interrupted after it wrote a trimmed host (or after a successful prior run), a second run
  finds no functions in the host → writes `""` → a 0-byte host file. If this happens,
  `git checkout HEAD -- host.c` to restore, then re-run the extraction ONCE from clean. (The
  `brace-counting-extractor.md` SAFE RUN RULES #1/#3 already codify this; restated because it bit
  B41.) Also: the extractor's `find_def` MUST require `lead` on the SAME line as the `{`. A locator
  that matches `lead` inside a *window* `lines[i:i+5]` returns an EARLIER line (whose window happens
  to contain a later definition) and OVERLAPS functions, corrupting the host. Use the `find_def`
  from `brace-counting-extractor.md` which walks to the `{` line and re-checks `lead in lines[j]`.

## Pitfalls Added 2026-07-11 (B50–B67 batch — third monolith-busting pass)

This pass (28 more extractions: B40 re-wire + B41–B67) hardened several earlier
rules with concrete new failures and pushed the STOP CONDITION to its real limit.

- ❌ **Before judging a leaf "coupled," confirm its dependencies are NOT already
  shared.** B50 started by dismissing `wubu_network.c`'s VPN/CNI/WireGuard/Tailscale
  leaves as "coupling to file-local `find_network`/`net_cmd` statics." That was
  WRONG: `find_network` was ALREADY declared non-static in `wubu_network_internal.h`
  and `net_cmd` was ALREADY defined in `wubu_netlink.c` (declared in `wubu_netlink.h`).
  The leaves were cleanly extractable — and got extracted (B50–B52, B58–B60). The
  earlier "leaf looks coupled → skip it" reflex burned a turn. Rule: when you think a
  candidate couples to a helper, `grep` that helper's DECLARATION first — if it's
  already in an internal header or another module's public API, the candidate is a
  clean leaf. Only >5 genuinely-file-local shared statics justify dropping it.

- ❌ **`grep -rln ' helper_name(' src --include=*.c` BEFORE promoting any `static`
  to non-static — or you collide with an EXISTING non-static copy.** B62: promoting
  gamelib's `static ensure_dir` to non-static hit `multiple definition of ensure_dir`
  because `wubu_proton_util.c` already defines `ensure_dir` non-static. The fix was
  to RENAME the gamelib copy `gamelib_ensure_dir` (module-prefixed, declared in the
  internal header) — same collision-avoidance as `archd_rm_rf`/`bottles_rm_rf`. The
  "THREE-WAY duplicate needs RENAME" pitfall covers 3+ TUs; this is the 2-TU variant
  where the OTHER copy is ALREADY non-static. Reaffirm: a promote-then-discover
  collision costs a reverted turn; `grep` first. (If the existing copy is itself a
  `static` duplicate, that's the dedup task — prefer renaming the new copy anyway to
  avoid touching the other module's callers.)

- ❌ **Per-function brace counting BEATS one big line-range slice for bulk extraction.**
  B60 first tried `block = "\n".join(lines[199:417])` (one slice for the whole
  network-create subsystem) and the module came out UNBALANCED (`expected declaration
  at end of input`) because `fn_end` had mis-counted one function's close brace (a
  `}` inside a `snprintf` format string fooled the raw depth counter). The fix was to
  iterate PER FUNCTION (`find_def(sig)` + `fn_end` for each of the 9 `create_*` fns +
  `profile_default`) and concatenate balanced segments. Rule: when extracting >1
  function, extract each by signature+brace-walk and join — never one `raw[a:b]` slice
  across many function boundaries. (The `brace-counting-extractor.md` reference already
  does per-function; this is the "don't hand-roll a bulk slice" reaffirm.) Also: after
  writing the module, READ ITS TAIL — if the last line is `}` followed by a stray
  `/* ... */` header from the NEXT function, the slice truncated.

- ✅ **A single shared helper used by BOTH the host and the extracted leaf → promote
  it (non-static + internal-header decl), don't drop the subsystem.** B60 promoted
  `static void emit_event(...)` because `wubu_network_create_*` AND the host's
  delete/enable/disable/endpoint functions all call it. Promoting one helper is the
  correct, low-risk path (the skill's "promote shared helpers" rule); it is NOT the
  ">5 shared helpers → drop" case. Same for module globals: B61 promoted `static
  GameLibraryState g_gamelib` to non-static + `extern` in `wubu_gamelib_internal.h`
  so the config save/load module links the one instance. Consistent pattern: promote
  the shared symbol to the internal header; leave sibling copies (if any) to a separate
  dedup pass.

- ❌ **Verify the test TARGET NAME exists before `make test_<x>`.** A non-existent
  target just says `make: *** No rule to make target 'test_exec'. Stop.` — looks like
  a failure but isn't. `wubu_exec.c`'s real test is `test_wubu`; there is no
  `test_exec` or `test_container`. Rule: before `make test_<x>`, `grep -n '^test_<x>:'
  Makefile` to confirm the target exists. The full-sweep loop (which uses correct
  names) is the reliable verification; ad-hoc single-target runs need the name check.

- ✅ **Blanket Makefile wiring must cover MULTI-RECIPE parents (standard + special).**
  `wubu_exec.c` is compiled by the RT_OBJS pattern rule AND by special `$(CC) …`
  recipes (the JIT/holyc recipes) that list sources inline. The
  `content.replace("$(RT)/wubu_exec.c", "$(RT)/wubu_exec.c $(RT)/wubu_exec_wasm.c …")`
  blanket caught ALL of them because they share the `$(RT)/wubu_exec.c` token — confirm
  with `grep -c`. General: when a parent has >1 compile recipe, the blanket replace
  handles each IF they share the parent token; verify the hit count equals the number
  of recipes that compile the parent.

- ✅ **STOP CONDITION reaffirmed and REACHED at B67.** After B41–B67, every
  self-contained leaf across `wubu_snapshot.c` (copy/GC/export-import), `wubu_network.c`
  (CNI/WG/Tailscale/DNS/QoS/create), `wubu_pkgmgr.c` (manifest/resolve/verify),
  `wubu_gamelib.c` (config/start-menu/playtime), `wubu_exec.c` (WASM/Mach-O/container),
  `wubu_proton2.c` (device/gamescope/launch), `wubu_ramdisk.c` (format) had been
  extracted. The remaining large files (`wubu_snapshot.c` 498, `wubu_exec.c` 429,
  `wubu_network.c` 331, `wubu_gamelib.c` 339, `styxfs.c`, `wubu_proton.c` runtime,
  `wubu_clipboard.c`) are cohesive single-responsibility managers whose only further
  "leaves" are sub-50-line fragments or >5-shared-static-coupled — artificial
  fragmentation, which this skill forbids. **Monolith busting of cleanly-separable
  leaves is COMPLETE.** Clean `make hosted`; 39/40 real tests PASS; the 40th
  (`test_apps`) is the documented known-broken opaque-discipline test, not a
  regression. The ONE remaining genuine defect is the **`wubu_proton_dxvk_*` cross-dir
  duplicate** (runtime `wubu_proton.c` + GUI `wubu_proton_dxvk.c`) — a DEDUP task, not
  a monolith split. Do NOT re-extract already-extracted leaves; do the proton-dxvk
  dedup as its own focused pass. See `references/monolith-b50-b67-status.md`.

## Dead/Build-Blocking File Protocol

Experimental `.c` files that `#include` uninstalled libraries must be excluded from the build, not left blocking `make`:

```makefile
# Problem: wubu_compositor.c includes <wlr/backend.h> (not installed)
# Solution: remove from GUI_OBJS, keep the source on disk for later
GUI_OBJS = ... $(GUI)/term.o  # wubu_compositor.o removed — needs wlroots
```

**Checklist before removing from build:**
- [ ] Is the file unused by any test target? Check `grep 'filename' Makefile`.
- [ ] Is the file referenced by any `#include` in other files? Check `grep -r 'filename.h\|"filename"' src/`.
- [ ] Is there a matching header that other files include? If yes, keep the .h.
- [ ] Does it have buildable tests that still pass? If yes, leave the .o in the build.

## Variant: Resume a Crashed Split Session

When a prior session left the split half-done (new files on disk, Makefile wired, but old monolith still has dead `static` definitions causing `static declaration follows non-static declaration` errors):

1. **Diagnose with git + grep**:
   ```bash
   git status --short src/<dir>/
   wc -l old_monolith.c new_module.c
   grep -n '^static void\|^static int' old_monolith.c | head -20
   ```

2. **Build baseline** — `make clean && make test_<target>` to see the exact set of errors. They'll tell you which functions need deleting vs which need `static` removed.

3. **Use a Python script for surgical deletion** — fuzzy patches on a 1600-line file thrash (as happened in the crashed session). Instead, write an `execute_code` script that:
   - Reads the file
   - Identifies every function definition whose name is declared non-static in the new `.h` files (cross-reference signature patterns)
   - Finds the closing brace (depth-matching `{`/`}`)
   - Deletes the block + trailing blank lines
   - Also removes forward declarations for deleted functions
   - Strips `static` from remaining functions that are now declared non-static in the internal header
   - Writes back atomically

   This approach eliminates the `static follows non-static declaration` cascade in one pass, and avoids the `patch` tool thrashing that corrupted the `term.c` session.

4. **FILL IN MISSING IMPLEMENTATIONS** — Always audit the new module files for functions DECLARED in headers or comments but NEVER ACTUALLY IMPLEMENTED. The `term_ansi.c` session had `term_process_pty_output`/`term_process_container_output` names in comments but no code, causing `undefined reference` at link time. Fix: add the thin wrappers (bind struct → dispatch to shared parser).

5. **Verify from clean** — `make clean && make test_<target>`, `make clean && make runtime`, `make clean && make hosted`. All three must pass.

6. **Commit before starting the next split** — the crashed session had no commit, so all state was in the dirty working tree.

### Session 2026-07-06 Learnings: wubu_snapshot.c / wubu_network.c / wubu_image.c splits

**FTW flag constants** — When `_GNU_SOURCE` isn't defined (or even when it is, on some toolchains), `FTW_MOUNT`, `FTW_DEPTH`, `FTW_PHYS`, `FTW_SL`, `FTW_SLN`, `FTW_DP`, `FTW_NS` are not visible from `<ftw.h>`. Define them in the internal header with their standard values:
```c
#ifndef FTW_MOUNT
#define FTW_MOUNT 0x0100
#endif
#ifndef FTW_DEPTH
#define FTW_DEPTH 0x0001
#endif
#ifndef FTW_PHYS
#define FTW_PHYS 0x0002
#endif
#ifndef FTW_NS
#define FTW_NS 0x0004
#endif
#ifndef FTW_SL
#define FTW_SL 0x0010
#endif
#ifndef FTW_SLN
#define FTW_SLN 0x0010
#endif
#ifndef FTW_DP
#define FTW_DP 0x0004
#endif
```

**dir_size migration** — `static inline uint64_t dir_size(const char*)` in the internal header collides with the real implementation in the `.c` file. Move the declaration to the header as `uint64_t dir_size(const char*);` (non-static, non-inline) and implement it once in the `.c` file without `static`.

**Signature mismatches** — Audit every call site against the header declaration. In this session, `build_snapshot_path` was declared in the header with 4 parameters but called with 5 (an extra `void* flags` argument). Add the parameter to the header declaration (with `(void)flags;` to silence unused warning) or update all call sites.

**FTW_SLN dangling case** — The original code had `case FTW_SLN:` alongside `case FTW_SL:` but `FTW_SLN` isn't a standard constant (it's an alias for `FTW_SL` on some systems). Just remove the dangling case label.

**btrfs detection** — `BTRFS_SUPER_MAGIC` is in `<linux/magic.h>` which may not be available. Guard with `#ifndef BTRFS_SUPER_MAGIC` and define it as `0x9123683E`. Also need `<linux/btrfs.h>` for `BTRFS_IOC_SNAP_CREATE_V2` and `BTRFS_PATH_NAME_MAX`.

**Surgical Python deletion works** — The Python script that reads the monolith, cross-references function names against the new headers, finds closing braces via brace-counting, and deletes entire blocks atomically is vastly more reliable than iterative `patch` calls. Use it whenever the monolith is >1000 lines and >10 functions need removal.

If `git filter-repo --invert-paths` deleted source files from disk:

1. **Don't panic** — the files still exist on remote (clone fresh)
2. **Clone the remote**: `cd ~ && git clone <remote-url> <new-dir> && cd <new-dir>`
3. **Reapply uncommitted changes** — rebuild any split files, patch Makefile targets, add new .test.c files
4. **Check if the old .git/refs/original/ exists**: `git for-each-ref --format="%(refname)" refs/original/`. If so: `git checkout refs/original/heads/master` to restore working tree, then re-run filter-repo with the correct flags.
5. **If refs/original/ is gone** (filter-repo ran twice): you must rebuild from session transcript.
6. **Clean up the borked repo**: `rm -rf ~/old-borked-repo`
7. **Add .gitignore FIRST** before committing source — without it, `git add -A` stages build artifacts.