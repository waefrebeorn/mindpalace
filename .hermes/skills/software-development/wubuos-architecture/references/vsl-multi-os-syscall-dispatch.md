# VSL Multi-OS Syscall Dispatch Pattern

The VSL (Virtualization Substrate Layer) now supports three OS personalities
via the same table-driven dispatch architecture. This document captures the
pattern so adding a 4th (or 5th) OS is mechanical.

## Architecture

```
User-mode binary (ELF / Mach-O / PE)
        │
        │  SYSCALL instruction (x86-64)
        ▼
vsl_syscall_dispatch(uint64_t num, uint64_t *regs)   ← in vsl_syscall.c
        │
        ├── num & 0xFF000000  == macOS (XNU) class bits?
        │       └── vsl_mac_syscall_dispatch(num, a..f)
        │               ├── class 0  → mac_trap_table[]  (Mach traps)
        │               └── class 2  → mac_bsd_table[]   (BSD syscalls)
        │
        ├── num == VSL_NT_SYSCALL_BASE?
        │       └── vsl_nt_syscall_dispatch(ctx, num, args, nargs)
        │               └── g_nt_dispatch[ordinal-1]     (NT syscalls)
        │
        └── else (normal Linux syscall numbers)
                └── vsl_syscall_table[num]                (Linux syscalls)
```

## The Three Personalities

| OS | Syscall Encoding | Table Pattern | Handler File(s) |
|----|-----------------|---------------|-----------------|
| Linux x86-64 | `num` in RAX (0-454) | `vsl_syscall_table[]` indexed by number | `vsl_syscall_proc.c`, `vsl_syscall_fileio.c`, `vsl_syscall_memory.c`, `vsl_syscall_net.c` |
| Windows NT (ReactOS) | Ordinal via `args[0]` | `g_nt_dispatch[296]` indexed by ordinal-1 | `vsl_nt_*.c` (10 modules) + `vsl_syscall_nt.c` facade |
| macOS (XNU) | `RAX[31:24]` class, `RAX[23:0]` num | `mac_bsd_table[]` + `mac_trap_table[]` | `vsl_syscall_mac.c` |

## Adding a New OS (Step-by-Step Checklist)

### 1. Syscall Numbers Header
Create `vsl_syscall_numbers_<os>.h` — pure `#define` constants, NO includes,
NO structs. Pattern from `vsl_syscall_numbers.h` and `vsl_syscall_numbers_mac.h`.

### 2. Binary Loader
If the OS uses a different executable format, create `vsl_<format>.{c,h}`:
- `vsl_macho.h/c` — Mach-O binary loader (FAT binary support, LC_MAIN, segment mmap)
- `vsl_elf.h/c` — ELF loader (used by both Linux and VSL itself)

API pattern:
```c
int  vsl_<fmt>_validate(const void *data, size_t size, uint64_t *out_entry, uint32_t *out_type);
int  vsl_<fmt>_load(const void *data, size_t size, uint64_t load_base, uint64_t *out_entry, uint64_t *out_stack);
bool vsl_<fmt>_is_<fmt>(const void *data, size_t size);
```

### 3. Dispatch Table + Handlers
Create `vsl_syscall_<os>.c` with:
- A dispatch function called from `vsl_syscall_dispatch()`
- Handler functions with the signature `int64_t handler(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f)`
- A static dispatch table array

### 4. Wire Into Dispatch
In `vsl_syscall.c`:
```c
int64_t vsl_syscall_dispatch(uint64_t num, uint64_t *regs) {
    if (num & 0xFF000000)
        return vsl_mac_syscall_dispatch(num, regs[0], regs[1], regs[2], regs[3], regs[4], regs[5]);
    return vsl_syscall(num, regs[0], regs[1], regs[2], regs[3], regs[4], regs[5]);
}
```

NT syscalls enter via a different path (the NT bridge calls
`vsl_nt_syscall_dispatch` explicitly from user code).

### 5. Handler Implementation Pattern

Most Unix-like syscalls map 1:1 to Linux:
```c
static int64_t mac_sys_read(uint64_t a, uint64_t b, uint64_t c,
                             uint64_t d, uint64_t e, uint64_t f) {
    (void)d;(void)e;(void)f;
    ssize_t n = read((int)a, (void*)(uintptr_t)b, (size_t)c);
    if (n < 0) return mac_errno(errno);
    return (int64_t)n;
}
```

Mach traps use an opaque port-based IPC model:
```c
static int64_t mac_trap_task_self(uint64_t a, uint64_t b, uint64_t c,
                                   uint64_t d, uint64_t e, uint64_t f) {
    return FAKE_TASK_SELF_PORT;
}
```

### 6. Makefile Updates

New objects must appear in:
- `VSL_OBJS` — main VSL object list
- `test_syscall` — syscall bridge test (direct .c compile list)
- Any test target that links VSL objects

### 7. Key Differences Between OS Personalities

| Aspect | Linux | macOS | NT |
|--------|-------|-------|----|
| Exec format | ELF64 | Mach-O 64 | PE32+ |
| Entry point | `e_entry` from ELF header | `LC_MAIN` entry_offset | `AddressOfEntryPoint` |
| Syscall ABI | RAX=num, args in regs | RAX=class\|num, args in regs | Args on stack or sysenter |
| Error reporting | `-errno` (negative) | `-errno` (negative) | `NTSTATUS` (0 = success) |
| IPC model | Unix signals + pipes | Mach ports + messages | LPC/ALPC ports |
| Thread model | pthreads clone | Mach threads | NT threads |
| Object namespace | /proc, /sys, /dev | Mach port namespace | NT Object Manager |

## Getting the macOS Syscall Numbers

Apple's open-source XNU kernel:
- `bsd/kern/syscalls.master` — BSD syscall table
- `osfmk/kern/syscall_sw.c` — Mach trap table

In WuBuOS, the Darwin SDK at `darling-ref/Developer/Platforms/.../SDKs/`
contains the SDK headers with `sys/syscall.h` and `mach/mach_traps.h`.

## Future Work

- **Mach-O code signing**: AMFI validates LC_CODE_SIGNATURE; skip for now.
- **Dynamic linking**: dyld-stub must resolve LC_LOAD_DYLIB references.
- **Objective-C runtime**: `_objc_msgSend` fast path calls `syscall(298)`.
