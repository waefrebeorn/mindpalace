# E1 Handler Return/Arg-Contract Pitfalls (Batches 7–8)

These are recurring contract bugs that surface when writing NEW NT handlers and
their regression tests in `vsl_nt_*.c`. The trap: the bridge's 6 raw `uint64_t`
args map loosely onto the real NT API, and the simplified ABI the WuBuOS bridge
uses does NOT match ReactOS's pointer-heavy signatures. A test that asserts the
wrong contract produces either a false failure or — worse — a SIGSEGV in the
handler (writing to a value treated as a pointer).

## 1. NtWriteFile / NtReadFile return a BYTE COUNT, not NT_STATUS_SUCCESS
The batch-3 handlers `vsl_nt_read_file` / `vsl_nt_write_file` return
`(int64_t)n` (bytes transferred), exactly like `pread`/`pwrite`. A test that does
`CHECK(r == NT_STATUS_SUCCESS, ...)` fails even when the I/O worked.

```c
r = vsl_nt_syscall_dispatch(&ctx, 285, args, 3);   // NtWriteFile
CHECK(r == (int64_t)strlen(msg), "NtWriteFile wrote N bytes");
r = vsl_nt_syscall_dispatch(&ctx, 192, args, 3);   // NtReadFile
CHECK(r == (int64_t)strlen(msg), "NtReadFile read N bytes");
```

## 2. NtCreateEvent (38) returns the HANDLE as its RETURN VALUE, not via out-param
Unlike `NtCreateKey`/`NtCreateFile` (which write the handle into `a_*`),
`vsl_nt_create_event` does `return (int64_t)h;`. The test's `a_init_state` arg is
the INPUT initial-state, NOT an out-param. Capturing the handle from the out-param
leaves it 0 → the next call (`NtPulseEvent(0)`) gets `INVALID_HANDLE`.

```c
r = vsl_nt_syscall_dispatch(&ctx, 38, args, 1);   // NtCreateEvent
CHECK(r != 0, "NtCreateEvent returned a handle");
ev = (uint32_t)r;                                  // capture the RETURN, not &ev
```

## 3. NtResetVirtualMemory (283) size arg is BY-VALUE in this bridge
The real NT `NtResetVirtualMemory` takes `PSIZE_T Size` (a pointer). The WuBuOS
simplified ABI passes the size as the raw `uint64_t` value. A test passing
`args[2] = (uint64_t)&size_var` (pointer) is fine, but a handler that does
`*(uint64_t *)c_size` dereferences address 4096 → SIGSEGV. Keep the handler
reading `size = (size_t)c_size;` (value), OR keep the test passing a pointer and
the handler dereferencing — just be CONSISTENT. This session standardized on
**by-value** for the memory-class handlers (matches `NtAllocateVirtualMemory`'s
`args[2]`/`args[3]` being value sizes here).

## 4. NtQueryValueKey (186): e_len is INPUT length (value), NOT a ResultLength pointer
Real NT: `Length` (input, value) + `ResultLength` (output, pointer, the LAST arg).
A handler that writes `*(uint32_t *)e_len_out = got;` while the test passes
`e = sizeof(buf)` (a value, 32) dereferences address 32 → SIGSEGV.

Fix: `e_len` is the input buffer cap; `f` is the optional ResultLength pointer.

```c
size_t cap = (e_len && e_len < (uint64_t)len) ? (size_t)e_len : (size_t)len;
size_t got = fread(buf, 1, cap, fp);
if (f_result_len) *(uint32_t *)f_result_len = (uint32_t)got;   // f, not e
```

**General rule for every new handler:** check whether each arg is (a) an input
VALUE, (b) an input POINTER (buffer/struct), or (c) an output POINTER. The bridge
uses raw `uint64_t`, so there is no compiler help — a value passed where the
handler dereferences a pointer is the #1 cause of E1 SIGSEGVs. Backtrace:
`gdb -batch -ex 'set debuginfod enabled off' -ex run -ex bt --args /tmp/wubu_vsl_nt_test_lite`

## 5. _DEFAULT_SOURCE for MADV_* / BSD extras under -D_POSIX_C_SOURCE
The runtime Makefile compiles with `-std=c11 -D_POSIX_C_SOURCE=200809L`, which
HIDES `MADV_DONTNEED` / `MADV_*` from `<sys/mman.h>`. If a handler uses
`madvise(...)`, add at the TOP of `vsl_nt_internal.h` (BEFORE any system include):

```c
#define _DEFAULT_SOURCE
```

This must precede the first `#include <sys/mman.h>` (the internal header is the
first include in every module). Without it the build fails with
`MADV_DONTNEED undeclared`.

## 6. NtMapViewOfSection (114) must stash the view SIZE for NtUnmapViewOfSection
The original batch-4 `NtMapViewOfSection` mapped a fixed 4096-byte view but did
NOT record the size, so `NtUnmapViewOfSection` (279) couldn't `munmap` the right
range. Store the size in the section handle's `styx_fid` (the `data` slot holds
the base, `styx_fid` is free):

```c
// in NtMapViewOfSection, after mmap succeeds:
for (int i = 0; i < 4096; i++)
  if (valid && type==NT_OBJECT_TYPE_SECTION && handle_table[i].data == sec_base)
    { handle_table[i].styx_fid = view_sz; break; }
// in NtUnmapViewOfSection, recover size from styx_fid before munmap:
size = g_nt_ctx->handle_table[i].styx_fid;   // 0 => default to a page
```
