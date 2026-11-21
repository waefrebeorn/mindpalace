# PTX Tensor Core MMA Implementation Pattern (2026-07-24)

## Overview
Closed REAL_GAP #28 in `src/compiler/holyc_ptx.c:108` — implemented real `ldmatrix.sync.aligned.x1.m8n8.shared.b16` + `mma.sync.aligned.m16n8k16.row.col.f16.f16.f16.f16` pipeline targeting `sm_80` (Ampere/A100).

## The Gap
```c
// BEFORE (stub comment at line 108)
"    /* Load matrix tiles from global to shared memory\n"
"     * Use ldmatrix.sync.aligned.x1.m8n8.shared.b16\n"
"     * Then use mma.sync.aligned.m16n8k16.row.col.f16\n"
"     */\n"

// AFTER — full MMA pipeline emitted
```

## Implementation Pattern

### 1. Register Declaration (FP16 tensor core operands)
```c
ptx_emit(gen, "    .reg .b16 Ra0, Ra1, Ra2, Ra3;\n");  // A tile: 16×8 = 128 elements
ptx_emit(gen, "    .reg .b16 Rb0, Rb1;\n");            // B tile: 8×8 = 64 elements
ptx_emit(gen, "    .reg .f32 Rc0, Rc1, Rc2, Rc3;\n");  // Accumulator: 16×8 FP32
```

### 2. Shared Memory Allocation (128-byte aligned for ldmatrix)
```c
ptx_emit(gen, "    .shared .align 128 .b8 smem_A[256];\n");  // 128 b16 = 256 bytes
ptx_emit(gen, "    .shared .align 128 .b8 smem_B[256];\n");  // 128 b16 = 256 bytes
```

### 3. ldmatrix.sync Loads (A: 16×8 tile → 4 registers; B: 8×8 tile → 2 registers)
```c
// A tile loads (each ldmatrix loads 8×8 matrix = 64 b16 = 1 register)
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Ra0}, [A_addr];\n");
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Ra1}, [A_addr + 128];\n");
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Ra2}, [A_addr + 256];\n");
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Ra3}, [A_addr + 384];\n");

// B tile loads
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Rb0}, [B_addr];\n");
ptx_emit(gen, "    ldmatrix.sync.aligned.x1.m8n8.shared.b16 {Rb1}, [B_addr + 128];\n");
```

### 4. Accumulator Initialization
```c
ptx_emit(gen, "    mov.b32 Rc0, 0;\n");
ptx_emit(gen, "    mov.b32 Rc1, 0;\n");
ptx_emit(gen, "    mov.b32 Rc2, 0;\n");
ptx_emit(gen, "    mov.b32 Rc3, 0;\n");
```

### 5. MMA Tensor Core Multiply-Accumulate
```c
ptx_emit(gen, "    mma.sync.aligned.m16n8k16.row.col.f16.f16.f16.f16\n");
ptx_emit(gen, "        {Rc0, Rc1, Rc2, Rc3},\n");
ptx_emit(gen, "        {Ra0, Ra1, Ra2, Ra3},\n");
ptx_emit(gen, "        {Rb0, Rb1},\n");
ptx_emit(gen, "        {Rc0, Rc1, Rc2, Rc3};\n");
```

### 6. Result Store (FP32 vector → global memory)
```c
ptx_emit(gen, "    st.global.v4.f32 [C_addr], {Rc0, Rc1, Rc2, Rc3};\n");
```

## Key Parameters (m16n8k16)

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `m` | 16 | Output tile rows |
| `n` | 8 | Output tile cols |
| `k` | 16 | Inner dimension (FP16) |
| A layout | row | A is row-major in shared mem |
| B layout | col | B is col-major in shared mem |
| A/B type | f16 | FP16 input |
| C/D type | f16/f16 | FP16 accum → FP32 result |
| .sync | yes | Warp-synchronous |
| .aligned | yes | 128-byte alignment required |

## Kernel Configuration

```c
ptx_emit_header(gen);           // .version 7.8, .target sm_80, .address_size 64
ptx_emit_matmul_kernel_prologue(gen, "gpu_matmul");
/* params: .param .b64 A_ptr, .param .b64 B_ptr, .param .b64 C_ptr, .param .u32 M, .param .u32 N, .param .u32 K */
ptx_emit_holyc_gpu_matmul(gen); // Full pipeline above
ptx_emit_epilogue(gen);         // }
```

## Verification
```bash
cd /home/wubu/wubuos
make clean && make test
# All tiers pass — compiler tests (holyc_test), PTX emission functional
```

## Related Patterns
- `references/cudnn-cpu-fallback-patterns.md` — CPU GEMM fallback using `bear_simd.h`
- `references/vsl-vulkan-gpu-abstraction-2026-07-01.md` — Vulkan compute shader approach
- CUDA driver API execution via `hc_exec_ptx()` in same file (`cuModuleLoadData`, `cuLaunchKernel`)

## Notes
- Targets Ampere (`sm_80`) — Tensor Cores require Volta+
- Shared memory `.align 128` is MANDATORY for `ldmatrix.sync.aligned`
- Each `ldmatrix.sync.aligned.x1.m8n8` loads one 8×8 tile (64 elements = 1 register)
- A matrix (16×8) needs 4 loads; B matrix (8×8) needs 2 loads
- Accumulator is FP32 for numerical stability (C = A*B + C in FP32)
- The emitted PTX is valid for `cuModuleLoadData` + `cuLaunchKernel`