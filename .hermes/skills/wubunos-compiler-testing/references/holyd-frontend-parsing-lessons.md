# HolyD Frontend Parsing Lessons (2026-08-30)

## Extern variable declarations — FIXED

**Problem**: `extern int x;` failed to parse. The parser only handled `extern "C"` function declarations.

**Root cause**: After matching `HD_KW_EXTERN`, the parser immediately tried to match `HD_TOK_STRING`. For `extern int x;`, the next token is `int`, not a string.

**Fix** (`holyd_parse.c`): Check if next token is `HD_TOK_STRING` before entering the `extern "C"` path. If not, fall through to `hd_parse_decl(p)` which handles it as a normal variable declaration.

```c
if (match(p, HD_KW_EXTERN)) {
    if (peek(p) == HD_TOK_STRING) {
        // extern "C" function declaration path
        ...
    }
    // extern variable declaration: extern type name;
    return hd_parse_decl(p);
}
```

**Test**: `{extern int x; x;}` now parses and returns 0.

## Function pointer parameter types — FIXED (2026-08-30)

**Problem**: `int p(int(*fn)(int)){...}` failed to parse. After `parse_type` returns `int`, the next token is `(` which the parser doesn't handle as part of the type.

**Failed approach**: Backtracking with `p->lex->pos = saved_pos; hd_lex_next(p->lex)` broke existing function declaration parsing.

**Successful fix** (`holyd_parse.c`): Source-level scan for `(*` pattern after `parse_type`. Since `parse_type` advances the lexer past the current token, `src[pos]` holds the character after the type (not `src[pos+1]`). Check `peek(p) == HD_TOK_LPAREN && src[pos] == '*'` to detect function pointers without backtracking:

```c
if (peek(p) == HD_TOK_LPAREN && p->lex->pos < (int)strlen(p->lex->src) && p->lex->src[p->lex->pos] == '*') {
    advance(p); // (
    advance(p); // *
    if (peek(p) == HD_TOK_IDENT) { strncpy(pname, p->lex->tok.text, HD_MAX_IDENT_LEN-1); advance(p); }
    expect(p, HD_TOK_RPAREN);
    if (peek(p) == HD_TOK_LPAREN) { /* skip (params) */ ... }
    // Build PTR(FUNC(...)) type
}
```

**Critical insight**: `parse_type` calls `advance(p)` which reads the NEXT token. After it returns, `pos` points past the current token (the `(`). So `src[pos]` is the character AFTER `(`, which should be `*`.

**Test**: `{int f(int x){return x+1;} int p(int(*fn)(int)){return fn(5);} p(&f);}` now parses and returns 6.

## const/volatile qualifiers — FIXED (2026-08-30)

**Problem**: `const int x=5;` and `volatile int x=5;` failed to parse.

**Fix** (`holyd_parse.c`): In `hd_parse_decl`, strip const/volatile qualifiers (like static/extern) since the JIT doesn't enforce type checking:

```c
if (match(p, HD_KW_CONST) || match(p, HD_KW_VOLATILE)) {
    return hd_parse_decl(p);
}
```

**Test**: `{const int x=5; x;}` and `{volatile int x=5; x;}` both parse and return 5.

## BF16 GEMM approaches tested

| Approach | GFLOPS (1024×1024) | Correct? | Notes |
|----------|---------------------|----------|-------|
| Conversion + FP32 GEMM | 33.6 | Yes | 1.9% conversion overhead. Best practical approach. |
| VDPBF16PS interleaved zeros | 15.7 | Yes | Wastes half vector bandwidth (zeros in odd lanes) |
| VDPBF16PS conversion approach (existing) | 35.0 | Yes | Scalar conversion, then FP32 GEMM |

**Key insight**: VDPBF16PS is a **dot product** instruction (`dst[i] += a[2i]*b[2i] + a[2i+1]*b[2i+1]`), not a broadcast-multiply. For GEMM's element-wise `C[j] += A[i][k] * B[k][j]`, you must either:
- Interleave with zeros (wastes half bandwidth)
- Process 2 rows simultaneously (complex data layout)
- Use the conversion approach (simplest, nearly as fast)

**Recommendation**: Stick with conversion approach. BF16's real benefit is 2× memory bandwidth reduction, not compute throughput.

## Full gauntlet performance

The full 19,088-test gauntlet with x86-64 JIT takes >1800 seconds (30+ minutes). The x86-64 JIT is the slowest backend because it actually compiles and executes machine code. Use `--core` for fast iteration (2 minutes) and run the full gauntlet overnight.

## Designated array-init `[index]=val` — BYTE-offset scaling (holyd_mir_eval.c)

`int a[3]={[0]=5,[1]=6,[2]=7]}` returned garbage (`a[0]+a[1]+a[2]`=460293). The array-index designator path set `offset = (int)elem->int_val` (the raw index), but the store does `elem_addr = addr + offset` where `offset` is a **BYTE** offset (each MIR cell is 8 bytes). So `[1]` and `[2]` wrote at byte 1 and 2 instead of 8 and 16 — mid-cell, corrupting neighbours.

Fix: `offset = (int)elem->int_val * elem_sz;` (elem_sz is 8 for scalar arrays; the sequential path already does `e * elem_sz`). The `@`-prefixed ident marks the array-index designator (parser sets `desig->int_val = idx` in holyd_parse.c). Verify with sparse (`{[2]=7,[4]=9}`) and mixed (`{1,[2]=3}`) designated init.

## `_Static_assert` was a silent no-op — and parser error recovery ate the fix

`_Static_assert(0,"msg")` compiled fine instead of erroring. Two separate problems:

1. **No handler**: `_Static_assert` was never parsed as a statement — it fell through as an ignored identifier. Add a case at the top of `parse_stmt`: match IDENT `_Static_assert`, consume `(const, "msg")`, and on a false constant call a NEW `parse_fatal()`.
2. **Error-swallowing**: even after `parse_error`, the failure didn't stop compilation. TWO recovery paths discard `has_error`: (a) the block parser clears it when the next token is `}` (assumes a missing trailing semicolon); (b) the expr-then-block fallback in `holyd_codegen_api.c` / `holyd_mir_eval.c` unconditionally does `parse.has_error=false; n_errors=0` before re-parsing as a block. A `_Static_assert(0); }` hits (a) because `}` follows.

Fix: add a `bool fatal_error` to the `HDParser` struct; `parse_fatal()` sets it; guard BOTH recovery sites with `&& !p->fatal_error` so a hard error is never cleared.

**Pitfall — don't read the literal's value off the parsed expr node**: `parse_expr` on a bare `0` returns a wrapper node whose `kind` is NOT `HD_AST_INT_LIT` and whose `int_val` is uninitialised (so `_Static_assert(1)` and `_Static_assert(5)` also looked false). For a constant-expression operand, read the literal token directly BEFORE calling `parse_expr`: `if (peek(p)==HD_TOK_INT){ cval=p->lex->tok.int_val; have_const=1; }`, then `parse_expr`, then fail iff `have_const && cval==0`.

## Cross-function func-ptr parameter propagation (the `f(args)` where f is a param)

A func-ptr passed as an argument resolved to garbage (returned 0) even though
indirect calls through a local func-ptr *variable* worked (`int(*fp)(int)=f;
fp(5)`=6). Root cause: the compiler tracked `fn_ptr_func_id` only on local
func-ptr variables set by an assignment (`fp = f`). A parameter's func_id is
established at the CALL SITE in the caller (`call(add,3,4)`), which is a
different compilation scope from the callee body (`call`'s `f(x,y)`), so the
callee saw no func_id and the bare-IDENT-callee dispatch had nothing to
resolve.

Fix = a cross-function pre-pass + seeding:
1. **Pre-pass** (`mir_collect_param_fnptr`) walks every `HD_AST_FUNC_CALL`;
   for `callee(fn, ...)` where `fn` is a bare IDENT naming a known function AND
   `callee`'s param at that position is a func-ptr type (PTR whose base is
   FUNC), record `param_fnptr[callee_id][arg_index] = func_id(fn)`. Run it in
   `hd_build_mir` right after `mir_collect_funcs` so the func table exists.
2. **Call dispatch**: the existing bare-IDENT-callee path (`n->callee->kind ==
   HD_AST_IDENT`) resolves `fid` from the var's `fn_ptr_func_id` — this already
   existed for locals; it now also fires for seeded params.
3. **Param seeding**: when a function body binds its params, set each param
   var's `fn_ptr_func_id` from `param_fnptr[fi][pi]`, and CLEAR it to -1 when
   absent — a stale func_id from another function's same-named var otherwise
   leaks in (the var table persists across function bodies).

A func-ptr type is PTR→FUNC; detect it with a helper (`t->kind==HD_TYPE_PTR &&
t->base && t->base->kind==HD_TYPE_FUNC`). Verified: `call(add,3,4)`=7,
`apply(dbl,21)`=42, a param called twice (`f(f(v))`) works. This is the same
mechanism that lets C11 `thrd_create(&t, fn, arg)` / `thrd_join` work as
cooperative builtins: `thrd_create` resolves `fn` to a func_id, maps the
handle var→thread id, stores the arg in a memory cell; `thrd_join` resolves the
handle's tid at COMPILE time (handle var→tid) and emits a direct `MIR_CALL`
(vr0 = callee return; capture with `mov_to(fresh_vr, 0)`). Transitive
func-ptr passing (`b(inc)`→`a(f)`→`f()`) still needs a fixpoint over the map —
not landed.

## Stale-binary trap — `make <obj>` is not enough (reinforced)

After editing a frontend `.c`, `make <obj>.o` compiles the object but the `gauntlet_runner` binary still runs OLD code until you rebuild the BINARY: `make gauntlet_runner` (or `rm -f gauntlet_runner && make gauntlet_runner`). A fix that appears to "not work" after `make holyd_parse.o` is almost always a stale binary — rebuild the runner and re-test before debugging the source. This is the same trap as the gauntlet_v3-deletes-gauntlet_runner rule above; it also bites single-file edits.
