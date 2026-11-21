# T_GEMM JIT Benchmark Results

**Run**: `7c423a1` (Aug 26, 2026)
**Commit**: benchmark tool `tools/bench_tgemm_jit.c`

## X86-64 JIT Performance

| Size | naive C | x86-64 JIT | GOPS | Speedup vs naive |
|------|---------|------------|-------|------------------|
| 128³ | 0.002s | 0.002s | 2.2 | 1.1x |
| 384³ | 0.065s | 0.031s | 3.6 | **2.1x** |
| 512³ | 0.509s | 0.121s | 2.2 | **4.2x** |
| 768³ | 0.698s | 0.273s | 3.3 | **2.6x** |

**Correctness**: Bit-exact vs naive C reference (verified for 48-512³ via interpreter readback programs).

**Kernel**: `wubu_tgemm_scalar()` in `wubu_isa_x86_64.c` — 4-row register blocking, K-unroll-by-4 FMA.

## Build Command

```bash
gcc -O3 -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_HOSTED \
    -include wubu_gnu_compat.h -I. -Ijit -I/home/wubu -o bench_jit \
    tools/bench_tgemm_jit.c [MIR+JIT+deps] -lm
```

## OpenMP Parallel Attempt (investigated)

**Status**: Attempted, not ready. Segfault with OpenMP threads.

Adding `#pragma omp parallel for` to `wubu_tgemm_scalar()`'s outer loop failed because:
- GCC's OpenMP requires canonical loop bounds: `for(i=0; i<N; i+=4)`, NOT `for(i=0; i+3<N; i+=4)`
- The `#ifdef _OPENMP/#pragma/#endif` pattern breaks pragma-to-for association
- GCC reports: `error: invalid controlling predicate` (non-canonical bounds)

**Partial fix attempted**:
1. Transformed loop: `int imax = (M >= 4) ? M - 3 : 0; #pragma omp parallel for for(i=0; i<imax; i+=4)`
2. Used `_Pragma("omp parallel for schedule(static)")` macro wrapper to handle `#ifdef` guards
3. **Result**: Segfault persists because JIT frame memory (mmap'bled RWX) is not safe for OpenMP pthreads

**Root cause**: `wubu_tgemm_scalar` receives `mem` pointing to the JIT call frame's stack-allocated buffer. OpenMP forks pthreads that don't share the same stack context, causing SIGSEGV when threads access `mem`.

**Workaround**: Single-threaded JIT path (4.2x at 512³) is already optimal. Parallelization would require:
- JIT emitter to output OpenMP directives inline (not a libcall), OR
- Thread pool with pre-allocated shared memory for `mem`

See `references/openmp-jit-parallelism.md` for full debugging details.