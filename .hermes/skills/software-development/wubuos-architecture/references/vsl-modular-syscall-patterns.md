# VSL Modular Architecture & Syscall Implementation Patterns

## Context
The VSL (Virtualization Substrate Layer) was refactored from a monolithic `wubu_vsl.c` (~2200 lines) into modular files under `src/runtime/vsl/`. This document captures the patterns and pitfalls discovered during the modularization.

## Modular File Structure

```
src/runtime/vsl/
├── vsl.h              # Main public umbrella (includes all submodule headers)
├── vsl_internal.h     # Internal type definitions (full structs)
├── vsl_process.h/c    # Process management (opaque VSL_PROC)
├── vsl_file.h/c       # File operations (opaque VSL_FD)
├── vsl_memory.h/c     # Memory management (opaque VSL_MMAP)
├── vsl_driver.h/c     # Driver management (opaque VSL_DRV)
├── vsl_shared.h/c     # Shared memory IPC
├── vsl_elf.h/c        # ELF validation/loading
├── vsl_syscall.h/c    # Syscall bridge & handlers
└── vsl.c              # Lifecycle & diagnostics
```

## Opaque Type Pattern (Critical)

### Public Headers (.h) - Opaque Declarations Only
```c
/* vsl_process.h */
#ifndef WUBUOS_VSL_PROCESS_H
#define WUBUOS_VSL_PROCESS_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* Opaque forward declarations */
typedef struct VSL_PROC VSL_PROC;
typedef struct VSL_MMAP VSL_MMAP;

typedef enum {
    VSL_PROC_UNUSED = 0,
    VSL_PROC_READY,
    VSL_PROC_RUNNING,
    VSL_PROC_BLOCKED,
    VSL_PROC_ZOMBIE,
    VSL_PROC_DEAD,
} VSL_PROC_STATE;

/* API functions only - no struct definitions */
VSL_PROC *vsl_get_process(uint32_t pid);
int vsl_create_process(const void *elf_data, size_t elf_size);
int vsl_destroy_process(uint32_t pid);
int vsl_list_processes(VSL_PROC *out, int max_count);

#endif
```

### Internal Header (.h) - Full Definitions
```c
/* vsl_internal.h - includes public headers FIRST */
#include "vsl/vsl_process.h"
#include "vsl/vsl_file.h"
#include "vsl/vsl_memory.h"
#include "vsl/vsl_driver.h"

/* Now define full structs using same names */
struct VSL_PROC {
    uint32_t         pid;
    uint32_t         ppid;
    VSL_PROC_STATE   state;
    uint64_t         entry_point;
    uint64_t         stack_pointer;
    uint64_t         brk;
    uint64_t         mmap_base;
    int              exit_code;
    uint64_t         regs[16];
    uint64_t         rip, rsp, rbp, flags;
};

struct VSL_FD {
    int              fd;
    uint32_t         flags;
    uint32_t         mode;
    int              vsl_fd;
    char             path[256];
};

/* Global state with full types */
typedef struct {
    VSL_PROC         procs[VSL_MAX_PROCS];
    uint32_t         n_procs;
    uint32_t         current_pid;
    VSL_FD           fds[VSL_MAX_FDS];
    uint32_t         n_fds;
    /* ... */
} VSL_STATE;

extern VSL_STATE g_vsl;
```

### Implementation Files (.c) - Include Internal Header
```c
/* vsl_process.c */
#include "vsl/vsl_internal.h"   // Full definitions
#include "vsl/vsl_file.h"       // For cross-module calls

int vsl_create_process(const void *elf_data, size_t elf_size) {
    VSL_PROC *proc = &g_vsl.procs[g_vsl.n_procs];
    memset(proc, 0, sizeof(*proc));
    proc->pid = pid;
    /* ... */
}
```

## Key Pitfall: Duplicate Type Definitions

### WRONG - Internal header redefines types
```c
/* vsl_internal.h - BAD */
typedef enum { VSL_PROC_UNUSED = 0, ... } VSL_PROC_STATE;  // REDEFINES public enum
typedef struct { ... } VSL_PROC;  // CONFLICTS with opaque typedef
```

### RIGHT - Internal header includes public headers then defines full structs
```c
/* vsl_internal.h - GOOD */
#include "vsl/vsl_process.h"  // Gets opaque typedef + enum
#include "vsl/vsl_file.h"
/* ... */

struct VSL_PROC { ... };  // Defines the SAME struct name
```

## Syscall Handler Pattern

All syscall handlers in `vsl_syscall.c` follow this signature:
```c
static int64_t vsl_sys_<name>(uint64_t a, uint64_t b, uint64_t c,
                               uint64_t d, uint64_t e, uint64_t f);
```

### Handler Implementation Categories

1. **Direct host delegation** - Call host syscall/library directly
```c
static int64_t vsl_sys_read(uint64_t fd, uint64_t buf, uint64_t count, ...) {
    ssize_t result = read((int)fd, (void *)buf, (size_t)count);
    return result < 0 ? -errno : (int64_t)result;
}
```

2. **VSL API wrapper** - Delegate to VSL API functions
```c
static int64_t vsl_sys_open(uint64_t path, uint64_t flags, uint64_t mode, ...) {
    return vsl_open((const char *)path, (int)flags, (int)mode);
}
```

3. **Host syscall fallback** - Use `syscall()` for missing libc wrappers
```c
static int64_t vsl_sys_getdents64(uint64_t fd, uint64_t dirp, uint64_t count, ...) {
    int host_fd = vsl_get_host_fd((int)fd);
    if (host_fd < 0) return -9;
    ssize_t result = syscall(SYS_getdents64, host_fd, (void *)dirp, (size_t)count);
    return result < 0 ? -errno : (int64_t)result;
}
```

4. **Deprecated syscall handling** - Map to modern equivalent
```c
static int64_t vsl_sys_futimesat(uint64_t dirfd, uint64_t pathname, uint64_t times, ...) {
    const struct timeval *tv = (const struct timeval *)times;
    struct timespec ts[2];
    if (tv) {
        ts[0].tv_sec = tv[0].tv_sec;
        ts[0].tv_nsec = tv[0].tv_usec * 1000;
        ts[1].tv_sec = tv[1].tv_sec;
        ts[1].tv_nsec = tv[1].tv_usec * 1000;
    }
    return utimensat((int)dirfd, (const char *)pathname, tv ? ts : NULL, 0);
}
```

## Syscall Table Pattern

```c
typedef int64_t (*vsl_syscall_fn)(uint64_t, uint64_t, uint64_t,
                                   uint64_t, uint64_t, uint64_t);

static const vsl_syscall_fn vsl_syscall_table[] = {
    [VSL_SYS_READ]         = vsl_sys_read,
    [VSL_SYS_WRITE]        = vsl_sys_write,
    /* Designated initializers auto-size to max syscall number */
};

#define VSL_SYSCALL_TABLE_SIZE (sizeof(vsl_syscall_table) / sizeof(vsl_syscall_table[0]))

int64_t vsl_syscall(uint64_t num, uint64_t rdi, uint64_t rsi,
                    uint64_t rdx, uint64_t r10, uint64_t r8, uint64_t r9) {
    if (!g_vsl.active) return -1;
    g_vsl.syscall_count++;
    if (num < VSL_SYSCALL_TABLE_SIZE && vsl_syscall_table[num]) {
        return vsl_syscall_table[num](rdi, rsi, rdx, r10, r8, r9);
    }
    g_vsl.syscall_errors++;
    return -38;  // ENOSYS
}
```

## Helper: Host FD Resolution

```c
static int vsl_get_host_fd(int vsl_fd) {
    if (vsl_fd < 3) return vsl_fd;  // stdin/stdout/stderr
    for (uint32_t i = 0; i < g_vsl.n_fds; i++) {
        if (g_vsl.fds[i].fd == vsl_fd) return g_vsl.fds[i].vsl_fd;
    }
    return -1;
}
```

## Makefile Target for Modular Build

```makefile
test_vsl:
	$(CC) -O0 -g -D_GNU_SOURCE -DHAVE_VULKAN -DHAVE_CUDA \
		-Isrc/runtime -Isrc/runtime/vsl \
		src/runtime/vsl/vsl.c \
		src/runtime/vsl/vsl_syscall.c \
		src/runtime/vsl/vsl_process.c \
		src/runtime/vsl/vsl_memory.c \
		src/runtime/vsl/vsl_file.c \
		src/runtime/vsl/vsl_driver.c \
		src/runtime/vsl/vsl_shared.c \
		src/runtime/vsl/vsl_elf.c \
		src/runtime/wubu_vsl_test.c \
		-o src/runtime/wubu_vsl_test -ldl -lvulkan -lcuda
	src/runtime/wubu_vsl_test
```

## Required Public Header Exports

Each submodule's public header must export all functions used by:
- The syscall table (`vsl_syscall.c`)
- Other VSL modules
- Test suite (`wubu_vsl_test.c`)

```c
/* vsl/vsl_process.h - exports for test suite access */
VSL_PROC *vsl_get_process(uint32_t pid);
int vsl_create_process(const void *elf_data, size_t elf_size);
int vsl_destroy_process(uint32_t pid);
int vsl_list_processes(VSL_PROC *out, int max_count);

/* Accessor functions for test suite to inspect opaque structs */
VSL_PROC_STATE vsl_proc_get_state(const VSL_PROC *proc);
uint32_t vsl_proc_get_pid(const VSL_PROC *proc);
uint32_t vsl_proc_get_ppid(const VSL_PROC *proc);
uint64_t vsl_proc_get_entry_point(const VSL_PROC *proc);
uint64_t vsl_proc_get_stack_pointer(const VSL_PROC *proc);
uint64_t vsl_proc_get_brk(const VSL_PROC *proc);
int vsl_proc_get_exit_code(const VSL_PROC *proc);
```

## Test Suite Compatibility

The test suite (`wubu_vsl_test.c`) uses opaque types via accessors:
```c
// Test CAN do this:
T(vsl_get_process(1) != NULL, "init process exists");
T(vsl_proc_get_pid(vsl_get_process(1)) == 1, "init PID is 1");

// Test CANNOT do this (opaque):
// VSL_PROC procs[32];  // ERROR: incomplete type
// proc->pid == 1;      // ERROR: incomplete type
```

## Verification Checklist

- [ ] All public headers only declare opaque types + API functions
- [ ] `vsl_internal.h` includes public headers BEFORE defining full structs
- [ ] Each `.c` file includes `vsl_internal.h` for full definitions
- [ ] Syscall table covers all VSL_SYS_* numbers from `wubu_vsl.h`
- [ ] Test target links all `.c` files in `vsl/` directory
- [ ] Accessor functions provided for test suite inspection
- [ ] No duplicate type definitions (enum/struct/typedef)
- [ ] All handler functions implemented (no "undeclared" errors)