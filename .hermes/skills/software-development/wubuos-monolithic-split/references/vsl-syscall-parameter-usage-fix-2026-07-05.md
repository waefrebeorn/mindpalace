# VSL Syscall Parameter Usage Fix (2026-07-05) — Monolithic Split Context

## Overview
During the OCI monolith split (completed 2026-07-05), the VSL syscall module (`src/runtime/vsl/vsl_syscall.c`) was already modular but had 118+ handlers with `(void)param` casts violating the "rewriting from scratch in C = REAL_GAP closed" principle.

## Problem
VSL maintains a virtual file descriptor table (`g_vsl.fds[]`). Raw syscall parameters containing VSL fds must be translated to host fds via `vsl_get_host_fd()` before calling the actual host syscall.

## Fix Applied
Updated 4 fd-based syscall handlers in `src/runtime/vsl/vsl_syscall.c`:

```c
// vsl_sys_dup - BEFORE
int result = dup((int)fd);

// vsl_sys_dup - AFTER  
int host_fd = vsl_get_host_fd((int)fd);
if (host_fd < 0) return -9; /* EBADF */
int result = dup(host_fd);
```

Similar fixes for `vsl_sys_dup2`, `vsl_sys_fcntl`, `vsl_sys_fsync`.

## Pattern Established
For all fd-based syscalls in VSL:
```c
static int64_t vsl_sys_XXX(uint64_t fd, ...) {
    int host_fd = vsl_get_host_fd((int)fd);
    if (host_fd < 0) return -9; /* EBADF */
    int rc = real_syscall(host_fd, ...);
    return rc < 0 ? -errno : (int64_t)rc;
}
```

## Verification
```bash
make clean && make test_vsl
# === Results: 62/62 passed ===
```

## Files Modified
- `src/runtime/vsl/vsl_syscall.c` — 4 handlers fixed

## Related
- BATTLESHIP.md Critical Tier #1 — VSL Syscall Parameter Usage
- wubuos-test-suite skill reference: vsl-syscall-parameter-usage-fix-2026-07-05.md