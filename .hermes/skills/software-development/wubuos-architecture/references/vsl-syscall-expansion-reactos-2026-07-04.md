# VSL Syscall Expansion via ReactOS Study (2026-07-04)

## Context
WuBuOS VSL implements ~50 Linux syscall translations. Need to expand to cover 297 NT syscalls for Proton/Wine compatibility. ReactOS provides the reference implementation.

## ReactOS Study Results

### Source Location
- Cloned: `/home/wubu/reactos-study/reactos/`
- Syscall definitions: `ntoskrnl/include/sysfuncs.h` (297 entries)
- Generated tables: `ntoskrnl/include/internal/napi.h`
- Entry handler: `ntoskrnl/ke/amd64/traphandler.c`
- User stubs: `ntoskrnl/ntdll.S`, `ntoskrnl/ntdll_nt6.S`, `ntoskrnl/ex/zw.S`

### Key Patterns Extracted
1. **SSDT structure** - Function pointer table + arg count array (direct model for VSL dispatch)
2. **Stub generation** - Macro-based asm stubs (template for VSL user-mode trampolines)
3. **Argument copying** - Fall-through switch for 0-16 args (VSL uses 6-register convention)
4. **Service tables** - Core + Win32k separation (VSL: Core + Styx/9P + HolyC JIT)
5. **Error mapping** - NTSTATUS ↔ errno (VSL: -errno return convention)

## Generated WuBuOS Artifacts
| File | Lines | Purpose |
|------|-------|---------|
| `REACTOS_NT_SYSCALL_STUDY.md` | ~1000 | Complete mapping document |
| `src/runtime/vsl/vsl_syscall_list.h` | 305 | 296 VSL_SYSCALL macros |
| `src/runtime/vsl/vsl_syscall_table.c` | 978 | Dispatch table + metadata |

## Mapping Statistics
- **296 NT syscalls** processed (sysfuncs.lst has 297, last is incomplete)
- **100 mapped** to real VSL handlers
- **196 mapped** to `vsl_sys_nosys` (ENOSYS)

## Priority Gaps (per BATTLESHIP.md v16 Critical Tier)

| Syscall Category | NT Syscalls | VSL Handlers Needed | ReactOS Reference |
|------------------|-------------|---------------------|-------------------|
| Process/Thread | NtSuspendThread, NtResumeThread, NtQueryInformationThread | vsl_sys_tgkill, vsl_sys_proc_info | `ntoskrnl/ps/thread.c` |
| Synchronization | NtCreateMutant, NtCreateEvent, NtWaitForSingleObject | vsl_sys_futex, vsl_sys_eventfd, vsl_sys_poll | `ntoskrnl/ex/mutant.c`, `ex/event.c` |
| Memory | NtMapViewOfSection, NtUnmapViewOfSection, NtProtectVirtualMemory | vsl_sys_mmap, vsl_sys_munmap, vsl_sys_mprotect | `ntoskrnl/mm/section.c` |
| Registry→Styx | NtCreateKey, NtOpenKey, NtQueryKey, NtEnumerateKey | vsl_sys_openat, vsl_sys_getdents | `ntoskrnl/config/` |

## Implementation Workflow
1. Add handler in `src/runtime/vsl/vsl_syscall.c`
2. Update mapping in `src/runtime/vsl/vsl_syscall_list.h`
3. Regenerate `src/runtime/vsl/vsl_syscall_table.c` (run generator script)
4. Run `make test_vsl` to validate

## Verification
- All 62 VSL tests pass
- Full test suite: 747+ assertions across 58 targets — ALL GREEN
- Runtime builds cleanly: `make runtime` ✅

## Related Reference
- `references/reactos-nt-syscall-study-2026-07-04.md` (in systems-programming skill)
- `references/devils-advocate-parity-audit-2026-07-04.md`
- `references/vsl-syscall-implementation-patterns.md`