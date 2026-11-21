# Phase 1 ZealOS Parity Extension Reference

## Summary
Extended `zealos_parity.h` from 96 → 150+ function mappings across 8 new subsystems.

## New Alias Categories Added

### HolyC Compiler (18 new)
```
HCCompile           → hc_compile
HCEval              → hc_eval
HCCompileFunc       → hc_compile_func
HCLexNext           → hc_lex_next
HCLexPeek           → hc_lex_peek
HCLexExpect         → hc_lex_expect
HCParseCompUnit     → hc_parse_compilation_unit
HCParseExpr         → hc_parse_expr
HCParseStmt         → hc_parse_stmt
HCParseDecl         → hc_parse_decl
HCAstNew            → hc_ast_new
HCAstFree           → hc_ast_free
HCAstAddStmt        → hc_ast_add_stmt
HCAstAddArg         → hc_ast_add_arg
HCAstPrint          → hc_ast_print
HCTypeSize          → hc_type_size
HCGenNode           → hc_gen_node
HCGenFunction       → hc_gen_function
HCGenCode           → hc_gen_code
```

### AHCI/SATA Storage (11 new)
```
AHCIInit            → ahci_init
AHCIShutdown        → ahci_shutdown
AHCIDiskRead        → ahci_disk_read
AHCIDiskWrite       → ahci_disk_write
AHCIIdentify        → ahci_identify
AHCIPortReset       → ahci_port_reset
AHCIPortStart       → ahci_port_start
AHCIPortStop        → ahci_port_stop
AHCICmdRead         → ahci_cmd_read
AHCICmdWrite        → ahci_cmd_write
AHCIFindDevice      → ahci_find_device
```

### TXFS Filesystem (13 new)
```
TXFSInit            → txfs_init
TXFSShutdown        → txfs_shutdown
TXFSFormat          → txfs_format
TXFSMount           → txfs_mount
TXFSUnmount         → txfs_unmount
TXFSCreate          → txfs_create
TXFSDelete          → txfs_delete
TXFSRead            → txfs_read
TXFSWrite           → txfs_write
TXFSOpen            → txfs_open
TXFSClose           → txfs_close
TXFSSeek            → txfs_seek
TXFSSync            → txfs_sync
TXFSStat            → txfs_stat
```

### GAAD/Phi Optimization (9 new)
```
GAADInit            → gaad_init
GAADShutdown        → gaad_shutdown
GAADComputePhi      → gaad_compute_phi
GAADOptimize        → gaad_optimize
GAADSnapToGrid      → gaad_snap_to_grid
GAADLayoutWindow    → gaad_layout_window
GAADLayoutWindows   → gaad_layout_windows
GAADRectOverlap     → gaad_rect_overlap
GAADPhiScale        → gaad_phi_scale
GAADFibonacciStep   → gaad_fibonacci_step
```

### Container Runtime (15 new)
```
CtCreate            → wubu_ct_create
CtDestroy           → wubu_ct_destroy
CtSetCmd            → wubu_ct_set_cmd
CtAddBind           → wubu_ct_add_bind
CtAddEnv            → wubu_ct_add_env
CtSetGPU            → wubu_ct_set_gpu
CtSetLimits         → wubu_ct_set_limits
CtStart             → wubu_ct_start
CtWait              → wubu_ct_wait
CtKill              → wubu_ct_kill
CtState             → wubu_ct_state
CtStateName         → wubu_ct_state_name
CtRuntimeName       → wubu_ct_runtime_name
CtSteamOS           → wubu_ct_steamos
CtNative            → wubu_ct_native
CtProton            → wubu_ct_proton
CtHolyC             → wubu_ct_holyc
```

### VBE/Drawing Extensions (15 new)
```
GrFill              → vbe_fill_rect
GrRect              → vbe_rect
GrLine              → vbe_line
GrCircle            → vbe_circle
GrGradient          → vbe_hgradient
GrVGradient         → vbe_vgradient
GrShade             → vbe_shade_rect
Gr3DSunken          → vbe_3d_sunken
Gr3DRaised          → vbe_3d_raised
GrSunkenColors      → vbe_3d_sunken_colors
GrRaisedColors      → vbe_3d_raised_colors
GrText              → vbe_draw_text
GrTextWidth         → vbe_text_width
GrSetPixel          → vbe_set_pixel
GrGetPixel          → vbe_get_pixel
GrClip              → vbe_clip_rect
```

### Vulkan/GPU (8 new)
```
VkInit              → wubu_vulkan_init
VkShutdown          → wubu_vulkan_shutdown
VkCreateSwapchain   → wubu_vulkan_create_swapchain
VkAcquireNextImage  → wubu_vulkan_acquire_next_image
VkPresent           → wubu_vulkan_present
VkCreatePipeline    → wubu_vulkan_create_pipeline
VkCmdDispatch       → wubu_vulkan_cmd_dispatch
VkAllocDescriptor   → wubu_vulkan_alloc_descriptor
VkUpdateDescriptor  → wubu_vulkan_update_descriptor
```

### Audio Subsystem (8 new)
```
SndInit             → wubu_audio_init
SndShutdown         → wubu_audio_shutdown
SndPlay             → wubu_audio_play
SndStop             → wubu_audio_stop
SndSetVolume        → wubu_audio_set_volume
SndMix              → wubu_audio_mix
SndAllocBuffer      → wubu_audio_alloc_buffer
SndFreeBuffer       → wubu_audio_free_buffer
```

### Wayland/Hosted Display (4 new)
```
WlInit              → hosted_init
WlShutdown          → hosted_shutdown
WlSwapBuffers       → hosted_swap_buffers
WlPollEvents        → hosted_poll_events
```

### Proton/Wine Compatibility (7 new)
```
ProtonInit          → wubu_proton_init
ProtonShutdown      → wubu_proton_shutdown
ProtonExec          → wubu_proton_exec
ProtonIsReady       → wubu_proton_is_ready
ProtonValidatePE    → wubu_proton_validate_pe
ProtonMapSections   → wubu_proton_map_sections
ProtonTranslateAPI  → wubu_proton_translate_api
ProtonLoadDLL       → wubu_proton_load_dll
```

### Styx/9P Extensions (7 new)
```
StyxInit            → styx_init
StyxShutdown        → styx_shutdown
StyxMount           → styxfs_mount
StyxServe           → styxfs_serve
StyxWalk            → styx_walk
StyxOpen            → styx_open
StyxRead            → styx_read
StyxWrite           → styx_write
StyxClose           → styx_close
StyxStat            → styx_stat
```

## Usage Example

```c
// ZealOS-style code compiles unchanged with parity header
#include "zealos_parity.h"

U0 MyFunc(I64 a, I64 b) {
    CMemUsed *mem = CAlloc(1024);   // → mem_alloc(1024)
    TaskSleep(100);                  // → task_sleep(100)
    WubuCt *ct = CtCreate("test");   // → wubu_ct_create("test")
    GrFill(0, 0, 100, 100);          // → vbe_fill_rect(0, 0, 100, 100)
    SndPlay(buffer, len);            // → wubu_audio_play(buffer, len)
    Free(mem);                       // → mem_free(mem)
}
```

## Design Rules Maintained
- WuBuOS snake_case = primary implementation name
- `#define` = compile-time alias, zero overhead
- No struct name `#defines` (use typedef)
- No conflicts with system headers
- Primitive type `#defines` (U0/I64/F64/Bool) kept safe