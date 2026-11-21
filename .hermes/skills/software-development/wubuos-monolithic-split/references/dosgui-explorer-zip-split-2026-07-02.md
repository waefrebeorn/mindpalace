# explorer ZIP Module Extraction (2026-07-02)

## Target
`src/gui/explorer.c` — 2598 lines, 4th-largest file in WuBuOS.

## Extracted
**ZIP archive module** — 313 lines (lines 637-949 in original):
- ZIP central directory parsing (raw file I/O, no libzip headers needed)
- libzip dlopen wrapper (optional, falls back to manual parsing)
- `explorer_mount_zip`, `unmount_zip`, `is_in_zip` (public API from header)

## Internal Header Pattern

Created `explorer_internal.h` containing:
1. **Safe-string macros** (`WUBU_STRCPY`, `WUBU_SNPRINTF`, `WUBU_STRLCAT`) — guarded with `#ifndef` so they work identically whether the host file `#define`s them first or not
2. **Exported internal helper** — `ex_update_breadcrumbs()` (was `static` in main file, now non-static for cross-module access)

The internal header `#include`s the public header first, so all public types (`ExExplorerState`, `ExEntry`, `g_explorer`) are available.

## What Changed in the Host File

1. Added `#include "explorer_internal.h"` (after public header)
2. Removed the duplicate WUBU_SAFE_STRING macro block (now in internal header)
3. Removed `static` from `ex_update_breadcrumbs` forward declaration AND definition
4. Deleted the ~313-line ZIP section

## Makefile Updates (3 separate places)

```
grep -n 'explorer\.c' Makefile
# → 3 hits: GUI_OBJS, hosted build recipe, test_explorer target
```

All 3 needed `explorer_zip.c` added right after `explorer.c`.

## Verification

```bash
make test_explorer  # 74/74 PASS
make test_phase4           # All GUI targets PASS
make hosted                # Builds clean
```

## Key Pattern: `#ifndef`-guarded shared macros in internal headers

When the same WUBU_* macros are `#define`d at the top of the host .c AND needed in extracted sub-modules:

```c
// explorer_internal.h
#ifndef WUBU_STRCPY
#define WUBU_STRCPY(dst, src, dst_size) \
    do { ... } while(0)
#endif
```

This way the host .c can keep its own `#define` (which might have file-specific customizations) and the sub-module gets the canonical version from the internal header. No conflict because of the `#ifndef` guard.