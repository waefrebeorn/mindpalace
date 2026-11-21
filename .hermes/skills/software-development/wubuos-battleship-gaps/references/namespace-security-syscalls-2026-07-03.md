# Namespace & Security Syscalls Implementation — 2026-07-03 Session

## Session Summary
**Date:** 2026-07-03
**Gap Closed:** Critical Tier #1 — `runtime/wubu_vsl.c` remaining namespace/security syscalls (landlock, bpf, perf_event_open, fanotify_init, fanotify_mark, unshare, setns)
**BATTLESHIP.md Status:** 1562 REAL_GAPs → reduced by 7 syscall implementations

## Files Modified
- `src/runtime/vsl/vsl_syscall.c` — 7 new syscall handlers + signature fixes
- `src/runtime/wubu_vsl.h` — removed duplicate syscall numbers, cleaned conflicts
- `src/runtime/wubu_vsl_test.c` — +7 tests for new syscalls

## Implemented Syscalls

### 1. landlock (syscall 444) — Linux 5.13+
```c
static int64_t vsl_sys_landlock(uint64_t cmd, uint64_t attr, uint64_t flags,
                                 uint64_t c, uint64_t d, uint64_t e) {
    (void)c; (void)d; (void)e;
    int result = syscall(444, (int)cmd, (void *)attr, (size_t)flags);
    return result < 0 ? -errno : (int64_t)result;
}
```
- **Params used:** cmd, attr, flags (3/6)
- **Test:** Returns EFAULT/ENOSYS/EOPNOTSUPP with NULL params on unsupported kernels
- **Fix:** Changed from 7 params to 6 to match vsl_syscall_fn typedef (eliminated 1 void cast)

### 2. bpf (syscall 321)
```c
static int64_t vsl_sys_bpf(uint64_t cmd, uint64_t attr, uint64_t size,
                            uint64_t c, uint64_t d, uint64_t e) {
    (void)c; (void)d; (void)e;
    int result = syscall(321, (int)cmd, (void *)attr, (size_t)size);
    return result < 0 ? -errno : (int64_t)result;
}
```
- **Params used:** cmd, attr, size (3/6)
- **Test:** Returns EINVAL/ENOSYS with NULL params
- **Fix:** Changed from 7 params to 6 to match vsl_syscall_fn typedef (eliminated 1 void cast)

### 3. perf_event_open (SYS_perf_event_open)
```c
static int64_t vsl_sys_perf_event_open(uint64_t attr, uint64_t pid, uint64_t cpu,
                                        uint64_t group_fd, uint64_t flags, uint64_t f) {
    (void)f;
    struct perf_event_attr *pe = (struct perf_event_attr *)attr;
    int result = syscall(SYS_perf_event_open, pe, (pid_t)pid, (int)cpu,
                         (int)group_fd, (unsigned long)flags);
    return result < 0 ? -errno : (int64_t)result;
}
```
- **Params used:** attr, pid, cpu, group_fd, flags (5/6)

### 4. fanotify_init (SYS_fanotify_init)
```c
static int64_t vsl_sys_fanotify_init(uint64_t flags, uint64_t event_f_flags,
                                      uint64_t c, uint64_t d, uint64_t e, uint64_t f) {
    (void)c; (void)d; (void)e; (void)f;
    int result = syscall(SYS_fanotify_init, (unsigned int)flags, (unsigned int)event_f_flags);
    return result < 0 ? -errno : (int64_t)result;
}
```
- **Params used:** flags, event_f_flags (2/6)
- **Test:** Returns EPERM (needs CAP_SYS_ADMIN) or ENOSYS

### 5. fanotify_mark (SYS_fanotify_mark)
```c
static int64_t vsl_sys_fanotify_mark(uint64_t fanotify_fd, uint64_t flags, uint64_t mask,
                                      uint64_t dirfd, uint64_t pathname, uint64_t f) {
    (void)f;
    int result = syscall(SYS_fanotify_mark, (int)fanotify_fd, (unsigned int)flags,
                         (uint64_t)mask, (int)dirfd, (const char *)pathname);
    return result < 0 ? -errno : (int64_t)result;
}
```
- **Params used:** fanotify_fd, flags, mask, dirfd, pathname (5/6)

### 6. unshare (SYS_unshare)
```c
static int64_t vsl_sys_unshare(uint64_t flags, uint64_t b, uint64_t c,
                                uint64_t d, uint64_t e, uint64_t f) {
    (void)b; (void)c; (void)d; (void)e; (void)f;
    int result = unshare((int)flags);
    return result < 0 ? -errno : (int64_t)result;
}
```
- **Params used:** flags (1/6)
- **Test:** Returns 0 (success with zero flags) or EINVAL

### 7. setns (SYS_setns)
```c
static int64_t vsl_sys_setns(uint64_t fd, uint64_t nstype, uint64_t c,
                              uint64_t d, uint64_t e, uint64_t f) {
    (void)c; (void)d; (void)e; (void)f;
    int result = setns((int)fd, (int)nstype);
    return result < 0 ? -errno : (int64_t)result;
}
```
- **Params used:** fd, nstype (2/6)
- **Test:** Returns EBADF/ENOSYS with invalid fd

## Header Cleanup (wubu_vsl.h)
Removed duplicate/conflicting syscall number definitions:
- `VSL_SYS_SIGNALFD` (308) — removed, conflicts with `VSL_SYS_SETNS` (308), legacy signalfd replaced by signalfd4 (282)
- `VSL_SYS_FSTATAT` (262) — removed, alias for `VSL_SYS_NEWFSTATAT` (262)
- `VSL_SYS_UNLINKAT` (263) — removed, duplicate of line 106
- `VSL_SYS_GETCWD` (79), `VSL_SYS_CHDIR` (80), `VSL_SYS_FCHDIR` (81) — removed, duplicates of earlier lines

## Syscall Table Updates (vsl_syscall.c)
Removed duplicate entries matching header cleanup:
- Removed `[VSL_SYS_SIGNALFD]` entry (conflict with SETNS)
- Removed `[VSL_SYS_FSTATAT]` entry (alias for NEFSTATAT)

## Test Results
```bash
make test_vsl
# === Results: 62/62 passed === (was 55/55, +7 new tests)

[Namespace & Security Syscalls]
  ✅ landlock() returns EFAULT/ENOSYS/EOPNOTSUPP/EINVAL with NULL params
  ✅ bpf() returns EINVAL/ENOSYS/EFAULT with NULL params
  ✅ perf_event_open() returns EFAULT/ENOSYS/EINVAL with NULL params
  ✅ fanotify_init() returns EPERM/ENOSYS/EINVAL with zero flags
  ✅ fanotify_mark() returns EINVAL/ENOSYS/EBADF with invalid fd
  ✅ unshare() returns 0/EINVAL/ENOSYS with zero flags
  ✅ setns() returns EBADF/ENOSYS with invalid fd
```

## Full Suite Verification
```bash
make test
# ✅ All tests passed (all tiers)
```

## Void Cast Elimination Summary

| Handler | Before (void casts) | After (void casts) | Eliminated | Notes |
|---------|---------------------|-------------------|------------|-------|
| `landlock` | 4 (c,d,e,f) | 3 (c,d,e) | **1** | Sig 7→6 params to match typedef |
| `bpf` | 4 (c,d,e,f) | 3 (c,d,e) | **1** | Sig 7→6 params to match typedef |
| `perf_event_open` | 1 (f) | 1 (f) | 0 | 5/6 params used |
| `fanotify_init` | 4 (c,d,e,f) | 4 (c,d,e,f) | 0 | 2/6 params used |
| `fanotify_mark` | 1 (f) | 1 (f) | 0 | 5/6 params used |
| `unshare` | 5 (b,c,d,e,f) | 5 (b,c,d,e,f) | 0 | 1/6 params used |
| `setns` | 4 (c,d,e,f) | 4 (c,d,e,f) | 0 | 2/6 params used |

**Total void casts eliminated this session: 2** (from function signature fixes)

## Next VSL Targets (Parameter Usage Optimization)

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

## Key Pattern: Syscall Signature Matching vsl_syscall_fn

The `vsl_syscall_fn` typedef expects exactly 6 uint64_t parameters:
```c
typedef int64_t (*vsl_syscall_fn)(uint64_t, uint64_t, uint64_t,
                                   uint64_t, uint64_t, uint64_t);
```

**Rule:** Every handler MUST have exactly 6 params. If Linux syscall has fewer, pad with unused params. If more, combine (rare). The landlock and bpf handlers originally had 7 params (added an extra `f`) which caused:
- Compiler warning: "initialization from incompatible pointer type"
- Array index mismatch in syscall table

**Fix:** Remove extra param, keep exactly 6. Unused params get `(void)param;` cast.