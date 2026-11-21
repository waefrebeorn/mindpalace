---
name: wubuos-test-suite
description: Run and verify WuBuOS test suite across all subsystems (kernel, runtime, GUI, JIT, containers, network, OCI, snapshots, HolyC, Proton, etc.)
category: software-development
---

# WuBuOS Test Suite Skill

## Overview
WuBuOS's `make test` gate is the green bar — run it for the live target/assertion count. A tiny set of targets that still
fail at HEAD are listed under "Known pre-existing broken targets" below
(`test_runtime`, `test_image`). Most reds you hit are Makefile recipe defects
or shared-code regressions — see the triage sections. Verify your change with
the shared-lib + `git stash` checks so you don't mistake a pre-existing red for
your regression.

## Test Targets (from Makefile)
Run individual test targets:
```bash
cd /home/wubu/wubuos
make test_jit           # JIT encoder/disasm/ASMJIT/MIR/minic (76 tests)
make test_memory        # Heap, red zones, canaries (29 tests)
make test_vsl           # Syscalls, ELF, drivers, SHM, identity/RES (87 tests)
make test_vsl_nt        # E1 ReactOS-NT bridge: cap-backed handles, sidset/SRM facade, revoke-cascade-to-alias, job objects — OUTSIDE the gate tiers, run it explicitly for VSL NT work
make test_oci           # Native HTTP, registry, manifests (10 tests)
make test_network       # 9 profile types, CNI, WG, TS (139 tests)
make test_snapshot      # Overlayfs, branches, GC (132 tests)
make test_holyd         # HolyC DOS daemon, 9P, sessions (33/32 passed)
make test_proton        # PE32/64, Win32→VSL, DXVK (32 tests)  [legacy wubu_proton.c / wubu_proton_t]
make test_proton2       # Proton manager + gamescope (15 tests) [wubu_proton2.c / WubuProtonManager]
make test_ahci          # SATA driver, sim disk (16 tests)
make test_fat32         # FS, RAM disk, persistence (20 tests)
make test_txfs          # WAL, CRC, crash recovery (25 tests)
make test_gaad          # Golden subdivision, feng shui (17 tests)
make test_drm_direct    # Direct DRM/KMS ioctl (1 test)
make test_wubu          # .wubu containers, universal exec (47 tests)
make test_host_exec     # Fork+exec, presets (15 tests)
make test_bridge        # VBE↔WorldSim (25 tests)
make test_syscall       # 26 ZealOS-compat syscalls (5 tests)
make test_wubu_wm       # Win98 desktop, GAAD snap (18 tests)
make test_apps          # pkg, VSL, Proton, compiler (15 tests)
make test_styx          # 9P2000 protocol (29 tests)
make test_styxfs        # Mount, serve, .wubu detect (11 tests)
make test_archd         # Arch roots, GPU, events (16 tests)
make test_holyc         # Lexer, parser, codegen, PTX (84 tests)
make test_tasking       # Priority, sleep/wake (17 tests)
make test_input         # Key/mouse queues (11 tests)
make test_deploy        # ISO, WSL, Docker, macOS (9 tests)
make test_gc            # Mark/sweep for HolyC (10 tests)
make test_iso           # Bootable ISO, El Torito (20 tests)
make test_weights       # Vision model check (8 tests)
make test_anticheat     # BE/EAC/Vanguard DB (14 tests)
make test_bottles       # Wine/Proton/Lutris/Flatpak (17 tests)
make test_startmenu # Win98 start menu (4 tests)
make test_explorer  # File manager (74 tests)
make test_pkgmgr        # SQLite, zstd, .desktop (11 tests)
make test_wm      # Win98 WM, GAAD snap (18 tests)
make test_holyc_terminal # HolyC terminal (73 tests)
make test_holyc_ptx      # HolyC PTX codegen (34 tests — includes NVIDIA GPU matmul kernel + store output)
make test_apps2         # Apps test suite 2 (16 tests)
make test_metal         # Metal layer (3 tests)
make test_vsl_macho     # Mach-O loader (24 tests — FAT, segments, entry resolution)
make test_vsl_mac       # macOS syscall dispatch (20 tests — Mach traps, BSD, IPC, filesystem)
make test_audio         # Audio engine (14 tests)
make test_hosted        # Hosted binary (3 tests)
make test_host_exec     # Host exec (15 tests)
make test_wubu_wm       # Window manager (18 tests)
make test_screenshot    # Screenshot tool (9 tests)
make test_gui_screenshot # GUI screenshot (11 tests)
make test_mime          # MIME types (11 tests)
make test_trash         # Trash bin (7 tests)
make test_gamelib       # Game library (16 tests)
make test_clipboard     # Clipboard + primary selection (17 tests)
make test_math          # Pure C libm (wubu_math) (5 tests) — NOW GREEN (see note)
make test_calc          # Calculator engine (calc.c) headless: 10/10 pass
make test_system        # Immutable/atomic system root (wubu_system on snapshot mgr) — run for live count
make test_launch        # Container/Proton launch + GAME session split (wubu_launch_windows): 10/10
make test_exec_elf      # RUNTIME ELF leg: builds a real ELF at runtime, dispatches via wubu_exec_linux_elf -> wubu_ct_native, asserts exit code round-trips (self-contained, no game binary)
make test_exec_pe       # RUNTIME PE leg: builds a real 32-bit PE via mingw-w64, dispatches via wubu_exec_win_pe -> wubu_ct_steamos -> Wine, asserts exit code round-trips (needs i686-w64-mingw32-gcc + wine; skips exit-2 if absent)
make test_compat        # Per-app Windows-compat DB (wubu_compat_db, ProtonDB lesson): 14/14
make test_control       # Control Panel Desktop tab: live apply + persist (9 tests)
make test_worldsim      # WorldSim engine (42 tests — terrain, entity ECS, physics, simulation, RNG)
```

## Adding a test recipe to mk/tests.mk -- INSERT AFTER THE RECIPE, NOT THE PREREQUISITE

This has bitten twice and it silently poisons the gate. A make rule is:

```
target: prereqs          <-- inserting after THIS line puts your recipe
	<recipe lines>        <--   INSIDE the previous target's rule
```

Anchoring on the `target: prereqs` line and inserting there means:

- the PREVIOUS target loses its recipe (it becomes a bare no-op that just
  builds its prereqs), and
- YOUR target inherits every recipe that followed, so running it runs several
  other suites and reports green while the previous target did nothing.

Observed three times: `test_colonel` lost its recipe to `test_kernel_xchg`,
`test_vkd3d_pso` lost its to `test_vkd3d_device`, and a later insertion
scrambled a whole run of targets -- four prerequisite lines stacked together
with every recipe dangling under the wrong target.  A green gate does NOT prove
it -- each target prints its own `ALL ... TESTS PASSED`, so the output looks
normal.

**When more than one target is involved, STOP patching and rewrite the whole
block.** Repeatedly repairing one insertion at a time leaves the surrounding
block half-migrated and the next repair re-breaks the previous one. Locate the
first and last target of the affected run, cut the entire span, and re-emit it
as one clean block with every target followed immediately by its own recipe --
then verify each target runs only its own suite.

**Rule: anchor on the target's LAST RECIPE LINE (the `./<binary>` line), not on
its prerequisite line.** Then VERIFY the structure, not just the result:

```bash
# a tab-prefixed recipe line must belong to the target whose prereq line
# precedes it -- print each target with its following lines and eyeball it
grep -nE '^[a-zA-Z_0-9]+:|^\t' mk/tests.mk | sed -n '/<target>/,+4p'
# and run each target SEPARATELY, confirming it prints ONLY its own suite
make -s test_<a>; make -s test_<b>
```

## Run All Tests
```bash
make test  # Runs all 58 test targets via 6 tiers (takes ~5 minutes)
```

### Tier-Based Test Organization (v20 — matches BATTLESHIP.md tiers)

After the battlefield cleanup, the test suite organization uses **Tier-based** organization matching the WuBuOS roadmap tier structure.

All test commands still work — only the naming and grouping changed.

#### Tier Test Targets

```bash
cd /home/wubu/wubuos

# CRITICAL TIER: Runtime Core (OCI, Network, Snapshots, VSL, HolyD, Proton)
make test_critical_runtime
# Runs: test_oci test_network test_snapshot test_vsl test_holyd test_proton test_proton2

# CRITICAL TIER: Kernel / Metal (FAT32, TXFS, AHCI, DRM, Vulkan)
make test_critical_kernel
# Runs: test_fat32 test_txfs test_ahci test_drm_direct

# HIGH TIER: Bridge (Syscall bridge, DOS flip)
make test_high_bridge
# Runs: test_bridge test_bridge_flip test_syscall

# HIGH TIER: Hosted / GUI (WM, desktop, startmenu, explorer, terminal, clipboard)
make test_high_gui
# Runs: test_wm test_startmenu test_explorer test_term test_clipboard test_screenshot test_compositor test_shell test_wallpaper test_control

# HIGH TIER: Bear RL / JIT / Compiler (JIT, memory, tasking, input, HolyC, PTX)
make test_high_bear
# Runs: test_jit test_memory test_tasking test_input test_holyc test_holyc_ptx

# MEDIUM/LOW TIER: Apps / Audio / Tools / WorldSim / Other
make test_medium_other
# Runs: test_worldsim test_audio test_apps test_apps2 test_wubu test_host_exec test_gaad test_iso test_weights test_gc test_txfs test_dbuf test_styx test_styxfs test_anticheat test_bottles test_deploy test_daemon_panel test_math test_pkgmgr test_gamelib test_mime test_trash

# Full test suite — runs all tiers sequentially
make test
# Runs: test_critical_runtime test_critical_kernel test_high_bridge test_high_gui test_high_bear test_medium_other
```

#### Verification (2026-07-05)

All tier targets pass:
```bash
make test_critical_runtime    ✅ 14/14
make test_critical_kernel     ✅ 4/4
make test_high_bridge         ✅ 5/5
make test_high_gui            ✅ all GUI targets
make test_high_bear           ✅ 9/9
make test_medium_other        ✅ all remaining
make test                     ✅ "All tests passed (all tiers)" — run for live target/assertion count
```

#### Key Insight

The tier names (Critical/High/Medium/Low) directly correspond to the **BATTLESHIP.md v20 tier structure** and the **WUBUOS_DISTRO_ROADMAP.md tier map**. No more "Phase N" language — only tier-based organization matching the gap priority.

### Control Panel / App launch by name matches title instead of registry key (2026-07-20)
**Symptom:** `app_launch_by_name("Control Panel")` returns `NULL` even though the app is registered.

**Root cause:** The registry entry for Settings/Control Panel is `{ "Settings", "Control Panel", ..., launch_settings }` — the first field (`name`) is the launch key, the second (`title`) is the window title. `find_by_name` matched only on `name`, so `"Control Panel"` (the title) failed.

**Fix:** Extend `find_by_name` to match on **either** `name` **OR** `title` — callers can resolve an app by the string a user would click.

```c
const DosGuiAppDef *app_find_by_name(const char *name) {
    if (!name) return NULL;
    for (int i = 0; i < g_app_def_count; i++)
        if (strcmp(g_app_defs[i].name, name) == 0 || strcmp(g_app_defs[i].title, name) == 0)
            return &g_app_defs[i];
    return NULL;
}
```

This is the angel-coder fix: the lookup should resolve a window by the name a user would click, not just the internal registry key.

### Control Panel Two-Pane Render Test Fixed (2026-07-21)
**Symptom:** `test_control` failed on "Control Panel orb (red quadrant) drawn in left rail" — the XP orb's 4 colored quadrants weren't detected in the framebuffer.

**Root causes (multiple):**
1. **Double-buffer confusion** — VBE drawing functions write to `g_vbe.back` (back buffer), but test read from `g_vbe.fb` (front buffer) before `vbe_swap()`
2. **Test called `chrome_draw_window()` twice** — first call inside `control_draw()` draws chrome+content; second call in test redraws chrome OVER the orb, erasing it
3. **Test used local `DosGuiWindow` without `user_data = c`** — `control_draw_content()` reads `win->user_data` for `ControlState*`, which was NULL

**Fix applied:**
- `control_draw()` now explicitly passes `vbe_state()->back` to chrome/content drawing
- Test calls `vbe_swap()` then reads from `vbe_framebuffer()` (front buffer)
- Test does NOT call `chrome_draw_window()` again — computes content rect from window geometry
- Test sets `win.user_data = c` before calling `control_draw()`

**Result:** `test_control` now passes 20/20 (was 19/20).

### FULL TEST SUITE PASS — All Tiers Green (2026-07-21)
```bash
make test  # run for live target/assertion count (all tiers green = the gate)
```

**Critical fixes this session:**
- NT syscall transliteration: ReactOS ordinal mapping wired to 100% parity (run `build_nt_test_lite.sh` for the live count)
- `test_control` 20/20 pass (orb double-buffer + user_data fix)
- `test_calc` linker errors fixed (removed duplicate `calc_test_stub.c`, compile all WM sources)
- `test_trash` target added to Makefile (was missing from `test_medium_other`)
- All tier targets green: `test_critical_runtime`, `test_critical_kernel`, `test_high_bridge`, `test_high_gui`, `test_high_bear`, `test_medium_other`

### Overlapping-window layout in GUI harness (2026-07-20)
**Symptom:** Calculator fully hidden behind Notepad in `wubu_gui_shot` frames — harness used `rand()` for some windows and fixed positions for others, causing overlap. Visual verification impossible.

**Fix:** Rewrite harness `main()` with deterministic, tiled, non-overlapping layout. Key patterns:

```c
// Tiled positions — every app visible
if (calc)   { calc->x = 24;   calc->y = 56;   calc->w = 300;   calc->h = 420; }
if (note)   { note->x = 344;  note->y = 56;   note->w = 500;   note->h = 400; }
if (ctrl)   { ctrl->x = 344;  ctrl->y = 472;  ctrl->w = 520;   ctrl->h = 440; }
// ... etc

// Focus the app you want verified active (navy title)
if (calc) wm_set_focus(calc);
```

Plus `srand(12345)` for deterministic `rand()`-based layout if any remains.

**Verification:** After rebuild, crop each window's exact coordinates from the full frame and pixel-count the expected colors (white text pixels, navy title bar, button bevel patterns).

Procedure when resuming a flagged red suite (proven on `test_pkgmgr` 8/11 → 11/11,
commit b4d9b2d):
1. **Run the target and read the actual FAIL lines**, don't trust the summary.
   `make test_pkgmgr 2>&1 | tail -40` — capture every `FAIL: <fn> (<file>:<line>)`.
2. **Each distinct FAIL line is a separate root cause** until proven shared. Group
   by failing test fn, then open the source at the reported line.
3. **Read the full call chain**: a failure at `install pkg` doesn't mean "payload
   extraction" — it can be a schema error aborting the DB INSERT, a conflict gate
   returning false unconditionally, a serializer dropping a field, etc. The 3
   `test_pkgmgr` failures split into SIX distinct root causes, only one of which
   was the advertised "payload-extraction TODO".
4. **Fix every root cause, then re-run**. A partial fix just moves the failure to
   the next bug. Target 100% green, not "fewer failures".
5. **Verify no regression**: `make clean && make runtime && make hosted` green, then
   full `make test`. **Do NOT blindly trust a handoff's "environmental" label.**
   The prestige/next-session note claimed `test_network` 114/139 was a
   pre-existing *root/netlink "Operation not permitted"* ENV-fail — it was NOT.
   The real cause was `wubu_network_create_bridge` / `create_host` leaving
   `p->enabled = false` (set by `profile_default`), so `wubu_endpoint_connect`
   rejected every connect (`if (!net->enabled) return -1;`), cascading into all
   25 endpoint tests. One-line fix (`p->enabled = true`) → 139/139. **Always
   read the actual FAIL lines and reproduce, not the handoff's diagnosis.**
6. **Changes to SHARED code (compiler/lexer/runtime libs) regress OTHER targets.**
   This session, fixing `hc_eval` in the HolyC compiler made `test_holyd` regress
   (`eval x+10 returns 133`) because holyd compiles via the same `hc_eval`. After
   any compiler/lexer/runtime-lib change, run the FULL gate (`make test`), not
   just the one target you were touching. Triple-DA the fix count.

Reference: `references/red-suite-rediagnosis-pkgmgr.md` — the full 6-root-cause
breakdown for `test_pkgmgr` (8/11 → 11/11), with file:line for each.
Reference: `references/red-suite-rediagnosis-network.md` — `test_network` 114/139
was a REAL code bug (created bridges left `enabled=false`, cascading into all 25
endpoint tests), NOT the "environmental root/netlink" the handoff claimed.Reference: `references/gate-blindness-and-pre-existing-reds-2026-07-07.md` — the
`make paint`/`doom` link failure + `test_math` silent-mask + gate-coverage
blindness recipes (how to prove each is pre-existing via `git stash`).

Reference: `references/debug-hang-crash-harness.md` — when a test target HANGS or
SIGSEGVs (not just fails an assertion): build a minimal standalone harness + gdb
(`timeout 15 gdb -q -batch -ex run -ex bt`), use `stdbuf -oL` to surface the hang
point, and use PIL/CRC as independent ground truth to localize encoder-vs-decoder
bugs. Includes a reusable hand-rolled-codec checklist (PNG zlib wrapper, CRC32
chaining, DEFLATE endianness, PNG unfilter pitch, GIF LZW `int16_t` table + Adam7
de-interlace, R/B byte order) and the "stale test binary masks a fix" trap.

### The COMPILER GAUNTLET is a SEPARATE harness from `make test`
The `make test` gate (WuBuOS subsystems) and `src/compiler/test_gauntlet_runner.c`
(the 14-ISA backend battery) are different test systems. The gauntlet is the oracle
for the JIT/backend codegen and has its own traps the `make test` section above does
NOT cover. Read `references/compiler-gauntlet-debugging.md` before running or
debugging it — it covers: the build command (hosted C11, exact object list), the
**"hung gauntlet = zero output, looks like passing but a JIT infinite loop is
spinning"** diagnostic (use `ps -o time` on the child to tell progress vs hang),
`--target` not skipping siblings, the ptx one-shot GPU-probe fail-fast, and the
x86-64 native-JIT `mov r32` zero-extends sign-extension class bug (use REX.W).
Do NOT hand-roll an x86-64 harness calling `drv->compile`/`drv->run` directly — it
crashes through the struct; use `hc_run_prog` or the gauntlet.

### Orthogonal-Failure Triage (is this red actually YOURS? — 2026-07-07)

When you finish a change and `make test` shows one target red, do NOT assume your
edit caused it. Some reds are **pre-existing and orthogonal** to the files you
touched. Quick isolation check before you start debugging:

1. **Did your edit even compile into the failing binary?** Test binaries link a
   *specific* set of `.c` files (see the target's recipe). If your change touched
   `src/gui/wm.c` / `wm_ctxmenu.c`, but the red target is
   `test_holyd` (which links only `src/runtime/wubu_holyd*.c`), your edits are
   **not in that binary** — the failure is pre-existing, not yours. Confirm with
   `git status --short src/runtime/` (unmodified = not your regression) and by
   reading the target's Makefile recipe.
2. **Recognize the WSL/root "Operation not permitted" noise.** Lines like
   `[wubu_net] bridge wubu0 host setup failed (non-fatal): Operation not permitted`
   and `[wubu_snap] mount on /tmp/... failed: Operation not permitted` are
   **pre-existing environmental gaps** (no CAP_NET_ADMIN / mount privs in WSL),
   not regressions from your change. They print during `test_network` and
   `test_snapshot` but those suites still pass their assertions. Don't chase them
   unless you specifically changed that subsystem.
3. **Read the actual failing assertion, not the summary line.** A target can print
   `Results: 31/31 passed, 1 failed` while `make` exits non-zero — the binary's
   own `return 1` (e.g. a hard-coded `exit(1)` on a specific `TEST`) is the real
   signal. Grep the log: `awk '/Test Suite/,/Results:/' /tmp/test.log | grep -i '❌\|FAIL'`.
4. **Prove pre-existing with `git stash`, don't just guess.** The decisive
   isolation check when a red looks unrelated: stash your working changes, run
   the failing target at HEAD, then pop back. Concretely:
   ```bash
   git stash >/dev/null 2>&1
   make <target> >/tmp/<target>_head.log 2>&1; echo "HEAD_EXIT=$?"
   grep -iE "error:|Results:.*failed" /tmp/<target>_head.log | head
   git stash pop >/dev/null 2>&1
   ```
   If HEAD also fails identically (same compiler error / same FAIL line), the
   red is **pre-existing and orthogonal** to your change — report it, don't fix
   it. This caught a real case (2026-07-07): after fixing the holyd persistent-
   variable bug, `make test` surfaced `test_syscall` failing with
   `vsl_syscall_net.c: struct sigaction / siginfo_t undeclared` — a missing
   `<signal.h>` + feature macro in `src/runtime/vsl/vsl_syscall_net.c`. The
   holyd fix touched only `holyc_types.h` + `holyc_codegen_stmt.c`, which don't
   link into `test_syscall`; `git stash` proved it failed identically at HEAD.
   (The fix there is a one-liner — add `#include <signal.h>` and
   `-D_POSIX_C_SOURCE=200809L` — but only do it if explicitly asked; it's a
   separate orthogonal bug.)
5. **Exception — shared-lib regressions ARE yours.** If you changed compiler /
   lexer / runtime-lib code (e.g. `holyc_codegen.c`, `wubu_holyd.c`) that MULTIPLE
   test binaries link, a red in a target you didn't touch is still your regression
   (the `eval x+10 returns 133` holyd case). When in doubt, run the FULL gate.

### Gap-hunting discipline for test-first closure (2026-07-07, bottles session)
When mining BATTLESHIP's "~400 REAL_GAPs" for a fixable gap, the per-file
counts and banner comments are UNRELIABLE:
- **"Stub implementation" banners lie.** `src/runtime/wubu_bottles.c` is headed
  "Cell 480: Stub implementation" but is fully implemented except ONE empty fn
  (`wubu_bottle_install_deps`). The "~20 bottle lifecycle thin" BATTLESHIP count
  is inflated by that header. Trust an empty-body scan, not the banner.
- **Empty-body candidates must exclude `*_test_stub.c` linker shims + no-op
  lifecycle fns** (e.g. `bridge_shutdown`, `task_preempt_disable`). A bare
  `grep '{}'` flags 27 intentionally-empty test shims.
- **Assert the FIXED behavior, not just the happy path.** For `install_deps`
  the old code returned 0 with no prefix; a test asserting only "install
  succeeds" wouldn't catch that. The fix (`17a79e8`) added assertions that it
  *rejects* missing prefix dir — that's what surfaced the bug. See
  `wubuos-battleship-gaps` skill `references/bottles-gap-closure-patterns.md`.
A red target is often a **Makefile recipe defect**, not a code bug. Two
concrete cases this session, both closed:
- **Missing object in the link line → `undefined reference`.** `test_styxfs`
  linked `holyc_codegen.c` but omitted `holyc_codegen_api.c`/`emit`/`expr`/`stmt`,
  so `hc_eval` (defined in `holyc_codegen_api.c`) was undefined at link time.
  FIX: add the full compiler backend to the `test_styxfs` recipe.
  When a test fails with `undefined reference to <sym>` for a symbol that
  clearly EXISTS in the tree, diff the target's `$(CC) ...` line against a
  neighboring target that links successfully and add the missing `.c` files.

  **SWEEP discipline — wiring a REAL dependency into a previously-stubbed one
  (fires the moment you dissolve a stub).** When an existing `.c` begins to
  *genuinely call* a symbol from a module that was previously a stub/weak ref
  (or you add a new `wubu_X_*` call into a shared `.c`), EVERY test recipe that
  links that `.c` now requires the module's `.o` — not just the one target you
  are touching. This session: `wubu_exec_dos.c` started really calling
  `wubu_dos_proc_launch/state/destroy`, so `test_syscall`, `test_wubu`, and
  `test_styxfs` (all link `wubu_exec_dos.c`) broke with
  `undefined reference to wubu_dos_proc_launch` until `$(RT)/wubu_dos_proc.o`
  was added to each link line. Procedure after wiring a new real dependency:
  1. `grep -n '<dependent>.c' Makefile` — lists every recipe line that links it.
  2. For each line containing it but NOT the matching `.o`, insert the `.o`.
  3. Use a Python splice (`s.split("\n")`, edit the line, `s.join("\n")`) to
     preserve recipe TABs — the `patch` tool mangles leading TABs in recipe
     lines and can silently corrupt a *different* recipe sharing a token.
  4. Re-run each affected target, not just the one you were editing.
  5. **EXCEPTION — targets that link a STUB file, not the real module.** Some
     test recipes link a stub TU (e.g. `src/runtime/wubu_ns_pkg_stub.c`) that
     hand-rolls no-op versions of symbols pulled in transitively by a shared
     `.c` (`wubu_host_exec.c`) but never exercised. When your shared `.c` change
     adds a call to a NEW symbol, do NOT add the real module `.o` to those
     targets — that collides (`multiple definition of '<sym>'`) with the stub.
     Instead add the stub definitions to the stub file (return the contract
     value: 0 / NULL / -1). Detect the case: a sibling target fails with
     `undefined reference to <new_sym>` AND its recipe names a `*_stub.c` /
     `*_stub.o` — fix the stub, not the link line. The targets that link the
     REAL module (`wubu_secmon.c`) are unaffected and need no stub.
  Also: a test can *hang* rather than fail when the spawn path is wrong
  (see the DOS-process QEMU-spawn case in `wubuos-monolithic-split`
  `references/dos-proc-qemu-spawn.md`) — a hang inside launch with no child
  process is a spawn/delegation bug, not a test bug.

### Module integration checklist (split a monolith / add a new self-contained module)
When you dissolve a stub or add a module like `wubu_dos_proc.c`:
- Spawn **real** external processes with direct `fork()`+`execvp()` — never
  route a nested emulator through `wubu_ct_*` (chroot/cgroup/seccomp hangs the
  parent before fork()). See `wubuos-monolithic-split`
  `references/dos-proc-qemu-spawn.md` for the verified pattern + QMP/Styx steps.
- After wiring a new `wubu_X_*` call into a shared `.c`, **sweep every test
  recipe** that links that `.c` and add the module's `.o` (SWEEP discipline
  above) — otherwise you get `undefined reference` regressions in siblings.
- Re-run each affected target, not just the one you touched.
- **Putting a new external dependency inside a SHARED module's init breaks
  every lean test that links that module.** The init is the one function every
  consumer calls, so a new call there (opening a device, loading a backend,
  spawning a thread) becomes a hard link dependency for all of them -- and the
  lean targets are built precisely to avoid pulling the world in. Observed
  class: adding a device-open call to a sound engine's `*_init()` reddened four
  unrelated lean suites (`test_wubu_sound`, `test_apps`, `test_wet_applet`,
  `test_first_run`) with `undefined reference`.
  FIX: open the device at the PRODUCT's boot path, not inside the module init;
  keep the init free of new external symbols. If a module genuinely must carry
  one, split the concern into its own small file (e.g. `*_sink.c`) so a lean
  target can link just that file instead of the whole engine.
- **Missing feature macro breaks an otherwise-fine source.** `test_syscall`
  compiled with `-DMYSEED_METAL` and NO `-D_GNU_SOURCE`/`-D_POSIX_C_SOURCE`, so
  `<signal.h>` hid `struct sigaction`/`siginfo_t` → `error: storage size of
  'sa' isn't known`. FIX: add `-D_GNU_SOURCE` to the recipe. Symptom
  `incomplete type 'struct sigaction'` / `unknown type name 'siginfo_t'` under
  a `-DMYSEED_METAL` or `-ffreestanding` flag = add the POSIX/GNU feature macro.

More Makefile/recipe traps (2026-07-07, desktop Stream 2/4 session):
- **Duplicate-header include trap (subdir vs sibling).** Two `control.h` exist:
  legacy stub `src/apps/control.h` (includes old `../gui/wm.h`) and the real
  `src/apps/control/control.h`. A test at `src/apps/control_test.c` that writes
  `#include "control.h"` resolves to the SIBLING stub, not the subdir →
  `unknown type name 'ControlState'` + implicit-declaration errors. FIX: use a
  relative include `#include "control/control.h"` OR add `-I$(APPS)/control` to
  the recipe. Same trap fires whenever a subdir shares a basename with a sibling
  header — always check `grep -rln '#include "X.h"'`.
- **`setenv` needs `_POSIX_C_SOURCE`.** Any test calling `setenv()`/`unsetenv()`
  must compile with `-D_POSIX_C_SOURCE=200809L`, else `implicit declaration of
  function 'setenv'` + int-conversion errors. `test_wm` and `test_control`
  both needed this after adding persistence tests that isolate `XDG_CONFIG_HOME`.
  (Same flag that enables `<signal.h>` features.)

**A gate must never write into the user's REAL data store.** When a test exercises
a module whose default path lives under `$HOME` / XDG (`~/.local/share/wubu/fs.img`,
`~/.config/wubu/…`), it is writing the operator's live desktop unless redirected.
The failure is silent: the suite passes, and the user's next boot shows phantom files
(observed: a Start-search gate left four files in the real guest FS image, which then
poisoned the live GUI verification and had to be deleted by hand). Redirect it every
time, unconditionally:

```c
/* the module honours an env override per call, so no init-order dependency */
snprintf(store, sizeof(store), "%s/wubu-<suite>-%d.img", kScratchDir, (int)getpid());
setenv("WUBU_FS_STORE", store, 1);   /* or the equivalent *_DIR / *_PATH knob */
unlink(store);                        /* start clean, not on top of last run */
…                                       /* run the suite */
flush(); unlink(store);                 /* leave no trace */
```

Verify the isolation, not just the pass: after a green run, confirm the real path is
still absent (`ls ~/.local/share/wubu/fs.img`). A gate that leaves bytes in a
user-writable location is a leak even when it exits 0.
Rule of thumb: **if a test's default storage path resolves inside `$HOME`, assume it
will hit the real file until you have proven otherwise.**
- **Patching the Makefile can hit the WRONG recipe.** Many recipes share identical
  lines (e.g. `$(GUI)/wm_test_stub.c \\` appears in `test_wm`,
  `test_holyd`, and others). A patch anchored only on that line silently rewrote
  `test_holyd` (a GATE target that does NOT link `wubu_settings.c`/`wm.c`)
  — which would have broken the gate. FIX: anchor on a line UNIQUE to the intended
  recipe (e.g. `$(RT)/wubu_holyd_test.c -o ...` or the full `$(CC) ... test_wm`
  line), then VERIFY with `make -n <target>` that the recipe parses and `cat -A`
  that its leading whitespace is real TABs (Make rejects spaces). When in doubt,
  hand-edit the specific recipe line.
- **Object path pitfall: `wubu_gaad.c` lives in `src/kernel/`, NOT `src/runtime/`.**
  When wiring a link line that pulls `wubu_gaad.o`, use `$(KERNEL)/wubu_gaad.o`,
  never `$(RT)/wubu_gaad.o` (that resolves to `src/runtime/wubu_gaad.o`, which
  does not exist → `ld: cannot find src/runtime/wubu_gaad.o`). Hit this on the
  `paint`/`doom` link rewires (commit 03473df fixed it). Symptom: `collect2: error:
  ld returned 1 exit status` with `cannot find src/runtime/wubu_gaad.o`.
- **Calc engine test convention.** `calc.c`'s `calc_launch()` references
  `wm_create()`, so the headless `test_calc` (`src/apps/calc/calc_test.c`)
  links a tiny `calc_test_stub.c` providing a weak/stub `wm_create` that
  returns `NULL` — the engine tests never call `calc_launch()`, so the symbol just
  needs to resolve. No GUI stack is pulled in. Test runs 10 assertions green.
- **Wiring a new/extended test into the gate.** When you add a target or assertions
  that touch shared code: (a) make sure the recipe `-I`s cover every header dir the
  new `#include`s need (settings, control subdir, etc.) and links the changed `.c`
  files (e.g. `wubu_settings.c`, `wm.c`); (b) if the target should run in
  `make test`, add it to the right `test_high_*` / `test_*_other` tier line; (c)
  ALWAYS run the FULL gate (`make clean && make runtime && make hosted && make test`),
  not just the one target — a recipe change shifts which objects link and can
  regress a sibling target.

These are real fixes (committed), so they are NO LONGER in the "pre-existing
broken" list below.

### Gate is FULLY GREEN (2026-11-08, measured)
`make -k -j24 test` -> RC=0, 0 make errors, 0 segfaults, "All tests passed (all tiers)".
The four 2026-11-08 reds were all REAL DEFECTS, not environment — do not relabel a
red as "environmental" without reading its FAIL line:
- `test_holyc_ptx` — the CUDA path was dead: `holyd_ptx.c` never included
  `<cuda.h>` and nothing defined `HAS_CUDA`. The emitted PTX also never assembled
  (undeclared `.reg .pred p0, p1`; `%ctaid.x * %ntid.x + %tid.x` — ptxas rejects
  special registers in arithmetic). Now 25/25 with a real GPU leg.
- `test_worldsim` — two orphaned build-graph objects; wired into `mk/tests.mk`.
- `test_audio` — asserted a NON-BLOCKING read on `/dev/snd/seq` returns data;
  with no MIDI events pending the kernel correctly returns EAGAIN. Now accepts it.
- **11 `test_jit_*` SEGFAULTS** — all 18 JIT recipes omitted `-DWUBU_HOSTED`, so
  `jit_alloc_exec()` fell back to plain `malloc()` and the tests called
  non-executable memory. Same class as the HolyC fix in e6518f5; the JIT family
  was never covered.
- `jit_supremacy_test` / `jit_torture_test` used fixed `/tmp/gcct.c` + `/tmp/gcct`
  for their GCC oracle, so under `-j24` sibling processes clobbered each other and
  gcc returned the INT64_MIN sentinel -> 39 + 37 phantom "divergences" where the
  WuBu result was correct. Now per-PID paths.

**Count segfaults explicitly.** They do NOT match an `Error [0-9]` grep, so an
error-count-only check reports a green gate while 11 targets crash:
`grep -c 'Segmentation fault' /tmp/test.log` must be 0.

### Vendored app suites (submodules with their own CMake + ctest)

Whole app repositories live under `src/apps/` as submodules and build with
THEIR OWN CMake, not the WuBuOS Makefile. `mk/vendored.mk` drives them:

```bash
make wubupad          # cmake + make in src/apps/wubupad/build
make wubuoffice       # depends on wubupad (its shell compiles WuBuPad's core)
make wubupad-test     # ctest --test-dir <build>
make wubuoffice-test
```

Three rules that keep these green:

1. **Bump the submodule pointer, then re-run.** `git submodule update --remote
   --init <path>` fetches upstream; `git add <path>` records the new commit.
   A submodule's own fixes do NOT reach the build until the pointer moves.
2. **Cross-repo paths are layout-dependent.** A submodule that hardcodes a
   sibling path (`../WuBuPad/src`) breaks the moment the repos are checked out
   under a different parent. Fix the path in the SUBMODULE's own repo and push
   there, then bump the pointer -- patching only the local checkout is lost on
   the next `update --remote`.
3. **A vendored gate that needs external tooling must SKIP, not FAIL** (see the
   gate-honesty rule above). Both WuBuPad and WuBuOffice had GUI-parity gates
   that hardcoded a shared `../tooling/` directory and reddened everywhere
   outside the original author's checkout. They now take a
   `*_TOOLING_DIR` cache path and print `SKIP:` with
   `PASS_REGULAR_EXPRESSION "SKIP"`.

**WuBuOffice needs SDL2 and cmake at build time**; without them its configure
step fails outright (`find_package(SDL2 REQUIRED)`). WuBuPad degrades to a tty
backend instead -- its gfx backend is optional, and the main binary guards the
`ui_gfx_backend()` symbol behind the `WUBUPAD_WITH_GFX` macro CMake defines.

### Kernel selftest output goes to the klog ring, not stdout (fixed 2026-11-08)
Selftests link the kernel's libc (`$(CACHE)/libc.o`), so their `printf` resolves
to `libc.c:printf` -> `klog_write` -> `putc_raw`, which with no serial console up
(`g_klog_ready == 0`) only wrote into the 4096-byte panic ring that nothing ever
reads. Every CHECK line of 436 test recipes was being discarded. The tell: a
selftest that prints its header and then nothing — GCC rewrites a
format-string-only `printf("...\n")` into `puts()` (glibc, reaches stdout), so
ONLY the header survived while every `%s`/`%d` CHECK line vanished. Diagnose with
`objdump -d <testbin> | grep -A20 '<main>'` and look for `puts@plt` vs a real
`call printf`; confirm with `strace -e trace=write`.

Fix shape: a weak hook in `klog.c` (`klog_putc_host`, no-op in the kernel where
there is genuinely nowhere to write before `klog_init`) overridden by
`wubu_test_stubs.c` to `write(1, ...)`. `wubu_test_stubs.c` is test-only (0
occurrences in `mk/objects.mk`, 436 in `mk/tests.mk`), so the override cannot
leak into the real kernel. After the fix `test_hw_vrr` reports 6/6 instead of one
header line. **If a kernel selftest appears to "print nothing", check this before
blaming the test.**

The kernel's `vsprintf` (`libc.c`) also has NO `%f` — it supports
`d i u x X s c p %` only. `%.1f` prints literally. Use `%d` with an `(int)` cast
when debugging a float, or extend the switch.

### Three gate-honesty rules

**A recipe that omits the macro gating the real implementation silently tests the
FALLBACK.** When a module is `#ifdef FEATURE ... real path ... #else ... fallback
... #endif`, every recipe linking it must define FEATURE — otherwise the suite
exercises the fallback and asserts against stub behaviour (a fallback that returns
non-executable `malloc` where the real path returns an RWX mapping segfaults the
test). Detection: `grep -n '<MACRO>' mk/tests.mk` — if the recipes linking the
module never define it, they are not testing the product. Fix the whole recipe
family in one pass with a Python splice over the recipe blocks (preserves TABs).

**A test that shells out to a tool or binds a fixed IPC name is not parallel-safe.**
Under `make -jN test`, sibling processes clobber the shared file (or all bind
the same `/tmp/<name>-styx.sock`), the oracle fails or a second guest attaches
to the wrong process, and the test reports phantom divergences from a CORRECT
result. Use per-PID paths (`/tmp/<tool>_<pid>`) and per-PID IPC names
(`<guest><pid>`), and `unlink` paths after each run. Detection: run the target
alone (green) then under `-j24` (red) — red only in parallel is a
shared-resource race, not a logic bug. Know the oracle's failure sentinel
(e.g. INT64_MIN) so a tool failure is not misread as a product divergence.

**Production deadlines / backoff windows use CLOCK_MONOTONIC milliseconds, never
`time(NULL)`.** A seconds-resolution wall clock makes a nominal "1 s" window
anywhere between ~0 and 1 s depending on where the event lands inside the tick:
the guard misbehaves in production (a crash-looping service can be restarted far
more often than intended) AND its gate reds under `-j24` while passing
standalone. Diagnose: target passes alone, fails in parallel; inspect the
deadline type, not just the assertion. Fix the deadline, then PROVE it by
running several instances of the same target concurrently. Instance: supervisor
crash-loop backoff used `time_t backoff_until = time(NULL) + delay`; now a
monotonic-ms deadline, with the exponential schedule extracted so reap() and
poll() share one copy.

### Wiring an orphaned driver / test binary

A module that compiles but has no target is coverage loss, not dead code. When
you go to wire one:

- **Choose the source closure by what the body CALLS**, not by its `#include`s
  (`rg '<fn>\(' <file>`). An include is not a dependency.
- **`-lm` goes LAST** on the gcc line. Placed before the objects it resolves
  nothing and every math symbol (`cosf`, ...) reads as `undefined reference`.
- **Filter out any source that defines its own `main`** -- demo drivers
  (`bear_train.c`) and `*_test.c` modules collide with the driver's main:
  `multiple definition of 'main'`.
- **Run the probe with the SAME include set the build uses.** A probe missing
  `-I.` reports files doing `#include "src/<dir>/x.h"` as missing-header dead
  code. That false verdict once labelled 18 real, compiling drivers STALE;
  re-derive with the build's flags before deleting or "retiring" anything.
- Wire the ones that link AND exit 0 into a tier; report the split (wired /
  unwired with the next missing symbol each), never just the wired count.

**A test that asserts on an instantaneous sampled state is a race — assert on a
cumulative counter instead.** Sampling a scalar that a background process can
change between the sample and the assertion (`pid == 0`, `state == IDLE`, a
buffer being empty) makes the result depend on scheduler timing. Under `-j24` it
reds intermittently, and a re-run that passes teaches you nothing. The fix is to
assert the CONTRACT, not one instant of it: poll inside the window and require
that a COUNTER (restart count, allocation count, bytes written) does not grow,
or that a monotonic value has reached a threshold. Same rule for a sleep inside
a timing assertion: a `usleep(100000)` can stretch past the very window under
test, so the assertion fails for a scheduling reason. A target that has reded
intermittently across several gates is telling you the ASSERTION is wrong, not the
product — fix the assertion, do not re-run until it happens to pass.

**A shared KERNEL source reached by hosted/GUI tests must not call metal-only
symbols.** One `.c` (e.g. `src/kernel/interrupt.c`) compiles into BOTH the metal
image and lean hosted/GUI test binaries, but the latter do NOT link the APIC/PIC
module (`interrupt_apic.c`). An unconditional `lapic_*` call therefore builds, then
reds the WHOLE gate with `undefined reference to lapic_eoi` in `test_first_run` /
`test_wet_applet` / `test_vws_designer` / `test_tutorial` while `make test_agi_metal`
is green. Guard the call AND its handler with `#ifdef MYSEED_METAL`, and re-run the
full gate after touching a shared kernel `.c` -- the per-target check does not
cover the other consumers.

**A feature whose ENTRY POINT no test drives is unverified, however green the
gate.** A subsystem can be fully written, bound and still dead: the WM's key
dispatcher was exercised by nothing, and its modifier masks disagreed with
`src/kernel/input.h` (`MOD_SHIFT 0x01 / MOD_CTRL 0x02 / MOD_ALT 0x04 / MOD_WIN 0x08`)
while the input layer never set `MOD_WIN` — so Alt+Tab, Ctrl+T and every Win+
shortcut were permanently unreachable, with a fully green gate the whole time.
Detection: for each interactive entry point (input dispatcher, settings apply,
hotkey table), grep for a test that CALLS it:
```bash
grep -rn 'wm_handle_key\|handle_key(' src/gui/*_test.c   # any caller?
```
Zero callers = unverified. Then check two things before declaring it correct:
(1) every hardcoded modifier/key bitmask matches a canonical `MOD_*` / key-code
define — never a raw `0x08`; (2) every modifier bit the dispatcher tests for is
actually SET somewhere in an input backend. Add a test that drives the dispatcher
with the real modifier values; that test is the only proof the feature works.

**A suite that only exercises VALID inputs never checks the pointer arguments.**
Probe every registered slot / dispatch entry ONCE with all-zero or hostile arguments,
in a forked child under `alarm(1)`, so a crash or hang costs one child instead of the
gate. This is what found real defects that a green suite had hidden for months:
an unchecked `getenv((void*)0)` and an unconditional `raise(SIGTRAP)` behind syscall
facade slots, and a `strchr` walk past the end of a section header. Ship it as its own
target (`make test_<subsystem>_contract`) linked against the REAL module — a refactor
that deletes the guard must redden the gate, not crash the user's process. Full
pattern, child-isolation pitfalls and reporting rules:
`references/hostile-input-contract-sweep.md`.

**A guard that nothing calls is not protection.** This is the other half of "no test
drives it": the code exists, is correct, and never runs. Concrete instance: red-zone
canaries were stamped on every allocation and a correct checker existed, but no
allocator path called it — an overflow was silently absorbed by `free()`. Grep cannot
find this shape (the checker DOES have a caller, which itself has no caller), so build
the real call graph instead: `tools/dead_guard_scan.py` in the WuBuOS repo scans
`src/**.c`, excludes each function's own signature from its call count, and reports
probe-named functions that nothing reaches. Treat every hit as a HYPOTHESIS — dispatch
tables (`tbl[N] = fn;`), parity `#define`s, cross-repo API and callbacks all fake a zero
count. Triage of a full run is recorded in `docs/DEAD_GUARD_AUDIT.md`.

**A test that depends on an external tool or directory must SKIP when it is
absent, not FAIL.** A suite that hardcodes a path outside its own repo (a shared
`tooling/` directory, a sibling repo, a system binary) reds everywhere except the
original author's checkout, and a missing audit tool is not a product defect.
Make the path a cache/config variable and have the test print `SKIP: ...` with a
pointer, then mark it `PASS_REGULAR_EXPRESSION "SKIP"` so the gate stays green
and the skip is visible in the log. Detection: the FAIL line names a file that
does not exist anywhere in the tree; the fix is the skip, not a stub that fakes
the tool's output.

### GPU on this box (2026-11-08)
RTX 5050 Laptop 8GB, driver 615.71.09 (CUDA UMD 13.4), CUDA 12.0 toolkit + cuDNN
8.9.2 installed, Vulkan NVIDIA ICD enumerates. `nvcc` 12.0 has NO native `sm_120`
— compile with `-gencode arch=compute_80,code=compute_80` and the driver JITs it.
`test_gpu_driver` (in `test_critical_runtime`) is a real 13/13 GPU behaviour gate:
cuInit -> nvcc PTX -> driver JIT -> launch -> verify.

**`test_vsl` is root-SENSITIVE, not root-requiring.** Running it under
`sudo -S` makes it WORSE: 83/87 (root adds `open() returns valid FD` and
`close() succeeds` failures, and `fanotify_init` changes errno). Do NOT "fix"
this suite by running it as root — the normal-user run is the better baseline.

### Root access (sudo pipe)
The box grants root via a password pipe — never type the password into a
command line argument, and never echo it into a log:
```python
p = subprocess.Popen(['sudo','-S','bash','-c',cmd], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
out,_ = p.communicate(input='<password>\n', timeout=900)
```
Prefer `sudo -n` first (passwordless); fall back to the pipe only when needed.
Root does NOT help the environmental reds above — verify before assuming.

### Known pre-existing broken targets (2026-07-07, end of session — FULL green gate ✅)
**AS OF 2026-07-07 (end of session): `make test` exits 0 with ALL targets passing.** The one remaining exception:
- WSL/root "Operation not permitted" noise in `test_network` / `test_snapshot`
  is environmental (CAP_NET_ADMIN / mount), not a code regression — those
  suites' assertions still pass. The bridge/netlink messages are non-fatal.

- **`make paint` / `make doom` remain ORPHAN app targets** with no `main()` in
  `src/apps/paint.c` / `src/apps/doom.c` — they are NOT standalone executables
  (the hosted binary / `apps` launches them). Their Makefile link lines
  were rewired (2026-07-07, commit 03473df) to pass `$(GUI_OBJS)` + full runtime
  object set + `-lsqlite3 -lzstd [-lwayland-client]`, which fixed the earlier
  `undefined reference` link errors, but they still fail with `undefined reference
  to 'main'` because the source has no entry point. OUTSIDE the gate (the
  `make test` tiers never build `APP_OBJS`). Reported, not chased — don't sink
  time into making `paint`/`doom` standalone unless explicitly asked.
- **`test_gui_screenshot` is PRE-EXISTING BROKEN** (not in any gate tier, confirmed
  2026-07-09). Its Makefile recipe links `wubu_screenshot.c` alongside `hosted.c`
  / `wm.c` but omits `wubu_clipboard.c` / `desktop.c` / `gui_dbuf.c`
  and the HolyC codegen objects, so it fails to link with `undefined reference to
  wubu_clipboard_init` / `desktop_shutdown` / `gui_dbuf_draw_char` / `hc_eval`.
  Don't chase it. For screenshot/clipboard PNG-encode verification use the
  self-contained `test_screenshot_clipboard` target (added 2026-07-09) which stubs
  the 4 GUI externals in the test TU and links `-lz -lm`.

### Makefile edit pitfall — TABs, not spaces (2026-07-09)
The `patch` tool's `replace` mode silently converts leading TABs in Makefile
recipe lines to spaces (or drops them) when the old/new block spans multiple
recipe lines. A recipe whose command lines start with spaces instead of a TAB
makes `make` either error ("missing separator") or mis-handle the rule. When you
must edit a Makefile with `patch` and the change touches recipe lines:
1. After the patch, verify leading whitespace with `cat -A <Makefile> | sed -n '<lines>p'`
   — recipe command lines MUST show `^I` (TAB), not spaces.
2. Prefer `execute_code` with a Python splice (open file, split lines, re-emit
   with explicit `\t` prefixes) for multi-line recipe edits; it preserves tabs
   reliably. The `patch` tool is fine for *non-recipe* context (variable defs,
   comments) but risky for recipes.

**A Python splice preserves TABs but cannot tell whether your anchor names the
rule you meant.** Blind splices corrupted the same file four ways in one session:
- `l.startswith("test_apps:")` also matches `test_apps_weak:` — a prefix test
  finds a DIFFERENT target than the one you named, and edits it.
- An anchor like `"-o src/apps/apps_test "` may not exist at all (the real line
  is `-o $(APPS)/apps_test -lm ...`). `assert len(hits)==1` then fires AFTER the
  file is already half-mutated by earlier replacements in the same script, leaving
  a mess that takes several more edits to unwind.
- Inserting "the line after the one containing `<source>.c \`" lands in the
  **prerequisite list**, not the recipe: prerequisites are lines 2..N of a rule
  and the recipe follows them. The source is added as a second prerequisite line
  and the compile command never sees it — `make` then reports
  `Permission denied` on the new path, which reads like a filesystem problem.

Procedure that avoids all four: print the WHOLE rule span first — from the
target line through the next line beginning at column 0 (or EOF) — pick the
anchor from what you actually printed, splice, then `grep -n` the new state and
`make -n <target>`.
3. **The `patch` tool ALSO mangles backslash line-continuations** (separate from
   the TAB problem). When a `patch` old/new block spans recipe lines that end in
   `\` (Makefile continuation), the tool doubles the backslash (`\` → `\\`,
   visible as `\\\\` in repr) and sometimes pads leading whitespace to extra
   TABs. Symptom: `make: *** No rule to make target 'gcc'` (the `$(CC)` recipe
   line got absorbed into the prerequisite list by a broken continuation) or a
   mangled recipe. After ANY `patch` touching a continuation line, verify the raw
   bytes: `python3 -c "d=open('mk/tests.mk','rb').read().split(b'\n'); [print(i+1, d[i][-12:]) for i in RANGE]"`
   — a continuation line must end in exactly ONE `\` (`b'\\'`), not two. When it
   is mangled, fix it with a Python splice that rewrites the exact line list
   (`lines[idx] = "\t\t...\\n"`), NOT another `patch` (which re-mangles).
4. Always `make -n <target>` after a Makefile edit to confirm the recipe still
   parses, before running the real build.

### A Python-splice edit that writes the ORIGINAL string silently drops the change

When editing a file from `execute_code`, `open(p,"w").write(s)` writes the
string you READ, not the one you built. If the replacement is
`s.replace(old,new,1)` and you write `s`, the edit vanishes entirely -- and the
build/test then fails with the OLD behaviour, which reads exactly like "my fix
was wrong" and sends you debugging the fix instead of the edit. No compiler
complains, because nothing changed.

Rule: write the REPLACEMENT, then assert it landed before running anything.

```python
s = s.replace(old, new, 1)
open(p, "w").write(s)
assert "<a token from new>" in open(p).read()   # prove the edit is on disk
```

Detection: a test failing with the PRE-FIX behaviour immediately after you
applied the fix. When that happens, re-read the file before touching the code.

Related: this is the same class as the recipe-insertion trap above -- an edit
that silently did not do what you intended, leaving a green-looking or
red-looking result that does not mean what it appears to mean. After ANY
structural file edit, verify the STRUCTURE, not just the outcome.

### Cloning a test recipe -- the clone inherits the source's `main`

Copying a working recipe is right, but the copy keeps two things it must not:
1. **The source target's own test object** (e.g. `$(VSL_OBJS)` ends in
   `$(RT)/wubu_vsl_test.o`). That object defines `main`, so the new binary links
   and silently RUNS THE OLD SUITE -- you read a green result for a test that
   never executed. Filter it out: `$(filter-out $(RT)/<oldtest>.o,$(OBJS))`.
2. **The source target's output path.** The clone's link line may name only the
   old binary, so the new test `.c` is never compiled. Confirm the new `.c` is on
   the `$(CC)` line, not merely in the prerequisites.
Detection: run the new binary directly and read its printed header. A green
result whose header names the OLD suite means the clone won.

### A recipe naming an object whose .c does not build is PRE-EXISTING red

Before diagnosing a link failure in a recipe you touched, build the object it
names: `make src/runtime/vsl/vsl_syscall_nt.o`. If the pattern rule itself fails
(missing `-I`, missing include), that target was already red and your change did
not cause it -- report it, and do not "fix" it by dragging the object into links
that never had it.

### Capture a test binary's output so you never loop on a flaky read
When you need a `make test_*` result, route the output to a FILE and read the
exit code separately — never pipe `make target | tail` (the pipe eats `$?` and
the harness tool can swallow long/emoji-heavy output into an empty or
"too large" result). Proven pattern:

```python
import subprocess, re, json
root="/home/wubu/wubuos"
with open('/tmp/tgt.txt','w') as f:                    # stdout to file
    rc=subprocess.run(['timeout','180','make','test_X'],
                      cwd=root,stdout=f,stderr=subprocess.STDOUT).returncode
d=open('/tmp/tgt.txt','r',errors='replace').read()    # read back via the file
m=re.search(r'(\d+)/(\d+) passed', d)
print(json.dumps({'rc':rc,'result':m.group(0) if m else None}))
```
Rules:
- **Grep the FILE, not the process.** Filter lines with `open(...).read()` +
  regex, or `grep -a 'Results' /tmp/…txt`. The binary's own pass/fail line is
the truth; the harness tool's stdout summary is unreliable for long suites.
- **Capture `returncode` from `subprocess.run`, never `$?` through a pipe** —
  `make | tail` reports tail's exit status, not make's.
- **A background/delegation child's result can be STALE.** A subagent or async
  batch that sampled the tree mid-edit (uncommitted) can report a green tree as
  red (or vice-versa). Before acting on a child's "make failed", verify the
  ON-DISK truth: `git status --short` + `git show HEAD:<file>` + one fresh run
  from the committed tree. Children inherit working-tree state, not your
  uncommitted fixes.
- **Terminal equivalent:** `make target > /tmp/x.txt 2>&1; echo RC=$?` then
  `grep -a 'Results' /tmp/x.txt` — exit code and log live independently.

### A built target that prints "up to date" never runs its test binary

`make test_X` executes its recipe — including the `./$@` line — only when the
target is out of date. Once the binary exists and no prerequisite changed, make
prints `make: 'test_X' is up to date.` and skips the recipe entirely. The run
exits 0, the log contains that one line, and the suite never ran. Any check that
greps the log for `PASS`/`WRONG`/`ALL PASSED` then reads an empty result and looks
like a code failure.

- Declare every test target `.PHONY`. Bulk fix: parse `^test_[A-Za-z0-9_]+:` out of
  the Makefile and emit a single `.PHONY:` line; on the compiler repo that covers 36
  targets and takes one edit.
- **A target whose name can never exist as a file needs no phony entry.** If the
  recipe writes to `$(KERNEL)/test_x` while the target is `test_x`, make always
  runs it (the file is not in the working directory). That shape is
  self-protecting; the .PHONY list is only needed where target name == produced
  file. Check both before declaring a repo "safe".
- Verify by running the same target twice: the second invocation must print the
  suite's results again, not "up to date".
- When a harness (including an external loop driver) scores a task by running
  `make test_X`, the check must force execution — otherwise a green check proves
  only that a stale binary exists.

### Test-graph audit — declared vs reachable targets

A repo can declare hundreds of `test_*` rules while `make test` depends on a
hand-written handful of tier targets. On this tree that ratio was **131 reachable
of 446 declared**: 315 suites never ran in the gate at all.

Run `scripts/check_make_coverage.py` (in this skill) over `Makefile mk/*.mk`.
It prints declared / reachable / unreachable and exits non-zero on orphans.

**Closing the gap -- run every orphan before wiring any of them.** An orphan
target is not automatically good; it may have been orphaned BECAUSE it fails.
Procedure that worked (135 orphans -> 105 wired, 29 honestly reported):

```python
# 1. defined minus referenced = the orphans
import re
s = open("mk/tests.mk").read()
defined = set(re.findall(r'^(test_[a-z0-9_]+):', s, re.M))
referenced = set()
for m in re.finditer(r'^([a-zA-Z0-9_]+):\s*(.*)$', s, re.M):
    referenced.update(re.findall(r'(test_[a-z0-9_]+)', m.group(2)))
orphans = sorted(defined - referenced)
```

2. Run each individually with a timeout and record PASS/FAIL + the first
   `error:` / `Segmentation fault` / `undefined reference` line:
   `timeout 90 make <target>` in a loop, appending to a results file.
3. Wire ONLY the passing ones into a new tier (`test_orphans:`) that the
   top-level `test:` depends on. A tier prerequisite line is NOT indented --
   a leading TAB makes make read it as a recipe and you get `Error 127`.
   Continuation lines start at column 0 and end in exactly one `\`.
4. Do NOT wire the failures. Categorise them in the commit message: targets
   naming a `.c` that does not exist; `undefined reference` to a symbol that
   does not exist anywhere (real missing code); and genuine assertion
   failures. Wiring known-broken tests makes the gate lie.

Report the split, never just the wired count.

Fix shape: generate one `ALL_TESTS = test_a ... test_z` line plus
`.PHONY: test_all` / `test_all: $(ALL_TESTS)` from the rules themselves, so the
list cannot drift, and include it after the file that declares the rules. Then
every new target is covered by construction.

Report three numbers, never one: declared, reachable, passing. "All pass"
without reachability is a statement about an unknown subset.

Two graph defects to look for while auditing (recipes in
`references/make-graph-audit.md`):

- **Header-less duplicated recipe blocks.** Tab-indented lines whose target and
  variable assignments were lost get attached to the *previous* target — the
  failure surfaces as `gcc -c` with no input, exit 127 on a binary that was never
  built, or extra commands in an unrelated rule. Delete the orphan block, keep
  the complete copy, then `make -n <target>`.
- **One missing file in a shared source variable.** When ten targets fail with
  the *same* undefined symbol, do not patch ten recipes: `grep` the defining `.c`
  and then grep it across `mk/*.mk` / `Makefile`. If it appears only once (in
  `$(HOLYD_SRC)`, `$(VSL_NT_OBJS)`, `$(FRONT)`), the variable is the bug. Fixing
  the definition fixed 10 targets in one edit; fixing recipes would have fixed
  them one at a time and missed the next consumer.

### Link repair: a new symbol every round means the source list is the defect

When you fix an `undefined reference` by appending one `.c` to a recipe and the
next build fails with a *different* `undefined reference`, you are not one file
away from green — you are walking a stale copy of the dependency set. Stop after
the second new symbol and fix the set instead:

- Targets with hand-maintained lists of 100+ sources are the ones that rot. Their
  recipe is a snapshot of what compiled on the day it was written; every module
  added to a shared `.c` since then is missing. Appending is unbounded because
  each newly linked `.c` pulls its own dependencies.
- Preferred shape: one object-set variable per layer (`$(RT_OBJS)`, `$(KERNEL_OBJS)`,
  `$(CORE_OBJS)`) plus a single link template, so a target cannot omit a module
  that the rest of its layer needs. Per-target lists are only defensible for
  genuinely optional subsystems.
- Distinguish the two cases before editing: **same symbol across many targets** →
  the shared variable is wrong (previous bullet). **Different symbol per target,
  growing chain** → that target's list is wrong; fix the list, not the chain.
- Measure the tail on the failing *list*, not the aggregate: `make -k test_all`
  over hundreds of targets includes multi-minute suites (gauntlets, JIT batteries)
  and will blow a foreground timeout long before it reaches the end. Release with
  `timeout`, then parse `make: *** [<mkfile>:<line>: <target>] Error` out of the log
  — the bracketed location names the exact rule to edit, which a bare
  `undefined reference` line does not — and re-run only those targets individually
  (seconds each). Re-running the whole aggregate to check three fixes is what turns
  a five-minute loop into an hour.

### Over-linking a test target — check what the selftest actually CALLS first

Before assembling a test target's link closure off the first `undefined
reference`, read the selftest body and list the symbols it truly CALLS. An
`#include` is NOT a dependency. A selftest that includes a module's header but
never calls its functions links fine without that module — adding it drags in a
whole raft of extra unresolved refs that were never needed. Concrete: wiring
`test_vulkan` by adding `wubu_hw_detect.c` (because the selftest includes
`wubu_hw_detect.h`) pulled 318 unresolved probe refs across the entire kernel
device raft; the selftest calls only `wubu_vulkan14_*`, so just `wubu_vulkan14.c`
links clean (6/6). For every seeming dependency, grep the test body for the call:
`rg '<fn>\\(' <selftest.c>` — link only what appears.

A heavy integration target can also fail to link because the unit under test
calls an unrelated SIDE-EFFECT function (a notification toast, a paint routine)
that the test does not check. Provide a no-op link stub for that one call to keep
the test a focused unit gate (no full render/ui stack), but leave the target OUT
of a gate tier if the CORE still needs a real raft — a failing tier target breaks
the whole gate, an unregistered orphan target does not. Document the stub and the
omit in the target comment so the next reader knows the closure is intentional.

### A repair count that does not move is the diagnostic

Track pass/fail per target across rounds. If round 1 fixes several and every later
round fixes none while each build reports a new symbol, the defect is structural
(stale lists) rather than a series of independent omissions — say so and switch
approach instead of continuing to append. Report the honest split: how many now
pass, and for each remaining one, the *next* symbol it wants. "Still failing" with
no symbol is not a status a future session can act on.

### Gate-coverage blindness — `make test` does NOT build everything (2026-07-07)
A GREEN `make test` (`GATE_EXIT=0`) does **not** mean the whole tree links. The
gate tiers (`test_critical_runtime` / `test_critical_kernel` / `test_high_bridge`
/ `test_high_gui` / `test_high_bear` / `test_medium_other`) compile only a
specific set of `.c` files into per-target test binaries. They NEVER build:
- **`APP_OBJS`** = `notepad.c doom.c explorer.c terminal.c paint.c control.c
  wubu_editor.c wubu_canvas.c wubu_codec.c apps.c` etc.
- **`tools:`** = `src/tools/*.c` (`iso9660.c weight_check.c screenshot.c
  wubu_demo_record.c …`).
So a file can be fully broken (missing `#include`, unresolved symbol, dead-struct
reference) and the gate STILL goes green. Concrete case this session: `make paint`
fails to link at committed HEAD with "undefined reference to `wubu_theme_colors`"
— yet `make test` is green. **If you changed an app/`tools` file, also run
`make <app-target>` / `make tools` to prove it still builds.** Don't assume
gate-green covers `src/apps/*` or `src/tools/*`.
- **`test_vsl_nt` is ALSO outside the gate.** The E1 ReactOS-NT test (`wubu_vsl_nt_test`) is an opt-in target not built by any `test_*` tier. A session left it HANGING in `NtTerminateJobObject` (blocking `waitpid(pgid,0)` never returned under WSL2) while `make test` reported full green — the gate never exercised it. **If E1 / `vsl_syscall_nt.c` work happened, run `make test_vsl_nt` (or `timeout 30 stdbuf -oL ./src/runtime/wubu_vsl_nt_test`) and confirm exit 0 before claiming green.** See `wubuos-nt-transliteration` skill + `references/nt-jobobject-waitpid-hang.md`. **A foreground timeout on `make test_vsl_nt` is NOT a hang** — the target links a large slice of the runtime tree (full build first) and routinely exceeds a ~200s foreground cap. Re-run it as a background job with notify and read the real exit code before diagnosing; reserve the hang diagnostics (`ps -o time`, zero output) for a genuinely spinning run. After a ONE-FILE edit the per-object pattern rules rebuild just that `.o` and relink (seconds) — re-run the target directly; the multi-minute build is first-time only.
- **NtAlertResumeThread SIGCONTs the calling process — a self-resume HANGS the test (observed closed).** Linux' default SIGCONT disposition is Stop, so `vsl_nt_alert_resume_thread()` SIGCONT'ing the test process (target = `getpid()`) suspends it forever; under gdb it looks like a stop inside libc `kill()` ("Program received signal SIGCONT, Continued"). The handler must refuse to signal `getpid()` or `getpgrp()` and return SUCCESS. The suite is fully GREEN now — run it and trust exit 0, not the hang.
- **`pkill -f <pattern>` self-match gotcha (debugging).** When you `pkill -f wubu_vsl_nt_test` to clean up a hung test, the pattern ALSO matches the very shell command line that contains the string, so the parent shell gets SIGKILLed before the target launches (you see "No such file" / no output, and the binary never ran). Either `kill` the specific PID (from `ps` / the process list), or rename the pkill target so the command line itself doesn't contain it. Don't debug a "missing" binary when the killer ate its own launcher.

### "Zombie processes" on the desktop are stale test runs holding X windows
A swarm of apparent zombies plus unmapped 340x250 / 320x200 windows parked at
`-10,-8` is normally long-lived TEST binaries -- often a SUPERSEDED build name
(e.g. `vsl_nt_contract_test` where the current target emits
`wubu_vsl_nt_contract_test`) wedged on GPU/driver init. Each holds one X
connection, which pins one window open; `ps` shows them alive for DAYS while the
process state count stays 0. Clean with `tools/dev/reap_stale_tests.sh` (kills test
binaries older than `WUBU_REAP_AGE_MIN`, default 10 min, and `xkill`s orphan demo
windows; `--dry-run` only reports). Diagnose by AGE, not by iteration count:
sample `ps -o etimes=` before killing, then confirm the CURRENT binary exits
(`timeout 15 ./src/runtime/wubu_vsl_nt_contract_test`) instead of assuming the
hang reproduces. Do not `pkill -f <name>` from a shell whose own command line
contains that name -- it kills the launcher first.

### Gui-shot / test-harness stale-object trap (2026-07-20)
**Symptom:** A test binary or harness (`wubu_gui_shot`, `test_gui_screenshot_apps`, etc.) runs but crashes / misbehaves (segfault, wrong layout, wrong window order) even though the source code looks correct.

**Root cause:** The target's prerequisite list in the Makefile omits most of the `.o` files it actually links. Example: `gui_shot` listed only 3 objects (`wm.o wubu_theme.o vbe.o`) but the link line pulled 20+. Editing `calc.c` rebuilt `calc.o` but `make gui_shot` didn't relink it → stale `calc.o` (with old `calc_draw_button` logic) linked → segfault at `calc_draw_button` with `w=-2` (impossible in current code).

**Fix:** The target's prerequisites MUST enumerate every `.o` that appears in its link recipe. Either:
- List all objects explicitly in the target's prereq line, OR
- Use a macro that expands to the full set (e.g. `$(GUI_OBJS) $(RT_OBJS) ...`) so `make` sees the full dependency graph.

**Check command after any header edit:**
```bash
find src -name '*.o' -older src/gui/<edited_header>.h
```
If any object is older than the header you just changed, that's the bug — `make` won't rebuild it.

**Pattern to audit:** Any `test_*` or harness target whose recipe has a long `$(CC) ... $(GUI)/foo.c $(GUI)/bar.c ...` line but whose prereq line is just `target: a.o b.o c.o`. Those are stale-object bombs.

### Theme Cycle Verification (2026-07-20)
The deterministic GUI capture harness (`wubu_gui_shot`) produces 5 themed frames:
- 01: Win98 Classic desktop (teal bg, navy active title)
- 02: Win98 Classic apps (5 tiled windows, calc shows "42")
- 03: Win98 Classic Control Panel (9 tabs, navy active title)
- 04: XP Luna Blue apps (blue gradient titles, rounded buttons)
- 05: WuBu Green apps (green accents, WuBu Canvas + Calc + Control Panel)

**XP Media Orange theme was REMOVED from the cycle.** If orange appears in Frame 04 of old captures, it's stale output.

**Verification workflow:**
1. Regenerate: `make wubu_gui_shot && ./wubu_gui_shot` (EXIT=0, 5 PPM frames in `/tmp/wubu_gui_shots/`)
2. Convert: `mkdir -p /tmp/ppng && for f in /tmp/wubu_gui_shots/*.ppm; do convert "$f" "/tmp/ppng/${f%.ppm}.png"; done`
3. Run pixel verification script (see `wubuos-gui-rendering` skill `references/theme-cycle-verification.md`):
   - 0 orange pixels across all frames
   - Correct theme colors per frame (teal/navy for Win98, blue gradient for XP, green for WuBu)
   - Window layouts match tiled coordinates (no overlap)

This catches the "orange window always there" class of complaint — the user is viewing a stale frame from the old cycle, or the orange theme was accidentally re-added.

**Add to test gate:** When modifying themes, WM chrome, or `wubu_gui_shot.c`, run the full verification before claiming green.

### Theme cycle verification gate (2026-07-20)
**Context:** The `wubu_gui_shot` harness cycles through 5 themes in hardcoded phases. User complaints about "orange window always there" were traced to stale captures from the old cycle that included XP Media Orange.

**Current cycle (verify in wubu_gui_shot.c main):**
1. `01_desktop_win98` — Win98 Classic (teal desktop, navy titles, silver taskbar)
2. `02_apps_win98` — Win98 Classic apps (tiled, calc active with navy title)
3. `03_controlpanel` — Win98 Classic Control Panel (9 tabs, navy title)
4. `04_apps_xp` — XP Luna Blue (blue gradient titles, rounded buttons)
5. `05_apps_wubu` — WuBu Green (green accents)

**XP Media Orange (orange title bars, borders, Start button) is NOT in current cycle.** If user reports orange, they're viewing a stale frame.

**Verification gate for any theme/wm change:**
1. `make wubu_gui_shot && ./wubu_gui_shot` → EXIT=0, 5 PPM frames in `/tmp/wubu_gui_shots/`
2. Convert: `for f in /tmp/wubu_gui_shots/*.ppm; do convert "$f" "/tmp/ppng/${f%.ppm}.png"; done`
3. Pixel-verify each frame with PIL:
   ```python
   # Frame 01/02/03: teal desktop (0,128,128), navy active title (0,0,128)
   # Frame 04: blue gradient title (0,82,138)  
   # Frame 05: green title (0,128,80)
   # NO frame should have orange (232,108,0) title bars
   ```
4. All 5 frames must match expected theme colors

UPDATED 2026-07-07 (end of session): `test_syscall`, `test_styxfs`, and
`test_holyc` were ALL FIXED this session (signal.h feature macro; missing
compiler backend in the link line; HolyC JIT global-var SIGSEGV — see
`wubuos-holyc-compiler` skill `references/holyc-global-sigsegv-fix.md`). The
full `make test` gate now exits 0 ("All tests passed"). Do NOT re-list those
three as broken.

Rule: a red that does not link your changed files AND is reproducible from clean
at HEAD before your edit is NOT your bug — report it, don't fix it.

### Synthetic title-bar drag tests must grab LEFT of the chrome buttons (2026-11-16)
`test_ui`'s "move window" + "replay" assertions silently failed while resize
passed. Root cause: the test dragged the title bar at `x + w/2` (centre). On a
200px/160px window the chrome close/max/min buttons are laid out FROM THE RIGHT
~38px each, so they span `[x+w-114, x+w]` -- for 200px that is `[x+182, x+w]`,
so the CENTRE is the minimize button. The DOWN hit minimize -> window became
not-hit-testable (MINIMIZED) -> the drag fell to empty desktop (lasso), nothing
moved. Resize worked because it grabs the right EDGE.

Diagnosis trail that nailed it (reusable): instrument `hit_test` to dump all
alive windows' rects (`[W0@x,y w h m]`) -- window a showed `m` (minimized)
while its struct said `(100,100)`. A later run showed NO `HITDBG` for the down,
proving the chk swallowed BEFORE hit_test; a `KHITDBG` print just inside the
chrome-button loop showed the down reaching it and returning.

Fix: grab the title bar LEFT of the buttons (`x+30`) in every synthetic drag.
Use center-x only for windows wide enough that the buttons can't reach it.

This is a two-sentence rule: **a synthetic title-bar drag must grab where the
title text is (left side), never centre-x on a small window -- centre-x is the
minimize button.**

### VBE Double-Buffer Pattern for Tests (2026-07-21)
When testing VBE-rendered content, follow this pattern to avoid double-buffer timing bugs:

```c
vbe_init(W, H);
// Draw to back buffer (VBE drawing functions write here automatically)
control_draw(&win, vbe_framebuffer(), W, H, c);
vbe_swap();  // Copy back → front
uint32_t *fb = vbe_framebuffer();  // Now read from front buffer
// Check pixels in fb
```

**Root cause of control panel test failure:** The test read from the front buffer (`g_vbe.fb`) before `vbe_swap()` copied the back buffer content. The orb was drawn to the back buffer but the test scanned the (empty) front buffer.

**Additional fix:** Test was calling `chrome_draw_window()` a second time, which redrew the chrome OVER the already-drawn orb. Test now computes content rect from window geometry instead of re-calling chrome.

**Fix applied:** `test_control` now passes 20/20 (was 19/20).
A prestige-update / next-session prompt's "remaining gaps" list is a HYPOTHESIS,
not ground truth. Don't act on a named "monolith frontier" or "N remaining
`system()` calls" without re-auditing. This session a v27 handoff claimed "10
remaining `system()` calls" and named 4 monoliths — a fresh audit found **1** real
`system()` call and **0** un-split monoliths (all 4 were already decomposed into
3–10-module families in an earlier session; the OBJS lists prove it). Re-audit
recipes (real `system()` enumeration excluding comment-noise, OBJS-sibling check,
empty-non-test-body scan) are in `references/stale-handoff-frontier-audit.md`.
The boss's standing order: "don't trust stale probes/handoffs."

### Silent-mask real bugs: recursive delete (2026-07-13)
A "green gate, broken code" class: `wubu_fs_rm_rf()` used `nftw` with an `unlink`
callback, which returns `EISDIR` on directory entries, aborting the traversal and
leaving the whole tree in place — every `rm_rf`/`archd_rm_rf`/`bottles_rm_rf`
caller ignored the rc, so recursive delete was a silent no-op. Fix + standalone
harness in `references/recursive-delete-nftw-eisdir.md`. Lesson: when a helper's
rc is widely ignored, test the deep path (dir, not just file) before trusting it.

### VSL Test Suite Growth (v21 — 2026-07-05)
- **v21**: 83 tests (+21 identity/credential/sysinfo tests). KEY: extracted VSL_SYS_* macros from wubu_vsl.h (god header) to self-contained vsl_syscall_numbers.h (zero includes, just #defines). vsl_syscall.c no longer depends on wubu_vsl.h.
- **New handlers**: geteuid, getegid, setuid, setgid, setreuid, setregid, getresuid, getresgid, setresuid, setresgid, getgroups, setgroups, setpgid, getpgid, setsid, getsid, umask, uname, sysinfo, getrandom, getrlimit, setrlimit, prlimit64, alarm
- **C11 fixes**: removed static forward decls from vsl_internal.h, removed duplicate static defs from vsl_process.c and vsl.c. VSL_PROC now tracks uid/gid/euid/egid/pgid/sesid/umask per-process.
- `vsl_init()` PID 1 initializes identity from host (was hardcoded 0)
- **getuid/getgid**: fixed hardcoded `return 0 /* root */` → returns real per-process uid/gid

### VSL Test Suite Growth (v20)
- **Before Phase 3**: 52 tests (Phase 3 syscalls)
- **After Phase 4**: 56 tests (+4 namespace/security syscall tests)
- **v20**: 62 tests (+6 namespace/security: landlock, bpf, perf_event_open, fanotify_init, fanotify_mark, unshare, setns)
- **Key Fix**: Function signatures for `vsl_sys_landlock` and `vsl_sys_bpf` changed from 7 params to 6 to match `vsl_syscall_fn` typedef

### VSL Syscall Parameter Usage Fix (2026-07-05)
**Problem**: Multiple VSL syscall handlers were using raw fd parameters directly instead of mapping through `vsl_get_host_fd()`, which is required for VSL's virtual fd table.

**Fixed handlers** (12 syscalls):
- `vsl_sys_dup` - now uses `vsl_get_host_fd(fd)` before `dup()`
- `vsl_sys_dup2` - now uses `vsl_get_host_fd()` for both oldfd and newfd before `dup2()`
- `vsl_sys_fcntl` - now uses `vsl_get_host_fd(fd)` before `fcntl()`
- `vsl_sys_fsync` - now uses `vsl_get_host_fd(fd)` before `fsync()`
- `vsl_sys_unlink` - already correct (path-based, no fd mapping needed)
- `vsl_sys_mkdir` - already correct (path-based)
- `vsl_sys_rmdir` - already correct (path-based)
- `vsl_sys_rename` - already correct (path-based)
- `vsl_sys_getcwd` - already correct (path-based)
- `vsl_sys_chdir` - already correct (path-based)
- `vsl_sys_clock_gettime` - already correct (no fd)
- `vsl_sys_sched_yield` - already correct (no fd)

**Pattern for fd-based syscalls**:
```c
static int64_t vsl_sys_XXX(uint64_t fd, ...) {
    int host_fd = vsl_get_host_fd((int)fd);
    if (host_fd < 0) return -9; /* EBADF */
    int rc = syscall_XXX(host_fd, ...);
    return rc < 0 ? -errno : (int64_t)rc;
}
```

**Result**: All 62 VSL tests pass. Pattern established for remaining fd-based syscalls needing real parameter usage.

### wubu_gnu_compat.h feature-macro doctrine — declare the surface natively, not via _GNU_SOURCE
WuBuOS builds runtime/syscall sources under `-std=c11` with a deliberate
`-D_POSIX_C_SOURCE=200809L` (and force-includes `src/runtime/wubu_gnu_compat.h`).
The project doctrine is: **WE define the feature surface; do NOT switch the whole
build to `_GNU_SOURCE`.** When a syscall/exec source uses a BSD/GNU/Linux libc
extension (`memfd_create`, `unshare`, `setns`, `pipe2`, `setresuid/gid`, `chroot`,
`strcasecmp`, `syscall`, `pread64/pwrite64`, `madvise`, `setgroups`, `wait4`),
`-std=c11` hides it → `implicit declaration of function 'X'` (which breaks under
`-Werror`/C23). Fix it the native way, per scope:
- **One shared header used by many handlers** (e.g. `vsl/vsl_syscall_internal.h`,
  included by every VSL personality): put `#define _GNU_SOURCE 1` at the TOP,
  after the include guard, BEFORE any system `#include`. `_GNU_SOURCE` is a
  superset of `_DEFAULT_SOURCE` + `_LARGEFILE64_SOURCE`, so one define covers
  every extension the handlers forward. This is the whole-family fix.
- **One or two files**: add `#define _GNU_SOURCE 1` (or `_DEFAULT_SOURCE` for
  POSIX-XSI-only like `usleep`) at the very top of that `.c`, before its first
  `#include` — glibc's `<features.h>` only honors it if set before any header.
- **A source missing a plain POSIX header** (`getpid`/`unlink` etc. undefined):
  the real cause is a missing `#include <unistd.h>`, not a macro — add the
  include. Don't reach for `_GNU_SOURCE` to paper over a missing header.
- **Bare `#define WUBU_HOSTED` at the top of a `.c`** that the build ALREADY
  passes via `-DWUBU_HOSTED` → `"WUBU_HOSTED" redefined` warning. It also does
  NOT expose any libc symbol (a common misreading). Guard it: `#ifndef
  WUBU_HOSTED` / `#define ...` / `#endif` so it is a no-op when already set.
Verify a fix by rebuilding the affected target and grepping its output for
`implicit declaration` / `redefined` (target 0). Do NOT rewrite the shared
`-D_POSIX_C_SOURCE=200809L` build flag to `_GNU_SOURCE` — that contradicts the
doctrine and re-hides the intent.

### Execution-leg verification pattern (build a real binary at runtime, run it, assert the exit code)
The RUNTIME "execution leg" goals (ELF/PE/Mach-O/WASM/DOS/OCI legs) all verify
"a real <format> binary runs on the kernel with correct output". The proven,
self-contained pattern (no external game/binary dependency):
1. **Precondition-probe + graceful skip.** Check the toolchain/runtime is present
   (`system("command -v i686-w64-mingw32-gcc")==0`); if absent, print a skip note
   and return a DISTINCT code (2) so it is not a code-failure red.
2. **Build a real binary at runtime** via a host compiler into a temp path:
   ELF=`cc`, PE32=`i686-w64-mingw32-gcc -mwindows` (32-bit — the kernel Wine
   prefix is `WINEARCH=win32`, so a PE32+ x64 binary won't load → exit 1), etc.
   Have it `ExitProcess(code)` / `return code` a KNOWN value (e.g. 42).
3. **Load the bytes back, validate the magic** (`0x7F 'E' 'L' 'F'` / `'MZ'`).
4. **Dispatch through the exec path** (`wubu_exec_linux_elf` / `wubu_exec_win_pe`)
   and assert the exit code ROUND-TRIPS (`rc == 42`). Plus the error path:
   garbage/NULL rejected (`-1`).
5. **Stub the deep deps you don't exercise** (`hd_eval`, `wubu_dos_proc_*`) in
   the test TU; link the REAL container/isolation stack. Match the working
   neighbor target's link line, then resolve link errors by adding only the
   genuinely-missing sources (and `-lm -fopenmp -lpthread` if holyd/JIT pull in
   math/OMP). See the SWEEP stub-file exception above.
6. **Wire the new target into a tier** (`test_high_bridge`) so it runs in the gate,
   and remove it from `mk/test_wiring_baseline.txt` if it was a known orphan.
Debugging an exit code that comes back as a signal (`-N`) or wrong: see
`references/exec-leg-secmon-observe-debug.md` — the two runtime bugs this pattern
surfaces (unregistered seccomp profile killing the child; secmon ptrace tracer
racing `wubu_ct_wait`'s plain `waitpid` and losing the exit code).

### All Tests Green — run `make test` for the live target/assertion count
```bash
make test  # ~5 minutes; all test targets must pass — run for the live count
```
Run `make test` for the live per-target tally; every target must read ✅ PASS. Do not hard-code the totals here — they shift as suites land.

**Note:** `test_vsl` is FIXED — the modular `src/runtime/vsl/vsl_syscall.c` syntax errors (periods instead of semicolons, truncated syscall table) were all fixed; it passes its live count. `test_apps` may still reference deleted `wm.c` (out of gate — see "Known pre-existing broken targets").

### Vacuous tests: a zeroed dimension global makes every assertion read nothing

When a model-shaped suite fails with *every* buffer empty ("d_x has non-zero
gradients" FAIL, forward weights all identical, argmax always 0), suspect the
dimension globals before the math: `WUBU_DIMS` / `WUBU_RUNTIME_DIMS` default to
zeros until an initializer runs. `D_MODEL=0` makes `calloc(0, …)` return a
pointer, so every loop executes zero times and every check inspects an empty
buffer — the module is fine, the test never ran it.

- Call the project's initializer (`wubu_dims_default()` /
  `wubu_runtime_dims_default()`) as the FIRST statement of the test's `main()`,
  before any allocation sized by a dimension macro.
- Print the resolved dims (`D_MODEL=… N_EXPERTS=…`) in the test header. A suite
  that cannot state its dimensions is not testing a model.
- This failure mode has appeared twice in different suites; treat "all zeros"
  as a dims error signal, not as evidence the kernel is broken.

### A pass/fail that flips with unrelated code is memory corruption — run ASan

If a suite passes, then fails after an unrelated addition (a new static array in
another translation unit, an extra test block at the end of `main`), do not
bisect the new code as a logic change. Layout sensitivity is the signature of a
latent out-of-bounds access: the new object shifts the heap/stack enough for a
stray read or write to land on something that matters.

- Reproduce with `-fsanitize=address,undefined` and read the first `SUMMARY`
  line; that names the exact file:line and the overflowing variable.
- A common shape: an API takes `const T *arr` with **no length argument** and
  scans to a sentinel (e.g. `WUBU_PID_NONE == -1`). Every caller must pass a
  full-size array padded with the sentinel — a 1- or 2-element array is an
  overread even when the values are right. Fix the production callers, not only
  the test, and write the contract into the header next to the capacity macro.
- Keep ASan clean as the closing check for that suite; "41/41 passed" without it
  only proves the stray access did not hit anything fatal this time.

### The sanitizer GATE and parser fuzzers (mk/sanitize.mk)

A green normal build does not prove memory safety, and `make test` does not run the
sanitized binaries at all. `make test_sanitize` builds a fixed set of input-handling
surfaces fresh under `-fsanitize=address,undefined -fno-sanitize-recover=all` plus
`-Werror=implicit-function-declaration` and runs them: the `.desktop`/MIME parser,
revolver env parsing, the guest FS image loader, the NT syscall sweep, and FOUR
deterministic mutation fuzzers — guest FS image (`WUBFS01`), `.desktop`/MIME, `.spell`
module container, and JSON.

- Run it after touching any parser, loader, wire-format reader or dispatch table —
  not only when you suspect a bug. It found a real defect on its first run.
- **Implicit function declarations are undefined behaviour, and silent.** A call with
  no visible prototype compiles under the default warning, the compiler assumes `int`,
  and the real return type is read from garbage. The result is a test whose PASS
  depends on stack layout — green at `-O0`, failing under `-O1`+ASan. This needs no bad
  index, only a missing `#include`; it is NOT an out-of-bounds access. **When a check
  passes normally and fails only under the gate, look for a missing prototype BEFORE
  suspecting uninitialised memory or a heap overflow.** With
  `-Werror=implicit-function-declaration` in the sanitized flags it becomes a compile
  error at exactly the moment you care.
- **Do not split a target out of the gate for a cost you have not measured.** The NT
  slot sweep forks once per slot and looks expensive; it measures ~0.7s under ASan.
  Splitting it would save nothing and hide it behind a command nobody runs.
- Four deterministic mutation fuzzers are wired into BOTH gates (`make test_<x>_fuzz`
  plain, and the same binary rebuilt under ASan/UBSan): guest FS image (`WUBFS01`),
  `.desktop`/MIME, `.spell`, and JSON. Seed and round count come from argv. Assert
  INVARIANTS, not just "no crash" — each checks properties a hostile file could break
  (bounded return values, corrupted magic refused, export offsets inside the declared
  blob, `child_count <= child_capacity`). **Two of the four found real memory-safety
  defects on their first run**, so a green fuzzer is a reason to add another parser.
- **A cap on NODE/ELEMENT COUNT does not bound per-node BYTE LENGTH.**
  `json_parse_number()` copied its literal into `char buf[64]` unchecked, while
  `JSON_MAX_TOKENS` limits how many nodes a document may have — ten thousand digits cost
  one token, so the arena cap protected nothing. When a parser enforces a token/element
  cap, audit every fixed-size destination for a per-element length the cap does not
  cover: a node cap bounds structure, not payload.
- **Validation split between parse-time and lookup-time leaves a hole.**
  `wubu_spellmod_open()` accepted images whose export table pointed outside the code
  blob; the lookup re-checked bounds, but only when `code_len > 0` — an image declaring
  no code skipped it entirely (1853 of 4000 mutants accepted). If the header states an
  integrity promise, enforce it unconditionally in the open/parse path. A CONDITIONAL
  lookup check reads as protection while leaving the hole open for whoever skips it.
- **When wiring a new target into `mk/sanitize.mk`, define its variable ABOVE the
  `test_sanitize` rule.** GNU make expands a prerequisite list at PARSE time, so a
  variable defined further down expands to EMPTY and the prerequisite is silently
  dropped — the recipe then runs a path that was never built (`not found`), and building
  the binary by hand makes the next run pass, disguising it as a flake. Verify with
  `make -qp | grep '^test_sanitize:'`.

Reference: `references/sanitizer-gate-and-parser-fuzzers.md` — the exact flags, the
implicit-declaration diagnostic order, the reusable fuzzer shape, the shared PRNG
header, the two defect patterns above, the shared-arena lifetime trap, the
parse-time prerequisite-expansion bug that bites new gate targets, how to PROVE a
regression test fails on the pre-fix code (revert discipline + strong assertions),
and the two borrowed-pointer harness traps (shared scratch buffer aliasing every
handle; a helper returning a lone static making `strcmp` compare an argument with
itself).

### Self-contained test fixtures (2026-07-15) — when a test assumes a fixture file that's never created

A test that opens a fixture (e.g. `mount_zip("/tmp/test.zip")`) but **never creates
it** fails with a misleading error (mount returns false / "file not found"), and the
gap is invisible until you read the test body. Two fixes that closed `test_explorer`
(3/3 red → green):

1. **Generate the fixture in-code** instead of depending on an external file or tool.
   Hand-roll a minimal, spec-valid binary (a STORE zip, a tiny ELF, etc.) in a helper
   called by the test's setup. This makes the test self-sufficient and reproducible
   (no `zip` binary or libzip headers required). See
   `references/test-fixture-in-code-generation.md` for the verified ZIP-builder pattern.
2. **When hand-rolling binary formats, size the magic fields correctly.** A 32-bit
   signature stored in a `uint16_t` then `fwrite(&sig,1,4,...)` reads 2 bytes past the
   var → corrupt header → the parser/loader rejects it. Store signatures in `uint32_t`.

This is a *test-harness* defect, not a product bug — but it reddens the gate, so treat
"fixture missing" as a first-class red-cause alongside assertion failures.