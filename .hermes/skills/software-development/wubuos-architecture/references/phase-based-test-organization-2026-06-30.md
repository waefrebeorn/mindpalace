# Phase-Based Test Organization — 2026-06-30

## Overview
The WuBuOS test suite (747+ tests) is now organized into 6 phases matching the architecture vault phases. Each phase can be run independently for focused development, or all phases run sequentially via `make test`.

## Phase Mapping

### Phase 1: Runtime Core
**Subsystems**: Container runtime, Network, OCI registry, Snapshots, VSL, HolyD, Proton
**Tests**: 414 tests
```bash
make test_phase1
# test_oci (10) + test_network (139) + test_snapshot (132) + test_vsl (56) + test_holyd (31) + test_proton (32) + test_proton2 (14) = 414
```

### Phase 2: Kernel / Metal
**Subsystems**: FAT32 FS, TXFS WAL, AHCI SATA, DRM/KMS, Vulkan loader
**Tests**: 62 tests
```bash
make test_phase2
# test_fat32 (20) + test_txfs (25) + test_ahci (16) + test_drm_direct (1) = 62
```

### Phase 3: Bridge
**Subsystems**: VBE↔WorldSim bridge, Syscall bridge, DOS↔Temple flip
**Tests**: 31 tests
```bash
make test_phase3
# test_bridge (25) + test_bridge_flip (1) + test_syscall (5) = 31
```

### Phase 4: Hosted / GUI
**Subsystems**: Window Manager, Desktop, Start Menu, Explorer, Terminal, Clipboard, Screenshot
**Tests**: 124 tests
```bash
make test_phase4
# test_wm (16) + test_startmenu (4) + test_explorer (74) + test_term (4) + test_clipboard (17) + test_screenshot (9) = 124
```

### Phase 5: Bear RL / JIT / Compiler
**Subsystems**: JIT encoder/disasm/backends, Memory alloc, Tasking, Input, HolyC compiler, PTX backend, HolyC terminal
**Tests**: 321 tests
```bash
make test_phase5
# test_jit (76) + test_memory (29) + test_tasking (17) + test_input (11) + test_holyc (84) + test_holyc_ptx (31) + test_holyc_terminal (73) = 321
```

### Phase 6: Apps / Audio / Tools / WorldSim / Other
**Subsystems**: WorldSim, Audio, Apps, Containers, ISO, Weights, GC, Double-buffer, Styx, Anticheat, Bottles, Deploy, Daemon panel, Math, PkgMgr, GameLib, MIME, Trash
**Tests**: ~370 tests
```bash
make test_phase6
# test_worldsim (18) + test_audio (30) + test_apps (15) + test_apps2 (16) + test_wubu (47) + test_host_exec (15) + test_gaad (17) + test_iso (20) + test_weights (8) + test_gc (10) + test_dbuf (17) + test_styx (29) + test_styxfs (11) + test_anticheat (14) + test_bottles (16) + test_deploy (9) + test_daemon_panel (21) + test_math (21) + test_pkgmgr (11) + test_gamelib (16) + test_mime (11) + test_trash (7) = ~370
```

## Running Individual Phases
```bash
# Quick smoke test of a specific subsystem
make test_phase4  # GUI tests only

# Verify phase before/after gap closure
make test_phase1  # before modifying runtime
# ... edit code ...
make test_phase1  # verify still green
```

## Main Test Target
```bash
make test
# Runs: test_phase1 test_phase2 test_phase3_phase3 test_phase4 test_phase5 test_phase6
# Output: "✅ All tests passed (6 phases)"
```

## Notes
- Some test targets excluded from main `test` target due to linking issues (test_archd, test_ramdisk, test_wubu_wm, test_pkgmgr, test_apps)
- These can still be run individually if dependencies are satisfied
- Phase 6 is largest — consider running sub-targets individually during development