# JIT Memory Backend Gotchas (2026-08-16)

## When JIT_CALL segfaults on the FIRST instruction despite correct emitted bytes

### Fingerprint
- `gen.code` hex dump before `JIT_CALL(exec)` is **correct** (e.g. for `"42"`:
  `55 48 89 e5 48 81 ec 00 01 00 00 48 b8 2a 00 00 00 00 00 00 00 c9 c3`).
- `jit_alloc_exec` returned a **non-NULL** pointer.
- gdb: `rip` lands inside the JIT region but the bytes at `rip` are `00 00`
  (`add %al,(%rax)`) — i.e. **zero-fill**, not your code.
- Under `WUBU_HOSTED`, `info proc mappings` shows **no `r-xp`/`r-xs` exec
  mapping** for the JIT; only `rw-p` or `rw-s`.

### Two root causes (check in this order)

#### 1. Missing `-DWUBU_HOSTED` on the compile line → `jit.c` picks the `#else` branch
The `#ifdef WUBU_HOSTED` guards the mmap/memfd backend. Without the flag,
`jit_alloc_exec` returns `malloc(size)` (plain RW heap, never executable),
`jit_lock_exec` is a no-op (`return ptr`), and `JIT_CALL` jumps into
non-executable heap memory → execute-disable SIGSEGV.

**Check:** grep the test recipe in `mk/tests.mk` for the flag. `holyc`,
`test_holyd`, `test_drivers`, `test_gauntlet`, `test_album` all carry it;
`test_holyc`, `test_battery`, `test_hedge` (pre-2026-08-16) did NOT.

**Fix:** add `-std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_HOSTED
-include wubu_gnu_compat.h -I$(RT)` to the recipe.

#### 2. memfd dual-mapping page mismatch (W^X kernel)
Even with `-DWUBU_HOSTED`, the `memfd_create → mmap(RW, MAP_SHARED) →
munmap → mmap(RX, MAP_SHARED)` sequence can produce **two 4KB aliases at
consecutive pages** whose perm bits disagree:

```
0x7ffff7fbb000  0x7ffff7fbc000  r-xs  /memfd:wubu_jit (deleted)   ← RX (the code)
0x7ffff7fbc000  0x7ffff7fbd000  rw-s  /memfd:wubu_jit (deleted)   ← RW (zero-fill)
```

`jit_lock_exec` returns the **RX alias** (`0x...b000`), but `JIT_CALL`
sometimes ended up at the **RW alias** (`0x...c000`) — or the RX view
didn't reflect the written bytes — and execution hit zero pages.

**Why it's hard to spot:** the bug is **intermittent** (depends on whether
the second `mmap` returns the same or a different VA), and gdb's `print
exec` lies if you're looking at a stale debug build.

### Working fix (2026-08-16)
Replaced the memfd dual-mapping backend in `src/jit/jit.c` (wubuos repo)
with a single anonymous `mmap(MAP_PRIVATE | MAP_ANONYMOUS, RWX)` followed
by `mprotect(RX)` at lock time. Verified on this host:

```
mmap(NULL, 4096, RWX, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0)  → alloc
memcpy(alloc, code, n)
mprotect(alloc, 4096, RX)                                → lock (in place)
JIT_CALL(alloc)                                          → runs correct code
```

The address is **stable** (mprotect is in-place), so `JIT_CALL` always
jumps to the page holding the emitted code. This is also what
`test_jit`/`test_jit_regression` already use for the minic backend.

### Quick diagnostic one-liner
```
make holyc_test   # if it segfaults, gdb:
gdb -batch -ex run -ex "info proc mappings" -ex "x/8i \$rip" ./src/compiler/holyc_test
```
If `$rip` is in a `rw-p`/`rw-s` region (not `r-x`/`r-xs`), the JIT buffer
is not executable → cause #1 or #2 above.
