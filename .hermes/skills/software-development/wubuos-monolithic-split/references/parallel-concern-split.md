# Parallel-Concern Split Pattern

Different from extracting a backend (which isolates a hardware concern for testability),
the **parallel-concern split** divides a single large module into files based on which
family of operations they handle — without changing any testability or hardware boundary.

## When to use

The file handles ONE well-defined subsystem (e.g. "macOS syscall dispatch") but has grown
past ~600 lines with clearly separable operation families. Every family shares:

- The same header constants
- The same typedefs
- The same global state / singleton
- The same inline helpers

## Pattern

### 1. Create `module_internal.h`

Shared types, extern tables, and inline helpers that every sub-module needs:

```c
#ifndef MODULE_INTERNAL_H
#define MODULE_INTERNAL_H
#include "module.h"           // public types

// Shared typedef
typedef int64_t (*handler_fn)(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);

// Inline helper (no .c overhead)
static inline int64_t errno_result(int err) { return -(int64_t)err; }

// Extern dispatch tables — defined by sub-modules
extern const handler_fn bsd_table[512];
extern const handler_fn mach_table[96];

// Extern shared globals (or put the definitions in the core dispatch file)
extern int g_sem_count;
#endif
```

### 2. Create one `.c` per concern family

Each sub-module:

- `#include "module_internal.h"` 
- Defines its handlers WITHOUT `static` (so the dispatch table can see them)
- Defines its dispatch table as non-static `const` (matches the extern decl in the header)
- Is a complete TU: compiles independently, links cleanly

```
vsl_syscall_mac_bsd.c   → BSD syscall handlers + bsd_table[512]
vsl_syscall_mac_mach.c  → Mach trap handlers + port table + mach_table[96]
```

### 3. Keep the core dispatch file lean

The original file retains only:

- The internal header include
- Shared global definitions (semaphore arrays, counters)
- The single dispatch entry point function

```
vsl_syscall_mac.c → #include internal.h + globals + vsl_mac_syscall_dispatch()
```

### 4. Update Makefile

Add each new `.o` to the same `OBJS` list as the original:

```makefile
VSL_OBJS = ... vsl_syscall_mac.o vsl_syscall_mac_bsd.o vsl_syscall_mac_mach.o ...
```

Also add the new `.c` files to every explicit test recipe that compiled the original:

```makefile
test_vsl_mac:
    $(CC) ... vsl_syscall_mac.c vsl_syscall_mac_bsd.c vsl_syscall_mac_mach.c ...
```

### 5. Verify

```sh
make runtime       # objects compile
make test_vsl      # dispatch loop still works
make test          # full regression
```

## Concrete example: `vsl_syscall_mac.c` (1215→3 files)

| Before | After | Concern |
|--------|-------|---------|
| `vsl_syscall_mac.c` (1215) | `vsl_syscall_mac.c` (65) | Dispatch entry + semaphore globals |
| | `vsl_syscall_mac_bsd.c` (867) | 77 BSD handlers + `mac_bsd_table[512]` |
| | `vsl_syscall_mac_mach.c` (235) | 13 Mach traps + port table + `mac_trap_table[96]` |
| | `vsl_syscall_mac_internal.h` (78) | `mac_syscall_fn` typedef, `mac_errno()` inline, extern tables |

## Contrast with backend-extraction pattern

| Dimension | Parallel-Concern Split | Backend Extraction |
|-----------|----------------------|-------------------|
| Motivation | File too large, multiple concern families | Isolate hardware dep for testability |
| Internal header | Shared types + extern tables + inline helpers | Extern globals + helper headers |
| Sub-modules | Non-static handlers, non-static dispatch table | Static or non-static depending on test needs |
| Dispatch table | Extern, shared across sub-modules | Private to each backend |
| Test impact | Same tests, same coverage | NEW tests possible (host-testable backend) |
| Example | `vsl_syscall_mac.c` 3-way split | `interrupt.c` → `interrupt_pic.c` |

## Anti-pattern: splitting when concern families are intertwined

If handler A and handler B call each other across concern boundaries, or share
mutable state that must be updated atomically by both, a parallel-concern split
creates cross-file coupling that's worse than the original monolith. The litmus
test: can you draw a line where NO handler in file A references a handler in
file B, except through the dispatch table? If yes → split. If no → the concerns
are genuinely coupled; keep them together or find a deeper decomposition.
