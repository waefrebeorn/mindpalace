# x86-64 JIT 32-bit Integer Overflow Semantics Fix (2026-08-30)

## Problem

The x86-64 JIT treated all `int` arithmetic as 64-bit operations. C `int` semantics require
32-bit overflow wraparound, e.g., `INT_MAX + 1 < 0` must be TRUE.

## Symptoms

- `stress_signed_overflow`: Expected 1 (true), got 0 (false)
- Related tests: compound assignment overflow, shift overflow

## Root Cause

x86-64 registers are 64-bit. Arithmetic instructions (ADD, SUB, MUL, etc.) produce 64-bit results.
The JIT did not truncate to 32-bit before storing back to virtual registers, causing incorrect
overflow behavior.

## Solution

Inject `movsxd rax,eax` after integer arithmetic operations:

- **Opcode**: `48 63 C0`
- **Operation**: `movsxd rax, eax` — sign-extend lower 32 bits of EAX to 64-bit RAX
- **Effect**: Truncates to 32-bit and sign-extends, making `INT_MAX+1 → INT_MIN`

## Implementation

```c
// After integer arithmetic operations, emit truncation
e8(&e, 0x48); e8(&e, 0x63); e8(&e, 0xC0);  /* movsxd rax,eax — 32-bit truncate */
```

Affected operations:
- Binary arithmetic: ADD, SUB, MUL, DIV, MOD
- Bitwise: AND, OR, XOR
- Shifts: SHL, SHR  
- Unary: NEG, NOT

## Location in wubu_isa_x86_64.c

Lines 894-904: Insert after the closing brace of `default` case in the main arithmetic switch
Line ~945: Insert after SHL/SHR shift operations  
Lines ~994 and ~1010: Insert after NEG and NOT operations

## Result

Gauntlet --core: 245/247 → 246/247 pass

The remaining failure (`stress_fib`) is a pre-existing crash unrelated to overflow handling.