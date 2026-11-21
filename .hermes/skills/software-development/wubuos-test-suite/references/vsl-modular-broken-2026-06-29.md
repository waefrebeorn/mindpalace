# VSL Modular Implementation - BROKEN (2026-06-29)

## Issue Summary
The modular VSL implementation under `src/runtime/vsl/` is **BROKEN** and excluded from the main test suite. The legacy monolithic `src/runtime/wubu_vsl.c` works correctly.

## What's Broken

### vsl_syscall.c Syntax Errors (~100 occurrences)
```c
// BROKEN - period instead of semicolon
return 0.
return rc < 0 ? -errno : (int64_t)rc.

// CORRECT
return 0;
return rc < 0 ? -errno : (int64_t)rc;
```

### Truncated Syscall Table
```c
// Line 1152 - incomplete
static const vsl_syscall_fn vsl_syscall_table[] = {
    [VSL_SYS_READ]         = vsl_sys_read,
    ...
    [VSL_SY   // <-- cuts off here
```

### Missing Helper Functions (declared but undefined)
- `vsl_get_host_fd()` - declared in vsl_internal.h, not implemented
- `register_child_pid()` - declared in vsl_internal.h, not implemented  
- `vsl_openat()` - declared in vsl_internal.h, not implemented
- `vsl_elf_validate()` - called from vsl_process.c:51, not implemented

## Working Alternative
**Legacy `src/runtime/wubu_vsl.c`** - 2175-line monolithic file with ALL syscall handlers working correctly. Used by `test_apps` target.

## Test Target Status
| Target | VSL Implementation | Status |
|--------|-------------------|--------|
| `test_apps` | legacy wubu_vsl.c | ✅ PASS (15 tests) |
| `test_vsl` | modular vsl/ | ❌ BROKEN (52 tests) |
| `test_wubu` | legacy wubu_vsl.c | ✅ PASS (47 tests) |
| `test_styxfs` | legacy wubu_vsl.c | ✅ PASS (11 tests) |
| `test_host_exec` | legacy wubu_vsl.c | ✅ PASS (15 tests) |

## Fix Required
To make modular VSL work:
1. Fix all `return 0.` → `return 0;` and `return ... .` → `return ... ;` in vsl_syscall.c
2. Complete syscall table with all VSL_SYS_* entries
3. Implement missing helpers: `vsl_get_host_fd`, `register_child_pid`, `vsl_openat`, `vsl_elf_validate`
4. Add modular VSL files to test_vsl Makefile target (already done)

## Decision
**Keep modular VSL excluded from main `test` target** until fixed. The legacy implementation is complete and tested. Modular refactoring is a separate effort.