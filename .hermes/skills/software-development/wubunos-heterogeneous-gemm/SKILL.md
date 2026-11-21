---
name: wubunos-heterogeneous-gemm
description: WuBuNOS GEMM kernel zoo for CPU and GPU tandem dispatch.
tags: [gemm, gpu, cuda, avx512, openmp, heterogeneous, wubunos]
---

# WuBuNOS Heterogeneous GEMM — Kernel Zoo & Tandem Dispatch

## Trigger
Use when working on T_GEMM performance, GPU kernels, CPU-GPU load balancing, or kernel dispatch in WuBuNOS.

## Architecture

Three-layer dispatch:
- **wubu_tandem_gemm()** — Auto load balancing for largest matrices (CPU+GPU simultaneous)
- **wubu_tgemm_parallel()** — CPU AVX-512 + OpenMP for small/medium
- **gpu_tgemm_smem()** — GPU shared-memory tiled for large

## Kernel Zoo

| Kernel | File | Strategy | Best For |
|--------|------|----------|----------|
| CPU AVX-512 | wubu_isa_x86_64.c | 8×4 micro-kernel, MC=NC=KC=64 | Small/medium |
| CPU OpenMP | wubu_isa_x86_64.c | Row-band parallelism | Medium |
| GPU naive | wubu_isa_ptx_tgemm.c | One thread per cell, global mem | Debugging |
| GPU smem | gpu_tgemm_smem.cu | 32×32 tile, shared memory | Large |
| Tandem | wubu_tandem_gemm.c | CPU+GPU simultaneous | 2048³+ |

## Cubin Caching

GPU kernels use content-hash cubin caching. Data-independent kernel ONE cubin for ALL sizes.

## Key Files

- wubu_isa_x86_64.c — CPU AVX-512 kernel
- wubu_isa_ptx_tgemm.c — Data-independent GPU kernel
- gpu_tgemm_smem.cu — Shared-memory tiled kernel (CUDA C)
- wubu_tandem_gemm.c — Heterogeneous dispatch

## Performance (Ryzen 7 7445HS + RTX 4050)

- 256³ CPU 0.02s vs GPU 0.6s → CPU
- 512³ CPU 0.10s vs GPU 0.6s → CPU
- 1024³ CPU 0.30s vs Tandem 0.84s → CPU
- 2048³+ Tandem wins (GPU compute dominates)
