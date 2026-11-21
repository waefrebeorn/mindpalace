# Monolith-Split Techniques (session-derived, 2026-07-13)

Condensed hard-won lessons from splitting `wubu_metal.c` (833→485, DRM/KMS
backend extracted to `wubu_metal_drm.c`). Companion to the SKILL.md PITFALLS.

## 1. Extraction near-miss: never slice a big facade via `read_file` + `execute_code`

`read_file` truncates at **500 lines** and frames every line as `NNN|CONTENT`.
Inside `execute_code`, `read_file(...).split("\n")` then `write_file` the
*slimmer* facade silently DROPS everything past line 500. This session did
exactly that on `wubu_metal.c` (833 lines) and wiped the unified
display/input/audio dispatch (lines 491–833) — a 137-line facade remained.
Rescued only by `git checkout -- src/hosted/wubu_metal.c`.

**Safe recipe to extract backend B out of facade F:**
1. `write_file B.c` with the extracted code (write_file does NOT truncate).
2. Remove the block from F with `patch` (fuzzy) targeting the exact
   `/* header */` + `#ifdef X` … `#endif` span. `patch` reads the real
   on-disk file, so no 500-line cap.
3. To find exact spans first, use `execute_code` +
   `subprocess.check_output(["cat", p]).decode().split("\n")` — NOT
   `read_file` — then drive `patch` from the computed 0-indexed bounds.
4. Keep F's dispatch calls (e.g. `wubu_disp_* → wubu_drm_*`); they now
   resolve against the new TU. Add `#include "B.h"` to F to kill
   implicit-declaration warnings (a real bug, not just noise).

## 2. Dead-macro / dead-code detection

Before extracting, `grep -rn "WUBU_USE_DRM" Makefile`. If the macro is
**never defined** in any compile/link flag, the "real" engine inside
`#ifdef X` is dead — only the stub `#else` compiled. That is a
form-without-function gap. When you extract, DEFINE the macro for the
relevant targets (`metal:`, `test_metal:`) so the real engine actually
builds and links (add `-I/usr/include/libdrm` + `-ldrm` where libdrm is
used).

A dead real-engine often carries latent compile errors once it finally
compiles:
- Re-defining libdrm's own structs (`struct drm_mode_atomic`,
  `drm_mode_object_properties`, `drm_mode_create_prop`) → collision.
  DELETE the hand-rolled structs; libdrm owns them.
- `DRM_FORMAT_XRGB8888` undeclared → add `#include <drm_fourcc.h>`.
Surface and fix these; that is real work, not churn.

## 3. Wire the new TU into EVERY compile site

A `src/hosted/` backend can be built by several independent Makefile
targets. After adding `B.o` to one list, grep for every sibling
(`wubu_metal_x11.o`, `wubu_metal_audio.o`, …) and mirror the addition:
- `METAL_OBJS` (for `metal:`)
- `HOSTED_OBJS_LIST` (for `hosted_objs:`)
- the `test_metal:` direct-link recipe
- `HOSTED_OBJS` / `METAL_OBJS` lists

Add a per-TU rule with the macro define when the generic
`$(HOSTED)/%.o: $(HOSTED)/%.c` rule lacks it:
```
$(HOSTED)/wubu_metal_drm.o: $(HOSTED)/wubu_metal_drm.c
	$(CC) $(CFLAGS) -DWUBU_USE_DRM -I$(HOSTED) -I$(KERNEL) -I$(RT) \
	      -I$(GUI) -I$(BRIDGE) -c $< -o $@
```
A missed site orphans the TU or yields an undefined-reference link in
only one target.

## 4. Test targets can be broken independent of your split

`make test_metal` links ONLY what its recipe lists. This session found it
missing `wubu_metal_audio.c` AND the APIC/PIT/syscall kernel objects
(`interrupt_apic.c`, `interrupt_pit.c`, `interrupt_syscall.c`,
`interrupt_timer.c`) → undefined `wubu_alsa_submit` / `lapic_eoi` /
`ioapic_route_irq` / `apic_init`. NOT a split regression — pre-existing
link gaps. After a split, run the full gate AND the backend's own test
target; if the only undefined symbols are unrelated to your extracted
functions, repair the link line (add the missing `.c`s + `-ldl` for the
audio dlopen path) rather than reverting the split.
