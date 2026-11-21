# wubu_oci.c SHA256 Dedup → wubu_crypto.h (2026-07-02)

## Problem
`wubu_oci.c` had its own 60-line SHA256 implementation (`sha256_digest`, `sha256_file`, K-array, compression round functions) alongside `wubu_crypto.h` which already provided `wubu_sha256_digest()`. The duplicate was never cleaned up when `wubu_crypto.h` was extracted in the VSL modular refactor.

## Fix
1. Added `#include "wubu_crypto.h"` at the top of `wubu_oci.c` with other includes
2. Replaced the 60-line SHA256 body with a 3-line wrapper:
   ```c
   static void sha256_digest(const void *data, size_t size, char *out_hex) {
       wubu_sha256_digest(data, size, out_hex, 65);
   }
   ```
3. Updated `sha256_file` to call `wubu_sha256_digest` directly (with `out_size=65`)
4. Removed the stray duplicate `#include "wubu_crypto.h"` that was in the middle of the file (~line 432)

## Diff Stats
- 1 file changed, 6 insertions(+), 43 deletions(-)

## Verification
- `make runtime` ✅
- `make test_vsl` 55/55 ✅
- No other files had stale SHA256 (wubu_image.c already used `#define sha256_digest wubu_sha256_digest`)

## Root Cause
The VSL modular refactor created `wubu_crypto.h` but the monolithic-split skill's workflow didn't include a post-extraction check for duplicate implementations in sibling files. Added a "Post-Extraction Verification: Dedup Scan" section to the skill.