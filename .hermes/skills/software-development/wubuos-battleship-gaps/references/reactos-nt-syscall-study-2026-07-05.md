# ReactOS NT Syscall Study — WuBuOS VSL Bridge (2026-07-05)

## Overview
ReactOS implements **297 NT syscalls** (sysfuncs.lst) up to NT 5.2/Vista parity. WuBuOS VSL must translate these to Linux syscalls → Styx/9P → ZealOS → TempleOS.

## Source Location
```
/home/wubu/reactos-study/reactos/
```

## Key ReactOS Directories for Transliteration

| ReactOS Path | What It Contains | WuBuOS Target |
|--------------|------------------|---------------|
| `ntoskrnl/ke/` | Executive kernel (threads, scheduling, sync, timers, APC/DPC) | `tasking.c` + VSL clone/fork |
| `ntoskrnl/mm/` | Memory manager (VAD, paging, section objects, working sets) | `memory.c` + VSL mmap/brk |
| `ntoskrnl/io/` | I/O manager (IRP, device stack, driver model, completion) | VSL read/write/ioctl + Styx/9P |
| `ntoskrnl/ob/` | Object manager (handle table, security descriptors, types) | Styx9 fid/namespace + VSL fd table |
| `ntoskrnl/ps/` | Process/thread creation, job objects, tokens | VSL fork/exec + tasking |
| `ntoskrnl/rtl/` | Runtime library (strings, unicode, heap, critical sections, AVL) | VSL + libc |
| `ntoskrnl/config/` | Registry (CM_KEY_BODY, hive loading, transactions) | Styx9 registry namespace |
| `win32ss/user/` + `gdi/` | Win32k (window manager, GDI, input, USER API) | Win98 WM + wm.c |
| `dll/ntdll/` | NTDLL syscall stubs → NT dispatch | VSL syscall entry points |

## NT → VSL Syscall Mapping (Sample)

| NT Syscall (sysfuncs.lst) | Args | VSL Handler | Linux Syscall |
|---------------------------|------|-------------|---------------|
| NtCreateProcess | 8 | vsl_sys_fork | clone() |
| NtCreateProcessEx | 9 | vsl_sys_clone | clone() |
| NtCreateThread | 8 | vsl_sys_clone | clone() |
| NtTerminateProcess | 2 | vsl_sys_kill | kill() |
| NtAllocateVirtualMemory | 6 | vsl_sys_mmap | mmap() |
| NtFreeVirtualMemory | 4 | vsl_sys_munmap | munmap() |
| NtProtectVirtualMemory | 5 | vsl_sys_mprotect | mprotect() |
| NtCreateFile | 11 | vsl_sys_open | openat() |
| NtOpenFile | 6 | vsl_sys_open | openat() |
| NtReadFile | 9 | vsl_sys_read | read() |
| NtWriteFile | 9 | vsl_sys_write | write() |
| NtClose | 1 | vsl_sys_close | close() |
| NtCreateMutant | 4 | vsl_sys_futex | futex() |
| NtCreateEvent | 5 | vsl_sys_eventfd | eventfd() |
| NtWaitForSingleObject | 3 | vsl_sys_poll | poll() |

Full mapping in `vsl_syscall_list.h` (generated from sysfuncs.lst).

## Critical Translation Challenges

### 1. Handle Inheritance & Security
```c
// NT: NtCreateFile takes ObjectAttributes with SecurityDescriptor, Handle inheritance
// Linux: openat() has no security descriptor, handle inheritance via O_CLOEXEC/fork
// WuBuOS: Must map NT security → Linux capabilities + VSL fd table with NT semantics
```

### 2. Overlapped I/O (Async)
```c
// NT: NtReadFile/NtWriteFile with ByteOffset + Key + IoStatusBlock
// Linux: read()/write() are sync; async via io_uring or aio
// WuBuOS: VSL needs overlapped I/O translation layer → io_uring
```

### 3. Virtual Address Descriptors (VAD)
```c
// NT: VAD tree tracks all virtual memory regions (MEM_COMMIT, MEM_RESERVE, PAGE_*)
// Linux: vm_area_struct list in mm_struct
// WuBuOS: memory.c needs VAD tree implementation for NT semantics
```

### 4. Object Manager → Styx/9P
```c
// NT: ObCreateObject, ObReferenceObject, ObDereferenceObject, handle table
// WuBuOS: Styx9 fid = object reference, VSL fd table = handle table
// Missing: Security descriptors, object types, directory objects, symbolic links
```

### 5. IRP (I/O Request Packets)
```c
// NT: IRP stack, device stack, completion, cancel, driver model
// Linux: No direct equivalent; syscalls go straight to driver
// WuBuOS: VSL syscall → Styx9 9P message → host driver
```

## Implementation Pipeline

```
ReactOS NT syscall (297)
    ↓
WuBuOS VSL syscall table (vsl_syscall_list.h) — GENERATED
    ↓
VSL handler (vsl_syscall.c) — translate NT args → Linux args
    ↓
Linux syscall / io_uring / netlink
    ↓
Styx/9P namespace (styxfs.c) — file/registry/device objects
    ↓
ZealOS kernel services (tasking, memory, vbe, input)
    ↓
TempleOS layer (HolyC JIT, compiler-as-library)
```

## Current Status

| Component | ReactOS Source | WuBuOS Status |
|-----------|----------------|---------------|
| Syscall table (297) | sysfuncs.lst | ✅ Mapped in vsl_syscall_list.h |
| Thread scheduling | ke/thrdschd.c + thrdobj.c | ❌ Simple RR only |
| Memory (VAD) | mm/*.c | ❌ Single heap region |
| Object manager | ob/*.c | ❌ Styx9 fid only |
| I/O manager (IRP) | io/*.c | ❌ Direct syscalls |
| Win32k | win32ss/user/gdi | ❌ Win98 WM subset |
| NTDLL stubs | dll/ntdll/ | ❌ VSL entry points only |
| Registry | config/*.c | ❌ Styx9 namespace only |

## Next Steps

1. **Implement VAD tree** in `memory.c` for `NtAllocateVirtualMemory`/`NtProtectVirtualMemory`
2. **Add handle inheritance** to VSL fd table for `NtCreateProcess`/`NtDuplicateObject`
3. **Build IRP→9P translation** in `styxfs.c` for device I/O
4. **Implement NT security descriptors** → Linux capabilities mapping
5. **Create `vsl_nt_bridge.c` as the NT→VSL translation layer.

## Reference
- ReactOS source: `/home/wubu/reactos-study/reactos/`
- VSL mapping: `REACTOS_NT_SYSCALL_STUDY.md` in project root
- Generated: `src/runtime/vsl/vsl_syscall_list.h` (296 entries)