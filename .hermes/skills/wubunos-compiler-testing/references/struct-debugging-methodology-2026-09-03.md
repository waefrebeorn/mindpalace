# Struct Debugging Methodology (2026-09-03 → 2026-09-03 v2 → v3)

## Core insight: MIR memory model = 8-byte cells
- Every struct member occupies >= 1 cell; member offsets are cell indices, not byte offsets.
- Parser must compute `t->size += (hd_type_size(member_type) + 7) / 8` per member.
- `hd_type_size(struct)` returns bytes (`t->size * 8`); MIR code must divide by 8 for cell counts.

## Three-layer fix pattern
1. **Parser** (`holyd_parse.c`): struct member size/offset in cells, not bytes.
2. **MIR eval** (`holyd_mir_eval.c`): `total_size = t->size` (cells); initializer/assign copy full struct, not scalar store.
3. **Scope** (`hd_build_mir`): top-level globals need `no_scope_pop=1` or `n_vars` restoration after phase 2.

## New finding (2026-09-03): global struct IDENT nodes have NULL `type`
When `a = bar(3)` assigns to a global struct variable `a`, the AST IDENT node
`n->left` has `n->left->type == NULL`. The parser does not propagate type info
to IDENT nodes for globals in the `HD_AST_ASSIGN` handler.

**Fix:** check `n->left->type` first; if NULL, consult the var table:
```c
int left_is_struct = 0;
if (n->left && n->left->type && n->left->type->kind == HD_TYPE_STRUCT)
    left_is_struct = 1;
else if (n->left && n->left->kind == HD_AST_IDENT && n->left->ident[0])
    left_is_struct = mir_var_is_struct(g, n->left->ident);
```

## New finding: `mir_find_struct` fallback for var-table struct size
When looking up struct size from a global IDENT, `mir_find_struct(name)` may
return NULL if the struct was parsed before the var table was populated. Fallback
to the var table's `array_size` field, which stores the struct's total cell size:
```c
for (int i = 0; i < g->n_vars; i++)
    if (strcmp(g->vars[i].name, ident) == 0 && g->vars[i].is_struct) {
        struct_size = g->vars[i].array_size;
        break;
    }
```
The `s->total_size` field is NOT reliable here; it may be -1 for structs parsed
early or in a different phase.

## Failing test signature
```
struct A { int a; char b[32]; } a, b;
a = bar(3);   // global struct = struct-return
if (a.b[0] != 3) return 1;
```
Fails when: a) globals popped from scope, b) member offset wrong, c) struct copy too short,
d) IDENT `type` is NULL and var table fallback is missing.

## Debug technique: stderr from gauntlet_runner
`gauntlet_runner` suppresses stdout but stderr is visible when run foreground.
Use `fprintf(stderr, "[DEBUG] ...\n"); fflush(stderr);` for runtime MIR debug.
Confirm with:
```sh
./gauntlet_runner x86_64 "..." 2>&1 | grep DEBUG
```

## Verification
```sh
./gauntlet_runner --dump-asm x86_64 "struct B{int x;int y;};struct A{int z;struct B b;};struct A f(){struct B b={0,1};struct A a={2,b};return a;}int main(void){struct A a=f();if(a.z!=2||a.b.x!=0||a.b.y!=1)return 1;return 0;}"
```

## Key files
- `holyd_parse.c:293` — struct member size computation
- `holyd_parse_ast.c:133` — `hd_type_size` for structs
- `holyd_mir_eval.c:932` — struct-to-struct assignment copy loop
- `holyd_mir_eval.c:1617` — global var scope persistence
- `holyd_mir_eval.c:143` — `mir_var_is_struct` helper (added 2026-09-03)

---

## Pointer-to-struct patterns (2026-09-04)

Four patterns that break when the struct type can't be resolved from the left
side of a DOT/MEMBER. All route through `mir_dot_struct_type(g, n->left)`.

### Pattern 1: pointer-to-struct DOT (`p->a`)
`n->left` is IDENT with `is_ptr_struct=1` (not `is_struct`). The IDENT lookup in
`mir_dot_struct_type` must check BOTH flags:
```c
if (strcmp(g->vars[i].name, left->ident) == 0 && (g->vars[i].is_struct || g->vars[i].is_ptr_struct))
    return g->vars[i].struct_name;
```
Without `is_ptr_struct`, `p->a` returns NULL struct_type → member offset = 0 → reads wrong cell.

### Pattern 2: pointer arithmetic DOT (`(p+1)->a`)
`n->left` is `HD_AST_ADD` (or SUB). Recurse into `left->left` to find the root pointer:
```c
if (left->kind == HD_AST_ADD || left->kind == HD_AST_SUB)
    return mir_dot_struct_type(g, left->left);
```
The root is typically an IDENT with `is_ptr_struct=1` or an INDEX node.

### Pattern 3: DEREF DOT (`(*p).member`)
`n->left` is `HD_AST_DEREF`. Two resolution paths:
1. Type annotation: `left->child->type->base->name` if type->kind==PTR and base->kind==STRUCT
2. Var table fallback: look up `left->child->ident` with `is_ptr_struct` flag

In `mir_gen_expr` DOT handler, add a DEREF case:
```c
} else if (n->left->kind == HD_AST_DEREF) {
    base = mir_gen_expr(g, n->left->child);
    struct_type = mir_dot_struct_type(g, n->left->child);
}
```

### Pattern 4: ADDR DOT (`.member` on `&s`)
`n->left` is `HD_AST_ADDR`. The `(&s)->member` form needs:
```c
} else if (n->left->kind == HD_AST_ADDR) {
    base = mir_address_of(g, n->left);
    struct_type = mir_dot_struct_type(g, n->left);
}
```
`mir_dot_struct_type` on an ADDR node hits the IDENT case (ADDR's child is the struct IDENT).

### Var table: `is_ptr_struct` flag
When storing a pointer-to-struct variable (`struct S* p = &s`), set both
`is_ptr_struct=1` and `struct_name` in the var table. Without `is_ptr_struct`,
patterns 1-3 all fail to resolve the struct type.

### Test pattern for all four
```c
{"ptr deref member", "struct S{int a;}; struct S s; s.a=42; struct S* p=&s; (*p).a;", 42},
{"ptr idx member",   "struct S{int a;}; struct S s; s.a=42; struct S* p=&s; p[0].a;", 42},
{"ptr arith arrow",  "struct S{int a;}; struct S arr[2]; arr[0].a=10; arr[1].a=20; struct S* p=arr; (p+1)->a;", 20},
```

---

## Struct return mechanism (2026-09-03 v3)

The struct return ABI was completely broken before this fix. Three bugs compounded:

### Bug A: `mir_address_of` for struct IDENT returned VALUE, not address
`holyd_mir_eval.c:444` — for non-array IDENT, was doing `wubu_mir_load(addr)` which loads the
first cell's VALUE. For struct vars, we need the ADDRESS itself, not the value.
**Fix:** check `mir_var_is_struct(g, ident)` and return `addr` directly. Pattern:
```c
wubu_vr_t addr = mir_find_var_addr(g, n->ident);
if (addr == 0) return 0;
if (mir_var_is_struct(g, n->ident))
    return addr;        /* structs: addr IS the address */
if (mir_var_is_array(g, n->ident))
    return addr;
return wubu_mir_load(g->prog, addr);  /* scalars: load value at addr */
```

### Bug B: Struct copy loop used `jz` instead of `jnz` (CRITICAL)
`holyd_mir_eval.c:1142` — the copy loop condition was `i >= struct_size` with `jz`:
```c
wubu_mir_jz(g->prog, MIR_GE(i, size), end_label);   // WRONG: exits immediately
```
`jz` jumps when the condition is ZERO. `i >= size` is ZERO when `i < size` — i.e. when we
WANT to continue. So the loop exited on first iteration, copying nothing.

**Fix:** use `jnz` (jump when condition is NON-ZERO):
```c
wubu_mir_jnz(g->prog, MIR_GE(i, size), end_label);  // exits when i >= size is TRUE
```
This is a subtle interpreter semantic: `jz(cond, lbl)` ≠ `if (!cond) goto lbl` of C.

### Bug C: Struct return used invalid local stack address
`holyd_mir_eval.c` HD_AST_RETURN — was putting the callee's local struct ADDRESS in v0.
After return, that address is invalid. Caller dereferenced garbage.

**Fix:** callee allocates a persistent buffer via `wubu_mir_alloc(g->prog, ret_struct_size)`,
copies struct data into it, puts the buffer address in v0, and emits a DIRECT `ret`
(bypassing the epilogue's `mov_to(0, fn_ret_vr)` which would overwrite v0).
Caller reads v0 (buf address), copies from buf to its destination struct.

```c
/* In callee's RETURN handler for struct types: */
wubu_vr_t buf_addr = wubu_mir_alloc(g->prog, ret_struct_size);
/* copy loop: src -> buf_addr */
wubu_mir_mov_to(g->prog, g->fn_ret_vr, buf_addr);  /* set fn_ret_vr so epilogue copies it */
wubu_mir_mov_to(g->prog, 0, buf_addr);              /* v0 = buf address */
wubu_mir_ret(g->prog, 0);                            /* DIRECT ret, bypass epilogue */
return buf_addr;
```

### Unit test for struct returns (added to tools/test_mir_battery.c)
```c
{"struct return", "struct A{int x;}; struct A f(int v){struct A r; r.x=v; return r;} struct A t; t=f(7); t.x;", 7},
```
This test catches ALL three bugs above. Run `./test_mir_battery` after any struct-return change.

## How to debug struct return failures end-to-end

1. Add unit test to `tools/test_mir_battery.c` — interpreter catches codegen bugs.
2. Run with `WUBU_DEBUG_MIR_BEFORE=1` to dump MIR before optimization.
3. Trace `mem[buf_addr]` through RET to confirm copy happened.
4. Check `mir_address_of` for the return expression (IDENT vs DOT vs CALL).
5. Verify copy loop exit condition uses `jnz` not `jz`.

## Pitfall: HDType.size is BYTES, not cells
Every site that converts `n->type->size` to a MIR cell count needs `(size + 7) / 8`.
Multiple existing sites were treating bytes as cells: `total_size`, `arr_size`,
the `struct_size` in copy loops. Search for `n->type->size` and audit each one.

## Pitfall: `fn_ret_vr` epilogue overwrites v0
The function epilogue (placed after the body) does `mov_to(0, fn_ret_vr)`. If a
struct RETURN handler emits its own `ret(0)`, it bypasses the epilogue — fine.
But if it uses `jmp fn_ret_label`, the epilogue overwrites v0 with `fn_ret_vr` (default 0).
**Fix:** either set `fn_ret_vr = buf_addr` before `jmp`, or emit direct `ret` and skip epilogue.