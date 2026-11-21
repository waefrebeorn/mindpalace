# PTX Tensor Core MMA Implementation (2026-07-24)

## Overview
Implemented real PTX `ldmatrix.sync` + `mma.sync` pipeline in `src/compiler/holyc_ptx.c` for HolyC → GPU tensor core compilation. Closed REAL_GAP #28.

## The MMA Pipeline (m16n8k16, FP16, sm_80/Ampere)

### 1. Register Declarations
```c
ptx_emit(gen, "    .reg .b16 Ra0, Ra1, Ra2, Ra3;\n");   // A: 16×8 = 128 b16
ptx_emit(gen, "    .reg .b16 Rb0, Rb1;\n");             // B: 8×8 = 64 b16
ptx_emit(gen, "    .reg .f32 Rc0, Rc1, Rc2, Rc3;\n");   // C: FP32 accum
```

### 2. Shared Memory (128-byte aligned for ldmatrix.sync.aligned)
```c
ptx_emit(gen, "    .shared .align 128 .b8 smem_A[256];\n");  // 128 b16 = 256 bytes
ptx_emit(gen, "    .shared .align 128 .b8 smem_B[256];\n");
```

### 3. ldmatrix.sync Loads
```c
// A: 16×8 → 4 registers (each x1.m8n8 = 8×8)
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Ra0}, [A_addr];\n");
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Ra1}, [A_addr + 128];\n");
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Ra2}, [A_addr + 256];\n");
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Ra3}, [A_addr + 384];\n");

// B: 8×8 → 2 registers
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Rb0}, [B_addr];\n");
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Rb1}, [B_addr + 128];\n");
```

### 4. MMA Tensor Core Multiply-Accumulate
```c
ptx_emit(gen, "    mma.sync.aligned.m16n8k16.row.col.f16.f16.f16.f16\n");
ptx_emit(gen, "        {Rc0, Rc1, Rc2, Rc3},\n");
ptx_emit(gen, "        {Ra0, Ra1, Ra2, Ra3},\n");
ptx_emit(gen, "        {Rb0, Rb1},\n");
ptx_emit(gen, "        {Rc0, Rc1, Rc2, Rc3};\n");
```

### 5. Store Result
```c
ptx_emit(gen, "    st.global.v4.f32 [C_addr], {Rc0, Rc1, Rc2, Rc3};\n");
```

## Kernel Signature
```ptx
.visible .entry gpu_matmul(
    .param .b64 A_ptr,
    .param .b64 B_ptr,
    .param .b64 C_ptr,
    .param .u32 M,
    .param .u32 N,
    .param .u32 K
) { ... }
```

## Verification
```bash
cd /home/wubu/wubuos
make clean && make test  # All tiers pass, including compiler/holyc_test
```

## Related References
- `references/ptx-tensor-core-mma-2026-07-24.md` (in wubuos-battleship-gaps skill) — Full detail
- `references/vsl-vulkan-gpu-abstraction-2026-07-01.md` — Vulkan compute alternative
- `references/cudnn-cpu-fallback-patterns.md` — CPU GEMM via bear_simd.h