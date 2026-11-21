# macOS Syscall Layer for WuBuOS VSL — 2026-07-22

## What Was Created

A full macOS (XNU) binary execution subsystem for the VSL (Virtualization Substrate Layer),
enabling Mach-O binary loading and macOS syscall dispatch within WuBuOS.

## Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `src/runtime/vsl/vsl_macho.h` | 242 | Mach-O header structs (MH_MAGIC_64, FAT, LC_MAIN, LC_SEGMENT_64), all CPU types, public API |
| `src/runtime/vsl/vsl_macho.c` | 348 | Mach-O loader: validate, FAT extract, segment mmap, entry point resolution |
| `src/runtime/vsl/vsl_syscall_numbers_mac.h` | ~250 | macOS syscall numbers — Mach traps (0-63) + BSD syscalls (exit-408), class encoding |
| `src/runtime/vsl/vsl_syscall_mac.c` | ~900 | Dispatch table with 52 BSD handlers + 13 Mach trap handlers + class-based dispatch |

## Architecture

### Syscall Dispatch Flow

```
User code (x86-64 macOS binary running in VSL)
  │
  ├─ RAX = 0x000000XX → Mach trap (class 0)
  │   ├─ task_self, host_self, thread_self, mach_reply_port
  │   ├─ vm_allocate, vm_deallocate, vm_protect
  │   ├─ mach_msg, semaphore_create/destroy/wait/signal
  │   └─ vm_statistics
  │
  ├─ RAX = 0x020000XX → BSD syscall (class 2)
  │   ├─ Core: exit, fork, read, write, open, close, mmap, munmap
  │   ├─ Files: stat, fstat, lstat, lseek, fcntl, fsync, truncate, getcwd
  │   ├─ Network: socket, connect, accept, bind, listen, sendto, recvfrom
  │   ├─ Process: execve, wait4, kill, getpid, pipe, dup
  │   ├─ Signals: sigaction, sigprocmask
  │   ├─ Memory: mprotect, madvise
  │   └── Sysctl: sysctl
  │
  └─ RAX = 0x040000XX → Mach dependent (class 1) — not yet implemented
```

### Mach-O Loader

- `vsl_macho_is_macho(data, size)` — detect by magic (FEEDFACE, FEEDFACF, CAFEBABE)
- `vsl_macho_fat_extract()` — extract x86-64 slice from FAT universal binary
- `vsl_macho_validate()` — check 64-bit MH_EXECUTE, find LC_MAIN entry point
- `vsl_macho_find_command()` — find specific load command type in Mach-O
- `vsl_macho_load()` — mmap all LC_SEGMENT_64 segments, map __TEXT/__DATA/__LINKEDIT

### VSL Process Integration

- `vsl_create_process_macho()` in `vsl_process.c` — loads Mach-O, sets VSL process state
- `vsl_create_process_any()` — auto-detects ELF vs Mach-O, routes to appropriate loader
- Sets `proc->flags = 0x00020000` to signal macOS dispatch on next syscall

### Dispatch Wiring

In `vsl_syscall_dispatch()` (vsl_syscall.c):
```c
if (num & 0xFF000000) {
    return vsl_mac_syscall_dispatch(num, regs[0], ...);
}
return vsl_syscall(num, regs[0], ...);
```

## BSD Syscall Handlers (52 total)

exit, fork, read, write, open, close, wait4, link, unlink, execve,
chdir, mkdir, rmdir, access, getpid, getppid, getuid, getgid,
geteuid, getegid, kill, dup, pipe, fcntl, ioctl, gettimeofday,
select, mmap, munmap, mprotect, madvise, socket, connect, accept,
bind, listen, setsockopt, getsockopt, getsockname, getpeername,
sendto, recvfrom, shutdown, socketpair, getgroups, setgroups,
sigaction, sigprocmask, stat, fstat, lstat, lseek, getcwd,
readlink, symlink, rename, fsync, ftruncate, truncate, readv,
writev, sysctl

## Mach Trap Handlers (13 total)

task_self, host_self, thread_self, mach_reply_port,
vm_allocate, vm_deallocate, vm_protect, mach_msg,
semaphore_create, semaphore_destroy, semaphore_wait,
semaphore_signal, vm_statistics

## Open Items

- `mach_msg` returns MACH_RCV_TIMED_OUT (stub) — real IPC routing needed
- `sysctl` returns ENOSYS (stub) — implement via /proc/sys or sysfs
- 32-bit Mach-O binaries are rejected with error code -2
- No dyld/dynamic-linker support (most macOS binaries need dyld)
- `wubu_exec_macho.c` still shells out to Darling as fallback; VSL-native path blocked until dyld is provided
- More Mach traps needed for real applications (mach_port operations, task_get_special_port, etc.)
