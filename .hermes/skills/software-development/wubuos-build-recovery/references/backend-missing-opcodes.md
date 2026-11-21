# Backends that silently skip opcodes, and the fallback that hides it (2026-09-30)

Two bugs in one family: an opcode reaches a backend with **no handler**, the
backend emits nothing, and the wrong value propagates instead of an error.
Found via the ptx target after the interpreter-table fix.

## Bug 1: ptx missing the integer width-cast opcodes

`wubu_isa_ptx.c` had no `case` for `MIR_SEXT32/16/8`, `MIR_ZEXT32` or
`MIR_TO_PTR`. They fell through `default: break;` and emitted **no
instruction**.

`127 + 1` lowers to `CONST/SEXT32/MOV/RET`. The SEXT32 and MOV emitted
nothing, so `%r0` was never assigned and the CUDA stub read back freshly
allocated device memory — a constant `0x0100000000000000` for all 195
failing ptx runs.

How to localise it fast: run the stub by hand.

    LD_LIBRARY_PATH=/usr/lib/wsl/lib:$LD_LIBRARY_PATH \
      /tmp/gpu_host_stub /tmp/wubu_kernel.cubin 0
    # -> 72055120136765440, and /tmp/gpu_run.log EMPTY

An empty error log means the GPU and the launch are fine — the *kernel* is
wrong. Then read the emitted PTX (`/tmp/wubu_kernel.ptx`); a `mov.b64 %r0,
%r6` where `%r6` is never assigned names the missing handler outright.

Fixed with `cvta`-based handlers in both opcode switches inside
`emit_kernel_body`.

## Bug 2 (still open): compile() failure falls back to the interpreter

`hd_run_prog` (holyd_mir_eval.c):

    if (driver->compile && driver->compile(...) == 0 && code) { ...run... }
    return wubu_mir_interp(prog);          /* <-- silent fallback */

If a backend's `compile()` returns -1, the run **silently becomes a MIR
interpreter run** and still reports a passing result. `arm64_compile`
returns -1 on any non-aarch64 host:

    #if !defined(__aarch64__)
        return -1; /* cannot compile ARM64 on this host */
    #endif

So on x86-64, **arm64 "passes" 247/247 without executing a single ARM64
instruction** — it is testing the interpreter, not the backend. Same risk
for `vulkan` and anything else whose compile is host-gated.

This matters when reading the gauntlet summary. `ALL TARGETS PASSED ALL
TESTS` is true, but it does NOT mean 14 independent code generators work.
On this host the genuinely-exercised native backends are **x86-64 and
ptx**; the rest route through `wubu_mir_interp`.

To audit which backend a target really used, check whether `compile` is
host-gated rather than trusting the score.

## The transferable lesson

An opcode with no handler disappears instead of failing loudly. When adding
to `wubu_mir_op_t`, grep **every** backend:

    for op in MIR_SEXT32 MIR_SEXT16 MIR_SEXT8 MIR_ZEXT32 MIR_TO_PTR; do
      grep -rl "case $op" --include='wubu_isa_*.c' .
    done

A positional dispatch table (see `mir-interp-dispatch-table.md`) and a
missing `case` are the same failure mode wearing different clothes.

## gauntlet --core progression

    pass=1247 fail=2211 error=0   (interpreter table positional, 5 behind)
    pass=3263 fail=195  error=0   (interpreter table fixed; ptx still broken)
    pass=3458 fail=0    error=0   (ptx casts implemented) -- 14/14 at 247/247