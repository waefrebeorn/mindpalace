# Gauntlet fork-isolation fix (2026-08-18)

## Problem
`test_gauntlet_runner.c` used in-process `sigsetjmp`/`siglongjmp` to "recover" from a
crash during `hc_eval(source)` (the x86-64 JIT). This CANNOT work: a SIGSEGV inside JIT'd
code means the JIT allocator / mmap page is corrupted; `longjmp` out of the signal handler
leaves the process in an undefined state and it dies at the NEXT JIT call. Result: the whole
19,088-test run aborted at test #14 with a core dump — one bad test killed everything.

The file's own header comment promised `fork()` isolation ("fork() with shared memory for
result communication") but the implementation never did it.

## Fix pattern (replace the signal-handler + run_test_safe with this)

```c
#include <unistd.h>
#include <sys/wait.h>
#include <errno.h>

/* Real crash isolation: each test runs in a forked child. The child resets signal
 * disposition to default so a crash terminates it; the parent reads the result over a
 * pipe and WAITs, recording TEST_ERROR on any crash. One bad test can no longer abort
 * the run. */
static int run_test_safe(const char *source, int64_t expected,
                         test_result_t *result, int64_t *actual) {
    int pipefd[2];
    if (pipe(pipefd) != 0) { *result = TEST_ERROR; *actual = 0; return 0; }

    pid_t pid = fork();
    if (pid == 0) {
        signal(SIGSEGV, SIG_DFL);
        signal(SIGBUS,  SIG_DFL);
        signal(SIGILL,  SIG_DFL);
        signal(SIGFPE,  SIG_DFL);
        close(pipefd[0]);

        uint8_t buf[9];
        int64_t res = hc_eval(source);
        test_result_t r = (res == expected) ? TEST_PASS : TEST_FAIL;
        buf[0] = (uint8_t)r;
        memcpy(&buf[1], &res, sizeof(res));
        ssize_t w = write(pipefd[1], buf, sizeof(buf));
        (void)w;
        close(pipefd[1]);
        _exit(0);
    }

    /* parent */
    close(pipefd[1]);
    uint8_t buf[9];
    size_t total = 0;
    while (total < sizeof(buf)) {
        ssize_t got = read(pipefd[0], buf + total, sizeof(buf) - total);
        if (got <= 0) break;
        total += (size_t)got;
    }
    close(pipefd[0]);
    int status = 0;
    waitpid(pid, &status, 0);

    if (total == sizeof(buf)) {
        *result = (test_result_t)buf[0];
        memcpy(actual, &buf[1], sizeof(*actual));
        if (*result != TEST_PASS && *result != TEST_FAIL) *result = TEST_ERROR;
    } else {
        *result = TEST_ERROR;
        *actual = 0;
    }
    return 0;
}
```

Also REMOVE the now-unused `install_signal_handlers()` call from `main()` (and the
`sigjmp_buf`/`sigaction` block). With this, the gauntlet runs to completion and a crash
shows up as a `TEST_ERROR` row instead of aborting.

## Verified result
After the fix, full `./gauntlet_runner` no longer segfaults. Failures that surface are
REAL HolyC→x86-64 JIT correctness bugs (wrong results on lacc/fujitsu/extern_gcc sources),
which is exactly the backlog to burn down.
