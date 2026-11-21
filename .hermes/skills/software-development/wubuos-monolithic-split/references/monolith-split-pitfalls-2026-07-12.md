# Monolith-Split Pitfalls — 2026-07-12 Session Additions

New pitfalls discovered while splitting `wubu_metal.c` (1225 LOC → facade + 3
backend siblings) on top of the established `wubuos-monolithic-split` workflow.
Capture these so the next split doesn't re-hit them.

## 1. Internal-header include-order break (`math.h` before `linux/input.h`)

`wubu_metal_internal.h` includes `<linux/input.h>` (early) and `<math.h>` (later).
A sibling TU that includes the internal header AND pulls `<linux/input.h>` itself
triggers a cascade:

```
/usr/include/bits/mathcalls.h: expected ';' before 'extern'
```

**Root cause:** `<linux/input.h>` forward-declares macros/types that poison the
subsequent `<math.h>` parse when the order is wrong in a TU that includes both.

**Fix:** a sibling that needs only `g_input`/`g_display`/etc. should NOT include
the whole internal header. Instead **mirror the ORIGINAL monolith's include set**
(which is proven to compile) and declare only the externs it touches:

```c
#include "wubu_metal.h"
#include <stdio.h> <stdlib.h> <string.h> <unistd.h> <fcntl.h>
#include <dirent.h> <linux/input.h> <sys/ioctl.h>
extern WubuInput g_input;   /* pulled from facade via internal header decl */
```

The internal header is fine for siblings that DON'T include `<linux/input.h>`
(e.g. the Vulkan sibling) — but for those, prefer a self-contained local type
shim (see #2).

## 2. Vulkan / X11 `#ifdef ... #else` typedef blocks: keep them self-contained

When you extract a region that carries its own `#ifdef WUBU_USE_VULKAN` / `#else`
**typedef block** (e.g. `VkExtent2D`, `Display`, `Window`, `VkResult` forward
decls), DO NOT rely on the internal header's duplicate `#else` typedefs — they
redefine and fail:

```
error: conflicting types for 'VkExtent2D'
```

**Fix:** copy the self-contained typedef/macro block into the sibling so it
compiles standalone. The internal header's `#else` branch already declares
these for the non-Vulkan build, but the sibling's own `#else` must NOT redeclare
them — keep only the stub *function bodies* in the sibling, drop the dup typedefs.

Also: when slicing with `sed -n 'A,Bp'`, if the original's closing `#endif` sits
on line `B+1`, the sibling loses it → `error: unterminated #ifdef` / `#else`.
Re-append the closing guard in the sibling.

## 3. Low blast-radius check BEFORE rebuilding everything

Before running `make clean && make runtime && make hosted && make test`,
**grep where the split object is consumed** so you know the real blast radius:

```
grep -n "wubu_metal\.o\|wubu_metal\.c" Makefile
```

`wubu_metal.o` was only in `METAL_OBJS` (line 32) and the `test_metal` recipe
(line 686) — NOT in the `hosted` binary. So the split's blast radius was just
those two targets. Don't waste cycles rebuilding `hosted` for a `wubu_metal.c`
change.

**Pre-existing link errors are NOT your regression.** `test_metal` (a bare-metal
target) fails to link under hosted/WSL with `lapic_eoi` / `ioapic_route_irq`
undefined — these are kernel stubs that only resolve in the metal kernel build.
Confirm by `git stash` + rebuild the original: if it fails identically, it's
pre-existing. Your split is clean when ONLY metal-specific symbols resolve.

## 4. De-static shared globals when splitting a facade

If the facade defines `static WubuDisplay g_display;` etc. and a sibling now
touches them, **remove `static` in the facade** (default extern linkage) and
declare `extern` in the sibling. The internal header often already declares
them `extern` — verify, don't redeclare.

Pitfall: a botched Python `re.sub` that left `<T> g_x` placeholder text on the
global lines (e.g. `static WubuBootEnv <T> g_x = WUBU_ENV_UNKNOWN;`). If you
script the de-static, re-read the edited lines and fix any garbage before
compiling.

## 5. `make clean` stale-`.o` quirk (archd split fallout)

After `make clean`, `wubu_archd_fs.o` may not be rebuilt by `make hosted`
(it's in `HOSTED_OBJS` but not a direct prereq of the `hosted:` recipe). You'll
get `cannot find src/runtime/wubu_archd_fs.o: No such file or directory`. Fix:
`make src/runtime/wubu_archd_fs.o` once, then `make hosted`. This is a Makefile
dependency-order quirk, not a code regression.
