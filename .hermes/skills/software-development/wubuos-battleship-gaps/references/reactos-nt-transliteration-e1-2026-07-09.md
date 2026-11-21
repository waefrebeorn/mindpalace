# ReactOS NT Syscall Transliteration (E1) — Batch Recipe + Pitfalls (2026-07-09)

## Context
E1 = the single largest parity block: 297 ReactOS NT syscalls mapped in
`src/runtime/vsl/vsl_nt_bridge.h` (syscall numbers) + `reactos-study/reactos/ntoskrnl/sysfuncs.lst`
(ordinal → name → arg-count). Transliterating one = writing a **real VSL handler**
in C that does genuine OS work, then wiring it into TWO dispatch tables and a
regression test. No stubs: every handler must do real work or be marked TODO.

As of 2026-07-09: **20/297 transliterated** (batch 1 = 10, batch 2 = 10). 277 remain.

## Batch 1 done (commit a15b04e, 2026-07-08)
9 NtAddAtom, 15 NtAlertThread, 16 NtAllocateLocallyUniqueId, 17 NtAllocateUserPhysicalPages,
18 NtAllocateUuids, 22 NtAssignProcessToJobObject, 25 NtCancelIoFile, 27 NtClearEvent,
81 NtFindAtom, 87 NtFreeUserPhysicalPages.

## Batch 2 done (commit a4ae8a9, 2026-07-09)
14 NtAlertResumeThread, 21 NtAreMappedFilesTheSame, 42 NtCreateJobObject, 63 NtDeleteAtom,
86 NtFlushWriteBuffer, 99 NtIsProcessInJob, 125 NtOpenJobObject, 158 NtQueryInformationAtom,
256 NtSetUuidSeed, 266 NtTerminateJobObject.

## The transliteration recipe (per syscall)
1. **Pick syscall number** from `vsl_nt_bridge.h` `#define NT_SYSCALL_NT<NAME> 0x00NN`.
   CROSS-CHECK against `reactos-study/reactos/ntoskrnl/sysfuncs.lst` ordinal — the
   bridge.h numbers ARE the ReactOS ordinals (verified: 9=NtAddAtom, 256=NtSetUuidSeed,
   266=NtTerminateJobObject all match). Use the correct ordinal or the handler lands
   in the wrong dispatch slot.
2. **Add a forward declaration** in `src/runtime/vsl/vsl_syscall_nt.c` near the other
   `vsl_nt_*` decls: `int64_t vsl_nt_<name>(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);`
   and the same `extern` line in `src/runtime/vsl/vsl_syscall_table.c` forward-decls block.
3. **Wire the slot** in BOTH tables:
   - local `g_nt_dispatch[]` init (`nt_dispatch_init`): `g_nt_dispatch[NN-1] = vsl_nt_<name>;`
   - canonical `vsl_syscall_table[]` (the big array): replace the
     `vsl_sys_nosys,  // NN: Nt<Name>` line with `vsl_nt_<name>,  // NN: Nt<Name>`.
   (Both are required: the local table backs the unit test's `vsl_nt_syscall_dispatch`;
   the canonical array backs the real runtime `vsl_syscall` path and `make runtime`.)
4. **Implement the handler** doing REAL work (examples below). Handler returns
   `NT_STATUS_SUCCESS` (0) on success, or a negative errno; the dispatch wrapper
   translates negative errno → NT status via `vsl_errno_to_nt_status()`.
5. **Add regression checks** to `src/runtime/vsl/vsl_syscall_nt_test.c`
   (the `vsl_nt_syscall_dispatch(&ctx, NN, args, n_args)` path), asserting FIXED
   behavior, not just non-crash. Then `make runtime && make hosted && make test`.

## Handler patterns that worked (real work, C11)
- **Atom table (NtAddAtom/Find/Delete/Query)**: process-local `g_nt_atoms[]` array,
  `strncpy` name, assign incrementing `g_nt_atom_next` id. Query returns name_len +
  ref_count + writes retlen out-param.
- **NtAllocateUuids (18)**: `getrandom(buf, count*16, 0)`, then set RFC4122 v4/variant
  bits (`p[6] |= 0x40`, `p[8] |= 0x80`). Test asserts those bits set.
- **NtSetUuidSeed (256)**: installs a global `g_nt_uuid_seed`; when nonzero, derive
  deterministic bytes via xorshift (`x ^= x<<13; x ^= x>>7; x ^= x<<17`) keyed on
  `seed ^ (i+1)*0x9E3779B97F4A7C15`. Test asserts same seed → same first byte.
- **NtClearEvent (27)**: `write(eventfd, &zero, 8)` resets counter; test reads
  EAGAIN after.
- **NtAlertThread/AlertResumeThread (15/14)**: `syscall(SYS_futex, uaddr, FUTEX_WAKE,
  INT_MAX, NULL,NULL,0)`; resume adds `kill(thread, SIGCONT)`.
- **NtCancelIoFile (25)**: `shutdown(fd, SHUT_RDWR)` so blocked IO unblocks.
- **NtAllocate/NtFreeUserPhysicalPages (17/87)**: `mmap(MAP_ANONYMOUS)` / `munmap`.
- **NtAreMappedFilesTheSame (21)**: `stat()` both paths, compare `st_ino`+`st_dev`.
- **NtFlushWriteBuffer (86)**: `fdatasync` with `fsync` fallback; tolerate
  `EINVAL`/`EROFS` (pipe) as success.

## ⚠️ PITFALL — Job objects MUST use an isolated sentinel-child process group
This is the #1 way to silently SIGKILL your own test. `NtTerminateJobObject`
does `kill(-pgid, SIGKILL)` (negative pid = whole group). If you make the
**caller** its own group leader via `setpgid(0,0)`, then `pgid == getpid()`,
and terminating the job kills the test process → exit 137 (SIGKILL), no useful
output.

**CORRECT pattern** (used in batch 2): `NtCreateJobObject` forks a sentinel child
that calls `setpgid(0,0)` then `for(;;) pause();` and records `child_pid` as the
job's `pgid`. `NtTerminateJobObject` does `kill(-child_pid, SIGKILL)` then
`waitpid(child_pid, &status, 0)` to reap it. The caller is NEVER in that group,
so it survives. Regression asserts: create→open(same id)→terminate→open-after
= NOT_FOUND.

## PITFALL — cross-handler state must be file-scope, declared BEFORE first use
The seed global is read inside `vsl_nt_allocate_uuids` (early in the file). A
`static` declared later → "undeclared (first use in this function)". Declare
`static uint64_t g_nt_uuid_seed = 0;` at file scope near the forward declarations
(before any handler that reads it). Same for any cross-handler state
(`g_nt_luid_counter`, `g_nt_atoms[]`, `g_nt_jobs[]`).

## PITFALL — build/test link weight in WSL
`make test_vsl_nt` links `-lvulkan -lcuda` — heavy. A naive single-shot run can
look like "Killed" (OOM, exit 137) or "hang" (the 180s timeout was just the
vulkan/cuda link compile, NOT a real hang). Re-run the built binary directly with
`timeout 25 stdbuf -oL ./src/runtime/wubu_vsl_nt_test` to get clean line-buffered
output. A genuine self-kill (job pitfall) also presents as exit 137 — distinguish
by WHERE it dies: self-kill dies mid-test (after "NtCreateJobObject"), OOM dies at
link/startup. Always read the actual last printed CHECK line.

## Find the next batch
Grep the canonical table for still-stubbed NT slots to transliterate next:
```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
grep -nE 'vsl_sys_nosys,  // [0-9]+: Nt' src/runtime/vsl/vsl_syscall_table.c
```
Pick ones that map to a real host primitive (file/ioctl/futex/mmap/fork/stat).
Avoid the ones needing full kernel semantics you can't emulate in userspace yet
(e.g. NtCreateProcess variants — prefer the already-mapped `vsl_sys_fork`/`clone`
shims where they exist, and only claim the syscall if you can do real work).

## Regression count
`vsl_syscall_nt_test.c`: 25 checks (batch 1) → **49 checks** (batch 2). Each new
syscall adds 1-5 CHECKs. The test's final line prints `Results: N passed, M failed`.
