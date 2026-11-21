# Multi-Argument Function Call Bug — Debug History (2026-09)

This file preserves the detailed diagnostic history of the multi-argument function call
bug that was fixed on 2026-09-04. The fix is summarized in the main SKILL.md.

## Bug signature

Symptom: Functions with 3+ arguments produced wrong results only on the JIT (interpreter
was correct). Root cause: `rcx` is both the JIT's second-operand register AND x86-64's
4th argument register. When the JIT loaded the 2nd operand into `rcx` for a binary op
inside a function prologue, it clobbered the 4th argument.

## Fix

In `wubu_isa_x86_64.c`, the binary operations (ADD/SUB/MUL/DIV/MOD/AND/OR/XOR/SHL/SHR)
load the second operand into `rcx`. For function calls with 4+ arguments, the 4th argument
is passed in `rcx` per x86-64 SysV calling convention. The fix: save/restore `rcx` around
binary operations that might clobber it, OR use a different register for the 2nd operand.

## Detailed diagnostic log

(See git history for the full 239-line diagnostic log — too long for this skill.
Key commits: the fix was in the register allocation and calling convention code in
`wubu_isa_x86_64.c` and `holyd_mir_eval.c`.)

## Remaining issue

9+ mixed-type args (int + double) still fail because:
1. Float arguments must be passed in XMM registers, not integer registers
2. The JIT currently passes ALL arguments in integer registers (rdi, rsi, rdx, rcx, r8, r9)
3. Stack-based args (7+) require proper stack alignment and mixed register/stack passing

This requires implementing the full x86-64 SysV calling convention with XMM register support.