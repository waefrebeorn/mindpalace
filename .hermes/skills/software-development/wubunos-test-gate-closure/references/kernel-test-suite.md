# Kernel test-suite isolation model (wubuos `mk/tests.mk`)

Applies to the `src/kernel/test/` gate family (`test_tasking`, `test_mm`,
`test_str`, `test_snapshot`, `test_cap`, `test_vsl_nt`, ...), whose recipes in
`mk/tests.mk` compile kernel sources directly (not via the prebuilt
`$(KERNEL)/*.o` prereqs) with a hand-curated CFLAGS family.

## Always-on rule set (the recipe contract)
A wubuos kernel test recipe is recognized by this pattern:
```
$(CC) $(CFLAGS) -DWUBU_BAREMETAL=0 -O0 -g -I$(KERNEL) <sources...> -o <bin>
```
The CFLAGS that travel through `$(CFLAGS)` into these TUs include
`-D_POSIX_C_SOURCE=200809L`, `-DWUBU_NO_LIBM`, and (for hosted variants)
`-DWUBU_HOSTED`. **Standalone probes that drop any of these miscompile the
same sources**: without `-DWUBU_NO_LIBM`, `src/kernel/memory.c` builds its
malloc-backed allocator path whose `mem_init` never receives the metal seed
and returns a NULL heap -> every `mem_alloc` fails -> `task_create` returns
NULL -> the test reports a false "create failed" failure. **A false result is
worse than a skipped result; if the probe can't honor the recipe's defines,
stop and edit-in-the-suite rather than chasing a phantom.**

## Per-section isolation (THE gotcha)
Each kernel test SECTION is a self-contained `main()` that ends with:
```c
tasking_shutdown();      /* drains the task list, frees idle */
mem_shutdown();          /* tears down the 4 MiB heap (mem_free all) */
```
i.e. the allocator and the tasker are BOTH dead on section exit.
A NEW section/test inserted anywhere in the file MUST open with:
```c
mem_init(4 * 1024 * 1024);   /* rebuild the heap BEFORE tasking */
tasking_init();              /* rebuild idle + g_current */
```
Order matters: `tasking_init` calls `task_create("idle", ...)` which calls
`mem_alloc`, so `mem_init` must precede it. Skipping `mem_init` leaves
`count=0, cur=(nil)`, `tasking_init` returns -1 (idle create failed), and
every subsequent `task_create` returns NULL — indistinguishable from "the
feature is broken" if you don't check `init`'s return code.

A re-init that is the FIRST one after a shutdown also frequently fails
(the second succeeds); insert the new test AFTER an existing section that
already re-initializes (e.g. after `test_create_destroy`), never directly
after `test_init_shutdown` — that placement alone avoids the
first-reinit-after-shutdown quirk.

## Feature-macro nesting trap
Headers that are valid only under `-DWUBU_HOSTED` MUST live at file scope,
NOT inside an `#ifndef WUBU_BAREMETAL` block. Recipes that build the
hosted variant pass `-DWUBU_BAREMETAL=0`, and a defined-but-zero macro
STILL satisfies `#ifndef` being false — so an include nested under
`#ifndef WUBU_BAREMETAL` is silently skipped and the host-only symbols
(`mmap`, `PROT_*`, `MAP_*`) are undeclared at the use site.

## Host-only headers collide with the kernel libc
Do NOT `#include <unistd.h>` in a kernel TU that also pulls the kernel's own
`libc.h`: glibc's `pause()` has a different signature than the kernel
`libc.h` declaration, so you get
`conflicting types for 'pause'`. Pull only what the TU needs
(`<sys/mman.h>` for `mmap`/`mprotect`/`munmap`) and express the machine page
size as a constant (4096 on x86-64) instead of `sysconf(_SC_PAGESIZE)`,
which is the only thing `<unistd.h>` was being included for.

## Verify a new kernel test gate in two compiles
1. metal: `make test_tasking` — exercises the `mem_alloc`-backed stack +
   canary path (`#else` branch).
2. hosted: `make test_tasking_hosted` — exercises the `mmap` guard-page +
   `fork/SIGSEGV` proof (`#ifdef WUBU_HOSTED` branch). A gate is only green
   when BOTH pass; "metal only" covers the canary path but not the actual
   guard page.

The hosted variant currently (see session report) compiles clean but its
RUN is gated by the `src/kernel/memory.c` hosted allocator, which is an
open defect in its own right — do not fold a `make test_tasking_hosted`
run failure into a tasking.c regression.
