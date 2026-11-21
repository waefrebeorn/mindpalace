---
name: wubunos-hosted-capture-bridge
description: "Link WM+GUI in hosted capture; Win98/XP parity rules + verification."
tags: [wubunos, gui, capture, hosted, kernel-boundary]
---

# WuBuOS Hosted Capture Harness Bridge

## Trigger Conditions
- Building a `wubu_*_shot` harness that compiles WM/GUI sources with `-DVBE_HOSTED`
- Need to init VBE + WM + create a window + capture frames WITHOUT a running kernel
- A capture harness recipe links kernel sources and hits `wdt_feed`/`syscall_handler`/`wubu_agi_kernel_*` undefined references

## Problem
WuBuOS has a hard boundary: the kernel sources (`src/kernel/interrupt.c`, `tasking.c`, `isr_stubs.S`, `memory.c`) are **bare-metal only** — they reference hardware symbols (`wdt_feed`, `handle_double_fault`, `syscall_handler`, `wubu_agi_kernel_*`) that don't exist in a hosted (`-DVBE_HOSTED`) binary. But the VBE/WM layer calls `mem_init()` and `input_init()` which are defined in those bare-metal files.

## Solution: Stub the kernel boundary in the test TU
Do NOT link `memory.c`/`input.c`/`interrupt.c` into the capture harness. Instead,
define the 3 functions the WM/VBE layer actually needs as **stubs in the harness
`.c` file itself** (before the GUI includes so the signatures match the headers):

```c
/* Hosted test stubs: mem_init/input_init live in bare-metal kernel sources
 * (memory.c/input.c) which pull wdt/irq/agi_kernel symbols. The VBE/WM layer
 * only needs a heap and an input queue — stub them here for the capture binary. */
int mem_init(size_t n) { (void)n; return 0; }
void *mem_alloc(size_t size) { (void)size; return (void*)1; }
int input_init(void) { return 0; }
```

**Critical:** match the header signatures exactly:
- `src/kernel/memory.h:87` → `int mem_init(size_t total_bytes);`
- `src/kernel/memory.h:101` → `void *mem_alloc(size_t size);`
- `src/kernel/input.h:48` → `int input_init(void);`

## Link dependencies (a11y_shot / gui_shot recipes)
The capture harness `$(CC)` line must include:
- **Kernel (minimal):** `$(KERNEL)/vbe.c` `$(KERNEL)/wubu_math.c` — NOT interrupt/tasking/memory/input
- **GUI sources:** all `wm_*.c`, `wubu_theme.c`, `wubu_a11y.c`, `wubu_wallpaper.c`, `wm_test_stub.c`
- **Runtime:** `$(RT)/styx*.c`, `wubu_session.c`, `wubu_spawn.c`, `wubu_fs_util.c`, etc.
- **Tools:** `$(TOOLS)/screenshot.c` (provides `wubu_shot_fullscreen`)
- **Libraries:** `-lwayland-client -lxkbcommon -lm -lsqlite3 -lzstd -lz -ldl -ljson-c -I/usr/include/libdrm`

## Hosted memory.c: the pattern rule
`src/kernel/memory.c`'s `mem_init()` picks its heap backing store by
compile-time macro: `-DMYSEED_METAL` selects the identity-mapped
physical heap (a low fixed address like `0x400000`) — valid in the
bare-metal kernel (PA==VA), a **guaranteed segfault in a hosted
userspace process**. The kernel pattern rule always passes
`-DMYSEED_METAL`, so ANY hosted binary that links the default-built
`memory.o` dies at startup in `memset <- mem_init`.

Fix: add a hosted-specific pattern rule in `mk/pattern-rules.mk`
AFTER the generic kernel rule so it wins the target:
```make
$(KERNEL)/memory.o: $(KERNEL)/memory.c
	$(CC) $(CFLAGS) -DWUBU_HOSTED -DWUBU_NO_LIBM -I$(KERNEL) -MMD -MP -c $< -o $@
```
and guard the source branch: `#if defined(MYSEED_METAL) && !defined(WUBU_HOSTED)`.
If a `.o` was already built by the wrong rule, `rm` it before rebuilding.

## -fopenmp poisons every hosted binary
If any linked source uses `#pragma omp` (e.g. `wubu_tgemm_avx512.c`),
link WITHOUT `-fopenmp` and compile that TU with a serial fallback:
guard `#include <omp.h>` and the `omp_get_max_threads()` call behind
`#ifndef WUBU_NO_OMP`, and pass `-DWUBU_NO_OMP` on that compile — the
`#pragma` lines become inert no-ops without `-fopenmp`. Linking WITH
`-fopenmp` crashes in libgomp's init (`__GI__IO_fwrite` under
`libgomp.so.1`) because libgomp writes to the process `stderr` FILE
handle, which `src/kernel/libc.c` redefines as a sentinel struct
(`g_kstderr`) whenever `WUBU_HOSTED` is NOT defined on that TU —
rebuild `libc.o` with `-DWUBU_HOSTED` too, or libgomp dereferences
a non-FILE. Serial is correct for a capture tool; never parallel.

## Pitfalls
- **`holyd_lifecycle_app.o` → `wubu_holyd_lifecycle.o`:** the source file is
  `src/runtime/wubu_holyd_lifecycle.c` but old recipes referenced
  `holyd_lifecycle_app.o` (wrong prefix + suffix). Use `wubu_holyd_lifecycle.o`.
- **`-I/usr/include/libdrm`:** `wubu_gbm.c` includes `xf86drm.h` → `drm.h`.
  Without this flag, `fatal error: drm.h: No such file`.
- **Double-escaped backslashes in Makefile recipe lines:** when patching recipe
  continuation lines, `\\` (2 actual chars) can become `\\\\` (4 chars) via the
  patch tool. Verify with `cat -A` — continuation is `\\` (1 backslash). Fix:
  Python splice with explicit backslash count.
- **Stale object trap:** if the recipe uses `.o` prerequisites instead of `.c`
  sources, every `.o` on the link line must be in the prereq list. Diagnostic:
  `find src -name '*.o' -older <edited_header>.h`.
- **Two checkouts, two roots — stage each path from its own repo.**
  `/home/wubu/wubunos` is the COMPILER repo: sources are flat at the repo
  root (`holyd.c`, `wubu_tgemm_avx512.c`), no `src/`, no `mk/`.
  `/home/wubu/wubuos` is the OS repo: `src/gui/`, `src/kernel/`,
  `src/runtime/`, `mk/` — and its `src/compiler/` is a symlink into the
  wubunos checkout. Git works from EITHER root for the files that root
  tracks; a `git add` naming the wrong path from the wrong root fails
  fatally and stages NOTHING ("did not match any files" from wubunos,
  "beyond a symbolic link" when staging `src/compiler/*` from wubuos) —
  in a multi-path `git add A B C` that aborts the whole batch, so the
  commit that follows lands zero files and reads as success. Stage
  compiler paths from wubunos, GUI/kernel/runtime/mk paths from wubuos.
  The two repos also carry DIFFERENT `mk/tests.mk` content: a link line
  fixed in one does not exist in the other, and the `gui_shot` /
  `a11y_shot` targets live only in the OS repo's tests.mk (from
  wubunos: "No rule to make target 'gui_shot'").
- **A successful link is not a working capture.** Diagnose runtime crashes in
  this order: `gdb -batch -ex run -ex bt ./<binary>` → the crashing frame names
  the subsystem. `memset <- mem_init` = hosted-heap bug (see "Hosted memory.c:
  the pattern rule"); `__GI__IO_fwrite <- libgomp` = the -fopenmp/`g_kstderr`
  collision (see "-fopenmp poisons every hosted binary").
- **Raw-address gdb breakpoints go stale across rebuilds.** An address copied
  from `disassemble` before a `make` can stop inside an ADJACENT function (an
  address read out of `wubu_shot_fullscreen` landed in `wubu_write_png`) or
  never fire — and a never-firing breakpoint reads as "that code path isn't
  taken", which sends the diagnosis backwards. Break on the function name or
  `file.c:line`, or re-derive the address after every rebuild.
- **Two no-information probe iterations = switch verification path.** When the
  same diagnostic returns nothing new twice in a row, stop iterating:
  `make a11y_shot` exercises the same `screenshot.c` writer and persists its
  frames, so it verifies chrome changes while a full-desktop harness is being
  diagnosed.
- **Capture harnesses link STUBS, not real subsystem sources.** The `*_shot`
  recipes link `wm_test_stub.c`, which provides a MINIMAL start menu
  (`tsm_*` state, a hardcoded item table, its own `startmenu_render`)
  with NO cascade registry, no real app catalog. A behavior that lives in the
  real `startmenu*.c` (nested cascades, registry, MIME-derived menus)
  CANNOT render in a capture harness, and a click there changes nothing.
  Verify real subsystem behavior in that subsystem's OWN test harness
  (`make test_startmenu` links the real `startmenu*.c`), not in
  the capture binary. Linking the real sources into a `*_shot` recipe pulls a
  large transitive graph (`wubu_mime_state`, era-app exec backends
  `wubu_exec_*`) that the harness doesn't carry — don't chase that link; use
  the subsystem test. To make a stub-vs-real choice per target, guard the
  stub block with `#ifndef WUBU_REAL_STARTMENU` and add the real sources +
  `-DWUBU_REAL_STARTMENU` to the one recipe that needs them.
- **Line-based Makefile edits silently drop recipe lines — "Permission denied"
  on a readable `.c` means a corrupted recipe, NOT a file-perms problem.**
  Splicing a Makefile by line list (Python `insert`/list-rebuild) can delete a
  recipe's `$(CC) …` compile line, leaving a bare `path/to/foo.c -o out` as the
  recipe; make then tries to EXECUTE the `.c` and reports
  `make: foo.c: Permission denied` even though the file is `rw-` and readable.
  Diagnose with `sed -n '<target>:,+2p' mk/tests.mk | cat -A` — if the `$(CC)`
  line is gone, the recipe is broken. ALWAYS `git diff --stat mk/tests.mk`
  after any Makefile edit and `git checkout --` to restore unintended
  deletions; a multi-line recipe's continuation `\\` also makes fuzzy string
  patches unsafe — prefer exact line edits + `git diff` verification.
- **Pixel-count assertions on shared colors are unreliable.** Under Win98 the
  menu background `startmenu_bg` is `RGB(0xC0,0xC0,0xC0)` — the same silver as
  the desktop/taskbar — so "count `startmenu_bg` pixels in the submenu column
  before/after" never proves a flyout opened. Assert the authoritative STATE
  (`g_submenu_open` transitions `0` then `1` across a Programs→category click
  chain) and use pixels only for colors unique to the element under test.
- **A themed unit test must restore the theme on exit.** Tests share global
  theme state; a test that sets `THEME_XP_LUNA_BLUE` and doesn't reset it makes
  a LATER dynamic-geometry test (e.g. taskbar height 30 under Luna vs 28 under
  Win98) fail. End every theme-setting test with `wubu_theme_set(THEME_WIN98_CLASSIC)`.
  Also sample a button face OFF the centered label — a center pixel hits the
  white glyph, not the face.
- **"Drawn but dead" is the default failure of a parity pass.** A control that
  renders but ignores clicks is not parity. Grep the launch path for `on_mouse`
  (missing = keyboard-only), then check draw-coords vs input-coords: the WM
  delivers window-relative coords but absolute-drawing apps hit-test absolute
  positions, missing every click by the window offset (fix: `x+=win->x` at the
  handler top). Full audit method + the `on_mouse` link footprint in the
  reference. A scrollbar whose render ignores the scroll offset is the same bug.
- **A new real-engine symbol the launch path calls needs a stub in the apps
  test.** `test_apps` links stubs, not the real app engine, so a new
  `on_mouse`/`on_scroll` handler referenced by the launch path goes `undefined
  reference` at link time unless added to `apps_test.c` AND
  `apps_test_stubs.c`.
- **A render-test recipe that drives `wm_render` MUST compile with
  `-DVBE_HOSTED`.** Without it `vbe.c` takes the kernel branch: `VBE_ALLOC`
  becomes `mem_alloc` (a kernel allocator) and `g_vbe.fb/back` come back NULL —
  the first `wm_render` → `vbe_set_pixel` SIGSEGVs at
  `g_vbe.back[...]=color`. The recipe's `$(CC)` line needs `-DVBE_HOSTED`
  (every VBE-rendering test like `test_wm` already carries it); a
  plain `-D_POSIX_C_SOURCE -DWUBU_NO_LIBM` line is the tell. Symptom: the test
  segfaults in `vbe_set_pixel <- vbe_fill_rect <- draw_wallpaper
  <- wm_render`.
- **Assert launch-rendered output by reading VBE's OWN frame buffer
  (`vbe_get_pixel` after `vbe_init`), not by scanning the `fb` you pass to
  `wm_render(fb,…)` / `wm_render_desktop`.** The WM's draw
  chain writes through `vbe_*` helpers into VBE's internal buffer, so the
  caller's `fb` stays black even when the window rendered fine — scanning it
  falsely fails the gate. Sample `vbe_get_pixel()` over the frame (or in the
  window region) instead; this is exactly how `wm_test` validates
  pixels. A "window drew" assertion written against the passed `fb` is
  testing the wrong surface.
- **A test with its own inline chrome stubs must forward-declare ONLY the WM
  entry points it calls — never `#include wm.h` to get them.**
  `src/apps/apps_test.c` defines a 7-arg `chrome_draw_window`
  stub, but `wm.h` declares the real 4-arg one returning
  `ChromeContentRect`; pulling the header in gives "conflicting types". Keep
  the inline stub and add local prototypes for the real linked functions
  (`wm_init/shutdown/window_count/render`). Relatedly, `DosGuiWindow`
  is OPAQUE in that TU — you cannot deref `win->x`; scan pixels instead.

## Verification
1. `make a11y_shot` → builds `wubu_a11y_shot` binary (no linker errors)
2. `./wubu_a11y_shot` → writes 5 PPM frames to `/tmp/wubu_a11y_shots/`
3. Convert: `for f in /tmp/wubu_a11y_shots/*.ppm; do convert "$f" "${f%.ppm}.png"; done`
4. Pixel-verify all 4 a11y palette colors in frame 1 (Green `#4CAF50`, Yellow `#FFB300`, Red `#E53935`, Purple `#9C27B0`)

For a full-desktop target (`gui_shot`), the pass condition is EXIT=0 AND every
frame listed in the harness exists under its output dir:
`make gui_shot >/tmp/shot.log 2>&1; echo EXIT=$?; ls /tmp/wubu_gui_shots | wc -l`

If the harness prints every "captured <path>" line but the output dir is
empty, treat EXIT=0 as unproven: check the harness's own startup
`system("rm -rf " OUT_DIR); system("mkdir -p " OUT_DIR)` pair before the
writer, and verify the chrome change through `make a11y_shot` (same
writer, frames persist) while diagnosing.

## Related skills
- `wubuos-test-suite` — stale-object trap + gate-blindness diagnostics
- `wubuos-build-recovery` — link-line triage, the 50+-source stop rule
- `wubuos-9p-namespace-subsystem` — when the WM render loop pushes state into
  a `/n/*` namespace module (weak-symbol decoupling so capture link lines that
  omit the bridge still link; the apps-test getter-stub footprint)
- `references/win98-xp-theme-parity.md` — per-surface Win98-vs-Luna chrome
  rules (title gradient direction, close/taskbar/start-orb treatment,
  the `Luna_start_button` era flag, the light-blue hover states, the 16×16
  menu-icon glyph pattern) + XP interaction semantics (single-click-select /
  double-click-launch with frame-clock detection) + the pixel-verification
  loop and the switch-to-a11y_shot rule when a harness diagnostic stalls
  + **functional-parity audit** (the window-relative-vs-absolute
  coordinate-space bug that silently kills all mouse input, the
  drawn-but-dead `on_mouse` grep method, the `on_mouse` link footprint in
  the stubbed apps test, and scroll-must-move-the-list)
