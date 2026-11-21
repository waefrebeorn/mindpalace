# VSL Syscall Split Crash — Session 2026-07-06

## State at crash
- `vsl_syscall.c`: 1664 lines, ~90 `static int64_t vsl_sys_*` handlers + syscall table + bridge + helpers
- Session had created partial split files but never finished gutting original

## Split files created (broken state):
| File | Status | Issue |
|------|--------|-------|
| `vsl_syscall_internal.h` | Created | `extern VSL g_vsl;` → fixed to `extern VSL_STATE g_vsl;` |
| `vsl_syscall_proc.c` | Created, broken | Syntax error line 31: stray `)` after getpid signature; `CLONE_VM`/`CLONE_VFORK` undeclared; missing identity/credential/sysinfo handlers |
| `vsl_syscall_fileio.c` | Created, mostly OK | Covers read/write/open/close/lseek/stat/fstat/ioctl/access/pipe/dup/dup2/fcntl/fsync/unlink/mkdir/rmdir/rename/getcwd/chdir |
| `vsl_syscall_memory.c` | Created, mostly OK | Covers mmap/munmap/brk/mprotect/msync/mremap + extra shm* + mlock* (some not in original table) |

## NOT extracted (still in original, need new module):
- **Identity/credential** (~20): getuid, getgid, geteuid, getegid, setuid, setgid, setreuid, setregid, getresuid, getresgid, setresuid, setresgid, getgroups, setgroups, setpgid, getpgid, setsid, getsid, umask
- **Sysinfo** (7): uname, sysinfo, getrandom, getrlimit, setrlimit, prlimit64, alarm, sched_yield
- **Signals** (~12): sigaction, sigprocmask, sigreturn, rt_sigaction, rt_sigprocmask, rt_sigsuspend, rt_sigpending, rt_sigtimedwait, rt_sigqueueinfo, signalfd, signalfd4
- **Socket family** (~13): socket, socketpair, connect, bind, listen, accept, sendto, recvfrom, shutdown, getsockname, getpeername, setsockopt
- **Timers** (9): timer_create/delete/settime/gettime, timerfd_create/settime/gettime, eventfd, eventfd2
- **Poll/epoll** (5): poll, epoll_create/ctl/wait, pselect6, ppoll, select
- **Extended I/O** (~7): pread64, pwrite64, readv, writev, truncate, ftruncate, creat, symlink, readlink, chmod, fchmod, chown, lchown, fchown, lstat, openat, newfstatat, unlinkat, faccessat, getdents64, statx
- **misc** (6): futex, exit_group, clock_gettime, nosys, waitpid, pipe2
- ***at family** (12): readlinkat, fchmodat, fchownat, utimensat, futimesat, renameat, mkdirat, symlinkat, linkat, mknodat, getwd, fchdir
- **io_uring** (3): io_uring_setup, io_uring_enter, io_uring_register
- **Namespace/security** (7): unshare, setns, fanotify_init, fanotify_mark, landlock, bpf, perf_event_open, clone3

## Makefile state:
- `RT_OBJS`: added `vsl_syscall_proc.o`, `vsl_syscall_memory.o` ✓
- `test_syscall`: patched to include split .c files + `.o` file error:
  ```
  $(RT)/vsl/vsl_memory.o $(RT)/vsl/vsl_file.o $(RT)/vsl/vsl_driver.o ...
  ```
  — `.o` files don't belong in test target recipes (compiles .c directly)

## Recovery approach:
1. Fix syntax error in `vsl_syscall_proc.c` (stray `)` line 31)
2. Add missing identity/credential/sysinfo handlers to proc.c
3. Create `vsl_syscall_net.c` for remaining ~70 handlers
4. Gut original to: includes → syscall table → bridge → helpers (~200 lines)
5. Fix Makefile: add `vsl_syscall_net.o` to `RT_OBJS`, add all .c files to `test_vsl`, fix `.o`→`.c` in test_syscall
6. Update internal header with ALL handler declarations
7. `make clean && make test_vsl` → verify 83/83 pass