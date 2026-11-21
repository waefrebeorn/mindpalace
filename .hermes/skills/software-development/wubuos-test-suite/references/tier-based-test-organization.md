# Tier-Based Test Organization (Post Battlefield Cleanup)

## Overview

After the battlefield cleanup (2026-07-03), the test suite organization changed from **Phase-based (1-6)** to **Tier-based** to match the WuBuOS roadmap tier structure.

All test commands still work — only the naming and grouping changed.

## Tier Test Targets (New)

```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed

# CRITICAL TIER: Runtime Core (OCI, Network, Snapshots, VSL, HolyD, Proton)
make test_critical_runtime
# Runs: test_oci test_network test_snapshot test_vsl test_holyd test_proton test_proton2

# CRITICAL TIER: Kernel / Metal (FAT32, TXFS, AHCI, DRM, Vulkan)
make test_critical_kernel
# Runs: test_fat32 test_txfs test_ahci test_drm_direct

# HIGH TIER: Bridge (Syscall bridge, DOS flip)
make test_high_bridge
# Runs: test_bridge test_bridge_flip test_syscall

# HIGH TIER: Hosted / GUI (WM, desktop, startmenu, explorer, terminal, clipboard)
make test_high_gui
# Runs: test_wm test_startmenu test_explorer test_term test_clipboard test_screenshot test_compositor test_shell

# HIGH TIER: Bear RL / JIT / Compiler (JIT, memory, tasking, input, HolyC, PTX)
make test_high_bear
# Runs: test_jit test_memory test_tasking test_input test_holyc test_holyc_ptx

# MEDIUM/LOW TIER: Apps / Audio / Tools / WorldSim / Other
make test_medium_other
# Runs: test_worldsim test_audio test_apps test_apps2 test_wubu test_host_exec test_gaad test_iso test_weights test_gc test_txfs test_dbuf test_styx test_styxfs test_anticheat test_bottles test_deploy test_daemon_panel test_math test_pkgmgr test_gamelib test_mime test_trash

# Full test suite — runs all tiers sequentially
make test
# Runs: test_critical_runtime test_critical_kernel test_high_bridge test_high_gui test_high_bear test_medium_other
```

## Mapping: Old Phase → New Tier

| Old Phase Target | New Tier Target | Component |
|------------------|-----------------|-----------|
| `test_phase1` | `test_critical_runtime` | Runtime Core |
| `test_phase2` | `test_critical_kernel` | Kernel/Metal |
| `test_phase3` | `test_high_bridge` | Bridge |
| `test_phase4` | `test_high_gui` | Hosted/GUI |
| `test_phase5` | `test_high_bear` | Bear RL/JIT/Compiler |
| `test_phase6` | `test_medium_other` | Apps/Audio/Tools/Other |

## Verification (2026-07-03)

All tier targets pass:
```
make test_critical_runtime    ✅ 14/14
make test_critical_kernel     ✅ 4/4
make test_high_bridge         ✅ 5/5
make test_high_gui            ✅ all GUI targets
make test_high_bear           ✅ 9/9
make test_medium_other        ✅ all remaining
make test                     ✅ "All tests passed (all tiers)"
```

## Key Insight

The tier names (Critical/High/Medium/Low) directly correspond to the **BATTLESHIP.md tier structure** and the **WUBUOS_DISTRO_ROADMAP.md tier map**. No more "Phase N" language — only tier-based organization matching the gap priority.