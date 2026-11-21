# Brace-Counting Extractor (reusable)

Used to split a monolithic `.c` into a new module + trimmed host **without** line-index
corruption. Locates each function by a signature substring, walks `{`/`}` to the matching
close, builds a single remove-mask, and writes both files atomically.

## Script (run via `execute_code`, edit `sigs` + header text)

```python
from hermes_tools import read_file, write_file

base = "/home/wubu/.hermes/profiles/mind-palace/home/myseed/src/gui"
pc = f"{base}/wubu_proton.c"
raw = [l[l.find("|")+1:] if "|" in l else l for l in read_file(pc, limit=2000)["content"].split("\n")]

def find_fn_end(start):
    depth = 0; started = False
    for i in range(start, len(raw)):
        for ch in raw[i]:
            if ch == '{': depth += 1; started = True
            elif ch == '}':
                depth -= 1
                if started and depth == 0: return i
    return len(raw) - 1

def find_def(lead):
    # `lead`: the distinctive FIRST token(s) of the signature, e.g.
    #   "static int copy_ftw_callback"  or  "int copy_tree_nftw"  or  "uint64_t dir_size"
    # Find the FIRST line containing `lead` that ALSO has the body-opening '{' on
    # the SAME line. Requiring `lead` on the same '{'-line is the critical guard
    # that prevents a FALSE MATCH when `lead` appears inside a *window* of lines
    # around a LATER definition.
    #
    # DO NOT match `lead` on line `i` and then walk forward for the '{' — that
    # returns the EARLIER line (whose 5-line window happens to contain a later
    # definition), overlaps the previous function, and corrupts the host. B41 hit
    # exactly this: `copy_tree_nftw` matched at line 143 (window contained line 148)
    # and the overlap assert fired. Require `lead in raw[i]` AND `'{' in raw[i]`.
    for i in range(len(raw)):
        if lead not in raw[i]:
            continue
        if '{' in raw[i] and lead in raw[i]:
            return i, find_fn_end(i)
    raise RuntimeError(f"def not found (lead '{lead}' with '{{' on same line)")

# NOTE: a forward declaration "int copy_tree_nftw(...);" ends in ';' (no '{' on its
# line), so it is never matched. Only the real definition (which has '{' AND contains
# `lead` on that line) is returned.
#
# WRAPPED SIGNATURES: if a signature spans two lines (e.g.
#   "static int scan_steam_appmanifest(const char *p,\n  <continuation>) {"),
# `lead` is NOT on the '{'-line. Fall back: match all `lead` WORDS on line `i`, then
# walk `j` forward from `i` to the line containing '{' (do NOT require lead in raw[j]
# for that wrapped case). Forward declarations end in ';' so the walk never closes on
# them. Use this fallback only when the same-line guard above fails to find the def.

# Signatures (LEAD tokens) of functions to MOVE (keep host globals OUTSIDE these ranges).
sigs = [
    "static int unlink_cb",
    "static int rm_rf",
    "static bool ensure_dir",
    "static uint64_t get_dir_size",
    "static bool file_exists",
    "static char *find_steam_path",
    "static void parse_vdf_pairs",
    "static int parse_appmanifest",
]
ranges = [find_def(s) for s in sigs]
assert all(ranges[i][0] > ranges[i-1][1] for i in range(1, len(ranges))), \
    "OVERLAP: function ranges intersect — locator matched a wrong/earlier line. " \
    "Use a more distinctive `lead` (include the return type + name, not just the name)."

# ---- SAFE RUN RULES (learned 2026-07-11: a bad run ZEROED wubu_snapshot.c) ----
# 1. Do the ENTIRE extraction in ONE in-memory pass: read host -> compute mask ->
#    write module file -> write trimmed host file. Never re-run the script against an
#    ALREADY-TRIMMED host (the second run finds no functions, writes "" -> 0-byte file).
# 2. `import re` at the TOP of the script (the host-write uses re.sub for blank-line
#    collapsing); a missing import throws AFTER the module is written but BEFORE the
#    host is written, leaving the host untrimmed/partial.
# 3. After writing, SANITY-CHECK: host line count should drop by ~the extracted span
#    (e.g. 856 -> 709), NOT to 0 or to a wildly different number. If it looks wrong,
#    `git checkout -- host.c` and re-run once from clean.
# 4. If a function's lead also appears as a CALL inside an earlier extracted function
#    (unlikely but possible), the assert above catches the overlap — refine `lead`.

mask = [False]*len(raw)
for s, e in ranges:
    for i in range(s, e+1): mask[i] = True

blocks = ["\n".join(raw[s:e+1]) for s, e in ranges]
util_block = "\n\n".join(blocks)

header = """/* wubu_proton_util.c -- Proton layer filesystem / parsing utilities.
 * Self-contained module extracted from wubu_proton.c.
 * _XOPEN_SOURCE must precede system headers for FTW_DEPTH/FTW_PHYS.
 */
#define _XOPEN_SOURCE 700
#include "wubu_proton_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>
#include <glob.h>
#include <libgen.h>
#include <limits.h>
#include <pwd.h>
#include <ftw.h>

"""
util_text = header + util_block + "\n"
# De-static every helper that the internal header declares non-static.
for fn in ["file_exists","rm_rf","ensure_dir","get_dir_size","find_steam_path","parse_vdf_pairs","parse_appmanifest"]:
    util_text = util_text.replace(f"static bool {fn}(", f"bool {fn}(")
    util_text = util_text.replace(f"static uint64_t {fn}(", f"uint64_t {fn}(")
    util_text = util_text.replace(f"static char *{fn}(", f"char *{fn}(")
    util_text = util_text.replace(f"static void {fn}(", f"void {fn}(")
    util_text = util_text.replace(f"static int {fn}(", f"int {fn}(")
write_file(f"{base}/wubu_proton_util.c", util_text)

new_raw = [raw[i] for i in range(len(raw)) if not mask[i]]
write_file(pc, "\n".join(new_raw) + "\n")
```

## Why this beats `patch` / line slices
- A multi-range `raw[a:b]+raw[c:d]` deletion SHIFTS indices; the second range lands on the
  wrong lines and deletes `g_proton` or truncates a function (happened on `wubu_proton.c`).
- A single `mask` applied once preserves every line you did NOT select — global state stays.

## Checklist after extraction
1. Host still compiles alone: `gcc -c host.c`.
2. New module compiles alone: `gcc -c module.c`.
3. Grep the host for any symbol the new module now owns; confirm none remain (unless it's a
   shared global that must stay non-static in the host).
4. `make clean && make hosted` + `make clean && make test_<t>` — stale `.o` masking.
