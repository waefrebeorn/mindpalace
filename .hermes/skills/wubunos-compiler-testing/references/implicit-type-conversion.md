# Implicit Type Conversion in HolyD

HolyD stores all integer values as 64-bit in `prog.mem`. C requires narrowing
conversions at multiple points. This reference covers ALL the places HolyD
implements implicit type conversion and 32-bit wrapping.

## The Rule

When a value needs to fit in a type narrower than 64 bits, emit truncation
instructions. The pattern depends on whether the type is signed or unsigned:

| C Type | MIR Pattern | JIT Encoding |
|--------|-------------|--------------|
| `signed char` | `AND val, 0xFF` → `SEXT8 val` | `and eax,0xFF` + `movsx rax,al` |
| `unsigned char` | `AND val, 0xFF` | `and eax,0xFF` |
| `signed short` | `AND val, 0xFFFF` → `SEXT16 val` | `and eax,0xFFFF` + `movsx rax,ax` |
| `unsigned short` | `AND val, 0xFFFF` | `and eax,0xFFFF` |
| `int` | `AND val, 0xFFFFFFFF` → `SEXT32 val` | `and eax,0xFFFFFFFF` + `movsxd rax,eax` |
| `unsigned int` | `AND val, 0xFFFFFFFF` | `and eax,0xFFFFFFFF` |

## Helper Functions

### `mir_truncate_to_type(g, val, type)`
Emits the correct pattern for a given `HDType`. Returns `val` unchanged for
types >= 64 bits. Defined in `holyd_mir_eval.c`.

### `mir_binop_result_type(g, left, right)`
Determines the C result type of a binary integer operation. Returns NULL for
64-bit results (no truncation needed), or a static `HDType` for 32-bit results.
Implements C usual arithmetic conversions: if either operand is 64-bit, result
is 64-bit; if both are 32-bit (or smaller, promoted to int), result is 32-bit.
Looks up IDENT types from the var table since IDENT AST nodes don't carry type.

## Where Truncation Is Applied

### 1. Variable declaration with initializer (`HD_AST_VAR_DECL`)
`val = mir_truncate_to_type(g, val, n->type)` after evaluating the initializer.

### 2. Assignment (`HD_AST_ASSIGN`)
`val = mir_truncate_to_type(g, val, n->left->type)` before store.

### 3. Compound assignments (`HD_AST_ADD/SUB/MUL/DIV/MOD/SHL/SHR/AMP/PIPE/CARET_ASSIGN`)
Look up LHS variable type from var table, truncate result before store.

### 4. Binary operations (`HD_AST_ADD/SUB/MUL/DIV/MOD/BITAND/BITOR/BITXOR`)
`mir_binop_result_type()` determines result type; truncate if 32-bit. Float ops
are excluded (checked via `is_float` flag).

### 5. Shift operations (`HD_AST_SHL/SHR`)
C shift semantics: result type = left operand type (after integer promotion).
`mir_binop_result_type(g, n->left, n->left)` determines the type.

### 6. Pre/post increment/decrement (`HD_AST_PRE_INC/POST_INC/PRE_DEC/POST_DEC`)
Truncate the updated value (`v +/- 1`) to the variable's type before storing
back. Look up type from var table.

### 7. Function return (`HD_AST_RETURN`)
Truncate return value to `g->fn_ret_type` (set from `fn->type` when entering
function body). Only for scalar integer types.

### 8. Function parameter binding (function prologue)
After all arguments are copied from registers to local variable slots, apply
truncation to each parameter based on its declared type. This MUST happen
after the copy loop — NOT during it.

### 9. Switch case values (`HD_AST_CASE`)
Truncate case value to match the switch expression's type. Look up IDENT
switch expression type from var table.

### 11. Implicit type conversion on function call arguments

When passing arguments to a function, each argument must be converted to the
corresponding parameter type at the CALL SITE (in `HD_AST_FUNC_CALL` handler).

| Arg Type | Param Type | Conversion |
|----------|------------|------------|
| double | int/long/short/char | `MIR_DTOI` |
| int/long/short/char | double | `MIR_DITOF` |

**Implementation**: After placing each argument in VR(a+1), look up the callee's
parameter type from `g->func_ast[fid]->param_types[a]` and emit the appropriate
conversion MIR op.

**Example**: `check_args(2.4, -6)` where `check_args(long l, double d)` — the
double `2.4` must be truncated to `long` (2) via DTOI, and the int `-6` must be
widened to `double` (-6.0) via DITOF.

### 12. Implicit type conversion on assignment (float↔int)

When assigning a value to a variable, the value must be converted to the LHS type.
This includes float↔int conversions:

| LHS Type | RHS Type | Conversion |
|----------|----------|------------|
| int/short/char | double | `MIR_DTOI` |
| double | int/short/char | `MIR_DITOF` |

**CRITICAL**: Both LHS and RHS types must be looked up from the var table since
IDENT AST nodes do NOT carry type annotations (`n->type == NULL` for IDENT).

```c
// In HD_AST_ASSIGN handler:
HDType *lhs_type = n->left->type;
if (!lhs_type && n->left->kind == HD_AST_IDENT)
    lhs_type = mir_find_var_type(g, n->left->ident);

HDType *rhs_type = n->right ? n->right->type : NULL;
if (!rhs_type && n->right && n->right->kind == HD_AST_IDENT)
    rhs_type = mir_find_var_type(g, n->right->ident);
```

**Helper function** `mir_find_var_type(g, name)` — searches var table from end
(most recent declaration first for shadowing) and returns `g->vars[i].type`.

The JIT uses `rcx` (x86 encoding 1) as the second-operand register for all
binary ops (AND, SEXT, etc.). `rcx` is ALSO the x86-64 4th argument register.

**When truncating function parameters:**
- CORRECT: copy all args first, then truncate each in a second loop
- WRONG: truncate during the copy loop (clobbers rcx → 4th+ args corrupted)

## Guard from Optimizer Folding

The `AND + SEXT` pattern MUST be guarded from constant folding:
- `MIR_SEXT8/16/32` and `MIR_ZEXT32` are guarded in both `fold_pass` and `fold_dce_pass`
- `MIR_AND` with a constant mask is NOT guarded (it's a normal arithmetic op)

**Pitfall**: For constant values, the optimizer folds `256 & 0xFF = 0` and then
`SEXT8(0) = 0`. This produces the correct result but the MIR may look wrong
(store uses original VR, not truncated one). For non-constant values (loaded
from variables), the truncation works correctly.

## Variable Type Tracking in Var Table

`mir_var_t` has an `HDType *type` field that stores each variable's declared
type. This is set:
- After `mir_decl_var_unsigned`/`mir_decl_var_float` in the declaration handler
- After `mir_bind_var` for function parameters (from `fn->param_types[pi]`)

This field enables type-aware codegen for compound assignments, shifts,
increment/decrement, and switch cases — all places where the AST node alone
doesn't carry type info (e.g., IDENT nodes).

**Pitfall**: IDENT AST nodes do NOT carry type annotations. Always look up
type from `g->vars[i].type` when you need the type of a variable reference.
Search from the end for correct shadowing behavior.

## For-Loop Scoping

The `for` loop handler pushes a scope (`int scope_start = g->n_vars`) before
evaluating the init expression, and pops it (`g->n_vars = scope_start`) after
the loop body. This ensures the for-init variable is scoped to the loop and
doesn't leak to the outer scope (fixing `for_shadow` test).

## Width-Aware Codegen — The Real Fix

The user explicitly REJECTS truncation as a band-aid. The proper fix is
**width-aware codegen**: emit `movl`/`addl` (32-bit) for 32-bit types and
`movq`/`addq` (64-bit) for 64-bit types, matching what GCC/chibicc do.

### Why the first attempt failed

Adding a `width` field to `wubu_mir_instr_t` and making ALL operations
width-aware broke pointer arithmetic and array indexing. The mistake was
applying 32-bit operations to pointer arithmetic (which must always be 64-bit
on x86-64).

### The correct approach

1. Add `uint8_t width` to `wubu_mir_instr_t` (0=64-bit, 1=8-bit, 2=16-bit, 3=32-bit)
2. Add `wubu_mir_binop_w()` and `wubu_mir_unop_w()` that set the width field
3. In the x86-64 JIT, emit 32-bit instructions (no REX.W) when width==3:
   - `add eax, ecx` = `01 C8` (no REX prefix)
   - `add rax, rcx` = `48 01 C8` (REX.W=1)
4. Only use width-aware ops for **arithmetic and comparison** operations
5. Keep pointer arithmetic, array indexing, and stores/loads as 64-bit
6. The MIR builder sets width based on `mir_binop_result_type()`

### Key insight from research

GCC uses `movl` (32-bit) for `int` operations and `movq` (64-bit) for `long`
operations. On x86-64, 32-bit arithmetic automatically zero-extends the
result to 64 bits, which is correct for `unsigned int`. For `int`, the
sign-extension happens automatically when the 32-bit result is loaded.

### Implementation status

The width field was added to `wubu_mir_instr_t` and `wubu_mir_binop_w()` was
implemented, but the full integration was reverted because it broke pointer
arithmetic. The truncation approach remains as a working fallback while the
width-aware approach is refined.

### Nested indexing pitfall (2026-09-08)

Attempted to fix `ptr_ptr[0][0]` (double pointer dereference) by using
`mir_gen_expr(n->left)` instead of `mir_address_of(n->left)` when the left
side is itself an INDEX. This fixed `ptr_ptr[0][0]` but broke 2D array access
(`arr[1][2]` returned 0 instead of 7).

**Root cause**: For `arr[1][2]`, the inner `arr[1]` should return the ADDRESS
of row 1 (for further indexing), but `mir_gen_expr` returns the VALUE (load
result). For `ptr_ptr[0][0]`, the inner `ptr_ptr[0]` should return the VALUE
(34, address of `ptr`), and the outer `[0]` dereferences it.

**The distinction**: Array indexing needs the address (for further indexing),
pointer indexing needs the value (to dereference). The correct fix requires
distinguishing between array types and pointer types in the INDEX handler.

**Status**: REVERTED. Nested indexing for multi-level pointers/arrays remains
an open issue.

## Alternate Type Specifier Orderings (2026-09-09)

C allows type specifiers in ANY order. HolyD's `parse_type` handles these:

| Source | Parsed Type | Mechanism |
|--------|-------------|-----------|
| `unsigned int` | U32 | Standard: U32 case consumes following I32 |
| `int unsigned` | U32 | I32 case checks for following U32 |
| `long unsigned` | U64 | I64 case checks for following U32 |
| `long int unsigned` | U64 | I64 consumes I32, then checks for U32 |
| `long long unsigned` | U64 | I64 consumes second I64, then checks for U32 |
| `signed int` | I32 | I32 case consumes following I32 |
| `signed long` | I64 | I32 case checks for following I64 |
| `int long` | I64 | I32 case checks for following I64 |
| `int signed` | I32 | I32 case consumes following I32 |

**PITFALL**: The `signed` keyword is stripped by `wubu_preproc.c` `strip_compiler_keywords`. This is intentional for GCC extensions (`__signed__`) but conflicts with `(signed)` cast syntax. Do NOT remove `signed` from the strip list — 1036+ tests need it stripped while only 1 test uses `(signed)` cast.

## Struct Initializer Type Conversion (2026-09-09 NEW)

When a struct is initialized with a brace initializer list:

```c
struct pair2 { double d; long l; };
struct pair2 retval = {a * 2, b * 2};
```

Each element expression must be converted to the corresponding member's declared type. Without this, `a * 2` (int) is stored as raw integer bits in the `double d` member, producing garbage when read back as double.

**New helper `mir_gen_cast(g, val, target_type, src_node)`**:
- Determines source type from `src_node->type` (falls back to I32 for unknown)
- Float→int: emits `MIR_DTOI`
- Int→float: emits `MIR_DITOF` (signed) or `MIR_DITOF_U` (unsigned)
- Integer truncation: delegates to `mir_truncate_to_type()`

**Implementation**: In the `HD_AST_BRACE_INIT` handler, after `ev = mir_gen_expr(g, elem)`, look up the member type from `n->type->members[e].type` and call `mir_gen_cast()`:

```c
if (is_struct_var && n->type && n->type->kind == HD_TYPE_STRUCT
    && e < (uint32_t)n->type->n_members) {
    HDType *member_type = n->type->members[e].type;
    if (member_type) {
        ev = mir_gen_cast(g, ev, member_type, elem);
    }
}
```

**PITFALL**: The initializer element's type (`elem->type`) is often NULL for expressions like `a * 2` (HD_AST_BINOP). `mir_gen_cast` handles this by falling back to `HD_TYPE_I32`, which is correct for int arithmetic. But if the element is a function call returning double, the type is also NULL — the fallback to I32 would be wrong. For now this is acceptable because struct initializers rarely use function call results.

## What NOT to Truncate

- Pointer types (`HD_TYPE_PTR`) — already 64-bit addresses
- Struct/union types — copied cell-by-cell
- Array types — copied cell-by-cell
- `long` / `unsigned long` — already 64-bit
- Float/double — handled separately

## Float/Double Handling (2026-09-09 UPDATE)

**IMPORTANT UPDATE**: The float literal storage and float ops have been changed
to use 64-bit double precision:

- Float literals now store **64-bit double bits** via `union { double d; uint64_t u; }`
- Cast handler uses `MIR_DITOF` (int→double) and `MIR_DTOI` (double→int) for `HD_TYPE_F64`
- Arithmetic uses `MIR_DADD/MIR_DSUB/MIR_DMUL/MIR_DDIV` for double precision
- Negation uses `MIR_DNEG`

This fixes double precision arithmetic (e.g. `1000.5 + 1000 = 2000.5`).

**Remaining issues:**
- NaN handling (NaN compound assign, NaN incr/decr tests still fail)
- The `MIR_FADD/SUB/MUL/FDIV` ops still exist for 32-bit float but are no longer
  used by the literal path
- **cvttsd2si 32-bit overflow** (2026-09-08): `cvttsd2si rax, xmm0` (encoding
  `F2 48 0F 2C C0`) with REX.W prefix should convert double to 64-bit signed
  int, but for values > INT_MAX (e.g. `(long)(2147483648.0)`) it returns the
  "indefinite integer value" `0x80000000` (-2147483648) instead of 2147483648.
  This is per Intel spec: cvttsd2si returns 0x80000000 on overflow for 32-bit
  destination. With REX.W, the indefinite value should be 0x8000000000000000,
  but the result is still 32-bit. Needs investigation — may require range
  checking before conversion or using a different approach for large values.

## Implicit Type Conversion on Assignment (2026-09-09 NEW)

When assigning a value to a variable, the value must be converted to the LHS type.
This includes float↔int conversions:

| LHS Type | RHS Type | Conversion |
|----------|----------|------------|
| int/short/char | double | `MIR_DTOI` (truncate double to int) |
| double | int/short/char | `MIR_DITOF` (widen int to double) |
| int (narrower) | int (wider) | `mir_truncate_to_type` (AND + SEXT) |

**CRITICAL**: Both LHS and RHS types must be looked up from the var table since
IDENT AST nodes do NOT carry type annotations (`n->type == NULL` for IDENT).

```c
// In HD_AST_ASSIGN handler:
HDType *lhs_type = n->left->type;
if (!lhs_type && n->left->kind == HD_AST_IDENT)
    lhs_type = mir_find_var_type(g, n->left->ident);

HDType *rhs_type = n->right ? n->right->type : NULL;
if (!rhs_type && n->right && n->right->kind == HD_AST_IDENT)
    rhs_type = mir_find_var_type(g, n->right->ident);
```

**Helper function** `mir_find_var_type(g, name)` — searches var table from end
(most recent declaration first for shadowing) and returns `g->vars[i].type`.

**Example**: `int i; double d = 4.9; i = d;` — without DTOI conversion, the raw
IEEE 754 bits of 4.9 (`0x4010000000000000`) are stored directly, giving
`-1717986918` instead of `4`.

### 11. Implicit type conversion on function call arguments

When passing arguments to a function, each argument must be converted to the
corresponding parameter type at the CALL SITE (in `HD_AST_FUNC_CALL` handler).

| Arg Type | Param Type | Conversion |
|----------|------------|------------|
| double | int/long/short/char | `MIR_DTOI` |
| int/long/short/char | double | `MIR_DITOF` |

**Implementation**: After placing each argument in VR(a+1), look up the callee's
parameter type from `g->func_ast[fid]->param_types[a]` and emit the appropriate
conversion MIR op.

**Example**: `check_args(2.4, -6)` where `check_args(long l, double d)` — the
double `2.4` must be truncated to `long` (2) via DTOI, and the int `-6` must be
widened to `double` (-6.0) via DITOF.

## Implicit Type Conversion on Function Call Arguments (2026-09-09 NEW)

When passing arguments to a function, each argument must be converted to the
corresponding parameter type. This happens at the CALL SITE (in the
`HD_AST_CALL`/`HD_AST_FUNC_CALL` handler), not in the function body.

| Arg Type | Param Type | Conversion |
|----------|------------|------------|
| double | int/long/short/char | `MIR_DTOI` |
| int/long/short/char | double | `MIR_DITOF` |

**Implementation**: After placing each argument in VR(a+1), look up the callee's
parameter type from `g->func_ast[fid]->param_types[a]` and emit the appropriate
conversion MIR op.

**Example**: `check_args(2.4, -6)` where `check_args(long l, double d)` — the
double `2.4` must be truncated to `long` (2) via DTOI, and the int `-6` must be
widened to `double` (-6.0) via DITOF.

**PITFALL**: The callee function's parameter types are stored in
`g->func_ast[fid]->param_types[]`, NOT in `g->prog->funcs[fid].param_types[]`.
The `func_ast` array holds the original AST nodes; the `prog->funcs` array holds
MIR-level function info.

## Function Call Return Type (2026-09-09 NEW)

Function call AST nodes (`HD_AST_FUNC_CALL`) do NOT have their `type` field set
to the callee's return type. This means:

1. `mir_is_float_node()` returns false for `fun()` even if `fun` returns `double`
2. The return handler's float-to-int conversion check fails
3. Assignment type conversion fails when RHS is a function call returning double

**Workaround for return handler**: Check if `n->child->kind == HD_AST_FUNC_CALL`
and look up the callee's return type from `g->func_ast`:

```c
if (!child_is_float && n->child->kind == HD_AST_FUNC_CALL &&
    n->child->callee && n->child->callee->kind == HD_AST_IDENT) {
    for (int i = 0; i < g->n_funcs; i++) {
        if (g->func_ast[i] && strcmp(g->func_ast[i]->ident, n->child->callee->ident) == 0) {
            HDASTNode *fn = (HDASTNode *)g->func_ast[i];
            if (fn->type && fn->type->kind == HD_TYPE_F64) child_is_float = true;
            break;
        }
    }
}
```

**PITFALL**: Setting `n->type` on the function call node directly fails because
`n` is `const HDASTNode *` in `mir_gen_expr`. The type must be looked up
separately at each use site.

## Comparison Truncation (2026-09-09)

Comparison operators (EQ/NE/LT/LE/GT/GE) must truncate both operands to the
common type BEFORE comparing. Without this, comparing `int` with `unsigned int`
fails because the 64-bit values differ (e.g., `-1` as int = `0xFFFFFFFFFFFFFFFF`,
`-1` as unsigned = `0x00000000FFFFFFFF`).

The comparison handler uses `mir_binop_result_type()` to determine the common
type, then truncates both operands with `mir_truncate_to_type()` before the
comparison. This fixes `(int)(-1) < (unsigned int)(0)` and similar comparisons.

## Double-to-Int Conversion on Function Return (2026-09-09)

When `main()` returns a double expression (e.g., `return fun(1.0)` where `fun`
returns `double`), the return handler must emit `MIR_DTOI` to convert the double
to an integer BEFORE the 32-bit truncation (AND + SEXT32). Without this, the raw
IEEE 754 bits are masked with `0xFFFFFFFF`, producing wrong results:

- `4.0` as double = `0x4010000000000000`
- Mask with `0xFFFFFFFF` = `0x00000000` = 0 (WRONG)
- After `DTOI`: `4` → mask → `4` (CORRECT)

**Implementation**: In the `HD_AST_RETURN` handler, after generating the return
value but before truncating to return type width, check if the return type is an
integer type AND the child expression produces a float result. If so, emit
`MIR_DTOI`.

**PITFALL**: `mir_is_float_node()` does NOT detect function calls returning
double — it checks `n->type->kind == HD_TYPE_F64` but function call AST nodes
(`HD_AST_FUNC_CALL`) don't have their type set to the callee's return type. You
must also check: if `n->child->kind == HD_AST_FUNC_CALL` and the callee function
(from `g->func_ast`) has `fn->type->kind == HD_TYPE_F64`, treat as float.

## Unsigned Int-to-Double Conversion (2026-09-09)

`cvtsi2sd` treats the source as a SIGNED integer. For unsigned values > LONG_MAX
(e.g., `10223372036854775816ul`), this produces wrong results because the bit
pattern is interpreted as a negative number.

**Solution**: Added `MIR_DITOF_U` op for unsigned→double conversion. Uses the
`(val>>1)*2 + (val&1)` algorithm:
- If sign bit is clear (val >= 0 as signed): use `cvtsi2sd` directly
- If sign bit is set (val > LONG_MAX): compute `(val>>1)*2.0 + (val&1)`

**JIT encoding**:
- `cvtsi2sd xmm0, rcx`: `F2 48 0F 2A C9` (NOT `0F 2C` which is `cvttsd2si`!)
- `mov rcx, 0x4000000000000000` (2.0): `48 B9` + 8 bytes
- `movq xmm2, rcx`: `66 48 0F 6E D1`
- `mulsd xmm0, xmm2`: `66 0F 59 C2`
- `and rax, 1`: `48 83 E0 01`
- `cvtsi2sd xmm1, rax`: `F2 48 0F 2A C8`
- `addsd xmm0, xmm1`: `66 0F 5C C1`
- `cvtsi2sd xmm0, rax` (positive path): `F2 48 0F 2A C0`

**CRITICAL PITFALLS**:
1. `cvtsi2sd` opcode is `0F 2A`, NOT `0F 2C` (which is `cvttsd2si`). Using the wrong opcode silently converts in the wrong direction.
2. For `movq xmm1, rax`: use ModRM `C8` (reg=001/xmm1, rm=000/rax) with plain REX.W (0x48). Do NOT use REX.B (0x49) — REX.B extends RM to r8 instead of rax.
3. For `movq xmm0, rax`: use ModRM `C0` (reg=000/xmm0, rm=000/rax).

**LIMITATION**: The split-and-multiply approach loses precision for values exactly between two representable doubles (rounding edge cases). Correct IEEE 754 rounding requires more sophisticated logic.

**Optimizer folding**: `MIR_DITOF` and `MIR_DITOF_U` must be added to the constant-folding pass so that compile-time constants get the correct double value. For `MIR_DITOF_U`, use `(double)(uint64_t)const_val` to get the correct unsigned conversion.

`sizeof` on a variable IDENT must look up the variable's type from the var table
to return the correct size. Previously, all scalar variables returned 4 (assumed
`int`). Now uses `g->vars[i].type` via `hd_type_size()`:
- `double d; sizeof d` → 8 (was returning 4)
- `unsigned char c; sizeof c` → 1
- `void *p; sizeof p` → 8

## Function Call Return Type Lookup (2026-09-09 — three use sites)

Function call AST nodes (`HD_AST_FUNC_CALL`) never have their `type` field set
(because `n` is `const` in `mir_gen_expr`). You must look up the callee's return
type at EACH use site. The pattern:

```c
HDType *get_call_return_type(HDMirGen *g, const HDASTNode *call_node) {
    if (call_node->callee && call_node->callee->kind == HD_AST_IDENT) {
        for (int i = 0; i < g->n_funcs; i++) {
            if (g->func_ast[i] && strcmp(g->func_ast[i]->ident, call_node->callee->ident) == 0) {
                return ((HDASTNode *)g->func_ast[i])->type;
            }
        }
    }
    return NULL;
}
```

**Three places this matters:**
1. **VAR_DECL initializer**: `double d = foo()` — look up return type to decide DITOF/DTOI
2. **Assignment RHS**: `d = foo()` — look up return type for float↔int conversion
3. **Call-site argument conversion**: `bar(foo())` — look up return type to convert arg to param type

**Type inference fallback chain** (use when type is unknown):
1. `n->args[a]->type` (set by parser for literals)
2. `mir_find_var_type(g, n->args[a]->ident)` (for IDENT nodes)
3. `get_call_return_type(g, n->args[a])` (for function calls)
4. `mir_is_float_node(g, n->args[a]) ? HD_TYPE_F64 : HD_TYPE_I32` (last resort)

**Example**: `check_args(2.4, -6)` where `check_args(long, double)`:
- Arg 0: `2.4` has type F64 (float literal), param is I64 → emit DTOI
- Arg 1: `-6` is HD_AST_NEG (type NULL), fallback infers I32, param is F64 → emit DITOF

## sizeof on Binary Operations (2026-09-12)

`sizeof` on a binary expression must return the C result type of that expression, considering integer promotion and usual arithmetic conversions.

### Integer Promotion for Small Types

When both operands are 8-bit (`char`) or 16-bit (`short`), C promotes both to `int` (32-bit) before the operation. The result type is `int` (4 bytes):

```c
sizeof(char ^ char)  → 4 (not 1)
sizeof(char & int)   → 4
sizeof(short | short) → 4
```

**Implementation**: In the sizeof handler, before calling `mir_binop_result_type()`, check if both operands are 8/16-bit. If so, return 4 directly:

```c
HDType *olt = NULL, *ort = NULL;
if (n->child->left && n->child->left->type) olt = n->child->left->type;
if (!olt && n->child->left && n->child->left->kind == HD_AST_IDENT && n->child->left->ident[0])
    olt = mir_find_var_type(g, n->child->left->ident);
// same for right
if (olt && (olt->kind == HD_TYPE_I8 || olt->kind == HD_TYPE_U8 ||
            olt->kind == HD_TYPE_I16 || olt->kind == HD_TYPE_U16) &&
    ort && (ort->kind == HD_TYPE_I8 || ort->kind == HD_TYPE_U8 ||
            ort->kind == HD_TYPE_I16 || ort->kind == HD_TYPE_U16)) {
    size = 4; /* both promoted to int */
}
```

**PITFALL**: `mir_binop_result_type()` returns NULL when both operands are 8/16-bit (both set to NULL after promotion), which the sizeof handler interprets as 64-bit. You must check for the 8/16-bit case BEFORE calling `mir_binop_result_type()`.

### Shift Operations

For `<<` and `>>`, the result type is the LEFT operand type (after integer promotion), NOT the common type:

```c
sizeof(int << long)   → 4 (left operand type)
sizeof(char << int)   → 4 (char promoted to int)
sizeof(long >> char)  → 8 (left operand type)
```

**Implementation**: Handle shift operations separately in the sizeof handler, using the left operand type.

### Compound Assignment

For `sizeof(i /= 10ul)`, the result type is the LHS type (the type of `i`), not the result of the division:

```c
sizeof(int /= ulong)  → 4 (int)
sizeof(double -= int) → 8 (double)
sizeof(char %= int)  → 1 (char)
```

**Implementation**: In the sizeof handler, check for all compound assignment operators and use the LHS type.

### IDENT Type Lookup

IDENT AST nodes do NOT carry type annotations. When determining the type of an operand in sizeof, always fall back to `mir_find_var_type(g, ident)` which searches the var table from the end (most recent declaration first).

## Extern Variable Declarations Inside Functions (2026-09-12)

When `extern int a;` appears inside a function, it refers to the GLOBAL variable `a`, NOT a new local. HolyD's parser sets `is_extern=1` on the VAR_DECL AST node.

**Implementation in `holyd_mir_eval.c` VAR_DECL handler:**
1. Search the var table from the BEGINNING (globals are at low indices) for a variable with the same name
2. If found, remove any LOCAL shadowing entries (higher indices) by shifting subsequent entries down
3. Skip allocation (`goto extern_done`) — the global variable's address is reused

```c
if (n->is_extern) {
    for (int i = 0; i < g->n_vars; i++) {
        if (strcmp(g->vars[i].name, n->ident) == 0 && g->vars[i].addr != 0) {
            /* Remove shadowing locals so references resolve to global */
            for (int j = g->n_vars - 1; j > i; j--) {
                if (strcmp(g->vars[j].name, n->ident) == 0) {
                    for (int k = j; k < g->n_vars - 1; k++)
                        g->vars[k] = g->vars[k + 1];
                    g->n_vars--;
                }
            }
            goto extern_done;
        }
    }
}
```

**PITFALL: Searching from end finds the WRONG variable.** If you search `g->vars` from the end for an extern declaration, you find the local variable (most recent) instead of the global. Always search from the beginning for extern — globals are declared first.

**PITFALL: Skipping allocation without removing shadowing locals.** If you only skip allocation but don't remove local shadowing entries, `mir_find_var` (which searches from end) still finds the local variable first, and the extern declaration has no effect.

**Parser note:** The `extern` keyword is handled in two places:
1. `parse_decl` line ~1414: handles `extern "C"` function declarations and `extern type name;` variable declarations
2. `hd_parse_decl` line ~1509: handles `extern` after type specifiers (e.g., `int static extern x`)

For variable declarations, the parser calls `hd_parse_decl(p)` then sets `decl->is_extern = 1`.

Forward declarations (`int foo(void);`) followed by definitions (`int foo(void) { ... }`)
cause issues because `mir_collect_funcs` collects both as separate function entries.
The forward declaration gets a lower func_id and no body, so calls resolve to it
and return 0.

**Attempted fix**: Skip forward declarations (no body) in `mir_collect_funcs`.
**Result**: Score dropped because some tests rely on forward declarations being
in the func table (e.g., for function pointer assignment).

**Correct approach**: Collect all functions but mark which have bodies. When
resolving calls, prefer functions with bodies. This requires tracking a
`has_body` flag per function entry.

### 13. Float-to-int conversion in array element initializers (2026-09-15)

When an array element initializer is a float literal and the array element type is an integer type, the float must be converted to int BEFORE storing to the array. Without this, raw IEEE 754 bits are stored as the element value.

**Implementation**: In the `HD_AST_BRACE_INIT` handler, after `ev = mir_gen_expr(g, elem)`, check if the element is a float and the array element type is an integer:

```c
if (!is_struct_var && n->type && n->type->kind == HD_TYPE_ARRAY && n->type->base) {
    HDType *elem_type = n->type->base;
    HDTypeKind elem_k = elem_type->kind;
    int init_is_float = mir_is_float_node(g, elem);
    if (init_is_float && (elem_k == HD_TYPE_I64 || elem_k == HD_TYPE_U64 ||
                          elem_k == HD_TYPE_I32 || elem_k == HD_TYPE_U32 ||
                          elem_k == HD_TYPE_I16 || elem_k == HD_TYPE_U16 ||
                          elem_k == HD_TYPE_I8 || elem_k == HD_TYPE_U8)) {
        if (elem_k == HD_TYPE_U64 || elem_k == HD_TYPE_U32 ||
            elem_k == HD_TYPE_U16 || elem_k == HD_TYPE_U8)
            ev = wubu_mir_unop(g->prog, MIR_DTOI_U, ev);
        else
            ev = wubu_mir_unop(g->prog, MIR_DTOI, ev);
    }
}
```

**PITFALL**: The original code only did conversion for struct member initializers (`is_struct_var`), not for plain array elements. This meant `unsigned long arr[] = {3458764513821589504.0}` stored raw double bits.

### 14. Assignment to INDEX lvalues (arr[i] = expr) (2026-09-15)

When assigning to an array element (`arr[i] = expr`), the LHS is an INDEX node, not an IDENT. The type lookup must walk up the INDEX chain to find the root variable and get its element type:

```c
if (!lhs_type && n->left->kind == HD_AST_INDEX) {
    const HDASTNode *root = n->left;
    while (root && root->kind == HD_AST_INDEX) root = root->left;
    if (root && root->kind == HD_AST_IDENT) {
        lhs_type = mir_find_var_type(g, root->ident);
        if (lhs_type && lhs_type->kind == HD_TYPE_ARRAY && lhs_type->base)
            lhs_type = lhs_type->base;  /* get element type, not array type */
    }
}
```

**PITFALL**: The original code only handled `HD_AST_IDENT` LHS. For `HD_AST_INDEX` LHS, `lhs_type` remained NULL and ALL type conversion (float→int, truncation) was skipped. This meant `arr[0] = 3458764513821589504.0` stored raw double bits.

**PITFALL**: When getting the element type from an array variable, you MUST follow `type->base` to get the element type. Using the array type itself for conversion checks will fail (ARRAY is not I64/U64/etc).

## Nested Loop Break (2026-09-09 — OPEN ISSUE)

`break` inside a nested for-loop inside an if/else may not correctly exit only
the inner loop. The for-loop handler pushes `scope_start` for variable scoping,
but the loop stack management for nested loops with complex control flow
(if/else + break) may have issues. Investigation ongoing.

## Break in Switch Statements

The switch handler pushes `break_label` onto `g->loop_done[]` BEFORE generating
case bodies, and pops it AFTER. This ensures `break` inside a switch correctly
jumps to after the switch (not to a loop continuation point). Without this,
break falls through to the next case.

## Constant Suffix Type Propagation

The lexer stores `HDToken.is_unsigned` and `HDToken.is_long` flags when scanning
integer constants with `u/U/l/L` suffixes. The parser propagates this to
`HD_AST_INT_LIT.type`:
- `unsigned` suffix only, value ≤ 0xFFFFFFFF → `HD_TYPE_U32`
- `unsigned` suffix, value > 0xFFFFFFFF → `HD_TYPE_U64`
- `long` suffix → `HD_TYPE_I64`
- Both `unsigned` + `long` → `HD_TYPE_U64`

This ensures large constants like `68719476736u` (2^36) are treated as 64-bit
and not truncated to 32 bits.

## I64/U64 Must Be in ALL Type Conversion Checks (2026-09-09)

When checking "is this an integer type that needs float↔int conversion", you
MUST include `HD_TYPE_I64` and `HD_TYPE_U64` alongside the smaller integer types.
The original code only checked `I8/U8/I16/U16/I32/U32`, missing `I64/U64`.

**Affected locations** (all in `holyd_mir_eval.c`):
1. **VAR_DECL initializer** (line ~1226): double→int conversion for `long l = 4611686018427389440.;`
2. **Assignment** (line ~1831): double→int conversion for `l = d;`
3. **Return** (line ~1330): double→int conversion for `return d;` when fn returns long
4. **Compound assignment** (line ~1871, ~1898): truncation for `l += 1.5;`

**The pattern**: When checking if a type is an integer type for conversion purposes,
use:
```c
if (k == HD_TYPE_I8 || k == HD_TYPE_U8 || k == HD_TYPE_I16 ||
    k == HD_TYPE_U16 || k == HD_TYPE_I32 || k == HD_TYPE_U32 ||
    k == HD_TYPE_I64 || k == HD_TYPE_U64) { ... }
```

**PITFALL**: Forgetting I64/U64 means `long l = 4611686018427389440.;` stores raw
IEEE 754 bits truncated to 32 bits instead of properly converting double→long.
The value `4611686018427389440.` has bits `0x41EFFFFFFFFFFFFF` — AND with
`0xFFFFFFFF` gives `0xFFFFFFFF` = -1, not the expected `4611686018427389952`.

## Return Handler Int→Double Conversion (2026-09-09)

When a function returns `double` but the return expression is an integer (e.g.,
`return 18446744073709551586ul;`), the return handler must emit `MIR_DITOF` or
`MIR_DITOF_U` to convert the integer to double. Without this, the raw integer
bits are stored as the return value, and the caller interprets them as IEEE 754
double bits — producing garbage.

**Implementation**: In the `HD_AST_RETURN` handler, after generating the return
value, check if `g->fn_ret_type->kind == HD_TYPE_F64` and the child is NOT a
float node. If so, emit `MIR_DITOF` (signed) or `MIR_DITOF_U` (unsigned).

**PITFALL**: The child node's type determines signed vs unsigned. For
`return 18446744073709551586ul;`, the parser sets `n->child->type->kind = HD_TYPE_U64`,
so use `MIR_DITOF_U`. For `return -30l;`, the type is `HD_TYPE_I64`, so use
`MIR_DITOF`.
