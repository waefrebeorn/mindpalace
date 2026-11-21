# 64-bit Arithmetic Bug in x86-64 JIT (2026-08-31 → FIXED 2026-09-07)

## Problem
The x86-64 JIT unconditionally truncated ALL integer arithmetic to 32 bits via `movsxd rax, eax` after every operation. This broke `long long` (64-bit) arithmetic.

## Symptom
```c
int main(void) { return 1000000000000L / 16; }
// Expected: 62500000000
// Actual (buggy): -1924509440  (= (int32_t)(62500000000 & 0xFFFFFFFF))
```

## Root Causes (THREE separate truncation sources)

1. **JIT `movsxd` truncation** (`wubu_isa_x86_64.c` ~line 971): `movsxd rax,eax` after every AND/OR/XOR/MUL/ADD/SUB/DIV/MOD
2. **Optimizer `WRAP32()` macro** (`wubu_mir_opt.c`): `(int64_t)(int32_t)(result)` wrapping constant-folded values
3. **Optimizer shift truncation** (`wubu_mir_opt.c`): SHL used `b & 31` instead of `b & 63`

## Fix Applied (2026-09-07)

1. Removed `movsxd rax,eax` from JIT — arithmetic ops already produce full 64-bit results (REX.W=1)
2. Removed `WRAP32()` macro from optimizer — constant folding now preserves full 64-bit values
3. Changed SHL/SHR shift counts from `b & 31` to `b & 63`
4. Changed JIT second-operand register from `rdi` to `rcx` (avoids clobbering rax when divisor VR is in rax)

## Verification
```c
int main(void) { return 1000000000000L / 16; }     // result=62500000000 ✓
int main(void) { return 40l << 40; }                 // result=43980465111040 ✓
int main(void) { return 9223372036854775807L; }     // result=9223372036854775807 ✓
```

## Lesson
**Never truncate as a band-aid.** The user's directive: "truncation is a bad practice" — fix the root cause (proper 64-bit codegen) rather than adding post-op truncation. The `movsxd` was originally added to make `INT_MAX + 1` wrap to `INT_MIN` (C int overflow semantics), but it applied to ALL integer ops including `long long`. The correct fix is to remove truncation entirely and let the 64-bit hardware produce correct results.
