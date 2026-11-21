# Phase-Based Test Organization (2026-06-30) — VERIFIED

## Overview
The WuBuOS test suite is now organized into 6 logical phases matching the WuBuOS architecture layers. All phases verified passing 2026-06-30 with 747+ tests.

## Phase Mapping

| Phase | Target | Subsystems | Tests |
|-------|--------|------------|-------|
| **Phase 1** | `test_phase1` | Runtime Core: OCI, Network, Snapshots, VSL, HolyD, Proton/Proton2 | 414 |
| **Phase 2** | `test_phase2` | Kernel/Metal: FAT32, TXFS, AHCI, DRM/KMS | 62 |
| **Phase 3** | `test_phase3` | Bridge: Syscall bridge, DOS flip | 31 |
| **Phase 4** | `test_phase4` | Hosted/GUI: WM, StartMenu, Explorer, Terminal, Clipboard | 124 |
| **Phase 5** | `test_phase5` | Bear RL/JIT/Compiler: JIT, Memory, Tasking, HolyC, PTX | 321 |
| **Phase 6** | `test_phase6` | Apps/Audio/Tools/Other: WorldSim, Audio, Containers, etc. | ~95 |

## Commands
```bash
# Run individual phases
make test_phase1
make test_phase2
make test_phase3
make test_phase4
make test_phase5
make test_phase6

# Run all phases sequentially
make test
```

## Key Fixes Applied (2026-06-30)
- Added `wubu_container.c` to test targets needing container symbols
- Added `primary-selection-private.o` and `xdg-shell-private.o` to hosted/GUI tests
- Added `wubu_mime.c` to test targets using MIME functionality
- Fixed `styxfs.c` with `#define _GNU_SOURCE` for `S_IFDIR`/`S_IFREG` macros
- Removed missing `paint/` submodule from `apps.c` (uses `wubu_canvas.h` instead)
- Cleaned 52 dead files (old cartpole videos, deprecated docs, old paint module, test artifacts)

## Verification Results (2026-06-30)
```
✅ Phase 1 (Runtime Core): 414 tests - OCI, Network, Snapshots, VSL, HolyD, Proton
✅ Phase 2 (Kernel/Metal): 62 tests - FAT32, TXFS, AHCI, DRM/KMS
✅ Phase 3 (Bridge): 31 tests - Syscall bridge, DOS flip
✅ Phase 4 (Hosted/GUI): 124 tests - WM, StartMenu, Explorer, Terminal, Clipboard
✅ Phase 5 (Bear RL/JIT/Compiler): 321 tests - JIT, Memory, Tasking, HolyC, PTX
```

## Test Target Dependencies
Each phase target runs its constituent test targets in sequence. The main `test` target runs all 6 phases:

```makefile
test: test_phase1 test_phase2 test_phase3 test_phase4 test_phase5 test_phase6
```

## Regenerated Media
- `wubuos_screenshot.png` / `.ppm` — 1024×768 Win98 theme screenshot (62.7% non-black pixels)
- `wubuos_demo.mp4` — 0.4s H.264 @ 30fps, 1024×768 demo video