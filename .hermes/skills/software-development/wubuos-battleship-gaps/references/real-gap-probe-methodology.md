# Real Gap Probe Methodology — refinement (2026-07-07 session)

## The trap
BATTLESHIP per-file counts ("~53 fileio", "~67 net", "~65 styxfs", "~46
network") are dominated by:
- 6-arg syscall shim void-casts `(void)d; (void)e; (void)f;` — correct by design
  (handlers take 6 ABI slots, use 1–2). ~170 of these in `vsl_syscall.c` alone.
- intentionally-empty `*_test_stub.c` linker shims (e.g. `wm_test_stub.c`,
  `term_test_stub.c`) — exist only so test binaries link.
- no-op lifecycle fns (`bridge_shutdown`, `task_preempt_disable/enable`).
- error-path defensive returns (`if (!mgr) return -1;`) — NOT gaps; the happy
  path works.

Chasing a file because its per-file count is high is the wrong move. Read the
function first.

## Refined probe (AST + heuristic)
A Python scan that:
1. Excludes `src/**/*_test*.c` and known no-op lifecycle fns.
2. For each function body, detects:
   - **empty `{}`** after stripping `(void)x;` lines.
   - **const-only return**: returns only `-1/0/NULL` and makes NO host syscall
     call (so it's not a legit error/success wrapper).
   - **dropped-buffer gap (NEW heuristic)**: function takes a `*buf`/`out`/`data`/
     `result` param but never writes to it — no `*buf =`, `memcpy(dst,…)`, `->`,
     AND makes no host syscall that writes (`stat`/`fstatat`/`lstat`/`read`/
     `pread`/`readlink`/`getdents`).
3. For each candidate, **READ THE ACTUAL FUNCTION** to confirm it's on a success
   path that should do work (not an error guard, not a no-op lifecycle fn).

`scripts/find_real_gaps.py` covers the empty-body + const-only case. The
**dropped-buffer** heuristic is the highest-signal addition — it catches
functions that silently swallow an output pointer (true form≠function).

## Concrete verdicts this session (gate-tested layer)
- `vsl_syscall_fileio.c` — **REAL**. `open`/`openat`/`creat`/`truncate` already
  pass `flags`+`mode` through to `vsl_open`/`open`. The "~53" was void-cast
  noise + the 6-arg shard. NOT a to-do list.
- `vsl_syscall_memory.c` — **REAL**. `mmap`/`mprotect`/`shm*`/`mremap` all
  forward their args. 0 dropped-buffer gaps.
- `wubu_network.c` — **REAL** in-memory impl (create/inspect/enable/disable,
  DNS records, firewall rules, endpoints, stats). The `TODO-NET` block is
  *documented limitations* (no netlink/tc on host), not form≠function stubs.
- `styx.c` / `styxfs.c` — **REAL**. 9P parse/handle callbacks all write to the
  caller's buffers via `memcpy`/`stat`/`read`. 0 pure-return stubs.
- `vsl_syscall_net.c` — **REAL**. Handlers return error/success after real host
  socket calls; the "return const" grep false-positives on the legit
  `result < 0 ? -errno : (int64_t)result` pattern.
- `wubu_x86.c` "placeholder" comments = rel32 backpatch slots (patched later by
  the assembler), NOT empty stubs.

The board's top-of-list files (wubu_metal, vsl_syscall_net, styxfs) are thus
**dominated by void-cast/error-path noise** — verify per-function before
counting them as gaps.

## The real gaps found & closed this session
- `vsl_sys_getresuid` / `getresgid` (**e89c828**): backfilled `suid`/`sgid` from
  a HOST `getresuid(NULL,NULL,&s)` call — there was no `suid`/`sgid` field on
  `VSL_PROC` at all. Fixed by adding the fields + per-process tracking at spawn
  (`vsl.c` PID-1 + `register_child_pid`) and persisting them in the *set*
  handlers. The test caught it: pre-fix, host saved-set disagreed with euid in
  WSL → 2 FAILs.
- `wubu_proton2.c::wubu_proton_verify_installation` (**b33ca26**): returned 0
  (success) whenever `container_running`, never checked that Wine or the
  WINEPREFIX actually existed. Fixed with `access(wine_path, X_OK)` +
  `stat(prefix, S_ISDIR)`. Test asserts it now rejects missing wine/prefix.

## Pitfall: two parallel Proton modules
- Legacy `src/runtime/wubu_proton.c` (PE/Win32→VSL, DXVK INI, prefix mgmt) is
  built + tested by `make test_proton` and is in `RT_OBJS`.
- Newer `src/runtime/wubu_proton2.c` (Arch container + real Wine/DXVK,
  GameScope) is built + tested by `make test_proton2` and is ALSO in `RT_OBJS`.
- A Proton gap living in `wubu_proton2.c` is **NOT** exercised by `test_proton`.
  When closing a Proton gap, target the right module and add the assertion to
  the matching test (`wubu_proton2_test.c` for `wubu_proton2.c`). Note
  `wubu_proton_t` (legacy, used by `wubu_proton_test.c`) ≠ `WubuProtonManager`
  (used by `wubu_proton2.c`) — don't mix the two type names.
