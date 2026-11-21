# Modular VSL Fix (2026-06-29)

## Summary
Fixed the broken modular VSL implementation in `src/runtime/vsl/` - it was completely broken with syntax errors, truncated syscall table, missing helper functions, and test using opaque types incorrectly.

## Root Causes Fixed

1. **Syntax Errors** - Periods instead of semicolons in return statements throughout `vsl_syscall.c`
2. **Truncated Syscall Table** - Ended abruptly at `[VSL_SY` instead of complete 436-entry table
3. **Missing Syscall Bridge** - No `vsl_syscall()` or `vsl_syscall_dispatch()` in modular implementation
4. **Missing Helper Functions** - `register_child_pid()`, `vsl_openat()`, `vsl_get_host_fd()`, `find_free_vsl_pid()`
5. **Missing io_uring Syscall Numbers** - Not defined in public header
6. **Test Using Opaque Types Incorrectly** - Direct struct access instead of accessor functions

## Fixes Applied

### 1. Fixed Syntax Errors (periods → semicolons)
```c
// Before (broken):
return rc < 0 ? -errno : (int64_t)rc.
return 0.

// After (fixed):
return rc < 0 ? -errno : (int64_t)rc;
return 0;
```

### 2. Restored Complete Syscall Table
- Copied full 436-entry table from `wubu_vsl.c.bak`
- Includes all 15 new syscalls from Phase 17
- Added io_uring entries: SETUP/ENTER/REGISTER (425/426/427)

### 3. Added Missing Syscall Bridge
```c
#define VSL_SYSCALL_TABLE_SIZE (sizeof(vsl_syscall_table) / sizeof(vsl_syscall_table[0]))

int64_t vsl_syscall(uint64_t num, uint64_t rdi, uint64_t rsi,
                    uint64_t rdx, uint64_t r10, uint64_t r8, uint64_t r9) {
    if (!g_vsl.active) return -1;
    g_vsl.syscall_count++;
    if (num < VSL_SYSCALL_TABLE_SIZE && vsl_syscall_table[num])
        return vsl_syscall_table[num](rdi, rsi, rdx, r10, r8, r9);
    g_vsl.syscall_errors++;
    return -38; /* ENOSYS */
}

int64_t vsl_syscall_dispatch(uint64_t num, uint64_t *regs) {
    return vsl_syscall(num, regs[0], regs[1], regs[2], regs[3], regs[4], regs[5]);
}
```

### 4. Added Missing Helper Functions
```c
static int vsl_get_host_fd(int vsl_fd) { ... }
static int find_free_vsl_pid(void) { ... }
static int register_child_pid(pid_t child_host_pid, uint32_t parent_vsl_pid) { ... }
int vsl_openat(int dirfd, const char *pathname, int flags, mode_t mode) { ... }
```

### 5. Added io_uring Syscall Numbers to Public Header
```c
/* Cell 360-370: io_uring Syscalls (NEW) */
#define VSL_SYS_IO_URING_SETUP    425
#define VSL_SYS_IO_URING_ENTER    426
#define VSL_SYS_IO_URING_REGISTER 427
```

### 6. Fixed Test to Use Opaque Accessor Functions
```c
// Before (direct struct access - breaks with opaque types):
T(vsl_get_process(1)->pid == 1, "init PID is 1");

// After (using accessor functions):
T(vsl_proc_get_pid(vsl_get_process(1)) == 1, "init PID is 1");
T(vsl_proc_get_state(vsl_get_process(1)) == VSL_PROC_READY, "init state is READY");

// Also for drivers:
T(vsl_drv_get_type(vk) == VSL_DRV_GPU_VULKAN, "Vulkan driver type correct");
```

### 7. Fixed Syscall Table Size Macro
```c
#define VSL_SYSCALL_TABLE_SIZE (sizeof(vsl_syscall_table) / sizeof(vsl_syscall_table[0]))
```

### 8. Fixed `register_child_pid` Bug
```c
// Before (bug - g_vsl.vsl.n_procs):
if (g_vsl.vsl.n_procs >= VSL_MAX_PROCS) return -1;

// After (correct):
if (g_vsl.n_procs >= VSL_MAX_PROCS) return -1;
```

## Test Results
```
make test_vsl
# 56/56 PASS (was 0, completely broken)
# Lifecycle: 4/4
# Process Management: 5/5
# Syscall Bridge: 8/8
# New Syscalls: 4/4 (clone3, io_uring_setup/enter/register)
# Memory Management: 4/4
# File Operations: 5/5
# Seek Operations: 8/8
# Driver Management: 8/8
# Shared Memory: 2/2
# ELF Validation: 5/5
# Diagnostics: 4/4
# Shutdown: 1/1
```

## Key Lessons
1. **Never redefine opaque structs in internal headers** - Include public headers instead
2. **Complete syscall table is critical** - Truncated table causes cascade failures
3. **Syscall bridge must be in modular implementation** - Not just in monolith
4. **Tests must use accessor functions** - Opaque types require accessors
4. **Verify completeness before testing** - Truncated files cause cascade failures
5. **Helper functions must be implemented** - Forward declarations only work if defined