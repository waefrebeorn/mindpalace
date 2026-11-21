# Block Expression Codegen Fix — 2026-08-16

## Signal
The universal test gauntlet found that block expressions like `{int a=5; a*b}` returned 0 instead of the expected value. Root cause: `hc_eval` called `gen_stmt()` for the entire block, which doesn't put the last expression's value in `rax`.

## Fix (holyc_codegen_api.c, hc_eval)

When the AST is a `HC_AST_BLOCK`, generate all statements except the last as statements, then generate the last one as an expression so its value ends up in `rax` (the return value):

```c
if (ast->kind == HC_AST_BLOCK) {
    if (ast->n_stmts > 0) {
        for (int i = 0; i < ast->n_stmts - 1; i++)
            gen_stmt(&gen, ast->stmts[i]);
        HCASTNode *last = ast->stmts[ast->n_stmts - 1];
        if (last->kind == HC_AST_EXPR_STMT) {
            gen_expr(&gen, last->child);
        } else if (last->kind == HC_AST_RETURN) {
            gen_stmt(&gen, last);
        } else {
            gen_expr(&gen, last);
        }
    }
}
```

## HolyC Expression Format for Tests

Tests MUST be written as HolyC expressions, NOT C programs:
- WRONG: `"int main(){return 1+2;}"` — hc_eval can't parse `int main(){}`
- RIGHT: `"1+2"` — bare expression
- RIGHT: `"{int a=5; int b=3; a*b;}"` — block with semicolons
- RIGHT: `"if(1) {42;} else {0;}"` — control flow (braces required)
- RIGHT: `"1?42:0"` — ternary

**Semicolons are REQUIRED** after every statement in a block, including the last expression. `parse_stmt` → `expect(SEMI)` fires without it.

## Debugging Lesson: Stale Binaries

When `make` doesn't rebuild after source changes:
1. The `holyc` target depends on `$(JIT_OBJS)` but compiles from source — stale `.o` files can prevent rebuild
2. `rm -f src/compiler/holyc && make holyc` forces rebuild
3. `objdump -d src/compiler/holyc | grep -A100 "<hc_eval>:"` verifies the binary matches source
4. Debug `fprintf` at the VERY START of the function to confirm it's being called
5. Early returns (parse errors, null checks) can silence later debug prints

## Result

53/63 tests pass (up from 47). Remaining 10 failures:
- if/else in expression context (braces fix needed)
- Complex blocks (nested loops)
- Signed overflow semantics
- Array/pointer access (need memory model)

## Reference
- ~/vault/WALKWAY.md — full work plan
- ~/vault/HARDWARE_TARGET_MATRIX.md — past/present/future hardware
- ~/vault/research/TEST_GAUNTLET_REFERENCE.md — 12 test suites, 121K+ tests
