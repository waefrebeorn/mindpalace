# Opaque-struct split: test-compile breakage + fully-dissolved monolith link gap

Two monolith-split failure modes that bit the `fat32.c` dissolution
(2026-07-16) and are NOT covered by the generic "wire the new `.o` into the
link line" rule. Both surface only after the split compiles as modules.

## Failure A — the test harness stack-allocates the now-OPAQUE struct

When the monolith's public struct becomes opaque (`typedef struct foo foo;`
forward decl in `foo.h`, concrete layout in `foo_internal.h`), any existing
test that did `foo vol; foo_mount(&vol, ...)` on the STACK now fails to compile:

```
fat32_test.c:574:18: error: storage size of 'vol' isn't known
fat32_test.c:593:18: error: storage size of 'vol' isn't known
```

The test code is correct — it just can no longer see the struct body.

### Fix (verified green)
Make the test WHITE-BOX: add `#include "foo_internal.h"` right after
`#include "foo.h"` at the top of the test `.c`. That exposes the concrete
`struct foo` so the stack local `foo vol;` compiles. No production code needs
to change — only the test's includes. Do NOT switch the test to `calloc` just
to dodge this (unless the struct is genuinely huge — see the build-recovery
skill's stack-overflow note); a direct stack local is fine for a small volume
struct and keeps the existing test logic intact.

## Failure B — a FULLY-dissolved monolith: the test target links only the old modules

If the split goes all the way (the original `foo.c` ends up defining ZERO
public functions — it's reduced to a shared-helper file or deleted), the old
`test_foo` Makefile target still links only `foo.c + foo_name.c + foo_cluster.c`
(the pre-split set). The functions the test calls (`foo_mount`, `foo_dir_read`,
...) now live in the NEW modules (`foo_fat.c`, `foo_dir.c`, `foo_file.c`,
`foo_format.c`), so the link fails with `undefined reference to foo_mount`.

### Fix (verified green)
Update the `test_foo` recipe to compile+link EVERY split module, not just the
pre-split subset:
```makefile
test_fat32: $(KERNEL)/fat32.o
	$(CC) $(CFLAGS) -O0 -g -I$(KERNEL) \
	  $(KERNEL)/fat32.c $(KERNEL)/fat32_fat.c $(KERNEL)/fat32_dir.c \
	  $(KERNEL)/fat32_file.c $(KERNEL)/fat32_format.c \
	  $(KERNEL)/fat32_name.c $(KERNEL)/fat32_cluster.c $(KERNEL)/fat32_test.c \
	  -o $(KERNEL)/fat32_test
	$(KERNEL)/fat32_test
```
### Detect BEFORE the link (fast audit)
List which module actually defines each symbol the test calls, then confirm
all those modules are on the link line:
```sh
grep -hoE "foo_[a-z_]+\(" src/.../foo_test.c | sort -u | sed 's/(//'
grep -rln "^int foo_mount" src/.../*.c
```
If a defining module is missing from the `test_foo` recipe, add it.

## Why this is its own note, not part of the generic link-gap rule
The generic "MONOLITH-SPLIT LINK GAP" in the build-recovery skill is about
`ld: cannot find foo_a.o` (a missing OBJECT on a clean tree). These two are
DIFFERENT:
- Failure A is a **compile** error (`storage size isn't known`) — the test
  can no longer see the opaque struct.
- Failure B is an **undefined-reference** link error even on a warm tree,
  because the symbol moved to a module the recipe never links.
Both are consequences of *opaque-struct + full dissolution*, which the
link-gap note predates. Encode both here so a future fat32-style split skips
the rediscovery.

## Verification (fat32 case, 2026-07-16)
- `make test_fat32` -> `=== Results: 20/20 passed ===`
- `make kernel` links (after the boot-diff s were restored to HEAD).
- `make test` -> all tiers green.
