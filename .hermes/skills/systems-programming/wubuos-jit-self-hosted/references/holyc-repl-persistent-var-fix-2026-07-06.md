# HolyC REPL Persistent Variable Bug Fix — 2026-07-06

## Problem
Test `holyd eval: persistent variable across evals` failed:
- First eval: `I64 x = 123;` → output `123` ✅
- Second eval: `x + 10` → output garbage (e.g., `5260204364651666002`, `3973`, `2949`) ❌ expected `133`

## Root Cause (3 Bugs)

### Bug 1: HC_AST_IDENT global var load check
In `src/compiler/holyc_codegen.c`, the check for global vs local was:
```c
if (off < 0) { /* global */ } else { /* local */ }
```
First global variable gets `stack_offset = -global_offset = -0 = 0`. Since `0 < 0` is false, it was treated as local → emitted stack-relative load `[rbp - 0]` instead of RIP-relative load `[rip + disp32]`.

**Fix**: Change to `if (off <= 0)` — includes offset 0 in global path.

### Bug 2: Missing runtime patches for IDENT global loads
`HC_AST_VAR_DECL` (stores) recorded `global_patches[]` entries for runtime fixup:
```c
gen->global_patches[gen->n_global_patches].code_patch_pos = patch_pos + 3;
gen->global_patches[gen->n_global_patches].global_offset = global_offset;
gen->n_global_patches++;
```

But `HC_AST_IDENT` (loads) did NOT record patches — it just emitted a computed disp32 based on current `gen->code_size`. First eval's disp32 was baked in. Second eval used different `code_size` but old disp32 → wrong address.

**Fix**: Add patch recording for IDENT global loads:
```c
size_t patch_pos = gen->code_size + 3;  // disp32 position in 7-byte instruction
emit_byte(gen, 0x48);  // REX.W
emit_byte(gen, 0x8B);  // mov rax, [rip+disp32]
emit_byte(gen, 0x05);  // ModRM
emit_dword(gen, (uint32_t)rip_disp);  // placeholder disp32

if (gen->n_global_patches < 32) {
    gen->global_patches[gen->n_global_patches].code_patch_pos = patch_pos;
    gen->global_patches[gen->n_global_patches].global_offset = data_offset;
    gen->n_global_patches++;
}
```

### Bug 3: Stale global_patches preserved across compilations
`hc_gen_init()` saved/restored `global_patches`:
```c
struct { size_t code_patch_pos; size_t global_offset; } saved_global_patches[32];
int saved_n_global_patches = gen->n_global_patches;
memcpy(saved_global_patches, gen->global_patches, sizeof(saved_global_patches));
// ... memset(gen, 0, sizeof(*gen)) ...
gen->n_global_patches = saved_n_global_patches;
memcpy(gen->global_patches, saved_global_patches, sizeof(saved_global_patches));
```

But `global_patches` are per-compilation ephemeral — tied to specific instruction offsets in the current code buffer. Second eval inherited first eval's patches pointing to wrong locations.

**Fix**: Don't preserve global_patches — clear them each compilation:
```c
/* Do NOT preserve global_patches - they are ephemeral per-compilation */
memset(gen, 0, sizeof(*gen));
// n_global_patches starts at 0 automatically
```

## Runtime Patch Formula Fix

In `src/runtime/wubu_holyd.c`, the runtime patch loop had wrong disp32 formula:
```c
// OLD (wrong):
int32_t disp32 = (int32_t)(compiler->gen.code_size + global_offset - patch_pos);

// NEW (correct):
int32_t disp32 = (int32_t)(compiler->gen.code_size + global_offset - patch_pos - 4);
```

RIP after the 7-byte `mov rax, [rip+disp32]` instruction is at `exec + patch_pos + 4` (instruction starts at `exec + patch_pos - 3`, ends at `exec + patch_pos + 4`). Target data address is `exec + code_size + global_offset`. So:
```
disp32 = target - RIP = (exec + code_size + global_offset) - (exec + patch_pos + 4)
       = code_size + global_offset - patch_pos - 4
```

## Verification
```bash
make clean && make test_holyd
```
Results: **33/32 passed** (persistent variable + persistent function tests both pass)

## Files Changed
- `src/compiler/holyc_codegen.c` — HC_AST_IDENT patch recording, hc_gen_init clear patches
- `src/runtime/wubu_holyd.c` — runtime disp32 formula fix

## Related
- `references/oci-split-2026-07-05.md` — similar runtime patching pattern for global variable stores
- `references/vsl-syscall-parameter-usage-fix-2026-07-05.md` — parameter usage patterns