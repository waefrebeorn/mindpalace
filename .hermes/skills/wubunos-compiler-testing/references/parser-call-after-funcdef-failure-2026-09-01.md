# Parser failure: call after function definition (2026-09-01)

## Symptom

Sources where a function definition is followed by a standalone function call statement fail to parse:

```
expected token 77 (SEMI), got 71 (RPAREN)
```

Token 77 = `HD_TOK_SEMI`, token 71 = `HD_TOK_RPAREN`.

## Failing cases

- `int f(){return 42;} f();`
- `int g=7; int f(){return g;} f();`
- `int f(){return 42;} f(6);`
- `int f(){return 42;} g=f();`
- `{ int f(){return 42;} f(); }`

## Passing case (for contrast)

- `int sq(int n){return n*n;} sq(6)+6;`  ← call is part of a larger expression

## Diagnosis

The failure is in `holyd_parse.c`, NOT in MIR codegen. `hd_build_mir` returns -1, so `hd_eval_mir` returns 0 without ever running the interpreter.

The parser appears to mishandle the transition from a function definition body (which ends at `}`) back to the enclosing block, where a call statement follows. The exact parse path is:

1. Block parser consumes `int f(){return 42;}` as `HD_AST_FUNC_DECL`
2. Block parser then attempts to parse the next statement `f();`
3. `parse_stmt` routes to the expression-statement path
4. `parse_expr` -> `parse_comma` -> `parse_assign` -> ... -> `parse_postfix`
5. `parse_postfix` sees `f`, then `(` — enters call parsing
6. After consuming `()`, it expects `;` but finds `)` from somewhere (likely the block's closing `}` is being misread, or the parser's position is off by one after the function definition)

The "got 71 (RPAREN)" suggests the parser's token position is one past the `;` after `f();`, landing on a `)` — possibly from the function definition's body or from an off-by-one in `advance`.

## Key clue

Only standalone call statements fail. Calls embedded in expressions (`sq(6)+6`) succeed. This points to the expression-statement wrapper path in `parse_stmt` (the `expect(p, HD_TOK_SEMI)` at the end), not the call syntax itself.

## Workaround / fix direction

Investigate `parse_block`'s error-recovery path:

```c
if (p->has_error) {
    if (peek(p) == HD_TOK_RBRACE) {
        p->has_error = false;
        p->n_errors = 0;
    } else {
        break;
    }
}
```

This clears errors when `}` is next, which may be masking the real error and allowing the parser to continue with a corrupted token stream. Alternatively, check whether `parse_decl`'s function-definition path consumes one token too many or leaves the lexer positioned incorrectly for the next statement.

## Files to inspect

- `holyd_parse.c`: `parse_stmt`, `parse_block`, `parse_postfix`, `hd_parse_decl`
- `holyd_lexer.c`: token positioning after `}`
