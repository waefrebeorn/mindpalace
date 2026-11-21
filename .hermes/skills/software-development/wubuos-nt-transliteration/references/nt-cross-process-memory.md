# NT Cross-Process Memory & Process-Launch Transliteration (Batch 5, E1)

This encodes the technique proven in Batch 5 (NtOpenProcess / NtTerminateProcess /
NtCreateSection / NtMapViewOfSection / NtWriteVirtualMemory / NtReadVirtualMemory).
These are the syscalls a Proton-style loader drives to boot an image inside a child
process. All do REAL Linux work — no stubs.

## The handle `data` payload slot (needed by every Batch-5 handler)
The NT handle table in `vsl_nt_bridge_ctx_t` is:
```c
struct { uint32_t nt_handle; int vsl_fd; uint64_t styx_fid; uint64_t data; nt_object_type_t type; bool valid; } handle_table[4096];
```
`data` carries an opaque payload per object type:
- `NT_OBJECT_TYPE_PROCESS` → `pid_t` of the forked child (as `uint64_t`)
- `NT_OBJECT_TYPE_THREAD`  → `pthread_t` tid
- `NT_OBJECT_TYPE_SECTION` → the `mmap` base address
Accessor: `int vsl_nt_handle_to_data(vsl_nt_bridge_ctx_t*, uint32_t nt_handle, uint64_t *out_data);`
After `vsl_nt_allocate_handle(...)`, loop the table to stash the payload:
```c
for (int i = 0; i < 4096; i++)
  if (ctx->handle_table[i].valid && ctx->handle_table[i].nt_handle == h) {
    ctx->handle_table[i].data = (uint64_t)(uintptr_t)pid; break; }
```

## NtOpenProcess (129)
Mint a PROCESS handle for an existing pid. `args[2]` = client_id (a `uint32_t` pid),
0 = open self. `kill(pid, 0)` probe to confirm the target is real (skip the probe for
self == `getpid()`). Store pid in `data`. Returns the NT handle.

## NtTerminateProcess (267)
`pid = vsl_nt_proc_pid(handle)` (reads `data`). **Refuse to kill self** — if
`pid == getpid()` return `NT_STATUS_INVALID_PARAMETER` (guards against the job-sentinel
self-kill regression). `kill(pid, SIGKILL)` then a **bounded `WNOHANG` reap loop** (never
blocking — the job-object hang lesson):
```c
for (int i = 0; i < 50; i++) {
  int st;
  if (waitpid(pid, &st, WNOHANG) == pid) break;
  struct timespec ts = {0, 5*1000*1000}; nanosleep(&ts, NULL);
}
vsl_nt_free_handle(g_nt_ctx, handle);
```

## NtCreateSection (53)
Allocate an anonymous image/section region via `mmap(NULL, size, PROT_READ|PROT_WRITE,
MAP_PRIVATE|MAP_ANONYMOUS, -1, 0)`. Store the base in `data`. Returns a SECTION handle.
`args[2]` is `size_t*` (IN/OUT). Default size to 4096 if 0.

## NtMapViewOfSection (114)
`args[0]` = section handle, `args[2]` = base* (IN/OUT). Map a fresh `MAP_PRIVATE|
MAP_ANONYMOUS` view of 4096 bytes (the minimum a loader maps first); write the mapped
base back into `*base`. (Full PE relocation/ASLR belongs to the loader — here we prove
the section is genuinely addressable memory.) `<sys/mman.h>` required.

## NtWriteVirtualMemory (195) / NtReadVirtualMemory (288)
Genuine cross-process memory via `process_vm_writev` / `process_vm_readv`:
```c
#include <sys/uio.h>
pid_t pid = vsl_nt_proc_pid(proc_handle);          // -1 => INVALID_HANDLE
struct iovec local  = { (void*)(uintptr_t)buf,  n };
struct iovec remote = { (void*)(uintptr_t)base, n };
ssize_t w = process_vm_writev(pid, &local, 1, &remote, 1, 0);
```
`args[3]` is `size_t*` (IN) and `args[4]` is `bytes_*` (OUT). Return
`vsl_errno_to_nt_status(errno)` on `< 0`. For the test, exercise the SELF process
(open self, write into a local buffer's address, read it back) — that still drives the
real `process_vm_*` syscalls and proves the round-trip.

## Test pattern (Batch 5, in `vsl_syscall_nt_test.c`)
- OpenProcess(self, client_id=0) → handle nonzero.
- WriteVirtualMemory into a local `dst[8]` buffer; assert `written == 8`.
- ReadVirtualMemory back; assert bytes match the source.
- CreateSection → handle nonzero; MapViewOfSection → base nonzero; write 0x5A, assert.
- CreateProcess then TerminateProcess: assert child alive before, dead (`kill(pid,0)
  != 0`) after. The terminate handler SIGKILLs + reaps its own child, so NO orphan.

## Pitfalls specific to this batch
- **Self-kill guard** in `NtTerminateProcess` is mandatory — without it a `NtTerminateProcess
  (self)` test would kill the test process (exit 137).
- **`process_vm_writev` needs a real target pid in `data`** — if you forgot to stash the
  pid when creating the process, `vsl_nt_proc_pid` returns -1 → INVALID_HANDLE.
- **`<sys/uio.h>` must be included** for `struct iovec` / `process_vm_*`.
- Redirect the lite binary to a FILE when running (see build script) — `NtCreateProcess`
  forks a child that holds the stdout pipe.

## Thread handle DUAL payload (`data` + `styx_fid`) — Batch 6 addition
`NtCreateThread` (and `NtCreateThreadEx`) handles need TWO pieces of state, so the
single `data` slot is not enough:
- **`data`** = pointer to the `vsl_nt_thread_params_t` (the resume-gate condvar/mutex),
  used by `NtResumeThread` to signal a `CREATE_SUSPENDED` thread.
- **`styx_fid`** = the `pthread_t` tid, used by `NtWaitForSingleObject(THREAD)` to
  `pthread_join`, and by `NtOpenThread` to duplicate.

In `NtCreateThread`, after `vsl_nt_allocate_handle`:
```c
g_nt_ctx->handle_table[i].data    = (uint64_t)(uintptr_t)tp;   // resume gate
g_nt_ctx->handle_table[i].styx_fid = (uint64_t)(uintptr_t)tid;  // for join/open
```
In `NtWaitForSingleObject`, the lookup loop must special-case THREAD to read `styx_fid`
(not `data`):
```c
if (type == NT_OBJECT_TYPE_THREAD)
    data = g_nt_ctx->handle_table[i].styx_fid;   // data held the params ptr, not tid
```
`NtOpenThread(client_id=tid)` sets ONLY `styx_fid` (no gate). `NtResumeThread` reads
`data` as the params ptr and signals `tp->gate_cv`. Do NOT store the tid in `data` for
created threads — `NtResumeThread` would then dereference a freed/wrong pointer.

## `NT_STATUS_TIMEOUT` is undefined
`vsl_nt_bridge.h` defines only `NT_STATUS_SUCCESS` (0), `NT_STATUS_UNSUCCESSFUL`
(0xC0000001), `NT_STATUS_PENDING` (0x103), etc. — there is NO `NT_STATUS_TIMEOUT`.
In `NtWaitForSingleObject` (poll timeout, or a wait that exhausts its bounded retry),
return `NT_STATUS_PENDING` (0x103), NOT an invented timeout code.

