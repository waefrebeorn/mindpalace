# Compound Literals (C99) and Variadic Functions in HolyD

## Compound Literals

Syntax: `(type){initializer-list}` — creates an unnamed object of the given type.

### Parsing (holyd_parse.c, `parse_cast`)

After parsing `(type)` in a cast, check if the next token is `{`. If so, it's a compound literal, not a cast:

```c
expect(p, HD_TOK_RPAREN);
if (peek(p) == HD_TOK_LBRACE) {
    advance(p); /* consume { */
    /* Parse initializer list: expr1, expr2, ... */
    /* Handle designated initializers: .field = expr */
    int elem_count = 0;
    HDASTNode **elems = calloc(sizeof(HDASTNode*), 8);
    while (peek(p) != HD_TOK_RBRACE && elem_count < 64) {
        if (peek(p) == HD_TOK_DOT) { /* designated initializer */
            advance(p); /* . */
            if (peek(p) == HD_TOK_IDENT) advance(p); /* field name */
            if (peek(p) == HD_TOK_ASSIGN) advance(p); /* = */
        }
        /* PITFALL: parse_assign, NOT parse_expr. parse_expr == parse_comma
         * and consumes the element-separator commas, so {10,20,30} parses
         * as ONE comma-expression yielding the last value (30) -- one element,
         * wrong value. parse_assign stops at the comma. */
        elems[elem_count++] = parse_assign(p);
        if (peek(p) == HD_TOK_COMMA) advance(p);
    }
    expect(p, HD_TOK_RBRACE);
    HDASTNode *cl = hd_ast_new(HD_AST_COMPOUND_LITERAL);
    cl->type = cast_type;
    cl->int_val = elem_count;
    cl->args = elems;
    cl->n_args = elem_count;
    return cl;
}
```

### Codegen (holyd_mir_eval.c)

1. Allocate memory via `wubu_mir_alloc(g->prog, n_cells)`
2. Store initializer elements at member offsets (structs) or index*8 (arrays)
3. Return address for struct/array, load+return value for scalar

### Limitations

- Array compound literals `(int[]){1,2,3}` require unsized-array type syntax
  which HolyD's `parse_cast` compound-literal path does not accept -- separate
  open gap. Sized `(int[3]){1,2,3}` also fails for the same parse reason.
- Struct compound literals work once element parsing uses `parse_assign` (above)
  AND the store path uses the struct-registry offsets: prefer
  `mir_struct_member_offset_by_index(g, sname, i)`, falling back to
  `members[i].offset * 8`. Using the parsed type's raw member offset (which is
  in cells) without the *8 scaling makes every element collide at cell 0.
- Designated initializers in compound literals work for simple cases
- The `args` array on `HDASTNode` is shared with function call args — don't mix

### Generalizable rule: initializer-list element parsers must stop at commas

Any parser reading a comma-SEPARATED list of initializer elements must parse
EACH element with the precedence level just above comma (i.e. `parse_assign`),
never with the top-level `parse_expr` when that is `parse_comma`. If a list
parser yields fewer elements than written, or the value equals the LAST element,
this is the bug. This applies to compound literals, brace-init lists, and any
enum/aggregate initializer -- not just compound literals.

## Variadic Functions

### Preprocessor macros (wubu_preproc.c)

```c
{"va_list", "int"},
{"va_start(ap, last)", "(ap = 0)"},
{"va_arg(ap, type)", "wubu_va_args[ap++]"},
{"va_end(ap)", ""},
```

Plus global: `int wubu_va_args[32];`

### Function entry copying (holyd_mir_eval.c)

At function entry for variadic functions (`fn->is_variadic`), copy v1..v8 to `wubu_va_args[0..7]`:

```c
if (fn->is_variadic) {
    /* Find or allocate wubu_va_args */
    for (int a = 0; a < 8; a++) {
        wubu_vr_t elem_addr = wubu_mir_binop(prog, MIR_ADD, va_args_addr,
                                              wubu_mir_const(prog, (int64_t)(a * 8)));
        wubu_mir_store(prog, elem_addr, (wubu_vr_t)(a + 1));
    }
}
```

### Limitations

- Only copies 8 arguments (v1..v8)
- `va_arg(ap, type)` reads `wubu_va_args[ap++]` — works for int-sized args
- `long double`, `long long`, struct args may not work correctly
- Tests using `va_arg` often also use `long double` which HolyD doesn't support

## strlen Compile-Time Builtin

`strlen("literal")` computed at compile time in `mir_gen_expr` `HD_AST_FUNC_CALL`:

```c
if (strcmp(fname, "strlen") == 0 && n->n_args >= 1) {
    if (n->args[0] && n->args[0]->kind == HD_AST_STRING_LIT) {
        return wubu_mir_const(g->prog, (int64_t)strlen(n->args[0]->str_val));
    }
}
```

This works because the preprocessor strips `__builtin_` prefix: `__builtin_strlen` → `strlen`.
