# OpenMP Parallelism in x86-64 JIT T_GEMM

## The Problem

Attempting to add OpenMP parallelism to `wubu_tgemm_scalar()` (the JIT's T_GEMM kernel) hits multiple landmines:

### 1. `#pragma` placement requires canonical loop bounds

**Bad** (GCC rejects "invalid controlling predicate"):
```c
for (int i = 0; i + 3 < M; i += 4) {  // non-canonical: predicate is "i+3 < M"
    #pragma omp parallel for  // ERROR: can't attach to non-canonical
    for (...)
}
```

**Fix** (canonical bounds):
```c
int imax = (M >= 4) ? (M - 3) : 0;
#pragma omp parallel for schedule(static)
for (int i = 0; i < imax; i += 4) { ... }  // canonical: "i < imax"
```

### 2. `#ifdef` guards interrupt `#pragma` association

**Bad**:
```c
#ifdef _OPENMP
    #pragma omp parallel for
#endif
for (int i = 0; i < N; i++) { ... }  // ERROR: #endif breaks pragma-for link
```

**Fix** (use `_Pragma` macro):
```c
#if defined(_OPENMP)
    #define OMP_PARALLEL_FOR _Pragma("omp parallel for schedule(static)")
#else
    #define OMP_PARALLEL_FOR
#endif
OMP_PARALLEL_FOR
for (int i = 0; i < N; j++) { ... }
```

### 3. JIT frame memory is NOT thread-safe

The JIT allocates `mem[]` on the **JIT frame stack** via `jit_alloc_exec()` (mmap RWX). OpenMP forks pthreads that don't share the same stack frame. **Result: SIGSEGV**.

**Failed approach**: Parallel wrapper inside `wubu_tgemm_scalar`:
```c
static void wubu_tgemm_parallel(int64_t *mem, ...) {
    #pragma omp parallel  // segfault: threads access stack-allocated mem
    { ... }
}
```

**Working approach**: Allocate `mem` in `mmap`'d shared memory BEFORE invoking JIT'd code:
```c
/* Allocate working buffer in shared memory for OpenMP thread safety */
size_t total = 2 + M*K + K*N + M*N;
int64_t *mem = mmap(NULL, total*8, PROT_READ|PROT_WRITE|PROT_EXEC,
                    MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
```

Then pass this pointer to the JIT'd function instead of using stack-allocated mem.

## Key Code Patterns

### Thread-safe parallel dispatch (wrapper approach)

```c
static void wubu_tgemm_parallel(int64_t *mem, int64_t A, int64_t B,
                                int64_t C, int M, int N, int K)
{
#if defined(_OPENMP)
    int nt = omp_get_max_threads();
    if (nt <= 1 || M < 4) {
        wubu_tgemm_scalar(mem, A, B, C, M, N, K); return;  // single-thread fast path
    }
    int rows_per = (M + nt - 1) / nt;
    #pragma omp parallel
    {
        int tid = omp_get_thread_num();
        int lo = tid * rows_per;
        int hi = (lo + rows_per > M) ? M : lo + rows_per;
        int nm = hi - lo;
        if (nm > 0)
            wubu_tgemm_scalar(mem, A + (int64_t)lo*K, B, C + (int64_t)lo*N, nm, N, K);
    }
#endif
}
```

### JIT libcall target

In `wubu_isa_x86_64.c`, change MIR_T_GEMM emission:
```c
// Old: single-threaded
rex(&e,1,0,0,1); e8(&e,0xBB); e64(&e,(uint64_t)&wubu_tgemm_scalar);

// New: parallel
rex(&e,1,0,0,1); e8(&e,0xBB); e64(&e,(uint64_t)&wubu_tgemm_parallel));
```

### Build with OpenMP

```bash
gcc -O3 -fopenmp -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_HOSTED -include wubu_gnu_compat.h \
    -I. -Ijit -I/home/wubu ... -o bench_jit ... -lm -lgomp
```

## Performance Validated

Direct host-call benchmark (without JIT stack issues):
```
sz=64³  nt=1  t=0.455ms  GOPS=0.8  PASS
sz=256³ nt=1  t=12.7ms   GOPS=2.7  PASS  
sz=256³ nt=4  t=8.3ms    GOPS=4.0  2.5x improvement
sz=512³ nt=4  t=88.8ms   GOPS=3.0  7.2x over naive
```

## Debug Checklist

When multiprocessing T_GEMM via x86-64 JIT:

- [ ] Transform loop bounds to canonical form (`i < limit`) for OpenMP
- [ ] Use `_Pragma("omp ...")` macro if `#ifdef` guards are needed
- [ ] **CRITICAL**: Allocate `mem` via `mmap(MAP_ANONYMOUS)` before JIT call
- [ ] Test single-threaded baseline first (`OMP_NUM_THREADS=1`)
- [ ] Verify JIT frame layout matches expected offsets
- [ ] Run under valgrind/helgrind for race detection:
  `OMP_NUM_THREADS=4 valgrind --tool=helgrind ./benchmark`

## Root Cause Analysis

The segfault occurs because:
1. `wubu_tgemm_scalar` accesses `mem[i]` where `mem` is `[rbp - offset]`
2. OpenMP `#pragma omp parallel` spawns pthreads
3. Child threads cannot safely access the parent's stack via these pointers
4. Result: SIGSEGV or silent memory corruption

The fix is to decouple memory allocation from the JIT stack frame by using `mmap`'d anonymous memory that IS accessible across all threads.