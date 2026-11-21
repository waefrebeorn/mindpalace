#!/usr/bin/env python3
"""
find_orphan_modules.py — WuBuOS orphaned-module scanner.

WHY: a recurring broken-code class is a module that compiles (is in an _OBJS
list) or is freshly split/written but is NEVER called and has NO test — it is
dead code (the "form-without-function" anti-pattern). Another variant is a `.c`
that is not referenced by ANY Makefile target at all (truly unwired). This
script finds both, fast, across the whole tree.

USAGE:
  python3 find_orphan_modules.py [src_root] [makefile]
  # defaults: src_root=src  makefile=Makefile  (run from repo root)

OUTPUT:
  - UNWIRED .c files (not referenced by basename .c OR .o anywhere in Makefile)
  - For each source .c, whether it is "wired" (compiled by some target)
  - HINT: also prints the count so you can eyeball if the scan itself broke.

The companion dead-code check (compiled but no callers + no test) needs a
per-symbol grep; this script handles the "is it even in the build graph?"
question, which is the cheaper and more common failure.
"""
import os
import re
import sys

ROOT = os.getcwd()
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "src")
MK = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "Makefile")

with open(MK) as fh:
    mk = fh.read()

# Makefile-referenced basenames: literal .c and .o forms.
mk_c = set(re.findall(r"[\s/'(]([A-Za-z0-9_]+\.c)", mk))
mk_o = set(re.findall(r"[\s/'(]([A-Za-z0-9_]+\.o)", mk))

# Walk src for .c files (exclude _legacy_bak).
all_c = []
for dp, dn, fn in os.walk(SRC):
    if "_legacy_bak" in dp:
        continue
    for f in fn:
        if f.endswith(".c"):
            all_c.append(os.path.join(dp, f))

mods = [c for c in all_c if not c.endswith("_test.c")]
tests = [c for c in all_c if c.endswith("_test.c")]

wired, unwired = [], []
for c in mods:
    base = os.path.basename(c)
    obase = base[:-2] + ".o"
    if base in mk_c or obase in mk_o:
        wired.append(c)
    else:
        unwired.append(c)

print(f"=== WuBuOS orphan scan: {len(mods)} modules, {len(tests)} test files ===")
print(f"wired into build graph: {len(wired)}   UNWIRED (not in any target): {len(unwired)}\n")
if unwired:
    print("--- UNWIRED MODULES (verify: dead code, or needs wiring/test) ---")
    for c in sorted(unwired):
        rel = c.replace(ROOT + "/", "")
        print("  ", rel)
else:
    print("No unwired modules. Build graph references every .c.")
