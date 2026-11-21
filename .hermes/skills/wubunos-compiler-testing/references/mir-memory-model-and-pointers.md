# MIR Memory Model and Pointer Conversion

## MIR Memory Layout

The MIR (Medium Intermediate Representation) model uses a flat memory space of 64-bit cells:

- `prog.mem` is allocated as `uint8_t *` (byte-addressable since 2026-09-13 rewrite)
- All variables, arrays, and structs are allocated as contiguous cells
- Each cell is 8 bytes; a `char buf[10]` occupies 10 cells (80 bytes) in the cell model
- **Array element addresses are byte offsets** into `prog.mem`. The JIT's LOAD/STORE uses `mem[addr]` directly (addr is byte offset). No `shl rax, 3`.
- `mir_struct_member_offset()` returns **byte offsets** (since byte-addressable rewrite)
- Struct size in `mir_struct_t.total_size` is in **cells** (for memory allocation)

## Type Size vs Cell Size Mismatch

**CRITICAL**: HolyD's type system uses real C sizes, but the memory model uses 8-byte cells:

| C type | HD type | hd_type_size() | Cell size | sizeof in gauntlet |
|--------|---------|----------------|-----------|-------------------|
| `int` | HD_TYPE_I32 | 4 | 8 | 4 |
| `long` | HD_TYPE_I64 | 8 | 8 | 8 |
| `char` | HD_TYPE_I8 | 1 | 8 | 1 |
| `double` | HD_TYPE_F64 | 8 | 8 | 8 |

**Pitfall**: When computing array element offsets for multi-dimensional arrays, use `array_size * 8` (cells), NOT `hd_type_size(base)` (bytes). For `int[2][2]`, each row is 2 cells = 16 bytes, NOT `hd_type_size(I32)*2 = 8` bytes. Using `hd_type_size` causes rows to overlap.

**Pitfall**: `sizeof(arr)` for an array variable must use `hd_type_size(g->vars[i].type)` (which walks the full array type chain), NOT `g->vars[i].array_size * 4` (hardcoded int size). For `long[5]`, `array_size * 4 = 20` but `hd_type_size(type) = 40`.

**Pitfall**: Multi-dimensional array `arr_size` (for memory allocation) must be the PRODUCT of all dimensions. For `int[2][2]`, `arr_size = 4` (2*2), NOT `2` (outermost only). Use a while loop walking the type chain: `arr_size *= at->array_size`.

## Multi-Dimensional Array Indexing (2026-09-15)

### INDEX Handler Base Selection (UPDATED 2026-09-20)

For `arr[i][j]` and deeper nesting, the INDEX handler must distinguish between:
- **Array base (IDENT)**: use `mir_address_of` to get the base address
- **INDEX/DEREF base where ultimate base is pointer-to-pointer**: use `mir_gen_expr` to get the loaded pointer VALUE
- **INDEX/DEREF base where ultimate base is pointer-to-array or array**: use `mir_address_of` to get the sub-array ADDRESS

The blanket rule "INDEX/DEREF base → mir_gen_expr" is WRONG for pointer-to-array parameters. See "Pointer-to-Pointer Double Indexing" section above for the correct type-based decision logic.

**Intermediate dimensions return addresses, not values.** For `arr[i][j]` on `int[3][4]`:
- `arr[i]` should return the ADDRESS of row `i` (it's `int[4]` which decays to `int*`)
- `arr[i][j]` should LOAD the value

**Rule**: If the base variable is a multi-dimensional array (type chain has >1 ARRAY), the outermost INDEX returns the address (no load). The same applies to `mir_address_of` and `mir_lvalue_addr` INDEX handlers — all three must use the same logic.

### mir_index_stride — Correct N-Dimensional Stride Computation

**OLD (broken for 3D+):** Used `array_stride * 8` for depth<=1, `8` for depth>1. Only worked for 1D/2D.

**NEW (correct):** Walk the type chain to collect all array sizes, then compute stride as the product of remaining dimensions:

```c
int sizes[8], nsz = 0;
HDType *t = vt;
while (t && t->kind == HD_TYPE_ARRAY && nsz < 8) {
    sizes[nsz++] = (int)t->array_size;
    t = t->base;
}
/* depth = number of INDEX levels from outermost (1 = outermost INDEX).
 * For depth=d, stride = product(sizes[d..nsz-1]) * 8 */
if (depth >= 1 && depth <= nsz) {
    int stride = 8;
    for (int d = depth; d < nsz; d++) {
        stride *= sizes[d];
    }
    return stride;
}
```

For `int[2][3][4]` with `sizes=[2,3,4]`, `nsz=3`:
- depth=1 (outermost): stride = 3*4*8 = 96
- depth=2: stride = 4*8 = 32
- depth=3 (innermost): stride = 8

**Pitfall**: `mir_index_stride` is called from the INDEX handler with the OUTERMOST INDEX node. Depth counts total INDEX levels in the chain. A single `arr[i]` has depth=1 regardless of array dimensionality.

## Multi-Dimensional Array Initialization

### Nested Brace-Init Flattening

Nested brace-inits like `int arr[2][2] = {{1,2},{3,4}}` require recursive flattening:
- Use a stack-based approach to collect all scalar values from nested `HD_AST_BRACE_INIT` nodes
- Element offset for outer dimension: `e * elem_sz` where `elem_sz = product_of_inner_dimensions * 8`
- Sub-element offset: `offset + s * 8`
- Store each scalar via `wubu_mir_store`

**Pitfall**: The `elem_sz` computation must use the PRODUCT of ALL inner dimensions, not just the immediate `base->array_size`. For `int[4][2][6]`, `elem_sz = 2*6*8 = 96`, NOT `2*8 = 16` or `6*8 = 48`.

```c
int total_cells = 1;
HDType *t = n->type->base;
while (t && t->kind == HD_TYPE_ARRAY) {
    total_cells *= (int)t->array_size;
    t = t->base;
}
elem_sz = total_cells * 8;
```

### Type Conversion in Array Initializers (2026-09-15)

**CRITICAL**: Array element initializers must convert the value to the element's scalar type before storing. The conversion code must be applied BOTH in the scalar (non-brace) path AND in the nested brace-init flattening loop — the flattening loop has its own `continue` that skips the scalar-path conversion.

For the element type, find the SCALAR base type by stripping array layers:
```c
HDType *scalar_type = n->type->base;
while (scalar_type && scalar_type->kind == HD_TYPE_ARRAY && scalar_type->base)
    scalar_type = scalar_type->base;
HDTypeKind elem_k = scalar_type ? scalar_type->kind : HD_TYPE_I64;
```

Conversions needed:
- `!init_is_float && elem_k == HD_TYPE_F64`: emit `MIR_DITOF` (int → double)
- `init_is_float && elem_k` is integer type: emit `MIR_DTOI` or `MIR_DTOI_U` (double → int)

**Pitfall**: For multi-dimensional arrays, `n->type->base` is another ARRAY, not the scalar type. Always walk to the scalar base before checking the kind.

## Uninitialized Variable Type Corruption (2026-09-15)

**ROOT CAUSE OF 3D ARRAY FAILURES**: `holyd_parse.c` declared `int vla_dims[8]` WITHOUT initialization. Garbage stack values caused `has_vla` to be true for non-VLA arrays, triggering the VLA code path which replaced the ARRAY type with a PTR type.

**Fix**: `int vla_dims[8] = {0};`

**Debugging pattern**: When array types show `kind=HD_TYPE_PTR` or `kind=HD_TYPE_BOOL` instead of `HD_TYPE_ARRAY` at codegen time, check for uninitialized local arrays in the parser. Use `fprintf(stderr, "type=%p kind=%d", (void*)n->type, n->type->kind)` at both parse time and codegen time to detect when/where corruption occurs.

**Pitfall**: Always initialize local arrays in parser functions — the parser is called repeatedly and stack contents persist between calls.

## Pointer Subtraction (2026-09-15)

**CRITICAL**: Pointer subtraction `(p2 - p1)` must DIVIDE the byte difference by the element size, NOT multiply the operand by the stride.

**WRONG**: `b = b * ptr_scale; result = a - b;`
**RIGHT**: `result = (a - b) / ptr_scale;`

```c
wubu_vr_t r = wubu_mir_binop(g->prog, MIR_SUB, a, b);
if (ptr_scale > 1) {
    r = wubu_mir_binop(g->prog, MIR_DIV, r, wubu_mir_const(g->prog, (int64_t)ptr_scale));
}
```

## Function Call Register Corruption

**CRITICAL BUG (2026-09-14, unresolved)**: When a function uses global variables and is called multiple times in sequence, the second call may read corrupted global values. Example:

```c
double two = 2.0;
int f1(void) { return two == 2.0; }
int f2(void) { return two == 2.0; }
int main(void) {
    if(!f1()) return 1;  // returns 0 (wrong!) when f2 is also defined
    if(!f2()) return 2;
    return 0;
}
```

**Mechanism**: Global variable addresses are loaded into registers before the call. The JIT saves/restores registers around calls (r11-r15, r8, r9, rdx), but r10 (reg 0, return value) is NOT saved. If a global address ends up in r10 or another unsaved register, the call clobbers it.

**Workaround**: None reliable. This affects ~15-20 gauntlet tests that use globals across function calls.

## The Pointer Problem

When calling external libc functions (via dlsym), the function expects actual memory pointers (e.g., `char*` for `strcpy`). But MIR variables only hold byte offsets into prog.mem. Without conversion, the libc function receives a small integer instead of a real address — leading to SIGSEGV.

## MIR_TO_PTR Instruction

The solution is the `MIR_TO_PTR` instruction, which converts a byte offset to an actual pointer:

```
MIR_TO_PTR dst, a   // dst = wubu_jit_mem_ptr + a
```

In the JIT, this compiles to:
```asm
mov r_dst, rbx      // rbx = wubu_jit_mem_ptr (set at program start)
add r_dst, r_dst, r_a  // add byte offset (no shift — already bytes)
```

**CRITICAL**: MIR_TO_PTR must NOT shift (addresses are already byte offsets since the byte-addressable rewrite).

## When MIR_TO_PTR is Generated

The MIR builder (`holyd_mir_eval.c`) generates MIR_TO_PTR before external calls when:
- Argument is `HD_AST_STRING_LIT` — string literal stored in prog.mem, needs pointer
- Argument type is `HD_TYPE_ARRAY` — array decays to pointer
- Argument type is `HD_TYPE_PTR` — pointer needs actual address
- `mir_var_is_array()` returns true — variable is an array

## DEREF Increment/Decrement (2026-09-16)

**Pattern:** `*p++`, `++*p`, `*p--`, `--*p` (pre/post increment/decrement through a dereferenced pointer).

The POST_INC/POST_DEC/PRE_INC/PRE_DEC handlers originally only handled IDENT and INDEX children. DEREF children (from `*p++`) fell through to `mir_gen_expr(g, n->child)` which evaluates the DEREF but doesn't write back the incremented value.

**Fix:** Add a DEREF case that:
1. Computes the pointer value from `n->child->child` (the pointer expression)
2. Loads the value from the pointer address
3. Adds/subtracts 1 (or the appropriate amount for the type)
4. Stores the result back to the pointer address
5. Returns the old value (post-inc/dec) or new value (pre-inc/dec)

**Float detection:** For `double *d_ptr`, the increment should use DADD/DSUB, not ADD/SUB. Check the pointer's base type using `mir_effective_type()` on `n->child->child` — if it's `HD_TYPE_F64`, use float ops.

```c
case HD_AST_DEREF: {
    wubu_vr_t ptr_val = mir_gen_expr(g, n->child->child);
    wubu_vr_t v = wubu_mir_load(g->prog, ptr_val);
    /* Check if float pointer */
    int is_float = 0;
    HDType *eff = mir_effective_type(g, n->child->child);
    if (eff && eff->kind == HD_TYPE_F64) is_float = 1;
    wubu_vr_t one = wubu_mir_const(g->prog, 1);
    wubu_vr_t upd = wubu_mir_binop(g->prog, is_float ? MIR_DADD : MIR_ADD, v, one);
    wubu_mir_store(g->prog, ptr_val, upd);
    return (n->kind == HD_AST_POST_INC || n->kind == HD_AST_POST_DEC) ? v : upd;
}
```

**Pitfall:** The effective type of `n->child->child` for `double *d_ptr` is `HD_TYPE_PTR` with `base = HD_TYPE_F64`. `mir_effective_type` on a DEREF node strips the pointer and returns the base type. But on the child of DEREF (the pointer itself), it returns the pointer type. Check `eff->base->kind == HD_TYPE_F64` for pointer types.

MIR uses 64-bit cells for ALL types. A `char` load returns the full 64-bit cell value. This means char comparisons (`buf[0] == 'A'`) fail when the cell contains multiple chars or when char values are sign-extended incorrectly.

## is_array Detection Pitfall

`char src[] = "hello"` was NOT detected as an array because `is_array` was based on `arr_size > 0`, but unspecified-size arrays have `arr_size=0`. Fix: check `n->type->kind == HD_TYPE_ARRAY` instead.

## Var Table Persistence Across Functions (2026-09-20)

**CRITICAL**: The var table (`g->vars[]`) persists across function compilations within a single `hd_build_mir` call. When you add a new flag to the var struct, you MUST:

1. **Initialize it to 0** in both `mir_decl_var_unsigned` and `mir_bind_var` — otherwise stale values from previous functions leak.
2. **Clear it for ALL entries with the same name** before setting it for a parameter — multiple functions with the same parameter name (e.g., `a`) share the var table.

**Debugging pattern**: When a fix works in isolation but fails when other functions are present, suspect var table state leakage. Add a debug print of the flag for ALL var table entries at function entry to detect stale values.

## Thread Safety

The JIT uses global state (`wubu_jit_mem_ptr`, code buffer) that is NOT thread-safe. Multi-threaded test runners (gauntlet_v3) crash with double-free when multiple threads compile/run JIT code simultaneously. Use fork+timeout (gauntlet_v2) for production runs.

## DEREF of Array ADD — Return Address, Not Value (2026-09-19)

**Pattern:** `*(arr + i)` where `arr` is a multi-dimensional array. In C, this returns the sub-array `arr[i]`, which decays to a pointer to its first element. In the flat memory model, this is the SAME address as `arr + i` — no load is required.

**Bug:** The DEREF handler unconditionally emits `wubu_mir_load(g->prog, addr)`, which loads the first element `arr[i][0]` instead of returning the sub-array address. This makes `*(*(x + i) + j)` compute `*(x[i][0] + j)` instead of `x[i][j]`.

**Fix in DEREF handler:** Before emitting the load, check if the child is an ADD whose left operand is an array IDENT. If so, return the address directly (no load):

```c
case HD_AST_DEREF: {
    wubu_vr_t addr = mir_gen_expr(g, n->child);
    if (n->child && n->child->kind == HD_AST_ADD && n->child->left) {
        const HDASTNode *base = n->child->left;
        if (base && base->kind == HD_AST_IDENT && base->ident[0]) {
            for (int vi = 0; vi < g->n_vars; vi++) {
                if (strcmp(g->vars[vi].name, base->ident) == 0 && g->vars[vi].is_array) {
                    return addr;  /* *(array + i) → address, not load */
                }
            }
        }
    }
    return wubu_mir_load(g->prog, addr);
}
```

## ADD Pointer Scaling for DEREF-of-Array (2026-09-19)

**Pattern:** `*(arr + i) + j` — pointer arithmetic on the result of `*(arr + i)`. The DEREF returns an address, and the ADD must scale `j` by the element size.

**Bug:** The ADD handler checks `n->left->type` to determine pointer scaling. But DEREF nodes have `type=NULL`, so no scaling is applied. `*(x + 2) + 1` adds 1 byte instead of 8 bytes (or `inner_dim * 8` for multi-dim).

**Fix in ADD handler:** Detect DEREF-of-array-ADD pattern and apply element-size scaling (always 8 bytes per cell — the element size in the flat model):

```c
if (ptr_scale == 0 && n->left && n->left->kind == HD_AST_DEREF) {
    const HDASTNode *child = n->left->child;
    if (child && child->kind == HD_AST_ADD && child->left) {
        const HDASTNode *base = child->left;
        if (base && base->kind == HD_AST_IDENT && base->ident[0]) {
            for (int vi = 0; vi < g->n_vars; vi++) {
                if (strcmp(g->vars[vi].name, base->ident) == 0 && g->vars[vi].is_array) {
                    ptr_scale = 8;  /* element size, NOT array stride */
                    break;
                }
            }
        }
    }
}
```

**CRITICAL distinction:** The DEREF handler uses the array stride (inner dimension × 8) for the `*(arr + i)` computation itself. But the ADD handler for `*(arr + i) + j` must use the ELEMENT size (8), not the stride. These are different scales for the same array.

**Why:** `*(x + 2)` on `int x[5][3]` computes `x_addr + 2 * (3 * 8) = x_addr + 48`. Then `*(x + 2) + 1` should compute `x_addr + 48 + 1 * 8 = x_addr + 56`. Using stride (24) instead of element size (8) would give `x_addr + 48 + 24 = x_addr + 72`, which is `x[2][3]` (out of bounds).

## Multi-Dimensional Array Parameters (2026-09-20)

**Parser type construction** — `int a[N][M]` as a function parameter must become `PTR(ARRAY(scalar, M))`, NOT `PTR(PTR(scalar))`. The C standard adjusts only the outermost dimension to a pointer; inner dimensions are preserved as ARRAY types.

**Parser implementation** — Collect all dimensions into `dims[]`, then build from innermost outward:
```c
HDType *inner = pt;  // scalar type (e.g., I32)
for (int di = ndims - 1; di >= 1; di--) {
    HDType *arr = calloc(1, sizeof(HDType));
    arr->kind = HD_TYPE_ARRAY;
    arr->base = inner;
    arr->array_size = dims[di];
    arr->size = hd_type_size(inner) * dims[di];
    inner = arr;
}
// Outermost dimension becomes pointer
HDType *ptr = calloc(1, sizeof(HDType));
ptr->kind = HD_TYPE_PTR;
ptr->base = inner;
ptr->size = 8;
```

**MIR eval `is_ptr_array` flag** — Set when parameter type is `PTR(ARRAY(...))`. Store `array_stride` from `base->array_size` (number of elements in the inner array). This flag is distinct from `is_array` — `is_array` means the variable IS an array in prog.mem; `is_ptr_array` means the variable is a POINTER to an array passed as a parameter.

**Initialization requirement** — `is_ptr_array` MUST be initialized to 0 in both `mir_decl_var_unsigned` and `mir_bind_var`. The var table persists across function compilations, so stale values leak between functions.

**Clearing requirement** — Before setting `is_ptr_array=1` for a parameter, clear it for ALL var table entries with that name. Multiple functions with the same parameter name (e.g., `a`) share the var table.

**INDEX handler no-load rule** — For `is_ptr_array` bases, `a[i]` returns the ADDRESS of the sub-array (no load), because the sub-array decays to a pointer. The subsequent `a[i][j]` then indexes into this address.

**Stride computation** — `mir_index_stride` checks `is_array || is_ptr_array`. For `PTR(ARRAY(I32, 3))`, the outermost index stride is `3 * 8 = 24` bytes (row size). Inner index stride is `8` (element size).

**Pitfall**: Setting `is_array=1` for pointer-to-array parameters (instead of `is_ptr_array=1`) causes `mir_address_of` to return the variable's prog.mem address instead of loading the pointer value. The parameter's VALUE is the pointer to the caller's array; its ADDRESS is where that pointer is stored locally.

**Pitfall**: `array_stride` must use `base->array_size` (element count), NOT `base->size` (byte size). For `ARRAY(I32, 3)`, `array_size=3` but `size=12`. The stride formula `array_stride * 8` gives `24` (correct) vs `96` (wrong).

## Pointer-to-Pointer Double Indexing (2026-09-20)

**Pattern:** `ptr_ptr[0][0]` where `ptr_ptr` is `int**` (pointer to pointer). The inner INDEX `ptr_ptr[0]` returns a pointer VALUE (loaded from memory). The outer INDEX must use this value as the base address.

**Distinction from pointer-to-array:** For `int (*a)[3]`, `a[0]` returns an ADDRESS (sub-array decays to pointer). For `int **ptr_ptr`, `ptr_ptr[0]` returns a VALUE (the pointer loaded from memory). The INDEX handler must choose between `mir_gen_expr` (value) and `mir_address_of` (address) based on the ultimate base type.

**Decision logic in INDEX handler:**
```c
if (base_node && (base_node->kind == HD_AST_INDEX || base_node->kind == HD_AST_DEREF)) {
    /* Walk to ultimate base IDENT */
    HDASTNode *ultimate = base_node;
    while (ultimate && ultimate->kind == HD_AST_INDEX) ultimate = ultimate->left;
    if (ultimate && ultimate->kind == HD_AST_DEREF) ultimate = ultimate->child;
    int use_value = 0;
    if (ultimate && ultimate->kind == HD_AST_IDENT) {
        for (int vi = 0; vi < g->n_vars; vi++) {
            if (strcmp(g->vars[vi].name, ultimate->ident) == 0 && g->vars[vi].type) {
                HDType *t = g->vars[vi].type;
                /* Pointer-to-pointer: inner INDEX yields a value */
                if (t->kind == HD_TYPE_PTR && t->base && t->base->kind == HD_TYPE_PTR)
                    use_value = 1;
                /* DEREF of pointer: yields a value */
                if (base_node->kind == HD_AST_DEREF && t->kind == HD_TYPE_PTR)
                    use_value = 1;
                break;
            }
        }
    }
    base = use_value ? mir_gen_expr(g, base_node) : mir_address_of(g, base_node);
} else {
    base = mir_address_of(g, base_node);
}
```

**Pitfall**: Using `mir_gen_expr` for ALL INDEX/DEREF bases (without type checking) breaks pointer-to-array parameters. For `int (*a)[3]`, `a[0]` must return the ADDRESS (sub-array decays), not the loaded value. Blindly using `mir_gen_expr` loads the first element of the sub-array instead of returning its address.

**Pitfall**: The type check must walk to the ULTIMATE base IDENT, not just check the immediate INDEX base. For `ptr_ptr[0][0]`, the outer INDEX's base is `ptr_ptr[0]` (an INDEX node), not `ptr_ptr` (the IDENT). Walking the left spine of nested INDEXes finds the ultimate IDENT.

**Test cases:**
- `int **ptr_ptr; ptr_ptr[0][0]` — pointer-to-pointer (needs `mir_gen_expr`)
- `int (*a)[3]; a[0][1]` — pointer-to-array (needs `mir_address_of`)
- `int arr[5][3]; arr[2][1]` — array (needs `mir_address_of` for base IDENT)

## Local `int (*p)[N]` Declaration — Parser Mis-parse (the ptr-to-array PARAM case is above; this is the LOCAL VAR case)

The sections above cover pointer-to-array **function parameters**. A **local** `int (*p)[3] = &a;` has a DIFFERENT bug: the parser's `(*name)` declarator path only special-cases function pointers (`(*p)(...)`). For `(*p)[N]` it falls through to `is_ptr=1` (plain pointer), then the generic `[N]` array-declarator loop wraps it as `ARRAY(PTR(int), N)` — an **array of pointers**, which is wrong. The variable's type comes out `HD_TYPE_ARRAY`, so `is_ptr_array` is never set and `p[i][j]` decays incorrectly.

**Symptom:** `int a[3]={10,20,30}; int (*p)[3]=&a; (*p)[1]` and `p[0][1]` both return 0 (garbage), while `int *q=*p; q[1]` may work (re-derives the address). `is_ptr_array` stays 0 because the type is `HD_TYPE_ARRAY`, not `HD_TYPE_PTR`.

**Fix in the parser `(*name)` path:** after consuming `(*p)`, if the next token is `[` (LBRACKET, not LPAREN), build `PTR(ARRAY(base, N))` directly and set a flag (e.g. `is_ptr_to_array`) that guards BOTH the generic array-declarator `while` loop and the plain-pointer `is_ptr` wrap so they don't re-wrap. Then the existing `is_ptr_array` marking in the VAR_DECL path (set when `type->kind==HD_TYPE_PTR && type->base->kind==HD_TYPE_ARRAY`) fires.

**DEREF of a local ptr-to-array:** `*p` must return the sub-array ADDRESS (decay), not load the first element. Add a DEREF case: if the child is an IDENT with `is_ptr_array` set, `return addr` (no load). Without it, `int *q = *p; q[i]` loads `mem[addr]` (the first element) instead of the array base.

**Distinction:** `HD_TYPE_ARRAY` kind = 12, `HD_TYPE_PTR` = 11 (VOID=0, I8..F64=9, BOOL=10, PTR=11, ARRAY=12). When a ptr-to-array local shows `kind=12` at codegen, the parser built the wrong type — check the `(*name)` declarator path.

## mir_binop_result_type — Untyped Float Operand Truncation Bug Class

**Pattern:** `1.0/a < 0` (a float expression compared directly to an int) returns the WRONG result, but the same computation stored to a variable first (`double r = 1.0/a; r < 0`) is correct.

**Root cause:** `mir_binop_result_type` decides whether a comparison/binop needs 32-bit truncation by inspecting each operand's AST `type`. A DIV/NEG-of-float-literal node (e.g. `1.0/a`, `-0.0`) has `type == NULL`, so the function doesn't see it as `HD_TYPE_F64`, falls through, and returns `I32` (from the int operand). The comparison handler then truncates the float operand to 32 bits — corrupting the double bit pattern (e.g. `-inf` = `0xFFF0000000000000` truncated to `0`), so `1.0/-0.0 < 0` is wrongly false. Storing to a variable works because the VARIABLE's type IS `f64` (found via the var table).

**Fix:** in `mir_binop_result_type`, after the var-table lookup, detect untyped float operands via `mir_is_float_node` and treat them as f64 so the result is 64-bit (no truncation):
```c
static HDType f64t;
if (f64t.kind == 0) { f64t.kind = HD_TYPE_F64; f64t.size = 8; }
if (!lt && mir_is_float_node(g, left))  lt = &f64t;
if (!rt && mir_is_float_node(g, right)) rt = &f64t;
```

**Generalizable rule:** any codegen decision keyed on `node->type` (truncation, op selection, signedness) must ALSO consult `mir_is_float_node`/`mir_is_unsigned_node` for operands whose AST type is unset — expression nodes (DIV, NEG, ADD of floats) routinely carry `type == NULL`. The var-table path only covers bare IDENTs. Symptom signature: an expression works when bound to a variable but fails when used inline in a comparison/return.

## Recursive Function Limitation (2026-09-09, confirmed 2026-09-19)

Static locals and function parameters are stored at FIXED memory offsets in `prog.mem`. When a function calls itself recursively, the recursive call overwrites the same memory locations, clobbering the outer call's variables. This affects BOTH the interpreter (memory not restored on return) and the JIT (flat VR model shares parameter memory).

**Example:** `double fun(double x) { if (x > 2) return x; double ret = fun(x + 2); return ret + x; }` — `fun(1.0)` returns 6 instead of 4 because the recursive call overwrites `x` in memory.

**Interpreter mechanism:** `op_ret` restores the VR file but NOT memory. Comment in code: "Recursion is not supported (locals would overlap)."

**JIT mechanism:** Parameters are stored to memory at function entry (`wubu_mir_store(prog, addr, v1)`). The recursive call stores its own parameter to the SAME address, overwriting the outer call's parameter.

**Fix requires:** Implementing a stack frame with rsp-based local variable addressing (significant architectural change). This is the highest-leverage remaining architectural blocker — needed for ch13 (recursive calls) and would enable proper local variable isolation.
