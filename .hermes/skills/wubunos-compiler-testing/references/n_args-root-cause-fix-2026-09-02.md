# n_args=0 Root Cause Fix (2026-09-02)

## The 30-test failure signature

Before the fix, `hd_build_mir` never called `wubu_mir_set_n_args()`, leaving
`prog->n_args = 0`. The register allocator in `wubu_mir_regalloc.c:305-330`
pre-assigns argument VRs `v1..vn_args` to physical registers 1..n_args only
when `n_args > 0`. With `n_args=0`, the pre-assignment loop was skipped and
v1..vN were allocated by linear scan alongside locals, causing the callee to
clobber the caller's argument registers mid-execution.

## Diagnostic signature in `--dump-asm` / `DEBUG_REGS=1`

```sh
WUBU_DEBUG_REGS=1 ./gauntlet_runner --dump-asm x86-64 \
  "int test(int q5, int nd) { return q5; } int main() { return test(42, 0); }"
```

Look for:
```
[DEBUG_REGS] mir_count_max_args=2    # was 0 before fix
[DEBUG_REGS] n_vr=23 n_intervals=11 n_phys_regs=9 n_args=2
assign[0] = reg 0  (r10 — return register)
assign[1] = reg 1  (r11 — first arg)   # missing before fix
assign[2] = reg 2  (r12 — second arg)  # missing before fix
```

Before fix: `assign[1]` and `assign[2]` were assigned by linear scan in the
same pool as locals, often colliding with callee VRs.

## The fix

Two additions to `holyd_mir_eval.c`:

1. **`mir_count_max_args()` helper** (static function, ~line 239): Recursively
   walks the AST, finds the maximum `n_args` across all `HD_AST_FUNC_CALL`
   nodes, clamped to `MIR_MAX_CALL_ARGS`.

2. **`wubu_mir_set_n_args()` call** (in `hd_build_mir`, after `mir_collect_funcs`
   and before the optimization pass):
   ```c
   int max_args = mir_count_max_args(ast);
   wubu_mir_set_n_args(prog, (uint32_t)max_args);
   ```

## Important: AST node kind

The function-call node is `HD_AST_FUNC_CALL`, NOT `HD_AST_CALL`. Using the
wrong kind returns 0 and silently defeats the fix.

## Before/after test counts

| Test group | Before fix | After fix |
|-----------|-----------|----------|
| x86-64 core | 247/247 | 247/247 |
| x86-64 gcc_torture | 30 fail (incl. 000028, 000111, 000172) | 27 of 30 fixed |

Tests that specifically validate this fix:
- `gcc_torture_000028_loop_13` (`scale(&alpha, x, 5)` 3-arg call)
- `gcc_torture_000172_pr83477` (`pl(1, !yf)` 2-arg call)
- `gcc_torture_000111_pr118915` (multi-arg function call)

## Per-function regalloc remains the true fix

`n_args` pre-assignment is a workaround that stabilizes the allocator's
pre-assignment loop. The architectural root cause is the SHARED `assign[]`
table in `wubu_mir_regalloc.c` — one global array mapping ALL VRs across ALL
functions to the same physical registers. The true fix is per-function
regalloc (each function gets its own assign[]), but that is a significant
refactor. The `n_args` fix is the high-leverage surgical fix that resolves
the dominant failure mode.
