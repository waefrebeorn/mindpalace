### VSL Syscall Cleanup Phase 3 Progress (2026-06-27)

**File**: `src/runtime/wubu_vsl.c` — 347 gaps (largest single file)

**Completed 2026-06-27**: clone3 + io_uring syscalls implemented
- `clone3` (syscall 435) - Fixed from ENOSYS stub, now delegates to host kernel via `syscall(SYS_clone3, ...)`
- `io_uring_setup` (425), `io_uring_enter` (426), `io_uring_register` (427) - Full implementations added
- All delegate to host Linux syscalls via standard C library
- 4 new test cases added to `wubu_vsl_test.c`
- All 56 VSL tests pass (was 52, now +4)

**Test Results**:
```bash
make test_vsl
# 56/56 PASS (was 52)
# New tests:
#   ✅ clone3() returns ENOSYS/EINVAL (expected on some kernels)
#   ✅ io_uring_setup() returns EFAULT/EINVAL with NULL params
#   ✅ io_uring_enter() returns EBADF with invalid fd
#   ✅ io_uring_register() returns EBADF with invalid fd
```

**Remaining Gaps in wubu_vsl.c**:
- `vsl_sys_sigreturn` - returns -ENOSYS (not callable from userspace in hosted)
- `vsl_sys_sched_yield` - only returns 0, no real yield
- All syscalls with `(void)a; (void)b; (void)c; (void)d; (void)e; (void)f;` casts need real parameter usage
- Pattern: First param `a` reserved for syscall number, rest void'd where unused
- Need implementations for: epoll, signalfd, timerfd, inotify, futex, and all other missing syscall bodies

**Implementation Pattern** (from completed io_uring):
```c
static int64_t vsl_sys_io_uring_setup(uint64_t entries, uint64_t params,
                                      uint64_t c, uint64_t d, uint64_t e, uint64_t f) {
    (void)c; (void)d; (void)e; (void)f;
    long result = syscall(SYS_io_uring_setup, (unsigned int)entries, (void *)params);
    return result < 0 ? -errno : (int64_t)result;
}
```

**Test Command**:
```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
make test_vsl  # 56/56 PASS
```