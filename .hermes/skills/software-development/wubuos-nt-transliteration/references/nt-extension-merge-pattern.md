# NT Extension Merge Pattern (2026-07-23)

How to link up a structurally-broken NT extension branch (exemplar:
`origin/nt-parity-wip` → merged via a `nt-plumbed` branch → pushed to
`origin/master` as `e6e7795`) WITHOUT regressing the green gate.

## Symptom of a broken branch
- `python3 scripts/nt_dispatch_collision_check.py` reports ~60 colliding `tbl[N-1]`
  slots: two handlers registered at the same ordinal → one silently overwrites the
  other → the wrong handler runs → SIGSEGV on the first test call.
- The branch's `vsl_syscall_nt_test.c` dispatch numbers are desynced from the args
  each call passes (corrupted ordinal scheme). A name-heuristic remap
  (`NT_ORD_NtXxx` macros derived from a nearest-COMMENT scan) re-crashes because the
  scan grabs the NEXT section's name at section boundaries.

## Correct merge sequence (verified green: 251 NT tests, full gate ALL PASSED)
1. Branch from master: `git checkout -b nt-plumbed`.
2. Copy the branch's `vsl_nt_*.c` files in, then split NEW vs MODIFIED:
   - **NEW** (absent from master): keep. These are the 8 extension modules
     (alpc, wnf, worker, enclave, ioring, partition, ktm, misc_w11) + 2 headers
     (`vsl_nt_ordinal_translate.h`, and any auto-generated `vsl_nt_ordinal.h`).
   - **MODIFIED** (present in master, different content): `git checkout
     origin/master -- <file>` to revert to master's working handler. Do NOT keep the
     branch's weaker re-implementation.
   Detection: `git diff --name-only master...origin/nt-parity-wip | grep vsl_nt_`;
   for each path test `git cat-file -e master:<path>` to split NEW vs MODIFIED.
3. Wire each new module: add `vsl_nt_<subsys>_register(g_nt_dispatch, NT_TBL_SIZE);`
   to `nt_dispatch_init()` in `vsl_syscall_nt.c`, and add
   `$(RT)/vsl/vsl_nt_<subsys>.o` to `Makefile` `VSL_NT_OBJS` (the `test_vsl_nt` target
   links that list — NOT `RT_OBJS`/`HOSTED_OBJS`). Missing either → `undefined
   reference to vsl_nt_<subsys>_register` at link time.
4. Add dependencies the new modules need:
   - `NT_STATUS_INSUFFICIENT_RESOURCES 0xC000009A` and `NT_STATUS_NOT_SAME_DEVICE
     0xC00000D4` to `vsl_nt_bridge.h` (grep first: `grep -nE 'define NT_STATUS_'
     src/runtime/vsl/vsl_nt_bridge.h`; add only the missing).
   - `uint32_t wnf_notify_event;` field to `vsl_nt_bridge_ctx_t` (the new files
     dereference `ctx->wnf_notify_event`; an absent field is a compile error).
5. Restore master's test: `git checkout origin/master --
   src/runtime/vsl/vsl_syscall_nt_test.c`. Do NOT use the branch's corrupt test file.
6. Collision-check: `python3 scripts/nt_dispatch_collision_check.py` → exit 0.
7. Gate: `make runtime && make hosted && make test` (ALL PASSED) and
   `make test_vsl_nt` (251 passed, 0 failed).
8. `git checkout master && git merge --no-ff nt-plumbed && git push origin master`,
   then `git branch -d nt-plumbed`.

## Pitfall: the 21-failure trap
If you `git checkout` the branch's MODIFIED files over master (instead of reverting
them), the branch's stub-ier re-implementations replace master's working handlers and
`make test_vsl_nt` drops from 251/0 to **230 passed, 21 failed**. The 21 failures are
all behavioral gaps in the branch's handlers:
- `NtAllocateLocallyUniqueId` returns wrong / LUID low part 0
- `NtAssignProcessToJobObject` doesn't move child into job pgid
- `NtAllocateUserPhysicalPages` / `NtFreeUserPhysicalPages` no-ops
- `NtAreMappedFilesTheSame` wrong (hardlinks / missing path)
- `NtCreateFile` doesn't create a file, returns no handle
- `NtWriteFile` / `NtReadFile` round-trip broken
- `NtSetInformationFile` doesn't truncate, `NtFlushBuffersFile` no fsync
- `NtQueryVolumeInformationFile` returns 0 bytes
- `NtClose` doesn't free the handle, `NtResetVirtualMemory` no decommit
- `NtLockFile` / `NtUnlockFile` no advisory lock
- `NtQueryOpenSubKeys` fails

Fix = revert the ~14 MODIFIED files to master; keep only the ~9 NEW files.

## Pitfall: extension ordinal range
`sysfuncs.lst` has ZERO ALPC/W11 entries. Assign extension handlers to **297+
contiguously** (stable subsystem grouping: alpc 23, transaction 20, wnf 10, enclave 5,
ioring 4, partition 8, worker 7, …). Never copy ordinals from `sysfuncs64.h`
(arg-counts, different line order — NtClose=13 there vs 28 in lst). The authoritative
base ordinal is `sysfuncs.lst` line number.
