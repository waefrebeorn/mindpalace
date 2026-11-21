# Unsigned Arithmetic: Division, Modulo, and Double-to-Int

## The Problem

HolyD uses 64-bit values for everything. Signed and unsigned integers share the same representation, but division and modulo require different x86-64 instructions:
- `idiv` (signed) — used by default, gives wrong results for unsigned operands > INT64_MAX
- `div` (unsigned) — required for unsigned arithmetic

Example: `18446744073709551605ul % 100` should be `5`, but `idiv` gives `-11` (since `18446744073709551605` as int64_t is `-11`).

## MIR_UDIV and MIR_UMOD

New MIR operations for unsigned division and modulo:

```c
MIR_UDIV,  /* dst = a / b (unsigned) */
MIR_UMOD,  /* dst = a % b (unsigned) */
```

### JIT Encoding

Signed division (existing):
```c
rex(&e,1,0,0,0); e8(&e, 0x99);   /* cqo — sign-extend rax into rdx:rax */
rex(&e,1,0,0,0); e8(&e, 0xF7); e8(&e, 0xF9);  /* idiv rcx */
```

Unsigned division (new):
```c
rex(&e,1,0,0,0); e8(&e, 0x31); e8(&e, 0xD2);  /* xor rdx, rdx — zero-extend rax into rdx:rax */
rex(&e,1,0,0,0); e8(&e, 0xF7); e8(&e, 0xF1);  /* div rcx */
```

Key difference: `cqo` (sign-extend) vs `xor rdx,rdx` (zero-extend). The `div` instruction divides the 128-bit value RDX:RAX by the source — for unsigned, RDX must be zero; for signed, RDX must be the sign extension of RAX.

### When to Emit Unsigned Ops

The MIR builder emits `MIR_UDIV`/`MIR_UMOD` when BOTH operands are unsigned:

```c
int is_unsigned = mir_is_unsigned_node(g, n->left) && mir_is_unsigned_node(g, n->right);
```

`mir_is_unsigned_node()` checks:
1. `n->type->kind` for U8/U16/U32/U64
2. For IDENT nodes (type=NULL), looks up `g->vars[i].type->kind`

### Interpreter Implementation

```c
op_udiv:
    { uint64_t a = (uint64_t)vr[in->a]; uint64_t b = (uint64_t)vr[in->b];
      vr[in->dst] = b ? (int64_t)(a / b) : 0; }
    DISPATCH();
op_umod:
    { uint64_t a = (uint64_t)vr[in->a]; uint64_t b = (uint64_t)vr[in->b];
      vr[in->dst] = b ? (int64_t)(a % b) : 0; }
    DISPATCH();
```

## MIR_DTOI_U: Unsigned Double-to-Int

For compound assignments with unsigned LHS and float RHS (e.g., `ul -= 1.5E19`), the result must be converted back to unsigned integer. `MIR_DTOI` uses `cvttsd2si` which returns the "indefinite value" (0x8000000000000000) for doubles > INT64_MAX.

`MIR_DTOI_U` uses the same `cvttsd2si` instruction but is semantically unsigned. For values < 2^63, the result is identical to `MIR_DTOI`. The op name documents intent and enables future optimization.

### When to Emit MIR_DTOI_U

In compound assignment handler, when `is_float` is true and LHS is unsigned:

```c
int lhs_unsigned = (lhs_type->kind == HD_TYPE_U8 || lhs_type->kind == HD_TYPE_U16 ||
    lhs_type->kind == HD_TYPE_U32 || lhs_type->kind == HD_TYPE_U64);
if (lhs_unsigned)
    upd = wubu_mir_unop(g->prog, MIR_DTOI_U, upd);
else
    upd = wubu_mir_unop(g->prog, MIR_DTOI, upd);
```

## Struct Array Member Size

The formula `(total_bytes + 7) / 8` undercounts array members. For `int sub[2]` (8 bytes), this gives 1 cell, but the array needs 2 cells (one per element).

**Fix**: for array members, compute `array_size * ceil(element_size / 8)` cells:

```c
if (member_type->kind == HD_TYPE_ARRAY && member_type->base) {
    int elem_cells = (int)((hd_type_size(member_type->base) + 7) / 8);
    if (elem_cells < 1) elem_cells = 1;
    member_cells = elem_cells * member_type->array_size;
}
```

## sizeof with Function Calls and Assignments

### sizeof(func())

The function name is in `n->child->callee->ident`, NOT `n->child->ident` (which is empty for FUNC_CALL nodes). Look up return type from `g->func_ast[]`.

### sizeof(lhs = rhs)

The result type is the type of the LHS per C standard. Look up LHS variable type from var table.

### sizeof(binary_op) and sizeof(unary_op)

For `sizeof(x + 1)`, `sizeof(-x)`, etc., use `mir_binop_result_type()` to determine the result type:

```c
} else if (n->child->kind == HD_AST_ADD || n->child->kind == HD_AST_SUB ||
           n->child->kind == HD_AST_MUL || n->child->kind == HD_AST_DIV ||
           n->child->kind == HD_AST_MOD || ...) {
    HDType *rt = mir_binop_result_type(g, n->child->left, n->child->right);
    if (rt) {
        size = (int)hd_type_size(rt);
        if (size <= 0) size = 4;
    } else {
        size = 8; /* 64-bit result */
    }
} else if (n->child->kind == HD_AST_NEG || n->child->kind == HD_AST_NOT ||
           n->child->kind == HD_AST_BITNOT) {
    HDType *rt = mir_binop_result_type(g, n->child->child, n->child->child);
    if (rt) {
        size = (int)hd_type_size(rt);
        if (size <= 0) size = 4;
    } else {
        size = 8;
    }
}
```

This correctly returns `sizeof(int + int) = 4`, `sizeof(-int) = 4`, `sizeof(long + int) = 8`.

## MIR_DTOI_U >= 2^63 Limitation (UNRESOLVED)

For double values >= 2^63 (e.g., `9223372036854775808.0`, `18446744073709549568.0`), `cvttsd2si` returns the "indefinite value" `0x8000000000000000`. Correct conversion requires:
1. Compare double with 2^63 (as double `0x43E0000000000000`)
2. If >= 2^63: subtract 2^63, convert with cvttsd2si, set high bit
3. If < 2^63: convert directly

**PITFALL: `or rax, imm32` truncates to 32 bits.** The `or rax, imm32` instruction (`48 0D imm32`) sign-extends a 32-bit immediate. To set bit 63, use `mov rcx, 0x8000000000000000; or rax, rcx` instead.

**PITFALL: Multi-jump scratch register conflict.** The compare-and-branch approach requires saving the original double (xmm2), the converted value (rax/rcx/r8), and the comparison constant (xmm1). Using rax for both the converted value AND the constant load clobbers the result. Using r8 for the converted value works for < 2^63 but the jae+jmp structure broke the common case (regression from 1194→1192). This remains an open bug — values < 2^63 work, values >= 2^63 return 0.

**PITFALL: `cvttsd2si r8, xmm0` needs REX.R for r8.** Encoding `cvttsd2si r8, xmm0` as `F2 4C 0F 2C C0` (REX.W=1, REX.R=1 for r8 in reg field). For `cvttsd2si rdx, xmm0` use `F2 48 0F 2C D0` (REX.W=1, no REX.R — rdx is reg field 010). Getting the REX prefix wrong silently targets the wrong register.

**PITFALL: `push rax` / `pop rax` in JIT may corrupt stack alignment.** The JIT frame starts with `push rbp` (8 bytes), making rsp ≡ 8 (mod 16). A `push rax` makes rsp ≡ 0 (mod 16), which is fine for SSE aligned moves but may cause issues if the JIT's call convention expects specific alignment. Prefer using xmm registers (xmm2) or callee-saved GP registers (r8-r15 with REX) over push/pop for scratch storage in JIT handlers.

**PITFALL: jae+jmp dual-jump structure broke the common case.** The approach of comparing first, then jumping to redo code for >= 2^63 and jumping over it for < 2^63, caused a regression where even values < 2^63 returned 0. The likely cause: the `jae` offset was miscalculated, causing it to jump into the wrong code path. Single-jump (jb to skip correction) with push/pop for scratch is simpler but has the stack alignment concern.

**Workaround**: Use `MIR_DTOI` (signed) for now — it gives correct results for values in [-2^63, 2^63) which covers most tests. The ~5 tests with unsigned double values >= 2^63 remain failures.

**Correct algorithm (for future implementation):**
```
1. movq xmm0, rax          ; double value
2. movq xmm2, xmm0        ; save original
3. cvttsd2si r8, xmm0     ; convert (correct for < 2^63, indefinite for >= 2^63)
4. mov rax, 0x43E0000000000000  ; 2^63 as double bits
5. movq xmm1, rax         ; load comparison constant
6. movq xmm0, xmm2        ; restore original double
7. ucomisd xmm0, xmm1     ; compare with 2^63
8. mov rax, r8            ; restore converted value (may be wrong for >= 2^63)
9. jb skip                ; if < 2^63, result in rax is correct
10. movq xmm0, xmm2       ; restore original
11. subsd xmm0, xmm1      ; subtract 2^63
12. cvttsd2si rax, xmm0   ; convert reduced value
13. mov rcx, 0x8000000000000000
14. or rax, rcx           ; set high bit
15. skip:
```
This was NOT tested end-to-end due to the regression risk. The key insight is using r8 (callee-saved, GP) to preserve the first conversion result across the comparison, avoiding push/pop.

## sizeof Unsigned Arithmetic (FIXED 2026-09-16)

`sizeof` returns `size_t` (unsigned) in C. Expressions like `sizeof 4 - sizeof 4 - 1 < 0` should be false (unsigned wrap: 0-1 = UINT64_MAX, which is NOT < 0).

**Fix:** Set `n->type = HD_TYPE_U64` on the sizeof result node, and propagate this type through SUB/ADD operations. When both operands of SUB are U64, the result is U64. The CMP handler then uses unsigned comparison.

**Key insight:** The sizeof handler sets `n->type` to U64 (allocated via `calloc`). The SUB handler checks `mir_binop_result_type()` which returns the common type of the operands. When one operand is U64, the result is U64. The CMP handler checks if either operand is U64 and uses unsigned comparison.

**Narrow fix (what actually works):** Only propagate U64 through SUB/ADD when BOTH operands are U64. A wide fix (propagate when either operand is U64) breaks struct tests because struct member offsets become unsigned and the comparison logic changes.

**Result:** `sizeof_sizeof_result_is_ulong` now passes. Score +1.

## Files Changed for MIR_DTOI_U + MIR_UDIV/UMOD

- `wubu_mir.h` — new opcodes in enum
- `wubu_mir.c` — string names ("dtoi_u", "udiv", "umod")
- `wubu_mir_interp.c` — dispatch table entries + handler implementations
- `wubu_mir_regalloc.c` — register class for new ops
- `wubu_isa_x86_64.c` — JIT encoding (xor rdx,rdx + div rcx for unsigned)
- `holyd_mir_eval.c` — emit unsigned ops based on operand types