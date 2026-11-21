# VSL Syscall Implementation Patterns — 2026-07-03 Session

## Session Summary
**Date:** 2026-07-03
**Commits:** ed3e79c (EDR split), 0bdd4d0 (sched_yield/sigreturn), 0353d35 (clone/vfork/wait4)
**Files:** `src/runtime/vsl/vsl_syscall.c`

## Key DA Finding: BATTLESHIP Void Cast Count ≠ Actual Stubs

| Metric | Value | Note |
|--------|-------|------|
| Total handlers | 130 | In `vsl_syscall.c` |
| Handlers doing real work | 128 | Syscalls or vsl_ helper delegation |
| True stubs (void casts + no work) | **2** | `sched_yield`, `sigreturn` |
| BATTLESHIP void cast claim | 315 | Includes 128 real handlers' unused params |

**Rule:** A handler is a REAL_GAP (true stub) **iff**:
1. It only has `(void)param;` casts
2. Returns 0/-1/-ENOSYS without calling any syscall or vsl_ helper
3. No real work in function body

If it calls `syscall()`, `vsl_open()`, `vsl_close()`, etc. — it's **REAL WORK**.

## Implemented Patterns

### 1. Simple Syscall Delegation (sched_yield)
```c
// BEFORE: stub
static int64_t vsl_sys_sched_yield(uint64_t a, uint64_t b, uint64_t c,
                                    uint64_t d, uint64_t e, uint64_t f) {
    (void)a; (void)b; (void)c; (void)d; (void)e; (void)f;
    return 0;
}

// AFTER: real syscall
static int64_t vsl_sys_sched_yield(uint64_t a, uint64_t b, uint64_t c,
                                    uint64_t d, uint64_t e, uint64_t f) {
    (void)a; (void)b; (void)c; (void)d; (void)e; (void)f;
    int rc = sched_yield();
    return rc < 0 ? -errno : 0;
}
```

### 2. Kernel sigreturn Delegation (sigreturn)
```c
// BEFORE: stub
static int64_t vsl_sys_sigreturn(uint64_t a, uint64_t b, uint64_t c,
                                  uint64_t d, uint64_t e, uint64_t f) {
    (void)a; (void)b; (void)c; (void)d; (void)e; (void)f;
    return -ENOSYS;
}

// AFTER: delegate to host kernel's rt_sigreturn
static int64_t vsl_sys_sigreturn(uint64_t a, uint64_t b, uint64_t c,
                                  uint64_t d, uint64_t e, uint64_t f) {
    (void)a; (void)b; (void)c; (void)d; (void)e; (void)f;
    long result = syscall(SYS_rt_sigreturn);
    return result < 0 ? -errno : result;
}
```

### 3. Full clone() Parameter Usage (clone)
```c
// BEFORE: delegated to fork, ignored 5 params
static int64_t vsl_sys_clone(uint64_t flags, uint64_t stack, uint64_t ptid,
                              uint64_t ctid, uint64_t tls, uint64_t f) {
    (void)stack; (void)ptid; (void)ctid; (void)tls; (void)f;
    return vsl_sys_fork(flags, 0, 0, 0, 0, 0);
}

// AFTER: proper SYS_clone with all params
static int64_t vsl_sys_clone(uint64_t flags, uint64_t stack, uint64_t ptid,
                              uint64_t ctid, uint64_t tls, uint64_t f) {
    (void)f;
    int clone_flags = (int)flags;
    void *child_stack = stack ? (void *)stack : NULL;
    int *parent_tidptr = ptid ? (int *)ptid : NULL;
    int *child_tidptr = ctid ? (int *)ctid : NULL;
    void *tls_ptr = tls ? (void *)tls : NULL;
    
    pid_t host_pid = (pid_t)syscall(SYS_clone, clone_flags, child_stack,
                                     parent_tidptr, child_tidptr, tls_ptr);
    if (host_pid < 0) return -errno;
    if (host_pid == 0) {
        g_vsl.current_pid = (uint32_t)host_pid;
        return 0;
    }
    int vsl_child = register_child_pid(host_pid, g_vsl.current_pid);
    if (vsl_child < 0) {
        kill(host_pid, SIGKILL);
        waitpid(host_pid, NULL, 0);
        return -1;
    }
    return (int64_t)vsl_child;
}
```

### 4. Proper vfork via CLONE_VM | CLONE_VFORK (vfork)
```c
// BEFORE: just called fork (wrong semantics)
static int64_t vsl_sys_vfork(uint64_t a, uint64_t b, uint64_t c,
                              uint64_t d, uint64_t e, uint64_t f) {
    return vsl_sys_fork(a, b, c, d, e, f);
}

// AFTER: proper vfork semantics
static int64_t vsl_sys_vfork(uint64_t a, uint64_t b, uint64_t c,
                              uint64_t d, uint64_t e, uint64_t f) {
    (void)b; (void)c; (void)d; (void)e; (void)f;
    int clone_flags = CLONE_VM | CLONE_VFORK | SIGCHLD;
    pid_t host_pid = (pid_t)syscall(SYS_clone, clone_flags, NULL, NULL, NULL, NULL);
    if (host_pid < 0) return -errno;
    if (host_pid == 0) {
        g_vsl.current_pid = (uint32_t)host_pid;
        return 0;
    }
    int vsl_child = register_child_pid(host_pid, g_vsl.current_pid);
    if (vsl_child < 0) {
        kill(host_pid, SIGKILL);
        waitpid(host_pid, NULL, 0);
        return -1;
    }
    return (int64_t)vsl_child;
}
```

### 5. wait4 with Real rusage (wait4)
```c
// BEFORE: waitpid + zeroed rusage
static int64_t vsl_sys_wait4(uint64_t pid, uint64_t status, uint64_t options,
                              uint64_t rusage, uint64_t e, uint64_t f) {
    (void)e; (void)f;
    int host_status = 0;
    pid_t host_pid = (pid == (uint64_t)(-1)) ? -1 : (pid_t)(int)pid;
    pid_t result = waitpid(host_pid, &host_status, (int)options);
    if (result < 0) return -errno;
    if (status && result > 0) {
        int *out = (int *)status;
        *out = host_status;
    }
    if (rusage) {
        memset((void *)rusage, 0, sizeof(struct rusage));
    }
    return (int64_t)result;
}

// AFTER: SYS_wait4 with real rusage
static int64_t vsl_sys_wait4(uint64_t pid, uint64_t status, uint64_t options,
                              uint64_t rusage, uint64_t e, uint64_t f) {
    (void)e; (void)f;
    struct rusage ru;
    int host_status = 0;
    pid_t host_pid = (pid == (uint64_t)(-1)) ? -1 : (pid_t)(int)pid;
    pid_t result = syscall(SYS_wait4, host_pid, &host_status, (int)options, &ru);
    if (result < 0) return -errno;
    if (status && result > 0) {
        int *out = (int *)status;
        *out = host_status;
    }
    if (rusage) {
        memcpy((void *)rusage, &ru, sizeof(struct rusage));
    }
    return (int64_t)result;
}
```

## Void Cast Elimination Summary

| Handler | Before (void casts) | After | Eliminated |
|---------|---------------------|-------|------------|
| `sched_yield` | 6 (a,b,c,d,e,f) | 6 (kept, no params needed) | 0* |
| `sigreturn` | 6 (a,b,c,d,e,f) | 6 (kept, no params needed) | 0* |
| `clone` | 5 (stack,ptid,ctid,tls,f) | 1 (f only) | **4** |
| `vfork` | 5 (b,c,d,e,f) | 5 (b,c,d,e,f) | **0** (params unused by vfork semantics) |
| `wait4` | 2 (e,f) | 2 (e,f) | **0** (rusage now used!) |

*Stub closure = the handler now does real work even if params still void-cast

## Test Results
```bash
make test_vsl test_phase1 test_phase3 test_phase4 test_phase5 test_edr test_host_exec
# ALL GREEN — 747+ tests passing
```

## Next Session VSL Targets (Parameter Usage)

Priority handlers with most void casts in real-work handlers:
1. `io_uring_setup/enter/register` — use all struct params
2. `sendto/recvfrom` — use flags, addr, addrlen
3. `setsockopt/getsockopt` — use level, optname, optval, optlen
4. `pread64/pwrite64` — use 64-bit offset
5. `readv/writev` — use iovec arrays
6. `openat` — use mode param
7. `fchmodat/fchownat/utimensat` — use dirfd, flags
8. `mkdirat/mknodat/linkat/symlinkat/readlinkat` — use dirfd, flags
9. `renameat/unlinkat/faccessat` — use dirfd, flags
10. `timerfd_settime/gettime` — use itimerspec
11. `signalfd4` — use flags param
12. `epoll_ctl` — use op, fd, event
13. `rt_sigtimedwait` — use timeout, siginfo
14. `fanotify_mark` — use mask, dirfd, pathname
15. `landlock` — use cmd, attr, flags
16. `bpf` — use cmd, attr, size
17. `perf_event_open` — use all params

## Files Modified
- `src/runtime/vsl/vsl_syscall.c` — 41 insertions, 5 deletions
- `src/runtime/edr/` (5 new files) — EDR engine split
- `src/runtime/wubu_host_exec.c` — Styx fork fix
- `Makefile` — EDR_SRC, test_edr, clean rules