---
name: wubuos-zealos-parity
category: systems-programming
description: ZealOS → WuBuOS 1:1 name parity mapping via zealos_parity.h
---

# WuBuOS ZealOS Name Parity

## Overview
`src/kernel/zealos_parity.h` maps ZealOS PascalCase function/type names to WuBuOS C11 snake_case. Reading ZealOS source alongside our C port requires zero mental translation.

## Design Rules
- WuBuOS snake_case is the PRIMARY implementation name
- `#define ZealOS_name → our_name` (compile-time alias, zero cost)
- Only `#define` things that don't conflict with existing typedefs
- For struct types, use typedef aliases, NOT #defines
- All new code uses snake_case internally

## Current Parity Status (Phase 1 Complete: 150+ Functions)
- **Primitive types**: 11/11 (U0/I8/I16/I32/I64/U8/U16/U32/U64/F64/Bool)
- **Memory subsystem**: 17/17 (CAlloc/MAlloc/Free/ReAlloc/HeapInit/etc.)
- **Tasking subsystem**: 21/21 (TaskInit/TaskDel/TaskRun/TaskKill/TaskYield/TaskSleep/TaskWake/etc.)
- **FAT32 filesystem**: 16/18 (stubs for rest in wubu_vsl.c)
- **VBE/Display**: 19/19 (GrFill/GrRect/GrCircle/GrGradient/GrText/GrClip/etc.)
- **Input**: 8/8
- **Interrupt**: 6/6
- **Styx/9P**: 14/14 (full 9P message types + server functions)
- **JIT/Compiler**: 26/26 (CJITCompile/HCGenInit/HCParseExpr/HCGenNode/etc.)
- **AHCI/SATA**: 11/11 (AHCIInit/AHCIDiskRead/AHCIIdentify/etc.)
- **TXFS**: 13/13 (TXFSInit/TXFSCreate/TXFSRead/TXFSWrite/etc.)
- **GAAD**: 9/9 (GAADInit/GAADOptimize/GAADSnapToGrid/GAADPhiScale/etc.)
- **Containers**: 15/15 (CtCreate/CtStart/CtWait/CtSteamOS/CtProton/CtHolyC/etc.)
- **Vulkan**: 8/8 (VkInit/VkCreateSwapchain/VkCmdDispatch/VkAllocDescriptor/etc.)
- **Audio**: 8/8 (SndInit/SndPlay/SndMix/SndAllocBuffer/etc.)
- **Wayland/Hosted**: 4/4 (WlInit/WlSwapBuffers/WlPollEvents)
- **Proton**: 7/7 (ProtonInit/ProtonExec/ProtonIsReady/ProtonTranslateAPI/etc.)
- **PTX/GPU**: 11/11 (hc_compile_ptx/hc_exec_ptx/hc_builtin_gpu_matmul/PTXGen init/emit/mma/etc.)
- **BearRL Training**: 8/8 (bear_policy_forward/backward, bear_value_forward/backward, bear_gae, bear_npole_step, etc.)
- **cuBLAS/cuDNN**: 12/12 (cublas_create/destroy/sgemm/saxpy/sdot/snrm2/sscal, cudnn_create/destroy/conv/activation/pooling/softmax/workspace)

**Total: ~180+ functions mapped** (Phase 1 complete)

## Usage Pattern
```c
// In ZealOS source: MAlloc(size)
// In WuBuOS: mem_alloc(size)
// With parity header: #define MAlloc(size) mem_alloc(size)

// Code using ZealOS names compiles unchanged:
void *ptr = MAlloc(1024);  // → mem_alloc(1024)
Free(ptr);                  // → mem_free(ptr)
```

## Struct Field Mapping
For structs, use comments in parity header:
```c
/* CHeapCtrl.heap_hash → WuBuHeapCtrl.hash_table */
/* CHeapCtrl.max_pages → WuBuHeapCtrl.max_pages */
/* CMemUsed.signature → WuBuMemUsed.magic */
/* CMemUsed.size → WuBuMemUsed.size */
/* CMemUsed.addr → WuBuMemUsed.addr */
/* CMemUsed.pid → WuBuMemUsed.pid */
```

## Adding New Parity
1. Implement snake_case function in WuBuOS
2. Add `#define PascalCase snake_case` to zealos_parity.h
3. Verify no conflicts with existing typedefs
4. Test that ZealOS-style code compiles

## Pitfalls
- Don't #define struct names (use typedef instead)
- Don't #define if it conflicts with system headers
- Keep primitive type #defines (U0/I64/etc.) — they're safe
- Document field mappings for structs in comments