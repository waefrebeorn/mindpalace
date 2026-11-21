# Recursion & the shared flat-memory frame model

STATUS: SOLVED. The interpreter is reentrant via a globals/frame memory boundary
+ per-call frame-cell restore; the x86-64 JIT (still one flat `wubu_jit_mem_ptr`)
routes recursive programs to the interpreter. fib(n) is correct, fact/sum/gcd/
mutual recursion pass. Full architecture + the frame_off/frame_cells detail is in
`references/mir-eval-correctness.md` ("Recursion — the call-frame architecture").
The notes below are the diagnostic background that still holds.

The HolyC→MIR→{x86-64 JIT, interpreter} pipeline historically addressed ALL
variables in one flat `prog.mem` array at FIXED byte offsets, with no per-call
frame. That was the root cause of every recursion wrong-result bug, and it bit
BOTH backends — diagnose them together.

## The symptom

`fib(10)` returns a garbage negative (not 55). `int x=n*100; f(n-1); return x`
returns the INNER frame's `x`. `int r=f(n-1); return n` returns 0 (param `n`
clobbered). Simple recursion (`1+f(n-1)`, `fact`) works by luck because the
result is consumed immediately; only the two-recursive-call pattern
(`fib(n-1)+fib(n-2)`) loses the first term.

## What fixed it (both backends)

- **Interpreter:** codegen sets `prog->globals_end` before the first function
  body; `op_call` snapshots the register file + the frame cells (byte addr >=
  globals_end/8, NOT all memory), `op_ret` restores them. Globals below the
  boundary persist. Snapshot only the frame region — full-memory restore is
  O(calls*mem) and times out on fib(20).
- **JIT:** `prog_has_recursion()` (call-graph cycle via iterative DFS) routes
  recursive programs to `wubu_mir_interp` (the golden oracle); non-recursive
  programs keep the JIT. The JIT's own flat-mem codegen was NOT rewritten.

## Diagnosis discipline (still valid)

- `test_single` and `gauntlet_runner` run the x86-64 JIT (`hd_run_prog`), NOT the
  interpreter; an interp-only change needs a throwaway interp binary to validate
  (recipe in `mir-eval-correctness.md`).
- Test simple recursion AND the two-call pattern separately — they fail
  differently.
- Before blaming the JIT, run the program through the interpreter directly; if
  both agree on the wrong answer, the bug is upstream (the shared mem model).

## Remaining known edge

A nested recursive call used as an argument — Ackermann
`ack(m-1, ack(m,n-1))` — still miscomputes (the inner call's frame restore can
clobber the outer frame's params before the outer call is set up). Rare.
