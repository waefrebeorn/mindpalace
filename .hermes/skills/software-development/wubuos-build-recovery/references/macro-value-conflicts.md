# Macro-value conflicts and pre-existing break triage

Verified 2026-09-30 on the `wubu_ftw.h` / `wubu_snapshot_internal.h` build break.

## Two headers, one macro, different values = include-order race

`wubu_snapshot_internal.h` defined its own `FTW_*` fallback set:

```c
#ifndef FTW_NS
#define FTW_NS  0x0004
#endif
#ifndef FTW_SL
#define FTW_SL  0x0010
#endif
#ifndef FTW_SLN
#define FTW_SLN 0x0010   /* aliases FTW_SL  */
#endif
#ifndef FTW_DP
#define FTW_DP  0x0004   /* aliases FTW_NS  */
#endif
```

`wubu_ftw.h` pins the POSIX values and proves them at compile time:

```c
typedef char wubu_ftw_unique_FTW_DP [FTW_DP  == 5 ? 1 : -1];
typedef char wubu_ftw_unique_FTW_SLN[FTW_SLN == 6 ? 1 : -1];
```

`wubu_snapshot_copy.c` includes `wubu_snapshot_internal.h` BEFORE `wubu_ftw.h`, so
the internal header wins the `#ifndef` race, `wubu_ftw.h`'s fallbacks are skipped,
and its asserts fire:

```
src/runtime/wubu_ftw.h:115:14: error: size of array 'wubu_ftw_unique_FTW_DP' is negative
```

**Fix:** delete the duplicated block and `#include "wubu_ftw.h"`. Do not re-add a
second value set — the asserts exist precisely to stop that.

### Why this was never merely cosmetic

`wubu_fs_unlink_cb` branches on `typeflag == FTW_DP` to choose `rmdir()` over
`unlink()`. With `FTW_DP` aliasing `FTW_NS`, every regular file takes the `rmdir`
path. The header comment records the earlier instance of exactly this bug.

## Diagnosing a macro-value compile error

Do not trust the source text. Dump what the preprocessor resolved:

```sh
gcc -E -dD -std=c11 -D_POSIX_C_SOURCE=200809L -Isrc/runtime \
    src/runtime/wubu_snapshot_copy.c 2>/dev/null | grep -aE '^#define (FTW_|DT_)'
```

That printed the conflicting set immediately:

```
#define FTW_SL   0x0010
#define FTW_SLN  0x0010
#define FTW_DP   0x0004
```

If `grep '^#define SYMBOL'` returns nothing but the macro clearly IS defined, the
macro is self-aliasing or expands to an enum — check the platform header.
`/usr/include/ftw.h` does `#define FTW_DP FTW_DP` (aliasing its own enum), so
`#ifndef FTW_DP` is always true regardless of the platform's real value.

## Proving a break predates your change

Use a throwaway worktree. **Do not use `git stash` for this.**

```sh
git worktree add /tmp/wt_prev HEAD~1
cd /tmp/wt_prev && make test_holyd 2>&1 | grep -aE 'undefined reference' | head -3
cd - && git worktree remove --force /tmp/wt_prev
```

`git stash pop` while testing a hypothesis can pop a PRE-EXISTING stash from
unrelated work and spray merge conflicts (including `modify/delete`) across the
tree. Recovery is `git reset --hard HEAD`, which works ONLY if your work is
already committed — so commit first, then experiment.

Also re-run the single failing compile line standalone. The flags decide which
header wins:

```sh
gcc -Wall -Wextra -std=c11 -O2 -g -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM \
    -I/usr/include/libdrm -Isrc/runtime -Isrc/runtime/vsl -Isrc/bridge \
    -Isrc/kernel -Isrc/compiler -c src/runtime/wubu_snapshot_copy.c -o /dev/null
```

## Known separate, still-open break

`test_holyd` fails to LINK with undefined `wubu_mir_*` symbols
(`wubu_mir_load`, `wubu_mir_store`, `wubu_mir_const`, `wubu_mir_binop`,
`wubu_mir_unop`, `wubu_mir_interp`, ...). Reproduces at `HEAD~1`, so it predates
recent work. The compiler link line in `mk/tests.mk` is missing the MIR object(s)
that define them — a distinct subsystem from the fs/FTW issue.
