# VSL God-Header Extraction (2026-07-05)

## The Problem

`vsl_syscall.c` included `wubu_vsl.h` — a "god header" that pulled in ALL VSL submodule headers (vsl_process.h, vsl_memory.h, vsl_file.h, vsl_driver.h, vsl_shared.h, vsl_elf.h, vsl_syscall.h) transitively. The ONLY thing vsl_syscall.c needed from wubu_vsl.h was the `VSL_SYS_*` macro constants.

Additionally, `vsl_internal.h` (included by 11 TUs) had `static` forward declarations for internal helpers, creating per-TU duplicate private copies.

## The Fix

### 1. Create `vsl_syscall_numbers.h` — self-contained, zero includes

```c
/* vsl_syscall_numbers.h — just #define constants, NO includes */
#ifndef WUBUOS_VSL_SYSCALL_NUMBERS_H
#define WUBUOS_VSL_SYSCALL_NUMBERS_H
#define VSL_SYS_READ        0
#define VSL_SYS_WRITE       1
#define VSL_SYS_OPEN        2
// ... 130+ syscall number constants ...
#endif
```

This header has ZERO `#include` lines. It can be included anywhere without pulling in the VSL subsystem.

### 2. Update the god header for backward compat

```c
/* wubu_vsl.h — was 222 lines, syscall numbers replaced with include */
/* VSL syscall numbers (see vsl_syscall_numbers.h for full list) */
#include "vsl/vsl_syscall_numbers.h"
```

Removed ~115 lines of `#define VSL_SYS_*` from wubu_vsl.h. Existing consumers that include wubu_vsl.h still get the macros via the include chain.

### 3. Fix the specific .c to drop the god-header dependency

```c
// vsl_syscall.c — BEFORE
#include "wubu_vsl.h"          // god header — pulls in EVERYTHING
#include "wubu_container.h"    // unused 
#include "vsl/vsl_syscall.h"
#include "vsl/vsl_internal.h"

// vsl_syscall.c — AFTER  
#include "vsl/vsl_syscall_numbers.h"  // just constants — self-contained
#include "vsl/vsl_internal.h"         // full struct defs
#include "vsl/vsl_syscall.h"          // vsl_syscall_fn typedef
```

### 4. Fix `static` in internal headers

`vsl_internal.h` had:
```c
static int vsl_get_host_fd(int vsl_fd);  // WRONG — static in a header!
```

Changed to plain declarations:
```c
int vsl_get_host_fd(int vsl_fd);
int find_free_vsl_pid(void);
int register_child_pid(pid_t, uint32_t);
int vsl_openat(int, const char*, int, mode_t);
```

### 5. Remove duplicate static definitions from sibling .c files

Three functions were duplicated across split modules:
- `vsl_process.c` had its own `static register_child_pid` and `static find_free_vsl_pid`
- `vsl.c` had its own `static vsl_openat`

All were duplicates of the canonical implementations in `vsl_syscall.c`. Removed the stale copies from `vsl_process.c` and `vsl.c`.

## Verification

- `make test_vsl`: 83/83 passed (expanded from 62 tests with new identity+credential syscall coverage)
- `make runtime`: clean production build
- `make test_syscall test_apps test_host_exec`: all pass