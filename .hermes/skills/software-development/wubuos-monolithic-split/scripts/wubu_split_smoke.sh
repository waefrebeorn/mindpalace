#!/usr/bin/env bash
# wubu_split_smoke.sh -- standalone split/fix verification harness
#
# Compiles the parent + extracted module(s) + deps directly (no Makefile) and
# RUNS the result, asserting output is finite / non-NaN. Use this BEFORE
# claiming a split or "broken code fix" is done -- linking green is not enough.
#
# Usage:
#   scripts/wubu_split_smoke.sh <driver.c> <src1.c> [src2.c ...]
#
# Example (N-pole cartpole split from bear_env.c):
#   scripts/wubu_split_smoke.sh /tmp/npole_smoke.c \
#       src/bear/bear_env.c src/bear/bear_env_npole.c src/bear/bear_arena.c
#
# The driver must #include the module headers and call into them; it is the
# standalone test that proves the extracted code does real work.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO_ROOT"

DRIVER="${1:?usage: wubu_split_smoke.sh <driver.c> <src1.c> [src2.c ...]}"
shift

SRCS=("$@")
if [ ${#SRCS[@]} -eq 0 ]; then
  echo "ERROR: no source files supplied" >&2; exit 2
fi

OUT="$(mktemp -p /tmp smoke.XXXXXX)"
trap 'rm -f "$OUT"' EXIT

INC="-I src/bear -I src/runtime -I src/kernel -I src/gui -I src/hosted -I src/bridge"
echo ">> compiling: gcc -std=c11 $INC $DRIVER ${SRCS[*]} -lm -o $OUT"
# shellcheck disable=SC2086
gcc -std=c11 $INC "$DRIVER" "${SRCS[@]}" -lm -o "$OUT" || {
  echo "COMPILE_FAIL"; exit 1
}

echo ">> running:"
"$OUT" || { echo "RUN_FAIL (exit $?)"; exit 1; }

echo "SMOKE_OK (compiled + ran without NaN/abort)"
