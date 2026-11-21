# x86-64 Encoder Return-Value Gap Closure (2026-07-08)

## Context
`src/jit/wubu_x86.c` had 33 encoder functions that emitted correct bytes but
always returned `0` instead of the actual byte count emitted. This was a pure
form≠function gap: the header documents `int wx86_*()` as returning the number
of bytes emitted, but every function lied.

## The Fix
Every function body: save `size_t start = e->pos;` at entry, return
`(int)(e->pos - start);` before exit.

## Pattern
```c
int wx86_mov_reg_imm64(Wx86Enc *e, Wx86Reg dst, int64_t imm) {
    size_t start = e->pos;                          /* SAVE */
    uint8_t rex = 0x48 | (reg_hi(dst) ? 0x01 : 0);
    wx86_emit_byte(e, rex);
    wx86_emit_byte(e, (uint8_t)(0xB8 + reg_lo(dst)));
    wx86_emit_qword(e, (uint64_t)imm);
    return (int)(e->pos - start);                   /* RETURN DELTA */
}
```

## Verification Test
Added to `src/jit/jit_test.c`: test `"encoder: return values match bytes emitted"`
proves 14 instruction types return correct lengths:

| Instruction | Expected | Actual | Encoding |
|------------|----------|--------|----------|
| `mov rax, imm64` | 10 | 10 | REX.W + B8+rd + imm64 |
| `mov rcx, imm32` | 7 | 7 | REX.W + C7 /0 + imm32 |
| `mov rax, rdx` | 3 | 3 | REX.W + 89 + ModRM |
| `add rax, rcx` | 3 | 3 | REX.W + 01 + ModRM |
| `ret` | 1 | 1 | C3 |
| `jmp rel32` | 5 | 5 | E9 + imm32 |
| `jcc rel32` (je) | 6 | 6 | 0F 84 + imm32 |
| `call rel32` | 5 | 5 | E8 + imm32 |
| `push rax` | 1 | 1 | 50+rd |
| `push r8` | 2 | 2 | REX.B + 50+rd |
| `shl rax, 3` | 4 | 4 | REX.W + C1 /4 + imm8 |
| `cqo` | 2 | 2 | REX.W + 99 |
| `neg rax` | 3 | 3 | REX.W + F7 /3 + ModRM |
| `idiv rcx` | 3 | 3 | REX.W + F7 /7 + ModRM |
| `sub rsp, 32` | 4 | 4 | REX.W + 83 + ModRM + imm8 |

## Key Insight for Future Gap Closure
This gap was only discoverable by **checking the API contract against the
implementation**. The header says "returns position/bytes", the code says
`return 0`. A naive grep for `return 0` wouldn't flag it (too many legitimate
returns). The fix is: for every `int` return, verify against the documented
semantics.

## Impact
- ~33 REAL_GAPs closed in one file (was 469 lines, now fully form==function)
- Callers still don't check the return value (they use `e->pos` directly),
  but the contract is now honest and future callers can rely on it
- 76/76 JIT tests pass, full gate green