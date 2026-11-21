# VSL + Crypto Split — 2026-07-02

## Files Changed

| File | Δ | New Size | Type |
|------|---|----------|------|
| `src/runtime/wubu_vsl.c` | -2172 lines | 3 lines | Gutted to shim |
| `src/runtime/Makefile` | +8 .o refs + pattern rule | — | Build integration |
| `src/runtime/wubu_crypto.h` | +171 lines | 171 lines | New header-only utility |
| `src/runtime/wubu_image.c` | -150 lines | ~1512 lines | Crypto removed |
| `src/runtime/wubu_container.c` | -12 lines | — | CRC32 moved out |
| `src/runtime/wubu_container.h` | -3 lines | — | CRC32 decl removed |
| `src/runtime/vsl/vsl.c` | +2 lines | 192 lines | `_GNU_SOURCE` guard |
| `src/runtime/vsl/vsl_process.c` | +5 lines | 133 lines | Fix missing include + guard |
| `src/runtime/vsl/vsl_*.c` (×7) | +2 ea | — | `_GNU_SOURCE` guard |

## What Was Done

1. **VSL split**: `wubu_vsl.c` (2175 lines) → 3-line shim defining `VSL_STATE g_vsl;`.
   All implementation already existed in `src/runtime/vsl/*.c` submodules.
   Updated `RT_OBJS` to include all 8 submodule `.o` files.
   Added `$(RT)/vsl/%.o` pattern rule with `-DHAVE_VULKAN -DHAVE_CUDA -I$(RT)/vsl`.

2. **Crypto extraction**: `wubu_crypto.h` created as header-only utility library.
   Contains `wubu_crc32()` and `wubu_sha256_*()` family.
   `wubu_image.c` aliases old `sha256_*` names to `wubu_sha256_*` via `#define`.
   `wubu_container.c` had its CRC32 definition removed (now gets it from header).

3. **Cleanup**: Removed `wubu_vsl.c.bak` (2175 lines), `wubu_vsl_new.h` (243 lines).

## Verification

- `test_vsl`: 55/55 ✅
- `test_oci`: 10/10 ✅
- `test_network`: All expected non-fatal permission errors, no failures
- `test_phase1` (Runtime Core): ALL ✅
- `test_phase4` (Hosted/GUI): ALL ✅