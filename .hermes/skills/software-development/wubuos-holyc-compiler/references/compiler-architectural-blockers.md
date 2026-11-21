# Compiler architectural blockers (MIR level)

Root-cause diagnoses for compiler features that are NOT local fixes — they need
a coordinated change across the MIR opcode set and BOTH backends (JIT +
interpreter). Treat any goal that lands on these as **architectural**: attempt
only in a dedicated session with the full gate held (core gauntlet + MIR
battery + selfhost), never mixed into unrelated module-closure work.

## Function-pointer parameter call — needs indirect-call-through-VR

Symptom: `int call(int(*fp)(int,int),int x,int y){ return fp(x,y); }` called as
`call(add,3,4)` returns a wrong value.

What works: calling a function pointer stored in a **variable** resolves
(`int(*fp)(int)=&f; fp(5)` → correct), because the frontend records the target
`func_id` for that variable at the point of assignment.

Why the **parameter** case is blocked: inside `call`, `fp` is a parameter slot,
not an entry in the variable table, so the call-site resolution finds no
`func_id`. The naive fix — record `{callee_func_id, param_index} → arg_func_id`
at each call site and look it up in the callee — fails structurally: the
callee's body is emitted ONCE, and the call instruction carries a **static
`func_id`**, not a VR holding a runtime target. Different callers passing
different functions would all hit the same baked-in target.

Real fix: `MIR_CALL` must gain the ability to dispatch to a **VR-resident
target** (indirect call), plus the frontend must load the function-pointer
param into that VR, and both the x86-64 JIT and the interpreter must implement
indirect dispatch (JIT: `call *reg`/jump table keyed by func_id; interpreter: a
VR→func_id lookup reading the map the caller passed). This is the same
coordination class as the recursion fix — one opcode, two backends, one
frontend path.

Diagnose-this-class fast: if a feature needs the *same* MIR instruction to
resolve a *different* target per call site, it is indirect-dispatch, and there
is no way to do it by stuffing more `func_id`s into the instruction.

## Recursion (fib) — the same indirect-dispatch + frame class

JIT uses one flat `prog.mem` and a shared caller frame (no per-call saved rbp),
so a recursive callee clobbers caller locals/params (`fib(10)` miscomputes).
Full-memory-restore in the interpreter fixes the standalone case but reverts
struct-return static buffers and recursive global writes. The correct fix is
frame-relative addressing for BOTH locals and params in both backends — the
same coordinated effort as indirect dispatch.
