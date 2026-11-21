# VSL Syscall Implementation Patterns — WuBuOS

## Overview
Patterns for implementing missing syscalls in `src/runtime/wubu_vsl.c`. The VSL (Virtualization Substrate Layer) provides a Linux ABI compatibility layer.

## Syscall Signature
All syscall handlers follow this pattern:
```c
static int64_t vsl_sys_<name>(uint64_t a, uint64_t b, uint64_t c,
                               uint64_t d, uint64_t e, uint64_t f) {
    (void)d; (void)e; (void)f;  // Unused params
    // Implementation using host syscalls
    return result < 0 ? -errno : (int64_t)result;
}
```

## Implemented Syscalls (Phase 17)

### select (23)
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

### pipe2 (293)
```c
static int64_t vsl_sys_pipe2(uint64_t pipefd, uint64_t flags, uint64_t c,
                              uint64_t d, uint64_t e, uint64_t f) {
    (void)c; (void)d; (void)e; (void)f;
    if (pipefd) {
        int *fds = (int *)pipefd;
        int host_fds[2];
        int rc = pipe2(host_fds, (int)flags);
        if (rc < 0) return -errno;
        fds[0] = host_fds[0]; fds[1] = host_fds[1];
    }
    return 0;
}
```

### clone3 (435) — ENOSYS fallback
```c
static int64_t vsl_sys_clone3(uint64_t cl_args, uint64_t size, uint64_t c,
                               uint64_t d, uint64_t e, uint64_t f) {
    (void)cl_args; (void)size; (void)c; (void)d;void)d; (void)e; (void)f;
    return -38;  // ENOSYS - clone_args struct not available in userspace
}
```

### *at Family (readlinkat 267, fchmodat 268, fchownat 260, utimensat 280, futimesat 261, renameat 264, mkdirat 258, symlinkat 266, linkat 265, mknodat 259)

```c
static int64_t vsl_sys_fchmodat(uint64_t dirfd, uint64_t pathname, uint64_t mode,
                                 uint64_t flags, uint64_t e, uint64_t f) {
    (void)e; (void)f;
    int result = fchmodat((int)dirfd, (const char *)pathname, (mode_t)mode, (int)flags);
    return result < 0 ? -errno : (int64_t)result;
}

static int64_t vsl_sys_utimensat(uint64_t dirfd, uint64_t pathname, uint64_t times,
                                  uint64_t flags, uint64_t e, uint64_t f) {
    (void)e; (void)f;
    const struct timespec *ts = times ? (const struct timespec *)times : NULL;
    int result = utimensat((int)dirfd, (const char *)pathname, ts, (int)flags);
    return result < 0 ? -errno : (int64_t)result;
}
```

### Deprecated Syscalls (futimesat 261, getwd 183)
Convert to modern equivalents:
```c
static int64_t vsl_sys_futimesat(uint64_t dirfd, uint64_t pathname, uint64_t times,
                                  uint64_t e, uint64_t f, uint64_t g) {
    (void)e; (void)f; (void)g;
    const struct timeval *tv = times ? (const struct timeval *)times : NULL;
    struct timespec ts[2];
    if (tv) {
        ts[0].tv_sec = tv[0].tv_sec; ts[0].tv_nsec = tv[0].tv_usec * 1000;
        ts[1].tv_sec = tv[1].tv_sec; ts[1].tv_nsec = tv[1].tv_usec * 1000;
    }
    int result = utimensat((int)dirfd, (const char *)pathname, tv ? ts : NULL, 0);
    return result < 0 ? -errno : (int64_t)result;
}

static int64_t vsl_sys_getwd(uint64_t buf, uint64_t size, uint64_t c,
                              uint64_t d, uint64_t e, uint64_t f) {
    (void)c; (void)d; (void)e; (void)f;
    char *result = getcwd((char *)buf, (size_t)size);
    return result ? (int64_t)buf : -errno;
}
```

### fchdir (81)
```c
static int64_t vsl_sys_fchdir(uint64_t fd, uint64_t b, uint64_t c,
                               uint64_t d, uint64_t e, uint64_t f) {
    (void)b; (void)c; (void)d; (void)e; (void)f;
    int result = fchdir((int)fd);
    return result < 0 ? -errno : (int64_t)result;
}
```

## statx Fix (332)
Populate statxbuf via fstatat fallback:
```c
static int64_t vsl_sys_statx(uint64_t dirfd, uint64_t pathname, uint64_t flags,
                              uint64_t mask, uint64_t statxbuf, uint64_t f) {
    (void)f;
    if (statxbuf) {
        struct stat st;
        int rc = fstatat((int)dirfd, (const char *)pathname, &st, (int)flags);
        if (rc < 0) return -errno;
        memset((void *)statxbuf, 0, sizeof(struct stat));
        memcpy((void *)statxbuf, &st, sizeof(struct stat));
    }
    return 0;
}
```

## Syscall Table Registration
Add to `vsl_syscall_table[]` with designated initializers:
```c
static const vsl_syscall_fn vsl_syscall_table[] = {
    [VSL_SYS_SELECT]       = vsl_sys_select,
    [VSL_SYS_PIPE2]        = vsl_sys_pipe2,
    [VSL_SYS_CLONE3]       = vsl_sys_clone3,
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
    // ... existing entries
};
```

## Alpha/Beta Pattern for Math Ops
For cuBLAS/cuDNN compatibility:
```c
float a_val = alpha ? *alpha : 1.0f;
float b_val = beta ? *beta : 0.0f;

if (b_val != 0.0f) {
    for (int i = 0; i < m * n; ++i) C[i] *= b_val;
} else {
    memset(C, 0, m * n * sizeof(float));
}
// ... compute ...
if (a_val != 1.0f) for (int i = 0; i < m * n; ++i) C[i] *= a_val;
```