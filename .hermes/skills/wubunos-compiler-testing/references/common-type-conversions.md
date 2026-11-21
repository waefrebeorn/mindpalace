# Common Type Conversions (C Usual Arithmetic Conversions)

## The Problem

In C, binary and comparison operators convert both operands to a common type before operating. HolyD's initial implementation checked individual operand types for signedness, which fails for mixed types:

```c
unsigned int u;
long l;
u > l;  // Common type is long (signed), but HolyD used MIR_UGT (unsigned)
```

## mir_common_cmp_type()

Determines the common comparison type per C standard rules:

1. If either operand is 64-bit (I64/U64), common type is 64-bit
2. If one is 64-bit and other is 32-bit: common type is the 64-bit type (signed long can represent all unsigned int values)
3. If both 32-bit: if either is unsigned, use U32; otherwise I32

```c
static HDTypeKind mir_common_cmp_type(HDMirGen *g, const HDASTNode *left, const HDASTNode *right) {
    // Look up types from AST node, then var table for IDENT nodes
    // ...
    if (l64 && r64) {
        if (lt->kind == HD_TYPE_U64 || rt->kind == HD_TYPE_U64) return HD_TYPE_U64;
        return HD_TYPE_I64;
    }
    if (l64 || r64) {
        if (l64) return lt->kind;
        return rt->kind;
    }
    if (lt->kind == HD_TYPE_U32 || rt->kind == HD_TYPE_U32) return HD_TYPE_U32;
    return HD_TYPE_I32;
}
```

## Application: Comparison Operators

The comparison handlers (LT/LE/GT/GE) use `mir_common_cmp_type()` to determine signedness:

```c
HDTypeKind ct = mir_common_cmp_type(g, n->left, n->right);
int is_unsigned = (ct == HD_TYPE_U32 || ct == HD_TYPE_U64);
wubu_mir_op_t op = is_unsigned ? MIR_ULT : MIR_LT;
```

This ensures `u > l` (unsigned int vs long) uses `MIR_GT` (signed) because the common type is `long`.

## Application: Ternary Float Conversion (IMPLEMENTED 2026-09-10)

When either branch of a ternary is float, the integer branch must be converted to float at runtime. The ternary handler checks `mir_is_float_node()` on both branches:

```c
int either_float = mir_is_float_node(g, n->then_branch) || mir_is_float_node(g, n->else_branch);
if (either_float) {
    if (!mir_is_float_node(g, n->then_branch)) {
        int u = then_unsigned; // from var table lookup or AST type
        then_val = wubu_mir_unop(g->prog, u ? MIR_DITOF_U : MIR_DITOF, then_val);
    }
    // same for else_branch
}
```

This handles `flag ? 5.0 : 9223372036854777850ul` correctly — the unsigned long branch is converted to double via `MIR_DITOF_U`.

## Application: Ternary Integer Common Type (IMPLEMENTED 2026-09-11)

The ternary operator `a ? b : c` converts both `b` and `c` to their common type. For integer-only ternaries with mixed signedness (e.g., `flag ? i : ui` where `i` is `int` and `ui` is `unsigned int`), the common type is `unsigned int`. Both branches must be zero-extended with `AND 0xFFFFFFFF`.

### Implementation

In the ternary handler, when `!either_float` and the common type is 32-bit unsigned:

```c
int then_unsigned = mir_is_unsigned_node(g, n->then_branch);
int else_unsigned = mir_is_unsigned_node(g, n->else_branch);
int common_unsigned = then_unsigned || else_unsigned;
int then_is_64 = (n->then_branch->type && (n->then_branch->type->kind == HD_TYPE_I64 || n->then_branch->type->kind == HD_TYPE_U64));
int else_is_64 = (n->else_branch->type && (n->else_branch->type->kind == HD_TYPE_I64 || n->else_branch->type->kind == HD_TYPE_U64));
if (!then_is_64 && !else_is_64 && common_unsigned) {
    then_val = wubu_mir_binop(g->prog, MIR_AND, then_val, wubu_mir_const(g->prog, 0xFFFFFFFF));
}
```

**CRITICAL**: Only apply zero-extension when BOTH branches are 32-bit (not 64-bit). For mixed 32/64-bit ternaries (e.g., `flag ? -30 : 10ul`), the common type is 64-bit so zero-extension is skipped — the cast/return handler uses `ditof_u` instead.

### Pitfall: Zero-Extending Both Branches

When `common_unsigned` is true, BOTH branches must be zero-extended (not just the unsigned one). This is because the common type is `unsigned int`, so the signed branch's value must also be interpreted as unsigned. For `flag ? -1 : 1u`, `-1` becomes `4294967295` after zero-extension.

### Pitfall: Don't Zero-Extend 64-Bit Branches

For `flag ? -30 : 10ul`, zero-extension would corrupt the `10ul` value (which needs all 64 bits). The check `!then_is_64 && !else_is_64` prevents this.

## Pitfall: FUNC_CALL ident Location

`HD_AST_FUNC_CALL` nodes store the function name in `n->callee->ident`, NOT `n->ident`. When `mir_common_cmp_type` encounters a FUNC_CALL node, it cannot determine the type from `n->type` (NULL) or `n->ident` (empty). Must look up `n->callee->ident` in `g->func_ast[]`.

## Files Affected

- `holyd_mir_eval.c` — `mir_common_cmp_type()` function, comparison handlers (LT/LE/GT/GE)
- `wubu_mir.h` — no changes needed (existing comparison ops sufficient)
- `wubu_isa_x86_64.c` — no changes needed (comparison encoding already correct)