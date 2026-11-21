#!/usr/bin/env bash
# audit_c11.sh — measure the strict-C11 gap over a repo's CORE_OBJ build.
#
# Usage: bash audit_c11.sh [repo-root] [--list-errors]
# Exit 0 only when the diagnostic file is empty.
set -u
ROOT="${1:-$PWD}"
cd "$ROOT" || exit 2
[ "${2:-}" = "--list-errors" ] || true

OUT="${TMPDIR:-/tmp}/wubu_c11_audit.$$"
LIST="$OUT.srcs"
DIAG="$OUT.diag"
trap 'rm -f "$LIST" "$DIAG" "$OUT".*' EXIT

make -pn 2>/dev/null | awk -F'= ' '/^CORE_OBJ *=/{print $2}' \
  | tr ' ' '\n' | sed 's/\.o$/.c/' | grep '^src/' | sort -u > "$LIST"

# .cu and .S are not C11 translation units
grep -vE '\.(cu|S)$' "$LIST" > "$LIST.c" && mv "$LIST.c" "$LIST"
N=$(wc -l < "$LIST")

: > "$DIAG"
while IFS= read -r f; do
  [ -f "$f" ] || { echo "$f: MISSING SOURCE" >> "$DIAG"; continue; }
  gcc -std=c11 -pedantic -fsyntax-only -I include "$f" 2>> "$DIAG" || true
done < "$LIST"

DIAG_LINES=$(wc -l < "$DIAG")
ERRORS=$(grep -c 'error:' "$DIAG" || true)
FILES=$(grep -oE '^[^:]+\.c' "$DIAG" | sort -u | wc -l)

echo "CORE_OBJ C sources:      $N"
echo "diagnostic lines:        $DIAG_LINES"
echo "errors:                  $ERRORS"
echo "files with diagnostics:  $FILES"

if [ "${2:-}" = "--list-errors" ]; then
  echo "--- errors ---"
  grep 'error:' "$DIAG" | sort -u
fi

[ "$DIAG_LINES" -eq 0 ]
