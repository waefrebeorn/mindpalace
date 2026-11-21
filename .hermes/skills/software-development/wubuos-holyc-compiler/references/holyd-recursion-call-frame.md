# HolyD recursion + call-frame architecture (the #37 class)

All the recursive-call / live-range / call-frame material that used to live
inline in SKILL.md. Root causes, diagnostics, and the confirmed fix direction.

## Recursive-call live-range spill — KNOWN OPEN BUG (diagnosed, NOT fixed)

`int fib(int n){return n<2?n:fib(n-1)+fib(n-2);}` returns garbage (fib(10)=-80,
not 55); `fact(5)`=16 not 120. **Trigger: TWO recursive calls in one
expression** — the FIRST call's result is clobbered by the SECOND call. A
single recursive call + arithmetic works (`f(n-1)+1`); two NON-recursive calls
work (`g(5)+g(3)`); two recursive calls to DIFFERENT functions work
(`f(2)+g(2)`). Only same-function recursion at depth ≥2 fails. 2-cell struct
returns work (that was the SEPARATE total_mem-units bug, already fixed).

Diagnostic: `WUBU_DEBUG_REGS=1 ./gauntlet_runner --dump-asm x86-64 "$(cat
t.c)"` prints every VR interval + spill decision. The call-result VR `a`
(defined by `mov(a, vr0)` right after the CALL) is NOT among the spilled VRs
(only the 5 high address VRs spill). The MIR layout emits callee bodies at
LOWER instruction indices than the caller, so the caller's call-result VR `a`
(high indices) and the recursive callee's internal VRs (low indices) look
non-overlapping in flat space and get the SAME physical register — but at
runtime the callee executes while `a` is live. Step 1c (live-range-across-call)
only extends VRs whose first_def is BEFORE a call; a call-result VR's first_def
is the mov AFTER its producing call, so the detection misses the runtime
overlap. Fix direction (JIT): treat a VR defined immediately after a MIR_CALL
(the `mov(dst, vr0)` result-capture) as live-from-the-call so any subsequent
call forces a spill; or spill every call-result VR outright.

## CONFIRMED root cause of the recursion param-clobber (holyd_mir_eval.c)

The `holyd_mir_eval.c` param prologue allocates each param's memory cell from
`prog->total_mem` at COMPILE time (one fixed byte address per param, bumped
once per source decl) — NOT a per-invocation frame. So every call to a
function reuses the SAME param cell address. A function that reads a param
AFTER a recursive call reads the value the recursive call left there:
`int f(int x){if(x>2)return x;else{int r=f(x+2);return r+x;}}` — `f(3)` sum
returns 3 not 6 because after `f(x+2)` runs, `x`'s cell holds the callee's arg,
not the caller's. Non-recursive `r=g(x); r+x` is correct (g's params alias f's
but g returns before f reads x). This is the SAME architectural gap as fib
(#37) — the fix is a runtime call-stack frame (push param/local frame on entry
keyed to a frame pointer, pop on return), which also fixes the interpreter.
Confirmed NOT a single-bug fix: single recursive call + arith works, two
recursive calls to DIFFERENT functions work, only same-function depth>=2 (or
read-after-recursive-call) fails.

## Interpreter side — the memory-scope bug

The interpreter (`wubu_mir_interp.c`) has the SAME fib bug, different root
cause: each `call_frame` captures `mem_save` on entry but the CALL-site comment
says "Memory is NOT restored" — only the return value VR is restored, not
`mem`. Adding `memcpy(mem, f->mem_save, mem_size*8)` on return fixes plain
recursion (fib(10)=55) BUT is NOT viable one-line: flat `mem` intermixes
persistent globals and static struct-return buffers (`wubu_mir_alloc`
addresses) with per-call locals, so a full restore reverts globals and
struct-return buffers (MIR battery drops 111→102). Reverted. **The real fix for
BOTH the JIT and the interpreter is coordinated frame-relative addressing of
locals AND params** (separate the flat `mem` into a persistent region + per-call
frame region) — one coordinated change, gated on the green 247/247 gate, in a
dedicated session. Do NOT patch it alongside module-closure work.

## Deprioritized / honest remainder (recursion-adjacent)

Known wrong result fib(10)=-80 in both backends; simple recursion
(f(5)=5, fact(5)=120) works. Deprioritized (rare/legacy, not worth the parser
risk): K&R function definitions (`int f(x) int x; {...}`), nested function
definitions, `asm volatile`, `__builtin_*`, `extern inline`, compound literals
with statement-expressions, LTO, parenthesized declarators
`int(return_3)(void)`, abstract declarator casts `(unsigned long(*))0`.

