#!/usr/bin/env bash
# Build a standalone hd_eval probe against the same sources test_battery uses.
#
# WHY: chasing a codegen bug through the full test binary means rebuilding
# everything each time and the failure is buried in 155 probes. A 5-line
# probe builds in ~4s and lets you gdb exactly one expression.
#
# Usage:
#   scripts/build-holyd-probe.sh /tmp/probe.c [out_binary]
#
# The probe C file should just call hd_eval() and print the result:
#   int main(void){ printf("%lld\n", (long long)hd_eval("1 ? 2 : 3;")); return 0; }
set -euo pipefail

REPO="${WUBU_REPO:-/home/wubu/wubuos}"
SRC_C="${1:?usage: build-holyd-probe.sh <probe.c> [out]}"
OUT="${2:-/tmp/probe}"

SRCS='holyd_lexer.c holyd_parse.c holyd_parse_ast.c holyd_codegen.c
      holyd_codegen_emit.c holyd_codegen_expr.c holyd_codegen_stmt.c
      holyd_codegen_api.c wubu_preproc.c holyd_runtime.c holyd_mir_eval.c
      wubu_mir.c wubu_mir_interp.c wubu_mir_opt.c wubu_softfloat.c
      wubu_tgemm.c wubu_mir_fuse.c wubu_mir_gvn.c wubu_mir_sccp.c wubu_mir_ssa.c'
JIT='jit.c jit_encode.c wubu_x86.c wubu_arm64.c wubu_rv64.c wubu_wasm.c
     wubu_disasm.c x86_regalloc.c jit_codegen_x86.c jit_codegen_arm64.c
     jit_codegen_rv64.c jit_codegen_wasm.c jit_minic_cg.c jit_minic.c
     jit_minic_expr.c jit_minic_token.c jit_minic_type.c jit_minic_loop.c
     jit_branch_profile.c'

C=""
for f in $SRCS; do C="$C src/compiler/$f"; done
for f in $JIT;  do C="$C src/jit/$f"; done

cd "$REPO"
gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_HOSTED \
    -include wubu_gnu_compat.h \
    -Isrc/compiler -Isrc/jit -Isrc/runtime \
    "$SRC_C" src/runtime/wubu_spawn.c $C \
    src/compiler/wubu_tgemm_avx512.o \
    -o "$OUT" -ldl -lm -fopenmp -lpthread

echo "built $OUT -- run it, or:"
echo "  gdb -batch -ex 'break holyd_codegen_api.c:337' -ex run -ex 'p gen->code_size' $OUT"
echo
echo "REMEMBER: rebuild before gdb. A stale probe reports a stale binary."
echo "Disassemble with:"
echo "  gdb -batch -ex 'break holyd_codegen_api.c:286' -ex run \\"
echo "    -ex 'dump binary memory /tmp/code.bin gen.code gen.code+gen.code_size' $OUT"
echo "  objdump -D -b binary -m i386:x86-64 -M intel /tmp/code.bin"