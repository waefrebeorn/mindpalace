# Assignment Dangling If Bug (2026-09-01)

## Bug Description

When removing debug `fprintf` statements from `holyd_mir_eval.c`, a "dangling if" bug was exposed that caused all variable assignments to fail.

## Root Cause

Original code (at HEAD):
```c
case HD_AST_ASSIGN: {
    wubu_vr_t val = mir_gen_expr(g, n->right);
    wubu_vr_t addr = mir_lvalue_addr(g, n->left);
    if (n->left && n->left->kind == HD_AST_MEMBER)
        fprintf(stderr, "ASSIGN to MEMBER: val=%d addr=%d\n", val, addr);
    if (addr) { wubu_mir_store(g->prog, addr, val); return val; }
    return val;
}
```

When the `fprintf` was removed, it became:
```c
case HD_AST_ASSIGN: {
    wubu_vr_t val = mir_gen_expr(g, n->right);
    wubu_vr_t addr = mir_lvalue_addr(g, n->left);
    if (n->left && n->left->kind == HD_AST_MEMBER)
    if (addr) { wubu_mir_store(g->prog, addr, val); return val; }
    return val;
}
```

The second `if (addr)` is now **nested** inside the `if (MEMBER)` check!

## Impact

For assignments to IDENT (variable) targets:
- `n->left->kind == HD_AST_MEMBER` is FALSE
- The entire `if (addr)` block is skipped
- The store operation never happens
- Variable retains initial value (often 0 from calloc)

Example failing test:
```c
int x; x = 42; x   // Returns 0 instead of 42
```

## Fix

Remove the guard statement entirely, or add braces:
```c
case HD_AST_ASSIGN: {
    wubu_vr_t val = mir_gen_expr(g, n->right);
    wubu_vr_t addr = mir_lvalue_addr(g, n->left);
    if (addr) { wubu_mir_store(g->prog, addr, val); return val; }
    return val;
}
```

## Prevention

After ANY debug removal:
```sh
./gauntlet_runner --core --target x86-64
```
Verify 247/247 before full gauntlet. The 30-second core check catches regressions.

## Related Code Patterns

Be careful with:
1. Debug-only `if` statements with no `{ }` body
2. `fprintf` inside conditionals (can be accidentally removed by scripts)
3. Multi-line debug statements split across lines

Always review git diff after bulk debug removal.