#!/usr/bin/env bash
# check_link_dupdef.sh <make-target>
#
# Predicts `multiple definition` link errors BEFORE running the link.
# Expands the target's real link command via `make -n`, extracts every .o it
# links, runs `nm --defined-only -g` on the ones that exist, and reports any
# global symbol defined in 2+ objects.
#
# WHY: WuBuOS's object lists (HOSTED_OBJS / RT_OBJS / GUI_OBJS ...) share many
# objects. A target that links two lists which both contain the same .o (e.g.
# HOSTED_OBJS + full RT_OBJS) feeds two distinct objects that define the same
# globals -> `ld: multiple definition`. This catches it deterministically.
#
# USAGE:
#   bash scripts/check_link_dupdef.sh test_hosted
#   bash scripts/check_link_dupdef.sh hosted
# Exit 0 = no dup-defined globals (link should be clean on that axis).
# Exit 1 = at least one symbol defined in 2+ objects (link WILL fail).
#
# NOTE: relies on the repo's Makefile being present in the cwd. Requires `make`,
# `nm` (binutils). Objects must already be built (run `make runtime` first).

set -u
TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "usage: $0 <make-target>" >&2
  exit 2
fi

# 1) Extract the link line(s). The recipe is the $(CC) ... -o <bin> command.
#    Grab every token ending in .o from `make -n` output for the target.
LINK_OBJS=$(make -n "$TARGET" 2>/dev/null | tr ' ' '\n' | grep -E '\.o$' | sort -u)

if [ -z "$LINK_OBJS" ]; then
  echo "[check_link_dupdef] no .o objects found in link for '$TARGET' (target may not link, or make -n failed)" >&2
  exit 2
fi

# 2) For each built .o, collect its globally-defined symbols.
#    Map: symbol -> "obj1 obj2 ..."
declare -A SYM_OBJS
while read -r obj; do
  [ -f "$obj" ] || continue
  # --defined-only -g : global (external) defined symbols only (T / D / B / R strong).
  while read -r sym _rest; do
    [ -z "$sym" ] && continue
    if [ -n "${SYM_OBJS[$sym]:-}" ]; then
      SYM_OBJS[$sym]="${SYM_OBJS[$sym]} $obj"
    else
      SYM_OBJS[$sym]="$obj"
    fi
  done < <(nm --defined-only -g "$obj" 2>/dev/null | awk '{print $3}')
done <<< "$LINK_OBJS"

# 3) Report any symbol defined in 2+ distinct objects.
found=0
for sym in "${!SYM_OBJS[@]}"; do
  # count whitespace-separated objects
  n=$(echo "${SYM_OBJS[$sym]}" | wc -w)
  if [ "$n" -ge 2 ]; then
    found=1
    echo "DUPLICATE: $sym  <-  ${SYM_OBJS[$sym]}"
  fi
done

if [ "$found" -eq 0 ]; then
  echo "[check_link_dupdef] OK: no global symbol defined in 2+ objects for '$TARGET'"
  exit 0
else
  echo "[check_link_dupdef] FAIL: above symbols will cause 'multiple definition' when linking '$TARGET'" >&2
  exit 1
fi
