# HolyC REPL Persistent Variable Bug Fix — 2026-07-06

## Problem
The test `holyd eval: persistent variable across evals` failed:
- First eval: `I64 x = 123;` → output `123` ✅
- Second eval: `x + 10` → output garbage (`2949`, `3973`, `5260204364651666002`) instead of `133` ❌

## Root Cause (3 bugs)

### Bug 1: Global variable load check in HC_AST_IDENT
First global variable gets `stack_offset = -global_offset = -0 = 0`. 
Check was `if (off < 0)` treating offset 0 as local variable → emitted `mov rax, [rbp - 0]` instead of RIP-relative load.

**Fix in `holyc_codegen.c`:**
```c
// Line 341: changed from
if (off < 0) {
    /* global */
}
// to
if (off <= 0) {
    /* global or zero-offset global */
}
```

### Bug 2: Missing runtime patches for IDENT global loads
`HC_AST_VAR_DECL` (stores) recorded patch info for runtime fixup via `global_patches[]`, but `HC_AST_IDENT` (loads) did not. So first eval's disp32 was baked in and used incorrectly for second eval.

**Fix in `holyc_codegen.c` (HC_AST_IDENT case):**
```c
// After emitting RIP-relative load instruction
size_t patch_pos = gen->code_size + 3;  /* Position of disp32 in 7-byte instruction */
if (gen->n_global_patches < 32) {
    gen->global_patches[gen->n_global_patches].code_patch_pos = patch_pos;
    gen->global_patches[gen->n_global_patches].global_offset = data_offset;
    gen->n_global_patches++;
}
```

### Bug 3: Stale global_patches preserved across evals
`hc_gen_init` was saving/restoring `global_patches` across compilations, but they're per-compilation ephemeral. Second eval used patches from first eval (wrong instruction offsets).

**Fix in `holyc_codegen.c` (hc_gen_init):**
```c
// REMOVED the save/restore of global_patches
// Added comment: "Do NOT preserve global_patches - they are ephemeral per-compilation"
// global_patches start fresh: n_global_patches = 0
```

## Runtime Patching Logic (wubu_holyd.c)
```c
// In wubu_holyd_eval after codegen, before execution:
for (int i = 0; i < compiler->gen.n_global_patches; i++) {
    size_t patch_pos = compiler->gen.global_patches[i].code_patch_pos;
    size_t global_offset = compiler->gen.global_patches[i].global_offset;
    // RIP after instruction = exec + patch_pos + 4 (7-byte instruction, RIP points to next)
    // Target = exec + code_size + global_offset
    // disp32 = target - RIP = code_size + global_offset - patch_pos - 4
    int32_t disp32 = (int32_t)(compiler->gen.code_size + global_offset - patch_pos - 4);
    *(int32_t*)((uint8_t *)exec + patch_pos) = disp32;
}
```

## Verification
All test suites pass after fix:
- `test_holyd`: 33/32 ✅ (persistent var + persistent func)
- `test_vsl`: 83/83 ✅
- `test_explorer`: 74/74 ✅
- `test_term`: 11/11 ✅
- `test_snapshot`: 132/132 ✅
- `test_oci`: 10/10 ✅
- `make runtime`: Clean build ✅