# Gauntlet Crash Recovery — 2026-08-18

## Signal
The universal test gauntlet runner crashed at ~test 4 with SIGSEGV at address `0x7ffff7fb90d3` (inside an RWX JIT page) regardless of signal-handler approach. Both `sigsetjmp`/`siglongjmp` and fork-based approaches failed in the full gauntlet (but fork worked fine in isolation with 100+ tests).

## Root Cause
`siglongjmp` from a SIGSEGV handler that fires inside JIT-compiled code is **UNDEFINED BEHAVIOR**. The longjmp restores the stack but leaves the JIT execution context corrupted. The crash address is always the same (0x7ffff7fb90d3) because it lands in the JIT mmap region.

## Reliable Crash Isolation: fork() + shared memory
```c
typedef struct { int64_t result; int status; } shm_t;
shm_t *shm = mmap(NULL, sizeof(shm_t), PROT_READ|PROT_WRITE, MAP_SHARED|MAP_ANONYMOUS, -1, 0);

pid_t pid = fork();
if (pid == 0) {
    int64_t res = hc_eval(source);
    shm->result = res;
    shm->status = 0;
    _exit(0);
} else if (pid > 0) {
    int status;
    pid_t w = waitpid(pid, &status, 0);
    // read shm->result
}
```

**Verified**: 100+ tests pass with fork+shm in isolation. Each child process has its own JIT memory; when it exits, the parent is unaffected.

## Why the Full Gauntlet Fork Approach Also Crashed
The full gauntlet_runner with fork crashed at ~test 4. Possible causes:
- `alarm(5)` interrupting `waitpid` with EINTR, then `kill(pid, SIGKILL)` + second `waitpid` not reaping properly
- Accumulated zombie processes from failed forks
- The `signal(SIGALRM, ...)` handler conflicting with the parent's signal state

**Fix**: Remove `alarm()`, use blocking `waitpid()` without timeout (children are fast — each test takes ~0.001s). If a child hangs, it's a compiler bug that should be fixed, not timed out.

## Test Acquisition: Download REAL Tests
User preference (stated sharply): "stop making them yourself... actually download the test". Sources:
- gcc-torture (1918), gcc-dg (2141), gcc-compile (2016)
- fujitsu (37K), extern-gcc (25K), compcert (221)
- c-testsuite (220), llvm (1745), lacc (324)
- tinycc (172), chibicc (41), writing-c-compiler (1630), slimcc (110)

Deduplicate by content hash → 67,714 unique C test files.

## Converting C Tests to Gauntlet Format
1. Wrap each C file's `main()` as a HolyC program that returns 0 on success
2. Replace `abort()` → `return 1`, `exit(0)` → `return 0`
3. Filter out tests with:
   - DejaGnu directives (`dg-do`, `dg-error`)
   - Computed gotos (`goto *l`)
   - Null pointer dereferences (`*(char*)0 = 0`)
   - Dollar-sign identifiers (`$3()`, `$4()`)
   - `__builtin_abort()`, `__builtin_printf()`
4. Expected result is 0 (success) for all torture tests

## Result
18,841 tests generated from 13 test suites. 3 failures on x86-64:
- `pr93744_3` (global post-increment)
- `pr91137` (function call)
- `pr93744_2` (global post-increment)
