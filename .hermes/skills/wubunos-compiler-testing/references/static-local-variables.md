# Static Local Variables in HolyD

## The Pattern: Guard-Based Init-Once

Static locals (`static int x = 5;` inside a function) must persist across function calls
and initialize only once. HolyD implements this with a guard variable:

```c
// Source:
int foo(void) {
    static int x = 5;
    x = x + 1;
    return x;
}

// Generated MIR (conceptual):
// At program start: x is allocated in global mem, guard is allocated in global mem
// Inside foo:
//   if (guard == 0) { x = 5; guard = 1; }
//   x = x + 1;
//   return x;
```

## Implementation

### Parser (`holyd_parse.c`)
When `static` is seen in `hd_parse_decl`, the returned `HD_AST_VAR_DECL` node is
marked with `is_static = 1`:

```c
if (match(p, HD_KW_STATIC)) {
    HDASTNode *decl = hd_parse_decl(p);
    if (decl && decl->kind == HD_AST_VAR_DECL)
        decl->is_static = 1;
    return decl;
}
```

### AST (`holyd_ast.h`)
New field on `HDASTNode`:
```c
int is_static;  /* 1 if this var_decl has static storage class */
```

### MIR Generator (`holyd_mir_eval.c`)
In the `HD_AST_VAR_DECL` handler, when `n->is_static && g->in_function_body`:

1. Allocate a guard variable in global memory (`wubu_mir_alloc(g->prog, 1)`)
2. Mark the var entry with `is_static = 1` and `guard_addr`
3. Evaluate the init expression
4. Emit: `if (guard == 0) { store(addr, init_val); store(guard, 1); }`
   - Uses `MIR_EQ` comparison, `MIR_JZ` conditional jump, `MIR_LABEL` for skip target

The guard check is emitted at the declaration point INSIDE the function body,
NOT at program start. This is because the init expression may reference other
locals or constants that are only valid inside the function scope.

### Var Table (`mir_var_t`)
New fields:
```c
int is_static;         /* 1 if this is a static local (global memory) */
wubu_vr_t guard_addr;  /* guard variable address for static init-once */
```

## Critical Pitfalls

1. **Guard check must be inside function body**: The init expression may reference
   other globals or constants. Emitting at program start would require evaluating
   the init expression after all function bodies are generated, which is complex
   and error-prone. The guard pattern avoids this entirely.

2. **Only for function-body statics**: Global `static` vars (outside functions) are
   handled normally — they don't need guards because their init is emitted at
   program start. The `g->in_function_body` check ensures guards are only emitted
   for locals.

3. **Scalar types only**: Static arrays with brace initializers (`static int a[] = {1,2,3};`)
   fall through to normal init (re-initialized each call). This is a known limitation.
   Fixing it would require deferring array init to program start.

4. **Memory allocation**: Both the static var and its guard are allocated in global
   memory via `wubu_mir_alloc`. They persist for the program's lifetime.

## Verified Working

```c
int foo(void) { static int a = 3; a = a * 2; return a; }
int bar(void) { static int a = 4; a = a + 1; return a; }
int main(void) { return foo() + bar() + foo() + bar(); }
// foo: 6, 12; bar: 5, 6; total = 29 ✓

int foo(void) { static int x; x = x + 1; return x; }
int main(void) { int r; for(int i=0;i<4;i++) r=foo(); return r; }
// Returns 4 (uninitialized static starts at 0) ✓
```

## Remaining Issues

- **Extern shadowing**: `extern int i;` inside a function that shadows a static local
  (`static int i;`) still fails. The `extern` declaration brings the global `i` into
  scope, but the var table lookup may resolve to the wrong one.
- **Static arrays**: `static int a[] = {1,2,3};` re-initializes each call (guard pattern
  only handles scalar init expressions).
- **Static redeclaration with initializers** (2026-09-12): The static redeclaration check
  (`if (n->is_static && !n->init)`) skips matching when an initializer is present.
  This means `int static i = 5;` after `static int i;` creates a NEW variable instead
  of reusing the existing one. The fix requires evaluating the initializer and storing
  to the existing variable's address — complex because the init expression is evaluated
  AFTER the var table entry is created. Only 1 test affected (`signed_type_specifiers`).
- **`int extern` keyword ordering** (2026-09-12): `int extern i;` inside a function
  creates a new local variable instead of referring to the file-scope global when
  there are multiple file-scope declarations of the same name.
- **Static local inside switch case** (2026-09-16): A `static int x = 10;` declared
  inside a `switch` case is never initialized when the case is skipped by the switch.
  The guard check is emitted at the declaration point, which is inside the skipped case.
  Attempted hoisting the static init to function top — BROKE 9 tests because allocating
  extra VRs for hoisted statics changes VR numbering, which destabilizes the linear scan
  register allocator (different register assignments → different spill behavior).
  **Do NOT hoist static inits without also fixing the register allocator to be
  VR-numbering-independent.**
