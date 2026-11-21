# Multi-threaded Gauntlet Runner (gauntlet_v3)

## Overview

`gauntlet_v3` is a parallel test runner that uses pthreads to execute up to 12 tests simultaneously. It provides ~9x speedup over `gauntlet_v2` (sequential fork+timeout).

## Build

```makefile
gauntlet_v3: test_gauntlet_v3.c $(FRONT) $(MIR) ... $(wildcard test_gauntlet/suites/*.c)
    $(CC) $(CFLAGS) -I. -Itest_gauntlet $^ $(LDFLAGS) -pthread -o $@
```

**Key:** Must include test suite `.c` files as explicit dependencies, otherwise they won't be linked.

## Usage

```sh
./gauntlet_v3 --jobs 12 --suite gcc_torture
./gauntlet_v3 --jobs 6  # fewer threads
```

## Worker Thread Model

Each worker thread maintains its own set of test indices and accumulates results:

```c
typedef struct {
    int thread_id;
    int start_idx, end_idx;
    thread_result_t result;  // pass/fail/error counts
    char fail_names[100][HD_MAX_IDENT_LEN];
    int n_fails;
} worker_arg_t;
```

## Test Execution Pattern

For each test, the worker:
1. Forks a child process
2. Child runs the test with 10s timeout
3. Parent polls with `waitpid(WNOHANG)` every 100ms
4. After 10s (100 iterations), kills child if still running
5. Records ERROR for timed-out tests
6. Merges results from all workers

## Memory Settings

```sh
MALLOC_MMAP_THRESHOLD_=128  # prevent arena OOM
```

## Thread Safety Notes

- Each thread fork's own child → no shared process table contention
- Results merged after all threads complete
- Test list is read-only during execution

## When to use

- For rapid iteration during development
- When you need to verify multiple suites quickly
- Not for production CI (gauntlet_v2 is more stable)

## When NOT to use

- Very memory-constrained environments (each thread needs memory)
- When you need deterministic test ordering
- Production CI runs (use gauntlet_v2 with --jobs 1)
- **Full gauntlet runs** — JIT global state is NOT thread-safe, causes double-free