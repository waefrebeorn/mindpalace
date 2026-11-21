# Strict-C11 ftw shim probe recipe

Reproduces a "silent" runtime failure (e.g. `wubu_fs_rm_rf` returning nonzero,
breaking `NtDeleteKey`) under the EXACT build flags the Makefile uses, then
localises the cause as a shim-vs-libc enum value mismatch.

## 1. Reproduce with the real flags

Build a tracer that links the same `wubu_fs_util.o` the test uses — NO
`_GNU_SOURCE`:

```c
/* probe_ftw.c */
#define WUBU_HOSTED
#include "wubu_gnu_compat.h"
#include "wubu_ftw.h"
#include <stdio.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>

static int traced(const char *fpath, const struct stat *sb,
                  int typeflag, struct FTW *ftwbuf) {
  (void)sb; (void)ftwbuf;
  if (typeflag == FTW_DP) { int r = rmdir(fpath);
    printf("  rmdir  %s -> %d errno=%d %s\n", fpath, r, errno, strerror(errno));
    return r == 0 ? 0 : -1; }
  int r = unlink(fpath);
  printf("  unlink %s -> %d errno=%d %s\n", fpath, r, errno, strerror(errno));
  return r == 0 ? 0 : -1;
}
```

```sh
RT=src/runtime
gcc -O2 -std=c11 -D_POSIX_C_SOURCE=200809L -include wubu_gnu_compat.h \
    -I"$RT" -I"$RT/wubu_cap" -pthread -o /tmp/probe_ftw probe_ftw.c "$RT"/wubu_fs_util.c
```

## 2. Read the values

Under the strict flags, glibc `<ftw.h>` only emits the enum constants when
`_XOPEN_SOURCE >= 600` (i.e. `__USE_XOPEN_EXTENDED`). Without it, the
constants are enums (values visible only via `gcc -E`/running the code),
and any `#ifndef`-guarded shim define silently replaces them.

```sh
# glibc truth as it compiles under the project's strict flags:
grep -nE '^\s*FTW_[FDSN]|^\s*enum' /usr/include/ftw.h
# Confirm what actually reached the translation unit:
gcc -E -P -std=c11 -D_POSIX_C_SOURCE=200809L probe_ftw.c | grep -E 'FTW_DP|FTW_F'
```

For x86-64 glibc the enum values are:
`FTW_F=0 FTW_D=1 FTW_DNR=2 FTW_NS=3 FTW_SL=4 FTW_DP=5 FTW_SLN=6`,
with control flags `FTW_DEPTH=8 FTW_PHYS=1 FTW_MOUNT=2 FTW_CHDIR=4`.

## 3. Diagnose

If `unlink` of a *regular file* lands in the `FTW_DP` (rmdir) branch, the
shim's `FTW_DP` disagrees with the libc value — a shadowing defect. Fix the
shim (`src/runtime/wubu_ftw.h`) to the glibc numeric values; `rm -f` the
stale `wubu_fs_util.o` (the Makefile is incremental and will otherwise
re-link the old object); rebuild and re-run `make test_vsl_nt`.

## 4. Regression guard

A value-file survive check after `NtDeleteKey`:
`find /tmp/wubu_nt_reg_* -name Name` should print nothing after a clean run.
