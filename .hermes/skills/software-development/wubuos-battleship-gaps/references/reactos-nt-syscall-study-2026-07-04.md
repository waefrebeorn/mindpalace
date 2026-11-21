# ReactOS NT Syscall Study — Session 2026-07-04

## Source
`/home/wubu/.hermes/profiles/mind-palace/home/myseed/reactos-study/reactos/`

## NT Syscall Inventory (from sysfuncs.lst)

**297 NT syscalls** mapped by number (0-296):

| Range | Category | Count | Examples |
|-------|----------|-------|----------|
| 0-20 | LPC/Ports | ~20 | NtConnectPort, NtAcceptConnectPort, NtCompleteConnectPort |
| 20-40 | Thread/Process | ~15 | NtCreateThread, NtCreateProcess, NtTerminateThread |
| 40-60 | Memory | ~15 | NtAllocateVirtualMemory, NtFreeVirtualMemory, NtMapViewOfSection |
| 60-80 | File/I/O | ~25 | NtCreateFile, NtReadFile, NtWriteFile, NtDeviceIoControlFile |
| 80-100 | Registry | ~15 | NtCreateKey, NtOpenKey, NtQueryKey, NtSetValueKey |
| 100-120 | Synchronization | ~20 | NtCreateEvent, NtCreateMutant, NtCreateSemaphore, NtWaitForSingleObject |
| 120-140 | Security | ~15 | NtAccessCheck, NtPrivilegeCheck, NtQuerySecurityObject |
| 140-160 | Object Manager | ~15 | NtOpenDirectoryObject, NtCreateSymbolicLinkObject |
| 160-180 | Timer/Profile | ~10 | NtCreateTimer, NtSetTimer, NtQueryPerformanceCounter |
| 180-200 | Debug/Exception | ~15 | NtDebugActiveProcess, NtRaiseException, NtContinue |
| 200-220 | Plug and Play | ~10 | NtPlugPlayControl |
| 220-240 | Power | ~10 | NtPowerInformation, NtInitiatePowerAction |
| 240-260 | System Info | ~15 | NtQuerySystemInformation, NtQuerySystemTime |
| 260-280 | Token/Job | ~15 | NtCreateToken, NtAssignProcessToJobObject |
| 280-297 | Misc/Extended | ~15 | NtCreateKeyedEvent, NtWaitForKeyedEvent, NtYieldExecution |

## Key Directory Mappings for Transliteration

| ReactOS Directory | WuBuOS Target | Notes |
|-------------------|---------------|-------|
| `ntoskrnl/ke/` | tasking.c + VSL sched | Thread scheduling, APC/DPC, synchronization primitives |
| `ntoskrnl/mm/` | memory.c + VSL mmap | VAD tree, paging, section objects, working sets |
| `ntoskrnl/ob/` | Styx9 fid/namespace + VSL fd table | Handle tables, security descriptors, object types |
| `ntoskrnl/io/` | VSL read/write/ioctl + Styx9 9P | IRP model → VSL syscall + 9P messages |
| `ntoskrnl/ps/` | VSL process + tasking | Process/thread creation, job objects, tokens |
| `ntoskrnl/rtl/` | wubu_math.h + VSL runtime | Unicode strings, heap, AVL, critical sections |
| `ntoskrnl/config/` | Styx9 registry (9P) | CM_KEY_BODY, hive loading, transactions |
| `win32ss/user/` | wm.c + WM layer | Window manager, GDI, input |
| `dll/ntdll/` | VSL syscall entry points | Syscall stubs → NT dispatch |

## NT → VSL Syscall Mapping Strategy

### VSL Syscall Convention (6-register x86-64)
```c
// VSL syscall handler signature
static int64_t vsl_sys_XXX(uint64_t a, uint64_t b, uint64_t c,
                           uint64_t d, uint64_t e, uint64_t f);
```

### Mapping Pattern
```
NT NtXXX(param1, param2, ...)
    → VSL vsl_sys_XXX(a=param1, b=param2, c=param3, d=param4, e=param5, f=param6)
    → Styx9 9P operation (Tread/Twrite/Topen/Tcreate/...)
    → ZealOS kernel service
    → TempleOS HolyC JIT (if userspace)
```

### Parameter Mapping Examples

| NT Syscall | NT Params | VSL Registers | Styx9 Op |
|------------|-----------|---------------|----------|
| NtCreateFile | 11 params (OBJA, IO_STATUS, FILE, ...) | a=path, b=access, c=share, d=create, e=flags, f=ea | Tcreate |
| NtReadFile | 9 params (HANDLE, IO_STATUS, ...) | a=fd, b=buf, c=len, d=offset, e=offset_high, f=key | Tread |
| NtWriteFile | 9 params | a=fd, b=buf, c=len, d=offset, e=offset_high, f=key | Twrite |
| NtDeviceIoControlFile | 10 params | a=fd, b=ioctl, c=inbuf, d=inlen, e=outbuf, f=outlen | Tioctl |
| NtAllocateVirtualMemory | 6 params | a=addr, b=size, c=type, e=protect, f=... | Tmmap |
| NtFreeVirtualMemory | 4 params | a=addr, b=size, c=type | Tmunmap |
| NtCreateThread | 8 params | a=entry, b=stack, c=flags, d=... | tfork + tclone |
| NtWaitForSingleObject | 3 params | a=handle, b=alertable, c=timeout | Tpoll/select |

## Styx9/9P Namespace Integration

### Styx9 Fid ↔ NT Handle Mapping
```
NT HANDLE (per-process handle table)
    → VSL FD (per-process vsl_fd table)
    → Styx9 Fid (9P fid, global namespace)
    → ZealOS resource (file, socket, device, section)
```

### 9P Operations for NT Semantics
| NT Operation | 9P Message | Notes |
|--------------|------------|-------|
| NtCreateFile | Tcreate + Twalk | Creates fid, walks to parent |
| NtOpenFile | Twalk + Topen | Reuses fid for same file |
| NtReadFile | Tread | Offset in 9P Tread is 64-bit |
| NtWriteFile | Twrite | |
| NtDeviceIoControlFile | Tioctl | Custom 9P ioctl for device control |
| NtCreateSection | Tcreate (special type) | Section objects as 9P files |
| NtMapViewOfSection | Twalk + Tread | Map section into process address space |

## ZealOS Kernel Services

| NT Service | ZealOS Target | Notes |
|------------|---------------|-------|
| Thread scheduling | tasking.c | Cooperative → preemptive |
| Virtual memory | memory.c | Page tables, VAD → ZealOS page frames |
| Object manager | Styx9 + VSL fd | Handles → fids → resources |
| I/O manager | VSL syscalls + 9P | IRP → syscall + 9P message |
| Registry | Styx9 (hierarchical) | Hive → 9P filesystem tree |
| Win32k | wm.c | Window manager, GDI, input |

## TempleOS Layer

| NT Service | TempleOS Target | Notes |
|------------|-----------------|-------|
| NtCreateThread | HolyC task = function | Tasks are HolyC functions |
| NtAllocateVirtualMemory | HolyC heap (malloc) | Identity-mapped, no paging |
| NtCreateFile | RedSea FS (doc/database) | Different paradigm — 9P bridge |
| NtDeviceIoControlFile | VBE/VGA direct | No driver model |

## Next Steps for ReactOS Mission

1. **Create complete mapping table** — All 297 syscalls from sysfuncs.lst → VSL numbers
2. **Implement missing VSL syscalls** — Priority: file I/O, memory, thread, sync, registry
3. **Build Styx9 fid allocator** — NT handle table → VSL fd → Styx9 fid translation
4. **Win32k → wm bridge** — Window creation, GDI drawing, input routing
5. **NTDLL stub generator** — Auto-generate syscall stubs from mapping table
6. **Test with real Windows binaries** — Use wubu_proton PE loader + ReactOS NTDLL

## ReactOS Source Files of Interest

| File | Purpose |
|------|---------|
| `ntoskrnl/sysfuncs.lst` | Master syscall list (297 entries) |
| `dll/ntdll/*.c` | Syscall stubs → syscall numbers |
| `ntoskrnl/ke/thrdobj.c` | Thread object implementation |
| `ntoskrnl/mm/*.c` | Memory manager (VAD, paging, sections) |
| `ntoskrnl/ob/*.c` | Object manager (handles, security, types) |
| `ntoskrnl/io/*.c` | I/O manager (IRP, device stack, drivers) |
| `ntoskrnl/ps/*.c` | Process/thread, jobs, tokens |
| `ntoskrnl/rtl/*.c` | Runtime library (strings, heap, AVL, CS) |
| `ntoskrnl/config/*.c` | Registry (hives, transactions) |
| `win32ss/user/*.c` | Win32k window manager |
| `win32ss/gdi/*.c` | GDI graphics |

## Verification Commands

```bash
# Count NT syscalls
grep -c "^Nt" /home/wubu/.hermes/profiles/mind-palace/home/myseed/reactos-study/reactos/ntoskrnl/sysfuncs.lst

# Find handler for specific syscall
grep -r "NtCreateFile" /home/wubu/.hermes/profiles/mind-palace/home/myseed/reactos-study/reactos/ntoskrnl/

# Compare with VSL syscall table
grep "VSL_SYS_" /home/wubu/.hermes/profiles/mind-palace/home/myseed/src/runtime/wubu_vsl.h
```

## Key Insight for WuBuOS

ReactOS proves **NT syscall emulation on Linux is viable** — they implement the NT kernel API on top of Linux syscalls. WuBuOS can do the same but targeting **ZealOS kernel + Styx9** instead of Linux.

The "NT → Styx9" transliteration layer is the missing piece for:
- Proton/Wine compatibility (they expect NT syscalls)
- SteamOS gamescope/pressure-vessel integration
- Windows application compatibility without full Wine