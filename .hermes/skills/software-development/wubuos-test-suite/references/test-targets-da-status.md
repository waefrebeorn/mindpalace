# Test Targets — DA Status Cross-Reference

Maps each test target to the REAL_GAPs it exercises and the gap categories it validates.

## Test Target → REAL_GAP Coverage

| Test Target | Tests | Gap Category | Key Files Exercised |
|-------------|-------|--------------|---------------------|
| test_proton | 32 | Runtime (Proton) | wubu_proton.c (15 gaps closed) |
| test_proton2 | 14 | Runtime (Proton) | wubu_proton2.c (gamescope config) |
| test_vsl | 52 | Kernel (VSL) | wubu_vsl.c (347 void casts) |
| test_network | 139 | Runtime (Network) | wubu_network.c (32 gaps, netlink) |
| test_snapshot | 132 | Runtime (Snapshot) | wubu_snapshot.c (24 gaps, nftw) |
| test_holyd | 31 | Runtime (HolyD) | wubu_holyd.c (22 gaps, hc_eval) |
| test_oci | 10 | Runtime (OCI) | wubu_oci.c (28 gaps, mbedTLS) |
| test_holyc | 76 | Compiler | holyc_codegen.c (29 placeholders) |
| test_jit | 76 | JIT | wubu_x86.c, jit_minic.c |
| test_ahci | 16 | Kernel | interrupt.c (41 void casts) |
| test_fat32 | 20 | Kernel | fat32.c (18 gaps) |
| test_txfs | 25 | Kernel | txfs.c (25 gaps) |
| test_wm | 16 | GUI | wm.c (22 gaps, GAAD) |
| test_startmenu | 4 | GUI | startmenu.c (24 gaps) |
| test_explorer | 71 | GUI | explorer.c (31 gaps) |
| test_archd | 16 | Runtime (Arch) | wubu_archd.c (14 gaps) |
| test_daemon_panel | 21 | GUI | daemon_panel.c |
| test_bottles | 16 | Runtime | wubu_bottles.c (11 gaps) |
| test_anticheat | 14 | Runtime | wubu_anticheat.c (12 gaps) |
| test_drm_direct | 1 | Hosted | wubu_metal.c (31 gaps) |
| test_metal | 3 | Hosted | wubu_metal.c (DRM/ALSA/Pulse) |
| test_audio | 11 | Audio | wubu_audio.c (13 gaps) |
| test_deploy | 9 | Runtime | wubu_deploy.c |
| test_screenshot | 9 | Tools | screenshot.c |
| test_gui_screenshot | 11 | GUI | wubu_screenshot.c |
| test_wubu_wm | 18 | GUI | wubu_wm.c |
| test_apps | 15 | Apps | apps.c |
| test_apps2 | 16 | Apps | wubu_apps2.c |
| test_holyc_terminal | 73 | Compiler | holyc_terminal.c |
| test_holyc_ptx | 11 | Compiler | holyc_ptx.c |
| test_gamelib | 16 | Bear RL | wubu_gamelib.c (11 gaps) |
| test_pkgmgr | 11 | Runtime | wubu_pkgmgr.c (8 gaps) |
| test_gc | 10 | Compiler | wubu_gc.c |
| test_iso | 20 | Runtime | iso9660.c |
| test_weights | 8 | Bear RL | wubu_math.c |
| test_gc | 10 | Compiler | wubu_gc.c |
| test_styx | 29 | Runtime | styx.c |
| test_styxfs | 11 | Runtime | styxfs.c |
| test_bridge | 25 | Bridge | bridge.c |
| test_syscall | 5 | Bridge | wubu_syscall.c (97 gaps) |
| test_hosted | 3 | Hosted | hosted.c (72 void casts) |
| test_host_exec | 15 | Runtime | wubu_host_exec.c |
| test_wubu | 47 | Runtime | wubu_exec.c |
| test_tasking | 17 | Kernel | tasking.c |
| test_input | 11 | Kernel | input.c |
| test_memory | 29 | Kernel | memory.c |
| test_worldsim | 18 | WorldSim | worldsim.c |
| test_gaad | 17 | WorldSim | wubu_gaad.c |
| test_mime | 11 | Tools | wubu_mime.c |
| test_trash | 7 | Tools | wubu_trash.c |\n| test_anticheat | 14 | Runtime | wubu_anticheat.c |\n| test_bottles | 16 | Runtime | wubu_bottles.c |\n| test_clipboard | 14 | GUI | wubu_clipboard.c (43 void casts) |\n\n## DA Audit Coverage by Category

| Category | Test Targets | Coverage |
|----------|--------------|----------|
| Runtime (420 gaps) | test_network, test_snapshot, test_holyd, test_oci, test_vsl, test_proton, test_proton2, test_archd, test_daemon_panel, test_anticheat, test_bottles | ✅ High — all critical paths tested |
| Kernel (230 gaps) | test_vsl, test_ahci, test_fat32, test_txfs, test_memory, test_tasking, test_input, test_interrupt | ✅ Medium — syscalls tested, drivers stubbed |
| GUI (280 gaps) | test_wm, test_startmenu, test_explorer, test_gui_screenshot, test_apps, test_apps2 | ✅ Medium — WM/desktop tested, file ops stubbed |
| Bear RL (190 gaps) | test_gamelib, test_weights, test_anticheat | ⚠️ Low — RL training untested |
| Hosted (120 gaps) | test_metal, test_drm_direct, test_hosted, test_screenshot | ⚠️ Low — display/audio stubbed |
| Compiler (25 gaps) | test_holyc, test_jit, test_holyc_terminal, test_holyc_ptx | ✅ High — compiler pipeline tested |
| Apps (55 gaps) | test_apps, test_apps2, test_explorer, test_calc, test_paint | ⚠️ Medium — some apps untested |
| JIT/Other (222 gaps) | test_jit, test_encoder, test_disasm | ✅ Medium — encoder/disasm tested |

## Verification Strategy

For each REAL_GAP closed:
1. Identify which test target exercises the code path
2. Run that specific target: `make test_XXX`
3. Verify still GREEN
4. Run `make all` for clean build
5. If target doesn't exist, add test case to relevant test case

## Current Status: ALL 47 TARGETS GREEN (747+ assertions)