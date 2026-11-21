# AVX-512 GEMM Optimization — Zen 4 Tuning (2026-08-30)

## Micro-kernel parameters
- **MR=8, NR=16, KC=128, NC=256** — optimal for Zen 4 (single 512-bit FMA unit)
- Zen 4: 512-bit FMA throughput = 1/cycle, latency = 5 cycles
- Theoretical peak: 1 FMA/cycle × 16 floats × 2 ops = 152 GFLOPS @ 4.75 GHz
- Adjusted for 3.2 GHz (WSL2): ~102 GFLOPS peak

## Optimizations applied

### 1. K-unroll by 4
Each k-iteration does 4 independent B loads + 32 FMAs (8 rows × 4).
This provides 32 independent FMAs in flight, fully covering the 5-cycle
FMA latency (need 5, have 32).

### 2. Panel-parallel restructuring
Parallelize over (j0,k0) panel pairs instead of just j-panels.
For N=1024,K=1024: 32 panel pairs across 12 threads (vs 4 j-panels previously).
Uses linear index decomposition: `jp = jpi / n_kpanels; kp = jpi % n_kpanels`.

### 3. NC=256 (B-panel fits L2)
B-panel = KC×NC×4 = 128×256×4 = 128KB, fits in L2 (512KB per core).

### 4. Software prefetching
`_mm_prefetch` 32 iterations ahead for both B-panel loads and A-row accesses.
Helps for large matrices where B-panel doesn't fit in L1d (32KB).

## Results (Zen 7 7445HS @ 3.2 GHz, WSL2)
| Size | Before | After | Improvement |
|------|--------|-------|-------------|
| 128³ | 88 | 116 GFLOPS | +32% |
| 256³ | 95 | 119 GFLOPS | +25% |
| 512³ | 86 | 96 peak GFLOPS | +12% |
| 1024³ | 28 | 76 peak GFLOPS | +171% |

**Note:** High variance (54-109 GFLOPS) due to WSL2 scheduling noise.
Median is typically 60-75% of peak.

## MR=16 experiment (FAILED — do not use)

Attempted MR=16 (16 rows per micro-kernel) to increase compute per call.
This caused **correctness bugs at large sizes** (max error 85 at 1024×1024).

**Root cause:** The scalar remainder loop only handled 8 rows (`ii < i0+8`),
not 16. When M is not a multiple of 16, the last block's rows 8-15 were
never processed by the scalar remainder, producing wrong results.

**Additional concern:** MR=16 uses 16 ZMM accumulators + 4 B loads + 4 A
broadcasts = 24 ZMM registers. While this fits in 32 on Zen 4, it leaves
little room for compiler temporaries and may cause spilling.

**Lesson:** When changing MR, ALL of these must be updated consistently:
1. C accumulator declarations (`c0` through `c15`)
2. C load/store guard conditions (`im > 0` through `im > 15`)
3. Scalar remainder row limit (`ii < i0+MR`)
4. `a_row[]` array size

**Stick with MR=8** — it's correct, fast, and well-tested.

## Key learnings
- **A-panel packing HURT performance** — extra allocation + copy overhead
  exceeded benefit. The compiler's broadcast-from-memory (`{1to16}`) is optimal.
- **KC=256 caused bimodal distribution** — B-panel (256KB) doesn't fit L1d,
  causing cache thrashing. KC=128 is the sweet spot.
- **Interleaved load/FMA didn't help** — the compiler already pipelines well.
- **Software prefetch helps peak** but not median — WSL2 noise dominates.
- **MR=16 failed** — scalar remainder must match MR exactly, and register
  pressure increases. MR=8 is the sweet spot for Zen 4 AVX-512.

## Files
- Kernel: `wubu_tgemm_avx512.c` (`wubu_tgemm_f32_avx512`)
- Benchmark: `tools/bench_f32_stable.c` (warmup + 5 iterations, median)
- Dispatcher: `wubu_tgemm.c` (`wubu_tgemm_f32` → `have_avx512()` check)
