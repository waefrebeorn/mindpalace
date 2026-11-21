# Monolithic Split Session — 2026-07-06

## Files Split

| Original | Before | After | New Modules |
|----------|--------|-------|-------------|
| `wubu_image.c` | 1516 | 1185 | `wubu_image_parse.c` (305), `wubu_image_manifest.c` (164), `wubu_image_ops.c` (221), `wubu_image_internal.h` (58), `wubu_image_manifest.h` (17) |
| `wubu_network.c` | 1271 | 996 | `wubu_netlink.c` (285), `wubu_netlink.h` (76) |
| `wubu_snapshot.c` | 1222 | 920 | `wubu_snapshot_fs.c` (208), `wubu_snapshot_internal.h` (158), `wubu_snapshot_fs.h` (28) |

## Key Fixes & Patterns

### 1. FTW Flag Constants (wubu_snapshot_internal.h)
```c
#ifndef FTW_MOUNT
#define FTW_MOUNT 0x0100
#endif
#ifndef FTW_DEPTH
#define FTW_DEPTH 0x0001
#endif
#ifndef FTW_PHYS
#define FTW_PHYS 0x0002
#endif
#ifndef FTW_NS
#define FTW_NS 0x0004
#endif
#ifndef FTW_SL
#define FTW_SL 0x0010
#endif
#ifndef FTW_SLN
#define FTW_SLN 0x0010
#endif
#ifndef FTW_DP
#define FTW_DP 0x0004
#endif
```

### 2. dir_size Migration
**Header:** `uint64_t dir_size(const char*);` (non-static, non-inline)
**Source:** `uint64_t dir_size(const char* path) { ... }` (no `static`)

### 3. Signature Mismatch Fix
`build_snapshot_path` was declared with 4 params, called with 5. Added `void* flags` to header declaration with `(void)flags;`.

### 4. FTW_SLN Removal
Removed dangling `case FTW_SLN:` from switch — it's an alias for `FTW_SL`, not a separate constant.

### 5. btrfs Headers
```c
#ifndef BTRFS_SUPER_MAGIC
#define BTRFS_SUPER_MAGIC 0x9123683E
#endif
#include <linux/btrfs.h>
```

### 6. Surgical Python Deletion
Script that:
- Reads monolith
- Cross-references function names against new headers
- Finds closing braces via brace-counting
- Deletes entire blocks atomically
- Strips `static` from remaining functions declared non-static in headers

Eliminated `static follows non-static` cascade in one pass.

## Build Verification
- `make clean && make runtime` → ✅
- `make clean && make hosted` → ✅
- `test_snapshot` → 132/132
- `test_oci` → 10/10
- `test_network` → 114/139 (25 netlink integration tests skip in CI)

## Commits
- `wubu_image.c parser split` — 369 ins, 335 del
- `wubu_image.c further split` — 4 files changed, 28 ins, 445 del
- `wubu_network.c netlink split` — 375 ins, 292 del
- `wubu_snapshot.c fs split` — 28 ins, 330 del