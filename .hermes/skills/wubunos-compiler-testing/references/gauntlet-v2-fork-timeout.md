# Gauntlet v2: fork+timeout runner pattern

## Problem with batch forking

The original `gauntlet_runner` forks batch children (MAX_TESTS_PER_CHILD=100). Each batch child forks grandchildren for individual tests. Over thousands of forks, the parent's COW page tables accumulate → OOM at ~3.5GB RSS. `MALLOC_MMAP_THRESHOLD_=128` delays but does not prevent this.

## Solution: per-test fork with SIGKILL timeout

`test_gauntlet_v2.c` forks ONE child per test. Parent runs a non-blocking `waitpid` loop with `usleep(100000)` (100ms) for N iterations (default: 100 iterations = 10 seconds). If the child hasn't exited after timeout, `kill(pid, SIGKILL)` then `waitpid(pid, &status, 0)` to reap.

```c
pid_t pid = fork();
if (pid == 0) {
    /* Child: run test, exit with result */
    signal(SIGSEGV, SIG_DFL);
    signal(SIGABRT, SIG_DFL);
    int rc = run_single_test(source, expected);
    _exit(rc);
}

/* Parent: wait with timeout */
int waited = 0;
for (int t = 0; t < 100; t++) {
    pid_t w = waitpid(pid, &status, WNOHANG);
    if (w == pid) { waited = 1; break; }
    if (w == -1) break;
    usleep(100000);
}
if (!waited) {
    kill(pid, SIGKILL);
    waitpid(pid, &status, 0);
    /* mark as ERROR */
}
```

## Why alarm() doesn't work for JIT hangs

Using `alarm(5)` + `sigsetjmp`/`siglongjmp` to detect JIT hangs DOES NOT WORK. The signal is not delivered while the JIT runs a tight infinite loop in the same process. The fork+timeout approach works because `SIGKILL` is delivered by the kernel regardless of the child's execution state.

## mallopt(M_MMAP_THRESHOLD, 0)

The parent calls `mallopt(M_MMAP_THRESHOLD, 0)` at startup. This forces ALL allocations through `mmap` (not `sbrk`), so freed memory is returned to the OS immediately via `munmap`. Prevents the parent's RSS from growing across thousands of forks.

## Results

| Metric | Old runner (batch fork) | v2 (per-test fork, latest) |
|--------|------------------------|---------------------------|
| gcc_torture | 361P/140F/681E | 801P/142F/239E |
| extern_gcc | 263P/109F/1072E | 755P/106F/583E |
| c_testsuite | 95P/15F/93E | 165P/14F/24E |
| llvm | 52P/17F/234E | 201P/13F/89E |
| lacc | 35P/76F/126E | 142P/48F/47E |
| fujitsu | 178P/1475F/12290E (OOM at ~200 tests) | 10853P/272F/2818E |
| **TOTAL** | **985P/1832F/14516E (5.7%)** | **12917P/595F/3800E (74.6%)** |

## Build

```sh
cd /home/wubu/wubuos/src/compiler
make gauntlet_v2
```

## Usage

```sh
./gauntlet_v2 --suite gcc_torture
```

Output: JSON line at end: `{"pass":N,"fail":N,"error":N,"total":N}`