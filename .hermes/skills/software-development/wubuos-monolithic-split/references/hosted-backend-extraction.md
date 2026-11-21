# Hosted-backend extraction (WuBuOS `src/hosted/*.c` monolith splits)

Condensed, session-agnostic techniques that emerged while splitting
`wubu_metal.c` (1225→833) into `wubu_metal_evdev.c` / `wubu_metal_x11.c` /
`wubu_metal_vulkan.c`, and `wubu_archd.c` (892) into `wubu_archd_daemon.c` /
`wubu_archd_svc.c`. Pair with the main SKILL.md procedure and
`references/dedup-shared-core-patterns.md` (§12 lists the `src/hosted/` audit
gap; this file closes it).

## A. Audit the RIGHT dirs first
`find src -name '*.c' | xargs wc -l | sort -rn` — the monoliths are not all in
`src/runtime/` / `src/gui/`. `src/hosted/` holds `wubu_metal.c` (~1225),
`hosted.c` (~1219), and `wubu_vulkan.c` (~990). Do NOT trust a "all monoliths
split" claim that only audited two dirs.

## B. De-static the FACADE GLOBALS for cross-TU access
When a backend is extracted to a sibling TU, the parent module's globals it
touches must lose `static`. Example: `wubu_metal.c` had
`static WubuDisplay g_display; static WubuInput g_input; static WubuAudio
g_audio; static WubuBootEnv g_env; static bool g_initialized;`. The extracted
`wubu_metal_evdev.c` references `g_input`, `wubu_metal_x11.c` references
`g_display`, `wubu_metal_vulkan.c` references `g_display` + `g_initialized`.
Fix: drop `static` on those 5 globals in the facade (they become `extern` by
default in C). The existing sibling `wubu_metal_audio.c` ALREADY referenced
`g_audio` without a local copy — confirming the facade globals were meant to be
shared. (Pure function-helper promotion is a different step; see §C.)

## C. Promote file-static HELPERS to extern (declare in internal header)
Shared `static` helpers (e.g. `wubu_archd.c`'s `archd_log`, `archd_write_pid`,
`archd_socket_create`, `archd_scan_roots`; `wubu_metal.c`'s `wubu_evdev_*`,
`wubu_x11_*`, `wubu_vk_create_*`) become non-static in the module that DEFINES
them, and are declared `extern` in an internal header
(`wubu_archd_internal.h`, `wubu_metal_internal.h`). The sibling that CALLS them
includes that header. Mechanical: `sed -i -E 's/^static (ret fn)/\1/'`.

## D. Include-order break: do NOT pull the fat internal header into a sibling
`wubu_metal_internal.h` includes `<linux/input.h>` (line 23) BEFORE `<math.h>`
(line 29). A sibling that `#include "wubu_metal_internal.h"` then triggers
`/usr/include/.../bits/mathcalls.h: error: expected ';' before 'extern'` —
because `linux/input.h` poisons a macro that breaks `math.h` parsing. The
ORIGINAL `wubu_metal.c` compiled ONLY because it did NOT include the internal
header. Fix: the extracted sibling should MIRROR the original file's include
set (proven to compile) + declare just the `extern` globals it touches (e.g.
`extern WubuInput g_input;`). Do NOT include `wubu_metal_internal.h` from a
sibling that also needs `<linux/input.h>`. The Vulkan sibling is the exception:
it does NOT need `linux/input.h`, so it MAY include `wubu_metal_internal.h`
(safe) — OR, cleaner, carry its own local Vk type shims (§E).

## E. Extracting a `#ifdef WUBU_USE_VULKAN` / `#ifdef WUBU_USE_DRM` backend
These blocks have a REAL-impl branch (`#ifdef`) AND a stub branch (`#else`)
that BOTH define the same symbols. Slicing the region must capture the WHOLE
nested `#ifdef … #else … #endif`, OR the `#else` stub functions reference
undefined types (`VkResult`, `Display`, `VkSurfaceKHR`, …).

- For Vulkan: the `#else` block carries the local type shims
  (`typedef int VkResult; typedef void *VkInstance; … #define
  VK_ERROR_EXTENSION_NOT_PRESENT -86`). KEEP them in the sibling (or restore
  them locally) — do NOT strip them as "duplicate" just because
  `wubu_metal_internal.h` also declares stubs in ITS `#else`. Stripping leaves
  `unknown type name 'VkResult'`.
- For DRM: the `#ifdef WUBU_USE_DRM` block at the TOP of the file holds the
  ioctl struct defs (`struct drm_mode_atomic`, `DRM_IOCTL_MODE_ATOMIC`, …) AND
  `drm_atomic_commit` / `drm_get_*_props`. When extracting the DRM backend,
  move the WHOLE `#ifdef WUBU_USE_DRM … #endif` region (struct defs + impls),
  not just the `wubu_drm_*` API functions, or the impls won't compile.
- Verify balance before cutting: `grep -cE '#ifdef|#ifndef'` == `grep -cE
  '#endif'` and `#else` count ≤ `#ifdef` count over the sliced range.
- If the sliced range ends exactly on a `}` with no trailing newline, the final
  `}` is DROPPED by `sed -n 'A,Bp'` — `printf '}\n' >> file` to fix.

## F. `hosted` binary link regressions exposed by splits (latent, masked by stale binary)
The `hosted:` link line may not actually list `$(RT_OBJS)` — it only lists a
hand-picked subset (e.g. `$(RT)/styxfs_vfs.o … $(RT)/wubu_fs_util.o`). After a
split, symbols the hosted shell now needs (e.g. `wubu_archd_svc_restart`,
`wubu_archd_health_check` from `archd_hosted.o`) become undefined. Probe:
`make -n hosted | grep -oE 'src/[a-z]+/[a-z_0-9]+\.o' | sort -u` — count the
objects the link PLANS to use; compare against what defines the missing symbol.
Fix: add the needed sibling `.o`(s) to the `hosted:` link line. NOTE the
`archd_hosted.o` recipe compiles ONLY `$<` (the daemon source) — so it does NOT
contain the svc symbols; add `wubu_archd_svc.o` explicitly. And `wubu_archd_daemon.o`
(HAS `main`, gated by `WUBD_TEST_MAIN` in `archd_hosted.o`) must NOT be linked
into `hosted` (conflicts with `hosted.o`'s `main`) — keep it out of `RT_OBJS`
for the hosted build; `hosted` gets archd via `archd_hosted.o` + `wubu_archd_svc.o`.

## G. `test_metal` is NOT in the gate — don't chase its link errors
`make test` (the gate) does NOT run `test_metal`. `test_metal` is a bare-metal
target that links `kernel/interrupt.c` and fails with PRE-EXISTING undefined
refs (`lapic_eoi`, `ioapic_route_irq`, `apic_init`, `syscall_init`,
`lapic_timer_init`) — these are real-APIC stubs absent in the hosted/WSL build,
present on HEAD BEFORE any split. After a metal split, confirm ONLY the
metal-specific symbols resolve (`g_*`, `wubu_evdev_*`, `wubu_x11_*`,
`wubu_vk_*`) — if those are clean and the gate is green, the split is correct.
Do NOT treat the `lapic`/`ioapic` errors as a regression.

## H. Verify a hosted split
1. `make runtime hosted apps` green (the three primary shipped binaries).
2. `make test` gate green (all tiers) — this is the real acceptance bar.
3. If `hosted` fails after `make clean` with `cannot find … .o`, it's a
   cold-build prereq race on a `.o` the `hosted:` target links but doesn't
   prereq (e.g. `wubu_archd_fs.o`). Build it explicitly once, or wire the
   prereq. Not a code regression — see `dedup-shared-core-patterns.md` §3/§13.
