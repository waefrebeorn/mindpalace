# NT Transliteration — Session Lessons (2026-07-13)

Concrete pitfalls and reusable techniques from the E1 Batch 9 push (`bcf46a1`)
plus the `d51d974` `system()`-closure fix. Captured so the next session starts
already knowing them. Pairs with the SKILL.md "STALE COUNTS" and "handle-table
`data` slot" pitfalls.

## 1. Stale counts in skill docs — re-scan before claiming a gap
The `nt-ordinal-verification.md` "Already-transliterated" table said **88/297**;
a fresh scan of `tbl[N-1]` across `src/runtime/vsl/vsl_nt_*.c` found **108**
wired that day, **117** after Batch 9. The ordinal list is URL-correct, but the
COUNT and the "next candidates" list are stale (NtOpenDirectoryObject 120,
NtLockFile 106, NtQueryDirectoryObject 153, etc. were already wired).

**Rule:** never trust a handoff's or a skill's tally of "N transliterated". Run:
```python
import re, glob
tbl = set()
for f in glob.glob('src/runtime/vsl/vsl_nt_*.c'):
    tbl |= {int(x) for x in re.findall(r'tbl\[(\d+)-1\]', open(f).read())}
print('wired', len(tbl), 'of 297')
```
The v27 copy-paste next-session prompt also claimed "10 remaining `system()`
calls" and a "monolith frontier (startmenu/explorer/pkgmgr/metal)" — both FALSE
(the one real `system()` was already closed; those files were already split into
3–10-module families). A fresh audit found 0 live `system()` + 0 un-split hot-path
monoliths. **Always re-run the gate + re-scan before acting on a handoff's
frontier claims.**

## 2. Handle-table payload slot for OBJECT/DIRECTORY handles (SIGSEGV trap)
`vsl_nt_allocate_handle(ctx, vsl_fd, styx_fid, type)` takes the path/payload in
the **3rd argument = `styx_fid`**, but the query helper
`vsl_nt_handle_to_data(ctx, h, &out)` reads the **`data` field**, which
`vsl_nt_allocate_handle` does NOT set. The registry handlers
(`vsl_nt_create_key`/`vsl_nt_open_key`) set it AFTER allocation:
```c
uint32_t h = vsl_nt_allocate_handle(g_nt_ctx, -1, 0, NT_OBJECT_TYPE_KEY);
for (int i = 0; i < 4096; i++)
    if (g_nt_ctx->handle_table[i].valid && handle_table[i].nt_handle == h) {
        g_nt_ctx->handle_table[i].data = (uint64_t)(uintptr_t)strdup(dir);
        break;
    }
```
**Bug (Batch 9):** `vsl_nt_create_directory_object` passed `strdup(path)` as the
`styx_fid` arg and never set `.data`. `NtQueryDirectoryObject` then called
`vsl_nt_handle_to_data` → got `data==0` and crashed in `opendir(0xe7d07)`.
**Fix:** store the backing path in `.data`, exactly like the registry handlers.
Repro via `gdb -batch -ex run -ex bt` on the lite binary — it points straight at
the `opendir(name=<garbage>)` frame.

**General rule:** for any new object type that needs a backing path/pid/base,
set `handle_table[i].data` after `vsl_nt_allocate_handle`, and have query handlers
read it via `vsl_nt_handle_to_data`. Reserve `styx_fid` for its documented uses
(thread tid, section size).

## 3. nftw recursive-delete must `rmdir` FTW_DP (reusable C technique)
`wubu_fs_rm_rf()` (canonical recursive delete, used by `rm_rf`/proton,
`archd_rm_rf`, `bottles_rm_rf`, and `NtDeleteKey`) had a latent bug: its nftw
callback only called `unlink()`, which returns `EISDIR` on directory entries, so
`nftw` aborted the traversal and **silently left the whole tree in place**.
**Fix:** with `FTW_DEPTH`, directories are reported as `FTW_DP` (post-order) —
`rmdir()` those, `unlink()` regular files:
```c
if (typeflag == FTW_DP) return rmdir(fpath) == 0 ? 0 : -1;
return unlink(fpath) == 0 ? 0 : -1;
```
Verify with a standalone harness: before, `rm_rf rc=-1 errno=21 (EISDIR)` and the
tree survives; after, `rc=0` and the tree is gone.

## 4. E1 test is outside the gate — verify it every session
`make test` NEVER builds/runs `test_vsl_nt`. After ANY change to a `vsl_nt_*.c`
or `vsl_syscall_nt.c`, run the lite build (WSL2-safe, no `-lvulkan -lcuda` hang):
```bash
bash skills/software-development/wubuos-nt-transliteration/scripts/build_nt_test_lite.sh run
```
Always redirect to a file (forked children hold the stdout pipe; `| tail` hangs).
Reap stray `wubu_vsl_nt_test` children (`pkill -9 -f wubu_vsl_nt_test`) before
re-running.
