#!/usr/bin/env python3
"""Re-TAB recipe lines in a Makefile that lost their leading TAB after a `patch`
edit (the patch tool converts recipe-line TABs to spaces, breaking the rule).

Usage:  python3 fix_makefile_tabs.py <makefile> <line1> [line2 ...]
  lineN are 1-indexed editor line numbers of the recipe lines that lost their TAB.
  Each named line is re-indented with a double TAB ('\t\t') -- correct for both
  continuation lines (ending in '\') and the final command line of a recipe.
  The bare target header line and its dependency line are NOT recipe lines; do
  not pass them.

After running: `cat -A <makefile> | sed -n '<lines>p'` and confirm recipe lines
show '^I^I' (TAB TAB), never spaces. Then `make -n <target>` to confirm it parses.
"""
import sys

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    path = sys.argv[1]
    lines = [int(x) for x in sys.argv[2:]]
    with open(path) as f:
        content = f.readlines()
    for ln in lines:
        i = ln - 1
        if i < 0 or i >= len(content):
            print(f"skip out-of-range line {ln}")
            continue
        stripped = content[i].lstrip("\t ").lstrip()
        content[i] = "\t\t" + stripped
        print(f"re-TABbed line {ln}")
    with open(path, "w") as f:
        f.writelines(content)
    print("done")

if __name__ == "__main__":
    main()
