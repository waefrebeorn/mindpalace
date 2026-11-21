# CPU GEMM Optimization on AMD Zen 4 (WuBuNOS `wubu_tgemm.c` / `wubu_tgemm_avx512.c`)

Captured 2026-08-28 while optimizing f32 GEMM for the WuBuNOS compiler repo on AMD Zen 4 (12-core, AVX-512DQ).

## Hardware reality (the non-negotiable baseline)

- **Zen 4 has ONE 512-bit FMA unit** (not 2 like Intel). Peak f32 = 16 × 2(FMA) × ~5GHz = **160 GFLOPS single-core**.
- Cache: L1d=32KB, L2=1MB, L3=32MB (per CCX). Cache line = 64 bytes.
- **Software prefetching DEGRADES Zen performance** (confirmed by rs-10345403 + our own testing).
- **Non-temporal stores cause catastrophic slowdown** on Zen.

## Micro-kernel config (MR × NR selection)

| Config | Registers used | Divides power-of-2? | Best for |
|--------|---------------|---------------------|----------|
| MR=8, NR=16 (AVX2) | 8+2+1=11 YMM | Yes (8) | AVX2 fallback |
| MR=8, NR=16 (AVX-512) | 8+1+1=10 ZMM | Yes (8) | Large matrices |
| **MR=6, NR=16 (AVX-512)** | 6+1+1=8 ZMM | **Yes (6 divides 64/128/256/510/1020)** | **Best overall** |
| MR=4, NR=16 (AVX-512) | 4+1+1=6 ZMM | Yes (4) | Small matrices |

**Why MR=6**: BLIS paper recommends MR=6 for AVX (avoids register pressure). On Zen 4 with 32 ZMM registers, MR=6 + NR=16 uses only 8 registers, leaving plenty of headroom. MR=6 divides all power-of-2 sizes evenly (no edge-case remainder loops).

**Why NR=16**: 16 floats = 1 full ZMM load. NR=16 = single `_mm512_loadu_ps` per B row. NR=32 would need 2 loads but reduce loop overhead — not worth it on Zen 4 (single FMA unit).

## K-unroll (the key optimization)

Unrolling the inner k-loop by 4 is the single biggest win on Zen 4:

```c
for (; k + 3 < kc; k += 4) {
    __m512 b0 = _mm512_loadu_ps(&B[(k+0)*N + j]);
    __m512 b1 = _mm512_loadu_ps(&B[(k+1)*N + j]);
    __m512 b2 = _mm512_loadu_ps(&B[(k+2)*N + j]);
    __m512 b3 = _mm512_loadu_ps(&B[(k+3)*N + j]);
    // FMA all 6 rows with each B row
}
```

**Why it works**: Zen 4 has a single 512-bit FMA unit with 4-cycle latency. K-unroll by 4 issues 4 independent FMAs per row, saturating the pipeline. Measured: **123 GFLOPS at 256×256** with k-unroll 4 vs **89 GFLOPS** without.

**K-unroll by 2**: smaller win (93 vs 89 GFLOPS). **K-unroll by 8**: register pressure (8 B rows + 6 C + 1 A = 15 ZMM, still OK but no additional benefit on single-FMA Zen).

## KC (K-cache blocking) tuning

KC controls how many B rows are loaded per k-iteration:

| KC | B panel size | Fits L2? | Best for |
|----|-------------|----------|----------|
| 64 | 64×N×4 | Yes | Small matrices (low overhead) |
| 128 | 128×N×4 | Barely (1MB at N=1024) | Large matrices (fewer C reloads) |
| 256 | 256×N×4 | No (2MB at N=1024) | Never (thrashing) |

**Benchmark variance warning**: On shared/cloud hosts, CPU frequency scaling and thermal throttling cause 20-30% variance between runs. Never trust a single benchmark number. Run best-of-3 and look for CONSISTENT improvements >10%.

**Isolated test showed KC=128 gives 40.8 GFLOPS at 1024×1024** (vs 14.7 for KC=64), but this didn't reproduce consistently in the benchmark harness. The interaction between KC, MC, and NC is complex and needs careful tuning per matrix size.

## Compiler flags (verified impact)

```makefile
CFLAGS = -O3 -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_HOSTE \
         -march=native -mavx2 -mfma -frename-registers -funroll-loops \
         -include wubu_gnu_compat.h -I. -I$(OS_ROOT)/jit -I$(OS_ROOT)/runtime -fopenmp
```

- **`-march=native`**: enables AVX-512DQ where available (critical for ZMM kernels)
- **`-frename-registers`**: eliminates register spilling in the inner kernel
- **`-funroll-loops`**: auto-unrolls the k-loop (but manual unroll is still better)
- **`-fopenmp`**: enables parallel GEMM

## OpenMP parallelization

- **Threshold**: `M*N*K >= 256000000` (avoids fork overhead on small matrices)
- **Parallelize at row-tile level**: `#pragma omp parallel for schedule(static)`
- **Thread distribution**: `mc = (M + nthreads - 1) / nthreads`, rounded to multiple of MR
- **Affinity**: `OMP_PROC_BIND=close OMP_PLACES=cores` essential for NUMA
- **12-thread scaling**: Only beneficial for large matrices (1024×1024+). For small matrices, thread overhead dominates.

## B-panel packing (BLIS-style)

Packing B into contiguous memory eliminates strided loads in the hot loop:

```c
float *bpack = aligned_alloc(64, KC * NC * sizeof(float));
for (int k = 0; k < kc; k++)
    memcpy(&bpack[k * nc], &B[k * N + j0], nc * sizeof(float));
// Then read from bpack[k*nc + j] instead of B[k*N + j]
```

**Result**: Helps for large matrices (reduces cache thrashing) but HURTS for small matrices (memcpy overhead dominates). NC must divide matrix size evenly or remainder loops kill performance.

## Performance scorecard (best observed, single-thread Zen 4)

| Size | GFLOPS | % of peak | Notes |
|------|--------|-----------|-------|
| 64×64 | 58.8 | 37% | Overhead-dominated |
| 128×18 | 103.6 | 65% | Sweet spot |
| 256×256 | 123.0 | 77% | Best observed |
| 512×512 | 87.1 | 54% | Memory-bound (B panel = 1MB) |
| 1024×1024 | 59.2 | 37% | Memory-bound (B = 4MB, C = 4MB) |

## The AVX-512 separate TU pattern

`wubu_tgemm_avx512.c` is compiled SEPARATELY with `-mavx512f -mavx512dq -mavx512vl`:

```makefile
wubu_tgemm_avx512.o: wubu_tgemm_avx512.c
    $(CC) $(CFLAGS) -mavx512f -mavx512dq -mavx512vl -c $< -o $@
```

Runtime dispatch in `wubu_tgemm_f32`:
```c
if (have_avx512()) {
    extern void wubu_tgemm_f32_avx512(...);
    wubu_tgemm_f32_avx512(A, B, C, M, N, K);
    return;
}
```

**Gotcha**: `#include <omp.h>` MUST be at file scope in the AVX-512 TU (not inside a function) for `omp_get_max_threads()` to be declared.

## Key research sources

- **rs-10345403** ("85.30 GFLOPS Single-Core FP32 Matrix Multiplication on Zen 3"): MR=6 optimal, no software prefetch, `-frename-registers -funroll-loops` critical
- **salykova.github.io/gemm-cpu**: BLIS cache blocking strategy, NC/MC/KC parameter selection
- **BLIS paper**: MR=6, NR=16 for AVX; KC=64 for L1d fit; on-the-fly B-packing

## Pitfalls

1. **MR=6 doesn't divide 512 or 1024 evenly** (512/6=85 r2, 1024/6=170 r4) — edge-case remainder loops for non-multiple sizes. MR=8 divides all power-of-2 sizes. Trade-off: MR=8 uses more registers but avoids edge cases.
2. **Benchmark variance** — never trust a single run. CPU frequency scaling on cloud hosts causes 20-30% swings.
3. **B-panel packing overhead** — memcpy cost dominates for small matrices. Only beneficial when B panel > L2 cache.
4. **OpenMP threshold too low** — fork overhead on small matrices can exceed computation. Gate on M*N*K >= 256M.
5. **`-march=native` on wrong TU** — must be on the GEMM TU, not just the main compiler.

## AVX-512 GEMM kernel bugs (2026-08-30)

Multiple correctness bugs found in `wubu_tgemm_f32_avx512`:

1. **K-unrolled loop missing rows 6-7**: The unrolled loop only had FMA
   instructions for rows 0-5. Fix: add rows 6-7 or remove unroll entirely.
2. **C accumulators loaded outside j-loop**: When nc > NR, must load C inside
   the j-loop for each column block.
3. **Missing c6/c7 stores**: After k-loop, all 8 row accumulators must be stored.
4. **A-panel packing overhead**: Adding A-panel packing caused severe degradation
   for small matrices due to gather overhead. Removed.

See `jit-codegen-x86-64-debug/references/avx512-gemm-kernel-bugs-2026-08-30.md`.
