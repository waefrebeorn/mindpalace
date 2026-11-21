# Statement Expressions & _Atomic Implementation (2026-09-06)

## Statement Expression `({ ... })` - GCC Extension

### Parser Implementation

Location: `holyd_parse.c:parse_primary()`

When `parse_primary()` sees `(` followed by `{`:

```c
case HD_TOK_LPAREN: {
    advance(p); /* ( */
    if (peek(p) == HD_TOK_LBRACE) {
        /* GCC statement expression: ({ stmt1; stmt2; ...; expr; }) */
        HDASTNode *block = parse_block(p);
        expect(p, HD_TOK_RPAREN);
        HDASTNode *n = hd_ast_new(HD_AST_STMT_EXPR);
        n->child = block;
        return n;
    }
    HDASTNode *expr = parse_expr(p);
    expect(p, HD_TOK_RPAREN);
    return expr;
}
```

**Key insight:** The `({...})` is a compound statement in parentheses. The last expression in the block becomes the value.

### AST Node

Location: `holyd_types.h`

```c
HD_AST_STMT_EXPR,  /* GCC statement expression: ({ ... }) */
```

### Code Generation

Location: `holyd_mir_eval.c`

```c
case HD_AST_STMT_EXPR: {
    /* Execute the block, return the value of the last expression. */
    return mir_gen_stmt(g, n->child);
}
```

The block handler returns the last statement's value, which is exactly what we need.

### Test Case

```c
int main() {
    int x = ({ int y = 5; y + 3; });
    return x;  // returns 8
}
```

### Common Use Cases

1. **Compound literals with initializers:**
   ```c
   x = (struct S){b:0, a:0, c:({ struct S o = x; o.a == 1 ? 10 : 20;})};
   ```

2. **Safe macros:**
   ```c
   #define maxint(a,b) ({int _a = (a), _b = (b); _a > _b ? _a : _b; })
   ```

## _Atomic Type Qualifier (C11)

### Parser Implementation

Location: `holyd_parse.c`

1. Add keyword `HD_KW_ATOMIC` in `holyd_types.h` enum
2. Add `"_Atomic", HD_KW_ATOMIC` in `holyd_lexer.c` keyword table
3. Handle in `parse_type()`:

```c
case HD_KW_ATOMIC: {
    advance(p); /* consume _Atomic */
    if (peek(p) == HD_TOK_LPAREN) {
        advance(p); /* consume ( */
        HDType *inner = parse_type(p);  /* parse (type) */
        expect(p, HD_TOK_RPAREN);
        return inner;  /* _Atomic(T) -> T (strip qualifier) */
    }
    return parse_type(p);  /* _Atomic T -> parse T */
}
```

### Preprocessor Handling

Location: `wubu_preproc.c` - `hd_parse_decl()`

Strip `_Atomic` qualifier at declaration level:

```c
if (match(p, HD_KW_ATOMIC)) {
    /* Skip _Atomic, continue with regular declaration parsing */
    return hd_parse_decl(p);
}
```

Also update `parse_stmt()` type check range:

```c
if ((_t >= HD_KW_I0 && _t <= HD_KW_VOLATILE) || _t == HD_KW_ATOMIC)
```

### Design Decision: Strip vs Implement

**Strip (what we implemented):** Recognize `_Atomic` as a type qualifier, parse the inner type, and return it unchanged. The atomic semantics (memory ordering, lock-free guarantees) are NOT implemented.

**Alternative: Full implementation** would require:
- Atomic operations (load/store with memory ordering)
- Lock-free algorithms for multi-threaded code
- ABI integration for atomic types

**Why stripping is correct for a single-threaded JIT:**
1. Tests that use `_Atomic` are testing the PARSER and CODE GENERATION
2. The atomic operations are a runtime concern, not a compilation concern
3. Stripping at the TYPE LEVEL (not source text level) means the AST has correct types
4. This matches how Clang/GCC lower `_Atomic(T)` to `T` in non-atomic contexts

## Related Patterns

### Forward Declaration Pattern

When adding new AST nodes used by `parse_primary()`:

```c
static HDASTNode *parse_block(HDParser *p);  /* forward declaration */
```

Needed when the parser function is called before its definition.

### Keyword in Type Range Check

When adding new type keywords like `HD_KW_ATOMIC`, update all places that check:

```c
int is_type_kw = (t >= HD_KW_I0 && t <= HD_KW_VOLATILE);  /* WRONG */
int is_type_kw = (t >= HD_KW_I0 && t <= HD_KW_VOLATILE) || t == HD_KW_ATOMIC;  /* CORRECT */
```

This appears in:
- `parse_cast()` for cast detection
- `parse_stmt()` for declaration recognition
- `sizeof` type parsing

## `__atomic_*` Builtin Operations (GCC/C11 style)

Distinct from the `_Atomic` TYPE qualifier above: these are the atomic OPERATION
builtins, dispatched in the CALL path of `mir_gen_expr` (alongside the other
`fname`-matched builtins like `ffs`, `abs`, `strlen`). They take a POINTER as
arg 0. `mir_gen_expr` on `&x` (`HD_AST_ADDR`) returns the address VR, so
`mir_gen_expr(g, n->args[0])` yields the pointer directly -- no MIR_TO_PTR needed
(the var table address IS the mem-cell base the LOAD/STORE expect).

Implement (each returns the right value; verify with `--dump-asm`):
- `__atomic_load_n(ptr, order)` -> `wubu_mir_load(prog, ptr)`
- `__atomic_store_n(ptr, val, order)` -> store val through ptr, return val
- `__atomic_fetch_add(ptr, val, order)` -> `old=load; store(old+val); return old`
- `__atomic_fetch_sub(ptr, val, order)` -> same with MIR_SUB
- `__atomic_exchange_n(ptr, val, order)` -> `old=load; store(val); return old`
- `__atomic_thread_fence(order)` / `__atomic_signal_fence` -> no-op, `mir_const(0)`
  (single-threaded codegen: ordering is trivially preserved, no barrier needed)

**Pitfall -- fetch_* return the OLD value, not the new one.** `fetch_add` is
read-modify-write returning the previous contents; tests assert on the old value
(`old + x` == new+old). Returning the new value is the classic off-by-one here.

**Pitfall -- do not build a real barrier/fence.** In the single-threaded JIT a
fence has nothing to order; emitting a `mir_const(0)` return (not an instruction)
keeps fences correct without pessimizing codegen. Do NOT strip fences out of
source text -- that is the "cheat fix" the user rejects; handling them as a
builtin no-op IS the proper implementation.