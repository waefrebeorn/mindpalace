# VSL Syscall Implementation Patterns (src/runtime/wubu_vsl.c)

This document captures the patterns for implementing missing syscalls in the WuBuOS Virtualization Substrate Layer (VSL). The VSL provides Linux ABI compatibility by translating Linux syscalls to host kernel calls.

## Overview

The VSL syscall table (`vsl_syscall_table`) maps Linux syscall numbers to handler functions. Missing syscalls were previously stubbed with `vsl_sys_nosys` returning `-ENOSYS`. Each new implementation follows the pattern of host delegation with proper error handling.

## Pattern: Host Syscall Delegation

### Basic Template

```c
static int64_t vsl_sys_<name>(uint64_t arg1, uint64_t arg2, uint64_t arg3,
                              uint64_t arg4, uint64_t arg5, uint64_t arg6) {
    (void)arg4; (void)arg5; (void)arg6;  // Unused args per convention
    
    // Extract and validate arguments
    int host_arg1 = (int)arg1;
    // ...
    
    // Delegate to host syscall
    long result = syscall(SYS_<name>, host_arg1, host_arg2, ...);
    
    // Return negative errno on failure
    return result < 0 ? -errno : (int64_t)result;
}
```

### Example: `select` (fully implemented)

```c
static int64_t vsl_sys_select(uint64_t nfds, uint64_t readfds, uint64_t writefds,
                               uint64_t exceptfds, uint64_t timeout, uint64_t f) {
    (void)f;
    fd_set *rfds = readfds ? (fd_set *)readfds : NULL;
    fd_set *wfds = writefds ? (fd_set *)writefds : NULL;
    fd_set *efds = exceptfds ? (fd_set *)exceptfds : NULL;
    struct timeval *tv = timeout ? (struct timeval *)timeout : NULL;
    int result = select((int)nfds, rfds, wfds, efds, tv);
    return result < 0 ? -errno : (int64_t)result;
}
```

### Example: `pipe2` (with flags)

```c
static int64_t vsl_sys_pipe2(uint64_t pipefd, uint64_t flags, uint64_t c,
                              uint64_t d, uint64_t e, uint64_t f) {
    (void)c; (void)d; (void)e; (void)f;
    if (pipefd) {
        int *fds = (int *)pipefd;
        int host_fds[2];
        int rc = pipe2(host_fds, (int)flags);
        if (rc < 0) return -errno;
        fds[0] = host_fds[0];
        fds[1] = host_fds[1];
    }
    return 0;
}
```

### Example: `clone3` (struct delegation)

```c
static int64_t vsl_sys_clone3(uint64_t cl_args, uint64_t size, uint64_t c,
                              uint64_t d, uint64_t e, uint64_t f) {
    /* clone3 uses struct clone_args passed via cl_args */
    int result = (int)syscall(SYS_clone3, (void *)cl_args, (size_t)size);
    return result < 0 ? -errno : (int64_t)result;
}
```

### Example: io_uring family (3 syscalls)

```c
static int64_t vsl_sys_io_uring_setup(uint64_t entries, uint64_t params,
                                      uint64_t c, uint64_t d, uint64_t e, uint64_t f) {
    (void)c; (void)d; (void)e; (void)f;
    long result = syscall(SYS_io_uring_setup, (unsigned int)entries, (void *)params);
    return result < 0 ? -errno : (int64_t)result;
}

static int64_t vsl_sys_io_uring_enter(uint64_t fd, uint64_t to_submit,
                                       uint64_t min_complete, uint64_t flags,
                                       uint64_t arg, uint64_t sz) {
    (void)arg; (void)sz;
    long result = syscall(SYS_io_uring_enter, (int)fd, (unsigned int)to_submit,
                          (unsigned int)min_complete, (unsigned int)flags,
                          (void *)arg, (size_t)sz);
    return result < 0 ? -errno : (int64_t)result;
}
```

## Pattern: Alias Syscalls (rt_* variants)

Linux has both legacy and `rt_` (real-time) variants of signal syscalls. The modern `rt_` variants should delegate to the same implementation:

```c
static int64_t vsl_sys_rt_sigaction(uint64_t signum, uint64_t act, uint64_t oldact,
                                     uint64_t d, uint64_t e, uint64_t f) {
    return vsl_sys_sigaction(signum, act, oldact, d, e, f);
}

static int64_t vsl_sys_rt_sigprocmask(uint64_t how, uint64_t set, uint64_t oldset,
                                       uint64_t d, uint64_t e, uint64_t f) {
    return vsl_sys_sigprocmask(how, set, oldset, d, e, f);
}
```

**Critical:** Match the exact function signature — 6 `uint64_t` parameters for the syscall convention.

## Pattern: *at Syscalls (Directory FD variants)

The `*at` family takes a directory file descriptor as first argument:

```c
static int64_t vsl_sys_openat(uint64_t dirfd, uint64_t pathname, uint64_t flags,
                               uint64_t mode, uint64_t e, uint64_t f) {
    (void)e; (void)f;
    return vsl_openat((int)dirfd, (const char *)pathname, (int)flags, (mode_t)mode);
}
```

## Pattern: Deprecated Syscall Fallbacks

Some syscalls are deprecated in Linux (e.g., `futimesat`, `getwd`). Fall back to modern equivalents:

```c
static int64_t vsl_sys_futimesat(uint64_t dirfd, uint64_t pathname, uint64_t times,
                                  uint64_t e, uint64_t f, uint64_t g) {
    (void)e; (void)f; (void)g;
    const struct timeval *tv = times ? (const struct timeval *)times : NULL;
    struct timespec ts[2];
    if (tv) {
        ts[0].tv_sec = tv[0].tv_sec;
        ts[0].tv_nsec = tv[0].tv_usec * 1000;
        ts[1].tv_sec = tv[1].tv_sec;
        ts[1].tv_nsec = tv[1].tv_usec * 1000;
    }
    int result = utimensat((int)dirfd, (const char *)pathname, tv ? ts : NULL, 0);
    return result < 0 ? -errno : (int64_t)result;
}
```

## Syscall Table Registration

After implementing the handler, register it in `vsl_syscall_table`:

```c
static const vsl_syscall_fn vsl_syscall_table[] = {
    // ... existing entries ...
    [VSL_SYS_SELECT]       = vsl_sys_select,
    [VSL_SYS_PIPE2]        = vsl_sys_pipe2,
    [VSL_SYS_CLONE3]       = vsl_sys_clone3,
    [VSL_SYS_IO_URING_SETUP]    = vsl_sys_io_uring_setup,
    [VSL_SYS_IO_URING_ENTER]    = vsl_sys_io_uring_enter,
    [VSL_SYS_IO_URING_REGISTER] = vsl_sys_io_uring_register,
    [VSL_SYS_READLINKAT]   = vsl_sys_readlinkat,
    [VSL_SYS_FCHMODAT]     = vsl_sys_fchmodat,
    [VSL_SYS_FCHOWNAT]     = vsl_sys_fchownat,
    [VSL_SYS_UTIMENSAT]    = vsl_sys_utimensat,
    [VSL_SYS_FUTIMESAT]    = vsl_sys_futimesat,
    [VSL_SYS_RENAMEAT]     = vsl_sys_renameat,
    [VSL_SYS_MKDIRAT]      = vsl_sys_mkdirat,
    [VSL_SYS_SYMLINKAT]    = vsl_sys_symlinkat,
    [VSL_SYS_LINKAT]       = vsl_sys_linkat,
    [VSL_SYS_MKNODAT]      = vsl_sys_mknodat,
    [VSL_SYS_GETWD]        = vsl_sys_getwd,
    [VSL_SYS_FCHDIR]       = vsl_sys_fchdir,
    [VSL_SYS_RT_SIGACTION] = vsl_sys_rt_sigaction,
    [VSL_SYS_RT_SIGPROCMASK]= vsl_sys_rt_sigprocmask,
    // ...
};
```

## Key Principles

1. **Host delegation** — Use `syscall(SYS_<name>, ...)` to delegate to host kernel
2. **Error handling** — Return `-errno` on failure, positive value on success
3. **Argument extraction** — Cast `uint64_t` to appropriate types (`int`, `void*`, etc.)
4. **Unused args** — Mark with `(void)argN;` to silence warnings
5. **Fallback for deprecated** — Map deprecated syscalls to modern equivalents
6. **Alias for rt_ variants** — Delegate `rt_sigaction` → `sigaction`, etc.
7. **Table registration** — Add entry at correct index matching `VSL_SYS_*` constant
8. **Test immediately** — Run `make test_vsl` after each addition

## Results (2026-06-29 Session)

Added 17 syscalls + 2 aliases, reducing VSL void casts from 347 → 315:

| Syscall | Type | Delegation |
|---------|------|------------|
| `select` | Basic | `select()` |
| `pipe2` | With flags | `pipe2()` |
| `clone3` | Struct args | `SYS_clone3` |
| `io_uring_setup/enter/register` | 3 syscalls | `SYS_io_uring_*` |
| `readlinkat` | *at variant | `readlinkat()` |
| `fchmodat` | *at variant | `fchmodat()` |
| `fchownat` | *at variant | `fchownat()` |
| `utimensat` | *at variant | `utimensat()` |
| `futimesat` | Deprecated → `utimensat` | Fallback |
| `renameat` | *at variant | `renameat()` |
| `mkdirat` | *at variant | `mkdirat()` |
| `symlinkat` | *at variant | `symlinkat()` |
| `linkat` | *at variant | `linkat()` |
| `mknodat` | *at variant | `mknodat()` |
| `getwd` | Deprecated → `getcwd` | Fallback |
| `fchdir` | Basic | `fchdir()` |
| `rt_sigaction` | Alias | → `sigaction` |
| `rt_sigprocmask` | Alias | → `sigprocmask` |

**Net:** 32 void casts eliminated from success paths.