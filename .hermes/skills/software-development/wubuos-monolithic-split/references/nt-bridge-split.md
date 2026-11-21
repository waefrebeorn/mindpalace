# Splitting vsl_syscall_nt.c (the E1 NT-bridge monolith) — pitfalls

Captured while decomposing the 1464-LOC `src/runtime/vsl/vsl_syscall_nt.c` into a
214-LOC facade + six self-contained modules (`vsl_nt_atoms/io/job/proc/sync/
registry.c`) behind `vsl_nt_internal.h`. These are the hazards SPECIFIC to
splitting a file that mixes (a) file-scope shared statics, (b) mid-file helper
functions, and (c) a dispatch table. General split procedure is in the parent
SKILL.md; these are the sharp edges that bit this session.

## 1. Shared file-scope statics must become `extern` in the header, defined ONCE
`vsl_syscall_nt.c` owned `g_nt_atoms[]`, `g_nt_atom_next`, `g_nt_jobs[]`,
`g_nt_job_next`, `g_nt_uuid_seed`, `g_nt_ctx`, `g_nt_reg_root`, and
`g_nt_luid_counter`. After the split these are referenced by EVERY module, so:

- Declare them `extern` in `vsl_nt_internal.h` (the header the modules include).
- In the FACADE (`vsl_syscall_nt.c`) they must NOT be `static` — drop `static`
  from each so they match the `extern` decl. (A module that re-declares one as
  `static` → `static declaration follows non-static declaration` error.)
- Define each exactly ONCE in the facade. Do NOT let a module also define it.

`g_nt_luid_counter` in particular is defined in `vsl_nt_atoms.c` (the module that
uses it) — that module must declare it WITHOUT `static` (matching the header's
`extern`), and the facade must NOT also define it.

## 2. Mid-file helpers get captured into the WRONG module by a line-range slicer
A naive "extract lines [L1,L2]" slicer grabs whatever sits between two batch
groups. `nt_atom_lookup()` (helper for atoms), `vsl_nt_thread_tramp()` and
`vsl_nt_proc_pid()` (helpers for the process/thread batch) sit BETWEEN batch
groups in the original file, so they landed in the wrong module
(`vsl_nt_io.c` got the trampoline; `vsl_nt_atoms.c` got a duplicate `proc_pid`).

Fix: place each helper in the module that owns its dependencies:
- `vsl_nt_thread_tramp` + `vsl_nt_proc_pid` → `vsl_nt_proc.c` (they touch the
  thread-params type and the process handle table).
- `nt_atom_lookup` → `vsl_nt_atoms.c`.
After slicing, grep `^<name>(` across all modules to confirm each definition
exists exactly once and in the right file.

## 3. Duplicate `vsl_nt_<subsys>_register()` + orphaned comment blocks from splice edits
When you INSERT a new handler block with a `patch` whose `old_string` is too
short, the replacement can leave a SECOND copy of the register function and a
stray `/* BATCH N ... */` comment floating mid-file (this happened in proc.c: the
original `vsl_nt_proc_register` got stranded after the batch-6 comment, producing
`redefinition of 'vsl_nt_proc_register'`). Symptom: `error: redefinition of
'vsl_nt_proc_register'`. Fix: `grep -n "void vsl_nt_proc_register" <file>` — if
it appears twice, delete the orphaned one (and its trailing comment) so exactly
ONE register fn ends the file. Always make the register fn the LAST thing in the
module.

## 4. `static` vs `extern` global collision on shared types
The facade defined `nt_atom_entry_t` / `nt_job_entry_t` as local types and the
modules needed them — but the modules ALSO tried to define the same struct
(anonymous in job.c) or the same global (`g_nt_job_next` as `static`). Result:
`conflicting types for 'g_nt_jobs'` / `static declaration follows non-static`.
Fix: the header owns the type + `extern` global decls; the facade defines them
(non-static); modules reference only. Never redefine a shared type or global in a
module.

## 5. `_DEFAULT_SOURCE` for `MADV_*` under `-D_POSIX_C_SOURCE`
If any module uses `madvise()` (e.g. `NtResetVirtualMemory`), the internal header
must `#define _DEFAULT_SOURCE` at its very top (before `<sys/mman.h>`). See
`references/nt-batch8-handler-contracts.md` §5 in the nt-transliteration skill.

## 6. Module TUs need their own includes; the facade shares them
Every `vsl_nt_*.c` includes `vsl_nt_internal.h` FIRST, which pulls
`vsl_nt_bridge.h` + `vsl_syscall_internal.h` + all needed system headers
(`<sys/mman.h>`, `<sys/eventfd.h>`, `<sys/uio.h>`, `<sys/statvfs.h>`, `<sched.h>`,
`<pthread.h>`, `<semaphore.h>`, `<dirent.h>`). The facade also needs to include
`vsl_nt_internal.h` now (it uses the types the modules share). Keep the header's
include block the single source of truth for system headers.

## 7. Makefile: add every new module `.o` to THREE places
`RT_OBJS`, the runtime link recipe line, AND the `test_vsl_nt` direct-compile
recipe (if you run the lite build). Miss one → `undefined reference to
vsl_nt_<x>`. The lite-build recipe lives in skill `wubuos-nt-test-lite` (the
Makefile `make test_vsl_nt` hangs under WSL2 on `-lvulkan -lcuda`).
