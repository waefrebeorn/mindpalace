# Float-Int Promotion in Mixed-Type Operations

When a binary operation has one float operand and one integer operand, C's "usual arithmetic conversions" require promoting the integer to double before the operation. HolyD's flat VR model (all values are 64-bit) means this promotion must be explicit.

## The Problem

`e + 1.0` where `e` is int: the JIT's `MIR_DADD` interprets both operands as IEEE 754 double bits. The integer `5` becomes a tiny denormal double (~2.5e-323), not `5.0`.

## The Solution: mir_promote_to_float()

```c
static wubu_vr_t mir_promote_to_float(HDMirGen *g, wubu_vr_t val, const HDASTNode *n) {
    if (!n) return val;
    if (mir_is_float_node(g, n)) return val;  /* already float */
    switch (n->kind) {
    case HD_AST_INT_LIT:
    case HD_AST_CHAR_LIT:
    case HD_AST_NEG:
    case HD_AST_ADD:
    case HD_AST_SUB:
    case HD_AST_MUL:
    case HD_AST_DIV:
    case HD_AST_MOD:
    case HD_AST_BITNOT:
    case HD_AST_AND:
    case HD_AST_OR:
    case HD_AST_BITXOR:
    case HD_AST_IDENT:
        break;
    default:
        return val;  /* don't promote ambiguous nodes */
    }
    int is_unsigned = (n->type && (n->type->kind == HD_TYPE_U8 || ...));
    return wubu_mir_unop(g->prog, is_unsigned ? MIR_DITOF_U : MIR_DITOF, val);
}
```

## Where to Apply

- **Binary arithmetic** (ADD/SUB/MUL/DIV): YES — apply to both operands when `is_float` is true
- **Compound assignment** (+=/-=/*=//=): YES — apply to RHS when `is_float` is true
- **Increment/decrement** (++/--): YES — use DADD/DSUB with 1.0 for float vars
- **Comparisons** (EQ/NE/LT/LE/GT/GE): YES — but ONLY when `mir_is_double_cmp(op)` is true, and exclude sizeof nodes from `mir_is_float_node()`

## Comparison Float Promotion (WORKING, 2026-09-12)

Naive promotion in comparison handlers broke `sizeof` tests (ch17) and pointer tests (ch14). The working approach:

1. After `mir_cmp_op()` selects the comparison op, check `mir_is_double_cmp(op)` (MIR_DLT/DLE/DGT/DGE/DDEQ/DDNE)
2. If double comparison, call `mir_promote_cmp_operands(&a, &b, left, right)` to promote the non-float operand
3. `mir_promote_to_float()` uses `MIR_DITOF` for signed, `MIR_DITOF_U` for unsigned sources

```c
static int mir_is_double_cmp(wubu_mir_op_t op) {
    return (op == MIR_DLT || op == MIR_DLE || op == MIR_DGT || op == MIR_DGE ||
            op == MIR_DEQ || op == MIR_DNE);
}

static void mir_promote_cmp_operands(HDMirGen *g, wubu_vr_t *a, wubu_vr_t *b,
                                      const HDASTNode *left, const HDASTNode *right) {
    int lf = mir_is_float_node(g, left);
    int rf = mir_is_float_node(g, right);
    if (lf && !rf) *b = mir_promote_to_float(g, *b, right);
    else if (!lf && rf) *a = mir_promote_to_float(g, *a, left);
}
```

### Critical: Exclude SIZEOF from mir_is_float_node

`sizeof(double)` has `n->type == HD_TYPE_F64` (the type being measured), but the sizeof result is always an integer constant. Without the sizeof exclusion, `mir_is_float_node` returns true for `sizeof(double)`, causing spurious `ditof` promotion of the other operand in comparisons like `sizeof(double) != 8`.

```c
/* sizeof always returns an integer constant, never a float */
if (n->kind == HD_AST_SIZEOF) return false;
```

This check must come BEFORE the `n->type->kind == HD_TYPE_F64` catch-all in `mir_is_float_node()`.

### Placement Order

Promotion must happen AFTER `mir_cmp_op()` selects the op but BEFORE truncation (`mir_truncate_to_type`). Truncation to 32-bit after promotion would corrupt the double value.

## MIR_DITOF_U Exact Algorithm

The unsigned int-to-double conversion uses an EXACT high/low 32-bit split:

```
result = (double)(uint32_t)(val >> 32) * 4294967296.0 + (double)(uint32_t)val
```

This is exact for ALL 64-bit unsigned values because:
- `(val >> 32)` is at most 32 bits, exactly representable as double
- `(uint32_t)val` is at most 32 bits, exactly representable as double
- The two parts don't overlap in the double representation (2^32 scaling separates them)

**JIT encoding** (wubu_isa_x86_64.c):
```
mov rcx, rax          ; save original val
shr rcx, 32           ; high 32 bits
mov edx, ecx          ; zero-extend to 64-bit
cvtsi2sd xmm0, rdx    ; convert high part to double
movabs rcx, 0x41F0000000000000  ; 2^32 = 4294967296.0
movq xmm2, rcx        ; load 2^32 into xmm2
mulsd xmm0, xmm2      ; high * 2^32
mov ecx, eax          ; low 32 bits
mov edx, ecx          ; zero-extend to 64-bit
cvtsi2sd xmm1, rdx    ; convert low part to double
addsd xmm0, xmm1      ; high*2^32 + low
movq rax, xmm0        ; result
```

**CRITICAL PITFALL**: Use `mov edx, ecx` (NOT `xor edx, edx`) for the low part. `xor edx, edx` zeros the register before `cvtsi2sd`, losing the low 32 bits. The sequence must be: `mov ecx, eax` THEN `mov edx, ecx` THEN `cvtsi2sd xmm1, rdx`.

**addsd opcode**: `66 0F 58 C1` (NOT subsd `66 0F 5C C1`). The two differ by one byte.

**OLD ALGORITHM** (lossy, DO NOT USE): `(val>>1)*2 + (val&1)`. This loses precision for values exactly between two representable doubles (e.g., `9223372036854776833ul` rounds incorrectly).

## Float Increment/Decrement

`d++` on a double variable must use `MIR_DADD` with `1.0` (double bits), NOT integer `MIR_ADD` with `1`:

```c
if (is_float_var) {
    union { double d; int64_t i; } u;
    u.d = 1.0;
    wubu_vr_t one_d = wubu_mir_const(g->prog, u.i);
    upd = wubu_mir_binop(g->prog, MIR_DADD, tmp, one_d);
}
```

## FUNC_CALL Detection

`mir_is_float_node()` must handle `HD_AST_FUNC_CALL` by looking up the callee's return type from `g->func_ast[]`. Without this, function calls returning double get spurious `MIR_DITOF`.

## mir_truncate_to_type Double-Promotion Bug (2026-09-21)

**BUG**: `mir_truncate_to_type(val, HD_TYPE_F64)` unconditionally calls `MIR_DITOF` (integer-to-double conversion), even when the value is ALREADY a double. This reinterprets the raw IEEE 754 bits as an integer and converts that to a different double.

**Symptom**: `double local = arr[0]` produces wrong value. `arr[0]` loads correct double bits, but the assignment handler calls `mir_truncate_to_type(val, HD_TYPE_F64)` which applies `MIR_DITOF`, converting the raw bits as if they were an integer.

**Fix**: In `mir_truncate_to_type`, check if the source value is already F64 before applying DITOF. Need to determine the RHS type from the AST node or var table. If `rhs_type && rhs_type->kind == HD_TYPE_F64`, skip the conversion.

**Also affects**: Any assignment of a double value to a double variable — `double d = 4e12; double local = d;` also fails. The bug is in the assignment handler's truncation logic, not in the load.
