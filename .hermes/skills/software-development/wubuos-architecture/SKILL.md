---
name: wubuos-architecture
description: WuBuOS architecture overview — ZealOS kernel + Win98 shell + Styx/9P namespace + Arch containers. Hosted binary pattern (Inferno emu). Build system and development and run commands.
category: software-development
---

## Memory pitfalls (devil's-advocate class)

- **A weak-DECLARED function must be TESTED before it is CALLED.** The house
  weak pattern (`__attribute__((weak))` on a launcher so a module links with
  or without it) only works when the call site reads the symbol's ADDRESS
  first: `if (launch_wet_applet) launch_wet_applet(p);`. A direct call to a
  weak function that has no definition in that link is relocated to 0 and the
  call jumps to NULL -- SIGSEGV with PC 0 and a backtrace pointing at the
  caller, which reads like a heap or struct bug. Found in `wm_render.c`
  calling `wubu_ns_effect_stack()` (weak, undefined in GUI-only test links);
  gdb showed `0x0 in ??()` then `#1 wm_render ... :228`. Always guard with an
  address test, never call the weak symbol bare.

- **A `clear`/`reset` that memsets the whole struct wipes runtime config.**
  Any hive/pool with runtime fields (`elem_size`, `block_cap`, alloc/free
  callbacks) must have its clear reset only the DATA, preserving config.
  WuBuOS's kernel `wubu_hive_clear` does this correctly (resets block
  skipfields/freelists + `size`; keeps `block_cap`/`alloc`/`free_`/head/tail/
  capacity). The wubuwizard `wubu_hive_t` has no runtime config (block cap is
  compile-time), so its memset is safe.
- **A worker pool's drop/teardown must be under the pool lock, and the
  failure path must not join uncreated threads.** `wdh_reader_create`'s
  malloc-failure branch called `wdh_reader_destroy` without first setting
  `r->n_workers = i`, so destroy joined `n_cores` pthread_t handles of which
  only `i` existed -- UB. Every early-return teardown path must set
  n_workers to the number actually spawned.
- **Hive stress is the gate:** random insert/erase with per-op invariants
  (live count, no duplicate live slots, capacity >= live, alloc+reuse ==
  inserts) catches the config-wipe and freelist-corruption classes.
- **A heap with a free list + coalescing must never leave an untracked hole,
  and its coalesce must unlink from EVERY list the block could be on.**
  `src/kernel/memory.c` (ZealOS-style hash + free list + forward coalesce) had
  two corruption bugs that only a 20k-op churn test exposed:
  1. `mem_alloc` trimmed `mu->size` to the requested total even when it did NOT
     split the block, so a 16/32-byte excess became bytes belonging to no block.
     The coalesce reads `((uint8_t*)mu + mu->size)` as the next block header, so
     stale bytes in such a hole could be mistaken for a free block and merged --
     growing a free block across a live one. Fix: split whenever the remainder
     is a useful block (`MEM_MIN_BLOCK`), otherwise keep the original size.
  2. A split remainder is linked on the free list at ANY size, but the coalesce
     only searched the hash bucket when `nxt->size < MEM_HEAP_HASH_SIZE`. A small
     remainder on the free list was absorbed while still linked, and the next
     alloc handed the same memory out twice. Fix: the unlink searches both lists.
  Also: `hc + sizeof(CHeapCtrl) + max_size` overshot the real backing store by
  128 bytes, letting the coalesce read past the heap -- use `g_heap_end`, and
  account the whole controller footprint (`hc_pages` pages, not one).
  **Gate:** `make test_heap_stress` (20k random alloc/free, per-op pattern +
  red-zone verification, drain, `used==0`). Add `mem_debug_walk()` -- a linear
  contiguity walk reporting the byte offset of the first impossible block size;
  it pinned bug 1 to op 9.

## Standing Work Directives

These are the user's explicit, repeated instructions about HOW work gets done.
Embed them in every session; violate them at the conversation's peril.

1. **"Go heavy first"** — tackle the highest-leverage item in every cycle.
   Large structural fix > 20 small fixes > cosmetics > plans.
2. **"Be the angel coder"** — fix broken code. Deliver working artifacts,
   not descriptions. Keep exercising until the test actually passes.
3. **"Stop lying about time scale"** — never hand-wave about complexity.
   Agentic AI work is fast; minutes are real hours. Just do the fix.
   Honest blockers (missing hardware, unfixable deps) are the only
   acceptable stop signals.
4. **"Maximum effort, do it all"** — no stubs. No "for later." Every function
   that's called from real code does real work. Compile-time `#else` blocks
   for unavailable hardware backends are the only legitimate exception.
5. **"No third party if we can write it"** — rewriting from scratch in C11
   is the point. Self-contained modules over external deps.
6. **C11 strictness** — opaque structs, minimal includes, no god headers,
   self-contained modules. `-std=c11`. No GNU C extensions in headers.
7. **"Small wastes time first but polished"** — when a small fix IS the
   right call, polish it thoroughly. Both heavy-first and small-polished
   are valid; choose based on leverage.
8. **"Triple Devil's-Advocate" on delivered work** — after ANY
   unify/relocate/merge/refactor, re-verify with FRESH tool calls before
   reporting done: filesystem sweep for leftover duplicate checkouts, a clean
   rebuild + full `make test` gate, and a re-scan of any invariant you claimed
   (e.g. "0 slot collisions"). A first-pass "done" is a hypothesis until an
   independent adversarial check confirms it. The user explicitly demands this
   and it has caught real misses (leftover duplicate checkouts, latent
   dispatch-slot collisions) that a passing test masked.
9. **NEVER force-push to shared branches** (2026-08-14 — user correction:
   "why would you be force pushing you need to be working together with the
   buddy?") — `wubu-integration` is shared with the buddy agent. Always
   `git pull --rebase` then fast-forward push. Force-push = overwrite their
   work.
10. **Survey BEFORE dispatching subagents** (2026-08-14 — subagents
    duplicated existing work) — before spawning a subagent to build X, grep
    the tree for existing implementations. Subagents don't know what already
    exists and will waste time rebuilding it.
11. **Spec before theory** — when hardware/emulator behaviour disagrees with
    expectation, fetch the authoritative spec or the reference implementation
    (QEMU `docs/specs/*.rst`, `hw/display/*.c`, tianocore `OvmfPkg`,
osdev wiki) before forming a hypothesis, and cite it in the commit. Assumed
    mechanisms ("the option ROM never ran", "there is no MMIO window") cost
    whole debugging arcs when a five-minute read of the spec shows the real
    register layout. Research first, then a single targeted change.
12. **"We make things real"** — when an audit, roadmap or vision names a
    capability, IMPLEMENT it. Never delete the claim from the doc to make the
    gap list shorter. A doc that says the OS has X while the tree does not have
    X is a build failure, not a documentation problem.

## WuBuOS Architecture Skill

## Identity
```
WuBuOS = ZealOS kernel + Win98 shell + Styx/9P namespace + Arch containers
```
- **ZealOS** = kernel (ring-0, single-user, HolyC JIT, boots on metal)
- **WuBuOS** = shell (Win98/XP desktop, Styx namespace, .wubu containers)
- **Pattern**: Inferno OS `emu` — one binary runs on any host OS
- **Arch base** rips through Linux drivers for SteamOS/Proton compat
- **X11 → DRM/KMS**, **libm → pure C** (wubu_math.c)

## Self-host independence (the "is the computer" test)

WuBuOS boots bare metal today through a 512-byte BIOS bootsector (`boot.S` →
`boot.bin` → `disk.img`, `make qemu`). That is L1, not independence. The ladder:

L0 hosted tests → **L1 bare-metal boot (exists)** → L2 own loader + measured chain
(a C11 UEFI firmware **does** exist — `src/firmware/`, built by
`bash src/firmware/build.sh`; the measured chain is proven by
`make test_agi_metal` → `src/firmware/run-agi.sh`, which boots the real kernel
as a WuBuFW payload and asserts every hop on the QEMU serial log) →
L3 self-hosted toolchain (partial: HolyD's
battery proves constructs, not a kernel build) → L4 on-device rebuild (build
`kernel.elf` inside a booted WuBuOS and boot the result) → L5 reproducible
bootstrap (two off-network builds hash-identical, rollback slot).

Rules: never call the build "self-hosted" because `make` works on Linux, and
never claim UEFI support without an `efi_main`. Each level needs its own
acceptance test before it counts: `nm -u src/kernel/kernel.elf` must be empty
(no host libc -- it is), and L4 = the on-target build hash appears in the boot
trace. There is NO `make boot-audit` target and NO self-host status doc; the
per-level evidence lives in the firmware scripts (`run.sh`, `run-agi.sh`,
`sb-gate.sh`, `rsa-gate.sh`).

**The metal path reaches the AGI supervisor, not the desktop.** `src/kernel/`
never calls `wm_init`/`desktop_init`, and the ISO is a GRUB multiboot of
`kernel.elf` alone -- the Win98/XP shell is built and captured only in hosted
harnesses. Do not describe a metal boot as "booting the desktop".

## OS-Source Steal Workflow (research -> /n control plane)

When the user asks to "steal from another OS's source" or "update the <os>
study," see [`references/os-source-steal-workflow.md`](references/os-source-steal-workflow.md)
— clone the target's source into `vendor/` (shallow), mine citable facts
(scheduler config, gaming-meta dep lists, hw-detect), map each stealable to
the Styx/9P `/n` control plane, update the study doc, and emit a build spec
(P1-P5). Thesis: other OSes use a different mechanism per concern; WuBuOS
expresses all of them through one `/n` filesystem.

Installer/onboarding captures are in `os-studies/omarchy_install_study.md` — its
PART 2 covers the Omarchy Configurator UX (gum-gated wizard, animated ColorShift
framebuffer logo in INDEXED colors, console-width-settle guard, deferred
provisioning = personal setup at FIRST boot on the same greeter frame) with a
P1-P3 spec for a WuBuOS configurator (greeter → questions → `fat32_format` +
write OS image to an AHCI/NVMe target; first-boot onboarding; unattended path).
The "cool graphics" are front-loaded console flair over a tiny question set — the
same-frame deferred onboarding is what makes install fast and first boot feel
intentional.

**`install-wubuos.sh` (repo root) is the shipped installer.** It asks four
questions (prefix, autostart, window launcher, MCP server), writes the answers
as a JSON plan to `~/.wubu/n/install/plan.json` -- the `/n/install` surface the
study specifies, so an install is a replayable document and an audit log --
then installs, then VERIFIES by booting what it installed: the binary must
render a frame and the launcher must pass `desktop-file-validate`. Rule: an
install that does not boot what it installed is not an install. `--uninstall`
removes the same file set; `--plan-only` writes the plan without installing.
It is POSIX sh (dash-safe: no `${var/#\~/...}` substitution; prompts go to
stderr so `$(ask ...)` captures only the answer, never the prompt).

## ISA DRIVER SPACE — THE "RUN ON EVERYTHING" PROOF (2026-08-14)

The AN13 driver space now has 10 drivers. `make test_drivers` runs
33 expressions through ALL SIX interpreter-based drivers (x86-64 native JIT,
8086, m68k, 6502, RISC-V, Z80) and they ALL agree. ARM64 is a native JIT
that cannot run on x86-64 hosts. 8051, MIPS, PTX are registered but not
yet in the test battery.

### Optimizer Infrastructure

- `src/compiler/wubu_mir_opt.{c,h}` — 6 passes: fold, strength, DCE, LICM, unroll, combine
- `src/compiler/wubu_mir_regalloc.{c,h}` — linear-scan SSA register allocator
- `src/compiler/x86_peephole.c` — post-codegen peephole (movabs shrink, self-mov elim)
- `src/compiler/wubu_isa_driver.{c,h}` — the registry (compile / run / describe / find)
- `src/runtime/wubu_*_interp.c` — interpreters for non-native ISAs

One frontend: AST → MIR (`wubu_mir.c` + `wubu_mir_lower.c`) → N backends.
The optimizer runs on MIR BEFORE codegen, so all backends benefit.

PITFALLS learned (the battery was RED for hours):
1. **The battery's probe files need the holyc header includes**
   (`holyc_lexer.h`/`holyc_parser.h`) — implicit declarations
   truncate the returned AST pointer on PIE builds and EVERY driver
   looks broken. This was the FIRST thing that was wrong.
2. **`mir_driver_test`'s loop was `i < 5` with 6 drivers** — the z80
   was never tested. Array grows must update the loop bound.
3. **The m68k/8086 drivers MUTATED the shared MIR prog** via
   `wubu_mir_new_label((wubu_mir_prog_t *)p)` — replaced with per-
   driver internal label counters (`internal_label(e)` starting at
   the snapshot `e.n_labels`). NEVER mutate the caller's prog.
4. **The riscv JAL decode was broken**: `sext21(inst >> 12)` shifts
   the whole word; the J-type imm must be extracted field-by-field
   (inst[31]=imm[20], inst[19:12], inst[20]=imm[11], inst[30:21]).
5. **The riscv compare was a half-finished mess** (no store of the
   result, wrong SLT operand order, NE put the register NUMBER into
   an immediate). Rewrote as boolean-compute (SLT/SLTU/XORI + sltu
   x0,x0-style register compare for NE).
6. **The z80 driver had NO interpreter** (wubu_z80_run declared,
   never defined) + missing MUL/DIV/MOD/SHR + broken SHL/NEG +
   reversed SUB/compare operands + the LD r,r' list stopped at 0x6F
   (missing 0x70-0x7F incl. LD A,C/LD A,D/LD A,E) + INC/DEC didn't
   set flags (the loops test DEC B with JR NZ) + XOR A,n (0xEE) was
   missing for NOT. Now: full 8-bit core + SIGNED DIV/MOD (E/H sign
   flags + JP P/M + result negation per C semantics) + sign-extended
   returns (`~0` -> -1).
7. **A `LD A,n` with n=0x7B is NOT `LD A,E`** — the single-byte
   register-copy opcodes must be emitted as one byte, not as an
   immediate load. (This one was sneaky: 100/7 worked in isolation
   and only failed in the full battery.)
8. Verify the driver space with the REAL build: `make test_drivers`
   — a stale `mir_driver_test` binary silently hides all of the
   above (the Makefile target links it fresh).

### x86-64 Codegen Pitfalls (2026-08-14)

1. **`emit_mov_reg` modrm encoding**: `0x89` = `MOV r/m64, r64`. The reg
   field is the SOURCE, the rm field is the DESTINATION. modrm =
   `0xC0 | (src<<3) | dst`. REX.R extends reg (src), REX.B extends rm (dst).
   Getting this backwards swaps the operands.

2. **Shift instruction encoding**: `shl/shr rax, cl` needs `mov rcx, b` first.
   The `mov rcx, src` encoding: `rex(1, reg_needs_rex(src), 0, 0); 0x89;
   0xC0 | ((src&7)<<3) | 1`. The `1` in the rm field is rcx's encoding.

3. **movabs shrink**: Only match REX.W (`0x48`/`0x49`/`0x4C`/`0x4D`) +
   `0xB8+rd`. Do NOT match `0x41 0xB8+rd` (that's already `mov r8d, imm32`,
   a 5-byte instruction). Use a separate output buffer for the shrink pass.

4. **Store-reload elimination**: In the x86-64 compile loop, a lookahead skips
   the store when the next instruction is RET consuming the same dst vr. This
   eliminates `mov dst,rax; mov rax,dst` pairs (29% code size reduction).

The ISA gate now also includes the Z80's 8-bit boundary behavior:
`~0 = -1` (sign-extended), `-7%3 = -1` (signed MOD), all comparisons,
the ternary, shifts.

## SteamOS EPIC E2 closures (2026-08-09)

Three E2 rows went from "not implemented" to GREEN tests:

- **Pressure Vessel** (`src/runtime/wubu_pressure_vessel.{c,h}` +
  `make test_pressure_vessel`): the Steam Linux Runtime container
  preset on the bwrap runtime — runtime lib bind (ro) + the game's
  libs layered + the curated LD_LIBRARY_PATH (game first, the runtime
  fills the gaps) + GPU/Wayland surfaces. **The embedded WubuCt must
  NOT be freed with wubu_ct_destroy** (that frees the struct itself —
  free the embedded strings + the pv block only).
- **Game mode / perf governor** (`src/runtime/wubu_gamemode.{c,h}` +
  `make test_gamemode`): init RECORDS the current cpufreq governor +
  power + nvidia boost (never guess), activate switches every policy
  to performance + boost 1, deactivate restores exactly. Tested with
  a FAKE sysfs tree. Pitfalls: init read the policy DIRECTORY not
  .../scaling_governor; the sys_root override was clobbered by init's
  memset (save it first); the writes need O_TRUNC (a shorter restore
  leaves a stale tail).
- **Steam Input** (`src/runtime/wubu_steaminput.{c,h}` +
  `make test_steaminput`): the controller→virtual-input mapping
  engine (default map: A=Space, L-stick=WASD, R-stick=mouse) emitting
  into the kernel input queue + per-game config persistence.

SteamOS E2 still open: CEF/Chromium UI shell, Steam Networking (P2P),
gamescope (nested compositor — the command builder exists but not the
compositor), Steam Cloud sync, Arch daemon as Desktop boot backend.

## SteamOS SOURCE STEAL — the driver space (2026-08-09)

Fresh SteamOS source pulled + mined, drivers implemented with green
tests (docs/steamos_source_steal.md = the build spec + scorecard).

SOURCES (vendor/ is gitignored, re-cloneable):
- `vendor/SteamOS/` = Valve's SteamOS repo (docs only)
- `vendor/mainline-linux/` = sparse clone of torvalds/linux with the
  driver dirs: `drivers/hid/hid-steam.c` (the Steam Controller/Deck
  gamepad — 1880 lines, the real protocol) + `ayaneo-ec.c` (handheld
  EC) + `hid-nintendo.c` (Switch Pro).
- NOTE: gitlab.steamos.cloud (the real SteamOS kernel) requires auth;
  Valve's GitHub linux fork is the ancient 4.14 staging branch. The
  current Deck drivers are IN MAINLINE — steal from torvalds/linux.

THE DECK CONTROLLER REPORT PROTOCOL (hid-steam.c, 64-byte report 9):
- buttons: byte 8 (TR2 TL2 TR TL Y B X A, bit0=TR2), byte 9
  (dpad up/right/left/down + select/mode/start/gripl2), byte 10
  (gripr2 lpad-click rpad-click lpad-touch rpad-touch thumbl), byte
  11 (bit2=thumbR), byte 13 (bit1=gripL bit2=gripR), byte 14
  (bit2=base/Steam)
- sticks: bytes 48/50 L (Y NEGATED), 52/54 R; triggers 44/46;
  trackpads 16/18 L + 20/22 R (gated by the touch bits)
- IMU: accel 24/26/28 (X/Z/Y), gyro 30/32/34 (X/Z/Y)
- battery (separate event): voltage u16 mV at 12-13, percent u8 at 14
- gyro-to-mouse: yaw (gyro Z) -> mouse X deltas (the Deck's aim)

THE EC PROTOCOL (ayaneo-ec.c, the Deck's EC class):
- fan speed: 16-bit across two registers (low, high)
- PWM: stored 0-255, percent*2.55 encoding (round, not truncate)
- PWM mode: 1 = manual / 2 = auto (0xFF = absent EC — the probe
  validates the mode register to detect a bare/nonexistent EC)
- temp register (0xFF = not exposed)

LIZARD MODE (hid-steam.c): the controller defaults to keyboard+mouse
mappings; a real client opening the device CLEARS them (raw gamepad);
closing restores. WuBuOS: wubu_si_set_lizard_mode() + the feed fns
honor it.

THE /n CONTROL PLANE (the 'one namespace' thesis):
/n/ec/{fan,pwm,mode,temp,status} + /n/steaminput/{map,status,report,
battery}. `echo <64 hex> > /n/steaminput/report` parses a real report.
Each file wraps the REAL API via ns_mkdir/ns_write (wubu_ns_fs.c +
wubu_ns_bridge_internal.h). PITFALL: the /n subtree TESTS must NOT
link wubu_ns_bridge.o (it drags the whole archd/bottle graph — the
memory-constrained-linker rule): set `*(const char **)&g_ns_root`
directly + link wubu_ns_fs.o + the module only.

PITFALLS:
1. The runtime pattern rule (mk/pattern-rules.mk) lacks -I$(KERNEL) —
   any runtime file including input.h fails in `make runtime` even
   though the test targets pass (they add -I$(KERNEL) themselves).
   Fixed by adding -I$(KERNEL) to the runtime %.o rule.
2. A 'LD A,n with n=0x7B' is NOT 'LD A,E' (z80 lesson) — one-byte
   register-copy opcodes must be emitted as one byte.
3. The g_lizard declaration must precede the feed functions that use
   it (C11: no implicit decls).
4. Tests with persistent held-state must re-init before a later test
   that presses the same button.

Gates (all green): test_steaminput 10/10, test_ec_control 5/5,
test_ns_ec 4/4, test_ns_steaminput 4/4, test_gamemode 4/4,
test_pressure_vessel 5/5, test_drivers 33/33.

Remaining steals: hid-nintendo.c (Switch Pro), the rumble/haptic
(ID_TRIGGER_RUMBLE_CMD 0xEB), the SETTING_GYRO_MODE_* configs.

## THE REAL-HARDWARE DRIVER SPACE (2026-08-09) — Steam Deck + laptop

The GOAL: WuBuOS boots on a REAL Steam Deck + laptop. The kernel's
bus layer (PCI/ACPI/XHCI/AHCI) existed; the driver space on top is
now complete (src/kernel/wubu_drv*.c, `make test_drv` 6/6):

- wubu_drv.c — the Linux-style registry: devices on buses, drivers
  with ID tables (vendor:device + class/subclass), match + probe,
  boot-log summary. The built-in table = the Deck's real IDs.
- wubu_drv_nvme.c — the NVMe controller (the Deck's 2230 SSD):
  BAR0 MMIO, admin queue + CSTS.RDY handshake, IDENTIFY namespace.
- wubu_drv_net.c — wifi (RZ616/MT7921 + Intel AX) + ethernet
  (r8168/I219): link + MAC from the class register window.
- wubu_drv_hda.c — HD Audio: the controller + codec verb model.
- wubu_drv_gpu.c — KMS-lite: connector (eDP/DSI/HDMI/DP) + mode +
  VRAM; the Van Gogh/Rembrandt/Cezanne/Intel Xe ID tables.
- wubu_drv_battery.c — ACPI _BIF/_BST: percent from capacity ratio.
- wubu_drv_ahci.c — the SATA shim binding the pre-existing ahci.c.

KEY DECK/LAPTOP PCI IDS: 1002:163F (Van Gogh iGPU), 144D:A80A
(Samsung 980), 15B7:5009 (SN770 2230), 14C3:7922 (RZ616 wifi),
8086:51F0/2723 (AX201/211), 1022:1457 (Van Gogh HDA), 10EC:8168
(r8168), the ACPI battery class = 01/0C.

THE TEST PATTERN (real-bus simulation): inject the FAKE MMIO windows
per driver (nvme_mmio with CSTS.RDY at 0x1C, wifi/eth windows with
the link byte + the 6-byte MAC, gpu window with connector/mode/vram,
battery via set_state) + add the Deck's devices to the registry via
wubu_drv_add_device() — the binding logic is proven without hardware.

PITFALLS:
1. The wubu_drv_dev_t/wubu_drv_t header ordering — the driver probe
   takes a struct wubu_drv_dev*; the driver typedef must come FIRST.
2. The GPU VRAM test encoding: 8192MB = LE bytes 00 20 00 00 (not
   00 00 20 00) — a 4-byte LE read of the wrong bytes gives 2097152.
3. Kernel test binaries link with -I$(KERNEL) + -O2 -Wall -Wextra
   (the test_acpi pattern), NOT the runtime pattern.
4. Each driver's test hook is an explicit set_*_mmio / set_state —
   no DI framework, the registry probe reads the injected state.

## THE AGI WORLD-STATE BRIDGE — the OS as the training space (2026-08-09)

THE VISION: WuBuOS is an AI operating system — the user plays games,
browses, interacts with the AGI, and makes things. Every act is LIVE
TRAINING DATA; the OS is a WORLD the AGI perceives. The integration:

- wubu_world.c (kernel/): the compact snapshot assembled from the
  REAL driver state (never counters): hw[] net[] scr[] power[] heat[]
- wubu_world_sample() -> wubu_world_snapshot(): the AGI's in-process
  read (holyd, the colony)
- /n/world/state + /n/world/hw (wubu_ns_world.c): the 9P reads
- the AGI trains on the DELTAS between samples — the world's motion

KEY LESSON (the live-link fix): a driver the world bridge samples
must re-read its hardware on EVERY call — wubu_net_wifi_link() reads
the LINK register per call instead of returning a probe-time cache,
or the world can never see a link drop. Any state the AGI senses
must be live, not cached.

THE 9/9 TEST-DRV DEVICE TABLE (the fake Deck bus, all bound):
1002:163F gpu, 144D:A80A nvme, 1022:7906 sd, 14C3:7922 wifi,
1022:1457 hda, 10EC:8168 net, 01/0C battery, 11/00 thermal,
03/01 usb-hid + 08/06 usb-msc + E0/01 usb-bt, 08/05 sd class;
one deliberately unbound (the 1B21:1242 USB 3 controller).

THE DECK'S SD READER = AMD 1022:7906 (SDHCI class 08/05); the
thermal fan curve: <50C=20%, 50-70=20+(t-50)*2, 70-90=60+(t-70)*2,
>90=100 + the throttle flag over the zone limits.

Remaining hardware classes: the PS/2 + I2C HID keyboard/trackpad
bind (wubu_hid feeds exist), the eDP/DSI backlight, the HDA DAC DMA
path, the USB-C/DP alt-mode.

## THE DESKTOP PARITY WAVE — SteamOS desktop in OUR code (2026-08-09)

The directive: "anything missing from the SteamOS desktop — any
button, any option, any click, any normal user interaction needs to
be done... make it so that Steam can run on our colonel and the games
can run on our colonel and everything runs on our colonel."

- **Big Picture Mode** (src/gui/bpm.c): the fullscreen
  gamepad-first shell over the era-apps grid (CP/M 1974 → HolyC 2020,
  7 apps / 4 runnable): d-pad = the selection (scancodes 0x48/0x50/
  0x4B/0x4D), A = 0x1C launch, B = 0x01 exit. The gaps show greyed.
  The launch hook is injectable (the tests record). The era-apps
  launch pulls the whole VSL graph — the TEST uses a stub
  (era_apps_test_stub.c), the house stub pattern.
- **The world-state tray** (wm_tray_world.c): the live
  battery/network/heat indicators from the world snapshot (green
  charging / red low / blue up / grey down / red throttled). + the
  systray gained systray_update_color/color.
- **The Control Panel MANAGER is REAL** (controlpanel.c): the
  header declared g_controlpanel forever but the manager was never
  built — the applets had no registry. Now: init/register/unregister/
  get/select/sidebar/render/show-hide-toggle/shutdown + input routing.
  The Hardware applet (cp_hardware.c) renders the machine the
  AGI perceives via an injectable world-state provider.
- **The Colonel runs everything**: 'bpm' + 'hardware' in the colonel
  app registry (src/runtime/wubu_colonel.c g_apps seed) → `colonel
  run bpm` validates. The desktop's Play action now has its missing
  backend: wubu_session_launch_game() writes the game bytes + runs
  them shell-free (fork + execvp, no /bin/sh).
- **THE STUB PATTERN** (used twice this wave): a GUI TU that pulls a
  heavy graph (the VSL exec / the WM render) gets a *_test_stub.c
  providing the same contract over a fixed fake — the shell logic is
  tested in isolation. Precedents: dos_window_test_stub.c,
  era_apps_test_stub.c, wm_systray_test_stub.c.
- **PITFALL**: wm_internal.h used hosted_state_t without
  including ../hosted/hosted.h — a pre-existing a11y build break
  (fixed). The GUI headers that use size_t/uint8_t must include
  stddef.h/stdint.h (C11 has no implicit decls).

Gates: test_bpm 5/5, test_wm_tray_world 4/4,
test_controlpanel 7/7, test_cp_hardware 4/4, a11y ok.

## THE APP-GAP WAVE — the registry is complete (2026-08-09)

The audit (docs/desktop_apps_roadmap.md): every colonel-registered
name vs its implementation. Found: taskmgr was REAL but NEVER
REGISTERED (the name validated, the launch went nowhere); notes/todo/
music had ZERO code; test_apps referenced stale .o files and
could not build at all.

**THE INTEGRATION RULE (this wave's lesson)**: a name in the colonel
registry MUST have a launchable implementation OR a scoped roadmap
entry — never a validated-but-empty name. g_app_defs is the single
source of truth (desktop + startmenu + colonel consume it).

Completed apps (all real, persisted to ~/.wubu/ on the 9P fs):
- Notes (src/apps/notes.c): create/select/delete/save on real files.
- Todo (src/apps/todo.c): [ ]/[x] lines in ~/.wubu/todo.txt.
- Music (src/apps/music.c): the playlist scan from ~/.wubu/music/,
  play/stop/next/prev over the REAL wubu_sound engine (the API is
  wubu_sound_play(s, event, sink) — NOT wubu_sound_event).
- Task Manager: real code existed (src/apps/taskmgr), orphaned — now
  registered. The registry is 20 real apps, zero shells.

PITFALLS hit:
- APP_OBJS had apps.o WITHOUT the new app objects AND the .o
  was STALE — the registry edit compiled into nothing; the runtime
  'built' against the old table. ALWAYS rm the .o + wire the objects
  together.
- test_apps referenced .o files (wubu_a11y.o etc.) that were
  never built — a pre-existing broken target. Fixed: all .c sources +
  the link-only stubs in the test file (the established pattern) +
  -lz. 44/44 green.
- The new app headers needed stdint.h + the DosGuiWindow forward;
  the test file's WM stubs collided with the real functions the graph
  pulls (remove the test's copy when the real one links).
- apps_gap test stub: notes/todo/music bind DosGuiWindow callbacks —
  the test links a tiny stub (wm_create returns NULL + a
  vbe_draw_text no-op) and exercises the LOGIC only.

Properly scoped FUTURES (docs/desktop_apps_roadmap.md): Browser (the
internet-basin project — first milestone: the /n/net path + an HTTP
GET rendering text into the terminal/canvas pipeline) + Freedoom (the
game-port project — a C11 Doom-class renderer over the Vulkan compute
leg). Honest status: designed, not started — no fake shells.

### XP accessory apps follow the calc/notepad pattern (Minesweeper precedent)

A new XP accessory (game or tool) is: opaque struct + `*_internal.h` (the
full struct lives ONLY there, never duplicated in the .c — a struct defined
in both the .c and the internal header is a redefinition error), real
`on_draw`/`on_key`/`on_mouse` bound to a `wm_create` window, registered
in `g_app_defs` (the single source of truth the desktop + startmenu +
colonel consume), and a **standalone logic test** (`*_test.c` + a
`*_test_stub.c` providing no-op `vbe_fill_rect`/`vbe_rect`/`vbe_draw_text` /
`chrome_draw_window` / `wm_create`) so the game logic is proven
without linking the GUI stack. Minesweeper shipped this way (GUI gate +
apps gate green).

**PITFALL — flood-fill / graph-walk recursion (bit during Minesweeper):** in a
recursive flood-fill (minesweeper reveal, region fill, connected-component),
mark the cell visited/revealed BEFORE recursing into its neighbours. Marking
it AFTER the recursive calls leaves it still "hidden" during the recursion, so
two adjacent zero-cells recurse into each other forever (stack-overflow
segfault, not a wrong answer). The visited-guard must be set on entry, not on
exit.

## THE TRIPLE-DA STEAMOS AUDIT + FILLS (2026-08-09)

docs/steamos_da_audit.md = the fine-tooth comparison vs SteamOS
(desktop layer / gaming layer / driver REAL-vs-SIMULATED). The DA
found two real gaps, both filled:

- **DECLARED-BUT-NEVER-BUILT APPLETS**: the header declared
  cp_create_display/network/theme_applet() with ZERO impls.
  Now real: display (connector/mode/VRAM from the world), network
  (wifi/eth from the world), theme (the real wubu_theme engine — a
  click cycles). The manager registers all FIVE (display/network/
  sound/theme/hardware). PITFALL: the applet .c typedefs must match
  the header's (a forward `struct wubu_world` ≠ the anonymous typedef
  `wubu_world_t` — the struct is now NAMED so GUI headers can
  forward-declare it).
- **THE BAR GLUE**: wubu_pci reads BAR0/BAR1 but wubu_drv_pci_scan
  DROPPED them — the real-hardware MMIO mapping was missing (the
  probes only worked with injected set_*_mmio). Now: the scan carries
  bar0/bar1 + wubu_drv_dev_bar() exposes the MMIO base. The drivers
  are contracts + simulated hardware in tests; the BAR accessor is the
  real-hardware mapping point (the honest boundary).

Remaining honest gaps (documented, never claimed): the keyboard/mouse
CP applets, the boot login (SDDM parity), the eDP/DSI backlight, the
HDA DAC DMA path, and the real Steam client UI — WuBuOS HOSTS Steam
via Proton/VSL, it does not clone the store/library/overlay.

## The media-creation path (the decoder-synthesis model)

The encoder side is SHIPPED (wubuwizard: the SLOT + our-image/audio/
text encoders + the VHF canvas + the universal codec — audio↔image
reversible). The DECODER that GENERATES media is NOT trained yet.
docs/decoder-synthesis-plan.md (wubuwizard) fixes the architecture
(a small transposed decoder inverting the frozen encoders, the canvas
field conditioning, the reconstruction + smoothness objective) + the
training plan (the Muon pipeline, the corpus, the gate = the canvas
continuity invariant). Training = a multi-day GPU job; the doc makes
it mechanical. Once trained: 'our-decoder' registers into the SLOT +
the OS gets a Media Studio app.

## Stream D — NT Registry as Styx9 Namespace (2026-07-24)

The NT registry (file-backed: key=dir, value=`[type:4][len:4][data]` file) is
now exposed as a 9P filesystem at `/n/nt/registry`. Implemented in
`src/runtime/styxfs_server.c::nt_registry_styx_export()`:

- Walk/read/write/stat callbacks operate on the same `g_nt_reg_root` that the
  NT syscall handlers (`vsl_nt_create_key`, `vsl_nt_set_value_key`, etc.) use.
- 9P `create` = new registry key (mkdir), `remove` = delete key/value,
  `read`/`write` = value data, `stat` = file attrs.
- No separate daemon — the Styx server shares the backing store with the NT
  personality. `make test` verifies the shared store survives cross-access.

**Pattern for new Styx9 exports**: add a `*_styx_export()` function to
`styxfs_server.c` that swaps the server's callbacks; the caller wires it into
its namespace mount point. See `nt_registry_styx_export` for the canonical
example.

**Standing directives when auditing a reference OS (from the 2026-07-18 GrahaOS
audit):**
- **Adopt the core, reject the stubs.** Port real subsystems (capability model,
  bootcap cascade, rollback primitive, manifest-driven dispatch). DO NOT copy
  `-ENOSYS` stubs (TLS/FS/restore) — wire them to WuBuOS's existing real
  subsystems (Styx9P FS, hosted userspace) instead.
- **Grep the tree for an existing equivalent BEFORE creating a "new" module.**
  The reference repo is a source of ideas, not a license to duplicate what the
  tree already has (a prior pass built `wubu_spec/` cap, then found `wubu_cap/`
  already existed — deleted the dupe, extended `wubu_cap/` instead). Grep order:
  `grep -rln '<concept>' src --include='*.c' --include='*.h'`.
- **Audit output → `docs/<OS>_AUDIT_AND_WUBUOS_ADOPTION.md`** with a
  steal/reject/scorecard structure (full pattern in the reference's GrahaOS
  refinements section).

The `/n` control plane is REAL code, not just a thesis — see
[`references/n-control-plane-pattern.md`](references/n-control-plane-pattern.md)
for the shipped `wubu_ns_bridge` / `wubu_ns_snap` / `wubu_ns_fs` module layout,
the svc→bottle→snap mapping table, the FS-core extraction that keeps lightweight
subtrees linkable, and the test-split + heap-struct rules for this memory-
constrained WSL.

## Project Structure
```
/home/wubu/wubuos
├── src/
│   ├── kernel/       # memory, tasking, vbe, input, interrupt, fat32, ahci, txfs, wubu_gaad, wubu_math
│   ├── jit/          # x86-64 encoder, disasm, regalloc, minic
│   ├── compiler/     # HolyC lexer, parser, codegen, PTX backend
│   ├── gui/          # Win98/XP WM, desktop, startmenu, explorer, terminal, theme, notify, settings
│   ├── bridge/       # VBE↔WorldSim, syscall bridge, DOS↔Temple flip
│   ├── apps/         # editor, canvas, codec, freedoom, repl, apps
│   ├── runtime/      # containers, exec, VSL, proton, OCI, network, snapshot, archd, holyd, gc, edr
│   │   └── vsl/gpu/   # VSL GPU/Vulkan compute (wubu_vsl_gpu.{c,h}, wubu_vsl_vulkan.{c,h}) + tests + Makefile
│   ├── hosted/       # Wayland/Vulkan/Metal hosted stack + hosted.c main (the product binary)
│   ├── tools/        # iso9660, screenshot, weight_check
│   └── bear/         # RL training (arena, env, nn, ppo, opt, cudnn, vulkan_soft)
├── Makefile          # Top-level build
├── BATTLESHIP.md     # ~3000 REAL_GAP audit (v20)
└── OS_BIBLE.md       # Architecture reference
```

## Fresh host build bring-up (a fresh clone is NOT buildable on its own)

wubuos builds depend on sibling repos/submodules by topology — a plain `git clone` of
wubuos cannot compile until all three are present:
1. `src/compiler` is a SYMLINK to `/home/wubu/wubunos`. Clone the compiler repo there
   or every `#include "../compiler/holyc.h"` fails with `No such file or directory`:
   `git clone https://github.com/waefrebeorn/WuBuNOS.git /home/wubu/wubunos`.
2. Init the submodules (`.gitmodules`): `src/brain` (wubuwizard),
   `src/apps/wubupad`, `src/apps/wubuoffice`, `src/lua/www` (WWW),
   `src/gui/wet` (WET), `src/gui/vws` (VWS) -- `git submodule update --init
   --recursive` from the wubuos root. The container is NOT a submodule: it is
   in-tree at `src/runtime/container/*.c`. Bringing a
   NEW external repo in (and fixing the cross-repo paths its build assumes) is
   its own procedure: `references/vendored-repo-onboarding.md`.
3. The host needs the system dev headers (json-c, openssl, zstd, wayland, vulkan, sqlite3,
   zlib, GL, pulseaudio, xkbcommon, cairo + the X11 stack). PROACTIVELY check the whole
   surface before the first gate run — `test -f /usr/include/<h>` per header — else the gate
   dies ONE header at a time across re-runs. On Debian/Ubuntu/Mint: `apt-get install -y
   libjson-c-dev libssl-dev libzstd-dev libwayland-dev libvulkan-dev libsqlite3-dev
   zlib1g-dev libgl-dev libpulse-dev libxkbcommon-dev libcairo2-dev libx11-dev
   libxkbcommon-x11-dev libpng-dev libjpeg-dev libexpat1-dev ninja-build pkg-config
   gcc g++ make git curl`. On hosts without passwordless sudo, install via the authorized
   python `sudo -S` subprocess mechanism (see the `wubuos-takeown` skill) — never shell-piped
   `sudo -S`.
A gate that fails on `fatal error: .../x.h` or a dangling `src/compiler` is a bring-up gap,
NOT a code regression — git status clean on the touched file confirms it before debugging.

## Build System
```bash
cd /home/wubu/wubuos

# Full build
make all              # kernel jit compiler runtime tools gui bridge apps worldsim metal audio shell bear hosted_objs hosted

# Individual layers
make kernel           # memory, tasking, vbe, input, interrupt, fat32, ahci, txfs, wubu_gaad, wubu_math
make jit              # encoder, disasm, regalloc, minic
make compiler         # holyc lexer, parse, codegen, ptx
make runtime          # container, exec, vsl, proton, styx, arch, oci, snapshot, network, archd, holyd
make gui              # WM, desktop, startmenu, explorer, terminal, theme, proton, gamelib
make hosted           # the product: ./src/hosted/wubu (the Win98/XP shell as
                      # a process on a host display). Same graph as the capture
                      # harnesses, but hosted.c is compiled WITHOUT
                      # -DWUBU_HOSTED_TEST so its main() is live. Part of `make all`.
make hosted_objs      # the Vulkan/GBM/Metal objects only (no link)

# Bear RL
make bear_train       # Training binary (./src/bear/bear_train)
```

## Hosted Binary (The Product) — verified 2026-11-11

`make hosted` builds `./src/hosted/wubu` (the Win98/XP shell as a process on a
host display) and is part of `make all`. Flags: `-h` headless boot + clean
shutdown, `--screenshot <path>` renders a real frame headless, `-w W H`,
`-t`/`-c` Temple/Console modes, `-f` fullscreen; no flag needs a Wayland
compositor, GUI mode does.

**`-h` is HEADLESS, not height.** Geometry is `-w W H` (both values after a
single `-w`). Writing `-w 960 -h 540` parses as width 960 then switches to
headless mode -- `540` is ignored and no window appears. A bare positional
after `-w W` is NOT a height.

```bash
make hosted                              # -> src/hosted/wubu
./src/hosted/wubu --screenshot /tmp/w.ppm
./src/hosted/wubu -h
```

**Why the link needs a hand-written closure.** The shared object lists
(`RT_OBJS`/`GUI_OBJS`/`APP_OBJS`) are NOT the hosted closure: the shell reaches
services they omit. `mk/targets.mk` carries that list as `HOSTED_EXTRA`
(a11y, sound, psych, bonzi_study, the EDR poller, gdpr_age, wine_env,
compat_db, kernel memory/world/kvfs/input, wubufx, the WET applet framework +
its slerm-Lua `$(LUAGUI_LV_SRCS)`, and three compiler backends). Three traps:

1. `src/hosted/*.code` are wayland-scanner **private-code C sources** with a
   non-C extension — compile them with `-x c -c` first, never pass them to the
   linker (it reads them as a linker script).
2. `wubu_tgemm_avx512.c` needs `-mavx512f -mavx512dq`; the tree ships a
   prebuilt `src/compiler/wubu_tgemm_avx512.o`, so link the `.o`, not the `.c`
   (compiling it inline makes the whole binary AVX-512-only).
3. `GUI_OBJS` used to carry `$(GUI)/lua/wubu_lua_gui.c`, which needs
   `wb_lv.h` from the WWW submodule — it broke every recipe that compiles
   `GUI_OBJS` directly (that is why `gui_shot` was RED). The module has no
   live consumer; it stays covered by `test_lua_gui`, which compiles it with
   `-I$(LUAWWW)`. Do not put it back in `GUI_OBJS` without the include path.

**Hardware sense.** The metal kernel senses hardware through its own drivers;
the hosted binary has no bus, so `src/hosted/wubu_hosted_hw.c` answers the
same accessor contract from the host's `/sys` + `/proc` (battery, net, thermal,
nvme/sd, DRM connector/modes, the `wubu_hw_*` detector API, and `wubu_drv_find`).
It replaces the `wubu_hw_stub.c` / `wubu_hw_sensors_stub.c` no-hardware shims
in the hosted graph. Gate: `make test_hosted_hw` — every probe is cross-checked
against the live host, and `wubu_world` is driven end to end.

Pitfall: `launch_app()` used to treat a launcher's `NULL` return as "no launch
path". Several launchers (HolyC/Temple terms) spawn via `wm_spawn_*` and return
`NULL`, so a registered app silently reported a false failure. `launch_app` now
checks `app_find_by_name()` first — a registry entry IS the launch path.

### The rendering law — do not intermix rendering policies

Two concerns live in the hosted body, and they must stay in separate owners:

- **Rendering** — how the desktop is drawn. Owned by the render path
  (`hosted_render_desktop` -> `wm_render` -> VBE back buffer -> `vbe_swap`).
  It must not know about the compositor.
- **Presentation** — whether a finished frame is handed to the compositor.
  Owned by the presentation layer (`hosted_wl_frame_render`: attach,
  damage_buffer, commit).

A shadow-buffer + `memcmp` comparison placed in the FRAME LOOP is a SECOND
rendering policy next to the first: it silently redefines when a frame is
drawn and breaks the double-buffer/damage/commit contract. The user called
this out as "intermixing rendering policies and breaking the laws of
rendering". The comparison itself is fine -- it belongs in the PRESENTATION
layer, the only owner of "should this frame be committed". That is the
shipped fix: `hosted_wl_frame_render()` keeps a shadow of the content it last
presented and returns early (no attach/damage/commit) when the SHM buffer is
byte-identical, keeping the buffer alternation consistent. The render path is
never told about it and never needs to be. A dirty flag out of the render
path (the animations/clock/input already know when something changed) is an
acceptable alternative, but a content compare in the PRESENTER is not a
workaround -- it is the correct owner.

**Measuring a repaint/flicker report (do this before and after any
presentation change):**
- Commit rate: run the client with `WAYLAND_DEBUG=1` and count
  `wl_surface@N.commit()` lines per second. ~19-30/s means every loop
  iteration presents; ~0.5/s means only genuine changes do.
- Window content: capture the weston window with `xwd` repeatedly and md5
  the pixel bytes to count DISTINCT frames (a static window = 1 distinct
  frame over 10 s).
- Control: run weston ALONE (no client) and measure the same way. If the
  compositor is static, it is not the flasher -- do not "fix" weston.

**Orphaned clients and compositors are a flashing source.** Every launch
leaves a `wubu` client and a `weston` behind unless it is killed; five clients
plus several compositors all repainting one X display reads as a flashing
laptop panel even when each is individually idle. Clean up with EXACT pids
(`ps -eo pid,comm --no-headers | awk '$2=="weston"||$2=="wubu"{print $1}'`)
-- never `pgrep -f "hosted/wubu"`: that pattern matches the shell running the
command itself and SIGTERMs your own session (the command dies with exit -15).

**A `960x0 window` + `mmap: Invalid argument` / `dup failed: Bad file
descriptor` means the client has no live compositor or a stale binary.** The
SHM pool cannot be created for a zero-height surface, so the VBE backend
attaches at `960x0`. Rebuild and relaunch against a live compositor before
diagnosing geometry code -- the failure is a harness artifact, not a product
bug.

**The federation surfaces (agent identity + space bridge).** The OS carries the
agent's own identity and reaches the ~WuBu~ space:
`src/runtime/wubu_agent.{c,h}` (the AID + sponsor + SHA-256 seal, persisted at
`~/.config/wubu/agent-card.txt`, published at `/n/agent/`) and
`src/runtime/wubu_ns_worldspace.c` (the `/n/worldspace/` subtree: world state,
agent, portal, transport, capabilities). `make worldspace` builds the WWW engine
the body REACHES — it does not embed it (that would drag MuJoCo, Lua and a second
renderer into the OS process); the body builds it and publishes the entry point.
The `/n` root is `~/.wubu/n`. Full contract + the AID arithmetic:
`references/federation-agent-surface.md`.

## Key Files to Understand
| File | Purpose |
|------|---------|
| `src/hosted/hosted.c` | Main entry, event loop, VBE, WM init, Wayland callbacks |
| `src/bridge/wubu_syscall.c` | Syscall bridge handlers, trampolines |
| `src/kernel/interrupt.c` | Full IDT/PIC/APIC/IOAPIC/LAPIC/SYSCALL |
| `src/runtime/wubu_vsl.c` | Syscall translation, ELF validation, drivers |
| `src/runtime/wubu_container.c` | .wubu parser, universal exec |
| `src/runtime/wubu_network.c` | 9 network types, CNI, WireGuard, Tailscale |
| `src/runtime/wubu_oci.c` | Native HTTP client, OCI registry ops |
| `src/runtime/wubu_snapshot.c` | OverlayFS snapshots, branching, GC |
| `src/gui/wm.c` | Win98 WM, GAAD snap, virtual desktops |
| `src/jit/jit.c` | x86-64 encoder + 4 backends (mmap, asmjit, MIR, minic) |
| `src/kernel/wubu_math.c` | Pure C libm replacement (sqrt, sin, cos, log, pow, atan2) |
| `src/runtime/wubu_edr.c` | EDR shim (split → `src/runtime/edr/`) |
| `src/runtime/edr/edr_core.c` | EDR core: lifecycle, modules, alerts, worker thread |
| `src/runtime/edr/edr_proc_pin.c` | Process pin: NETLINK_CONNECTOR + cn_proc (59+ processes) |
| `src/runtime/edr/edr_fanotify.c` | File telemetry: fanotify + inotify + FAN_ATTRIB timestomp |
| `src/runtime/edr/edr_poller.c` | Periodic /proc: unix sockets, modules, cron, proc recovery |
| `src/runtime/vsl/vsl_macho.h` | Mach-O binary loader: header structs, FAT, API |
| `src/runtime/vsl/vsl_macho.c` | Mach-O loader: validate, FAT extract, segment mmap, entry |
| `src/runtime/vsl/vsl_macho_test.c` | Mach-O loader tests: 24 tests |
| `src/runtime/vsl/vsl_syscall_numbers_mac.h` | macOS syscall numbers: Mach traps + BSD syscalls + IPC constants |
| `src/runtime/vsl/vsl_syscall_mac.c` | macOS syscall dispatch: 77 BSD handlers + 13 Mach trap handlers + mach_msg IPC |
| `src/runtime/vsl/vsl_syscall_mac_test.c` | macOS syscall dispatch tests: 20 tests |
| `src/runtime/vsl/vsl_mach_ipc.h` | Mach IPC types: port tables, msg formats, return codes |

## REAL_GAP Classification — What's Actually a Gap (2026-07-08)

The BATTLESHIP.md gap count (~400 sprint REAL_GAPs) is a **hypothesis, not ground
truth**. Many patterns flagged by naive grep are intentional — chasing them wastes
cycles. Distinguish carefully before editing:

### NOT Real Gaps (intentional patterns, do not chase)

1. **Void casts on 6-register syscall params (d, e, f)**: Every VSL syscall handler
   receives 6 uint64_t params (a,b,c,d,e,f). Many syscalls use only 1-3 and void-cast
   the rest. This is NOT a gap — it's the fixed-register dispatch convention.
   Files: `vsl_syscall_net.c` (58), `vsl_syscall_fileio.c` (46), `vsl_syscall_proc.c` (37).

2. **`#else` compile-time stubs for unavailable hardware**: Backends like DRM, ALSA,
   PulseAudio, PipeWire, and X11 have `#if HAVE_DRM` / `#else` blocks. In the `#else`
   path, init returns -1 and shutdown/flip are empty — correct behavior for
   "backend not compiled in."
   File: `wubu_metal.c` (6 empty shutdown/flip functions — all in `#else` blocks).

3. **`return 0;` on success-path helpers**: Many helper functions write to out-buffers
   and return 0 for "message handled." These are not stubs.
   File: `styx.c` (37 return-0 — all real work before the return).

### Real Gaps (form≠function — close these)

1. **Functions with ONLY void-casted params and `return 0`/`-1`** — the entire body
   is empty aside from `(void)args; return 0;`. Classic cases: `bear_checkpoint_save/load`,
   `bear_trainer_save/load`, `vsprintf` (in freestanding libc), `wubu_anticheat_proton_config`.

2. **Functions that `return 0;` / `-ENOSYS` when the return value should be a computed
   result or a real operation.** The classic case: `wubu_x86.c` had 33 encoder functions
   returning hardcoded 0 instead of the actual byte count emitted. A 2026-07-08 session
   case: `lvm_snapshot_create` returned hardcoded `-ENOSYS` instead of running the real
   `lvcreate` command. Fix: do the real work (fork/exec the tool, compute the value) and
   return its result. Prove with a test that asserts the function no longer returns the
   hardcoded stub value.

3. **Functions whose body is a no-op despite real downstream callers / explicit
   `/* stub */` markers.** 2026-07-08 session cases: `bear_optimizer_step` (empty loop
   with comment "This function is a no-op") and `bear_optimizer_zero_grad`
   (`(void)opt;` with comment "Zero grads of registered params - stub"). Fix: store the
   param/state pointers needed at registration time, then dispatch to real per-element
   update/zero logic. The word "stub" in a comment is the single highest-signal marker —
   grep for it before any body scan (see extended scanner reference).

4. **Serialization/checkpoint stubs in compute stacks.** Functions named `*_save` / `*_load`
   that take struct pointers and file paths but only void-cast + return 0. The caller
   expects state persistence — if the function is a no-op, training progress is lost.
   Fix: binary serialization with magic+version header, dimension validation on load.

5. **Freestanding libc stubs called by real code.** `vsprintf(buf,fmt,args)` returning 0
   means its caller `sprintf` returns 0 → all callers get empty output. Fix: implement
   format specifier lexer (%d, %u, %x, %s, %c, %p, %l, %ll, %%, %0N width) using
   the existing `itoa()` helper.

6. **Config-mutator stubs.** `wubu_anticheat_proton_config(type, config)` that only
   void-casts and returns 0 — downstream callers (Proton launcher, bottles) query
   `wubu_anticheat_recommended_config()` and get the defaults even after a custom
   config was "applied." Fix: store into the mutable config array.

### Automated Scanner

See `references/gap-hunting-scanner-2026-07-08.md` for the baseline reusable Python
script that walks the tree and finds function bodies consisting solely of void-casts
+ return 0/-1. **Current state (2026-07-08):** that class is now EMPTY except
`wubu_x11_set_mode` (a `#else` X11-absent hardware stub — correct `-1`, NOT a gap).
Run it after each gap-closure session to audit the remaining real gaps.

The baseline scanner misses two other form≠function shapes (real-work-but-hardcoded-
return, out-param-never-written). Use the extended scanners in
`references/gap-hunting-scanners-extended-2026-07-08.md` for those.

## WM Module Split — 2026-07-21

`wubu_wm.c` (548 lines) was split into 4 files + internal header, following
the `_internal.h` + sub-module pattern. See
[`wubuos-monolithic-split/references/wm-split-case-study-2026-07-21.md`]
(../wubuos-monolithic-split/references/wm-split-case-study-2026-07-21.md)
for the full recipe.

| File | Lines | Concern |
|------|-------|---------|
| `wubu_wm.c` | 186 | Core: init, window lifecycle, GAAD snap |
| `wubu_wm_desktop.c` | 61 | Virtual desktops (switch/next/prev/move) |
| `wubu_wm_input.c` | 180 | Keyboard & mouse input, drag/resize |
| `wubu_wm_render.c` | 142 | Rendering: chrome, taskbar, snap preview |
| `wubu_wm_internal.h` | 18 | Shared `extern WubuWM g_wm` for sub-modules |

**Pre-existing test bugs found during split:**
1. `test_wubu_wm` couldn't link (missing container objects)
2. Theme cycle test — assumed 4 themes (THEME_COUNT=5 with Zune)
3. Teal desktop color — `0x00808000` should be `0x008080`

## Theme Cycle & User Complaints — 2026-07-21

**Current `gui_shot` capture cycle (hardcoded in main):**

| Frame | Theme | Window Titles |
|-------|-------|---------------|
| `01_desktop_win98` | Win98 Classic | — |
| `02_apps_win98` | Win98 Classic | Calculator (navy), Notepad, File Manager, TaskMgr, Canvas |
| `03_controlpanel` | Win98 Classic | Control Panel (navy) |
| `04_apps_xp` | XP Luna Blue | Calculator, Notepad |
| `05_apps_wubu` | WuBu Green | Calculator, Control Panel |

The XP Media Center Orange theme was **REMOVED** from the cycle. If a user reports "the orange window is always there", they are likely viewing a stale frame from the old cycle where Frame 04 was XP Media Orange (`THEME_XP_MEDIA_ORANGE`, `win_title_active = 0xE86C00`).

## Theme Application Order Trap (2026-07-21)

**Symptom:** Captured frames show orange Control Panel window / orange title bars when Win98 Classic was requested.

**Harness root cause:** `wubu_theme_set(THEME_WIN98_CLASSIC)` was called **BEFORE** `desktop_init()`, and a later `wubu_theme_set(...)` from a settings load overwrites it. The fix is to set the harness theme **AFTER** init:

```c
wm_init(SHOT_W, SHOT_H);
desktop_init();
wubu_theme_set(THEME_WIN98_CLASSIC);  /* AFTER init - survives settings load */
```

**The product root cause is deeper, and `desktop_init()` does NOT call
`wubu_settings_init()`** (grep it -- zero hits). Nothing outside tests called
`wubu_settings_init()` at all, so no real binary ever applied a theme: the live
colour table is only seeded from `wubu_theme_set()`, so `tc()->btn_face` and
`tc()->icon_text` stayed 0 -- black taskbar, invisible desktop icons, borderless
windows. The capture harness looked right only because it calls
`wubu_theme_set()` directly and never loads settings. **Any binary that renders
the GUI must call `wubu_settings_init()` (or `wubu_theme_set()`) itself, before
the first render.**

**Two settings-loader rules that follow:**
1. **Apply defaults BEFORE the JSON load.** `wubu_settings_load()` overrides
   only the keys it finds; a key absent from a saved file keeps whatever was
   there, which is zero if defaults were not applied first. Order is
   `settings_apply_defaults()` -> load -> apply theme.
2. **Every settings key needs a deliberate default.** `show_desktop_icons` had
   none, so it took the zero value (false) and `desktop_init()` hid every icon
   -- the product surfaced an empty desktop while the harness (no settings)
   showed them. A bool that gates a visible surface defaults to the state a
   fresh install should have.

**Verification:** After the fix, all 5 fresh frames had **0 orange pixels**. The cycle is now: Win98 → Win98 Apps → Win98 Control Panel → XP Luna Blue → WuBu Green. No orange frames.

**Debugging tip:** If a theme "doesn't stick", check the call order of
`wubu_theme_set()` vs any `*_init()` that might call it -- the last call wins.
If the whole CHROME is black rather than a wrong colour, the theme was never
applied at all: look for the missing `wubu_settings_init()`/`wubu_theme_set()`
call in that binary's boot path.
1. Generate fresh frames: `make gui_shot && ./gui_shot` (EXIT=0)
2. Convert: `for f in /tmp/wubu_gui_shots/*.ppm; do convert "$f" "/tmp/ppng/${f%.ppm}.png"; done`
3. Pixel-verify each frame with PIL:
   ```python
   # Win98 Classic: teal desktop (0,128,128), navy title (0,0,128)
   # XP Luna Blue: blue gradient title (0,82,138)  
   # XP Media Orange: orange title (232,108,0) — NOT in current cycle
   # WuBu Green: green title (0,128,80)
   ```
4. If user sees "wrong" color, check which frame they're viewing — old frames may have orange

**Verification gate for theme changes:**
- All 5 frames render EXIT=0
- PIL analysis confirms expected theme colors per frame
- No "orange box" artifacts in Win98 or WuBu frames

## C11 Constraint — No Nested Functions (2026-07-08)

WuBuOS compiles with `-std=c11` (GCC). GCC nested functions (`auto int fn() { }`
inside another function) are **not valid C11** and will fail to compile. Do NOT use
GNU C nested function syntax, including the `auto int fn() -> int { }` trailing-return
form.

**WRONG** (will not compile):
```c
int resolve_deps(...) {
    auto int helper(const char *id) -> int {
        return 0;
    };
    helper("foo");
}
```

**RIGHT** — use a static context variable + callback pattern (already used in codebase):
```c
static int g_helper_idx = 0;  /* context variable */
static int cb_helper(void *data, int argc, char **argv, char **col) {
    (void)data; (void)col;
    g_helper_idx = ...;  /* access context */
    return 0;
}
int resolve_deps(...) {
    g_helper_idx = 0;
    db_query(sql, cb_helper, NULL);
}
```

Or use inline macro helpers for simple lookup logic:
```c
static int pkg_index(const char *id, char (*pkg_set)[128], int n_total) {
    for (int i = 0; i < n_total; i++)
        if (strcmp(pkg_set[i], id) == 0) return i;
    return -1;
}
```

## C11 Constraint — Feature Macros Must Precede Includes (hosted test .c files)

A hosted runtime-test `.c` that calls a glibc-extension function must `#define
_GNU_SOURCE` (or the strictest feature macro it needs) as the FIRST line of the
file, BEFORE any `#include` — otherwise the compiler falls back to an implicit
int declaration and, for `char *mkdtemp(...)`, truncates the returned pointer (int
vs pointer): the test then SEGFAULTS calling the result. The glibc headers only
print the declaration when the macro was visible at the very top of the TU. A
`#define _GNU_SOURCE` placed after the standard includes is too late and does
nothing. Same class: `PATH_MAX` is only defined by `<limits.h>` when
`_POSIX_C_SOURCE` is set — a host .c that uses `PATH_MAX` must set the feature
macro first AND, to stay kernel/host-portable, guard it: `#ifndef PATH_MAX\n#define
PATH_MAX 4096\n#endif` after `<limits.h>` (the bare-metal build has no
`_POSIX_C_SOURCE`). The build failing on the missing define rather than silently
misbehaving is the good case; the mkdtemp pointer-truncation is the bad one — it
compiles and then crashes at runtime.

## EDR Engine (src/runtime/edr/)
Split from single 566-line file into 5 self-contained modules. **12/12 tests passing**.

| Module | Lines | What It Does |
|--------|-------|--------------|
| `edr_core.c` | 406 | Lifecycle, module system, alert buffer, FNV-1a, worker thread, public API |
| `edr_proc_pin.c` | 201 | NETLINK_CONNECTOR + cn_proc — process fork/exec/exit (heavener's PsSetCreateProcessNotify) |
| `edr_fanotify.c` | 244 | fanotify (file ops + FAN_ATTRIB timestomp + script capture) + inotify (6 config dirs) |
| `edr_poller.c` | 324 | Diff-based /proc/net/unix, /proc/modules, cron dirs, missed-process recovery |
| `edr_internal.h` | 212 | Opaque struct pattern, extern globals, cross-module API |

See `references/edr-alert-routing-research.md` for routing/pins gap analysis (~1,200 LOC new C).

---

### Session 2026-07-04: Orientation & State Sync + Devil's Advocate Limit Break

**Context**: User requested "continue from last session and get oriented — it was a dumb model moment" followed by "limit break our limits" with devil's advocate parity review.

**State Found** (counts are point-in-time — do NOT treat as current; run `make test` to get live numbers):
- **Test green = gate**, not a fixed count. Aggregate assertion total grows as suites land; verify with `make test` rather than citing a stale number.
- **REAL_GAP backlog** is tracked in BATTLESHIP.md (versioned). Re-read the file; never cite a historical count as current.
- **VSL syscall convention**: 6-register dispatch; trailing register params (d,e,f) are unused by most handlers and appear as void casts — that is the *expected* shape of the table, not automatically a bug. A REAL_GAP is a stub on the *success path* (returns -1 / not_impl / const), not a void-cast of an unused reg.

**Devil's Advocate Limit Break — Scope Reclassification**:
- **Previous rule**: Only void casts, placeholders, stubs, system() calls, weak aliases, not_impl = REAL_GAP
- **New rule (Limit Break)**: EVERY parity gap with SteamOS/Ubuntu/Arch/TempleOS/ZealOS = REAL_GAP
- **Parity Audit Expansion**: ~860+ new REAL_GAPs from SteamOS (95%), Ubuntu/Arch (80-95%), TempleOS (70%), Arch Daemon (95%), TempleOS Daemon (80%)
- **Updated Critical Tier**: 8 active work items (VSL, Package Manager, Audio, Arch Daemon, TempleOS Daemon, Proton, Bear Vulkan, SteamOS Parity)
- **Reference**: `references/devils-advocate-parity-audit-2026-07-04.md`

**Parallel Execution Campaign — Completed Workstreams (4/8)**:
1. **VSL Syscall Void Casts** — ✅ 173 void casts are unused register params (d,e,f) in 6-register convention; 17 syscalls already implemented
2. **Package Manager** — ✅ 9 system() calls in tests replaced with fork+exec; pacman/apt wrapper, repo sync, deps, hooks, signing; all 11 tests pass
3. **Audio Engine** — ✅ 14/14 tests passing; Furnace tracker (30+ chips), TinySoundFont (SF2), Ardour-style DAW, AI plugin containers, USB MIDI, ingestion protocols (ALSA/evdev/JACK/PipeWire)
4. **Arch Daemon** — ✅ AUR support (build/search), package signing & repo management, pacman hooks, ABS; all 16 tests pass
5. **TempleOS Daemon** — ✅ Persistent compiler state (HCCompiler maintained across eval calls); REPL mode (repl_start, repl_eval, repl_stop); Macro expansion (macro_define, macro_undef); Session save/restore with compiler state; tests pass (run for live count)

**Parallel Execution Campaign — In Progress (4/8)**:
5. **TempleOS Daemon** — wubu_holyd.c has session/window/9P framework; need HolyC REPL, persistent compiler state, symbol table, macro expansion
6. **Proton/Wine** — PE loader, API translation table, Wine fork+exec; need DXVK/VKD3D integration, Steam runtime detection, prefix management, compat database
7. **Bear Vulkan** — 29 void casts in tensor ops; need full GPU compute pipelines, memory management, tensor operations
8. **ReactOS NT Syscall Study** — 297 NT syscalls mapped from sysfuncs.lst; need complete mapping NT→VSL→Styx9→ZealOS→TempleOS

**Test green = gate**: run `make test` for the live pass/fail + assertion count. Do not rely on a memorized total — suites are added continuously.

## Common Rendering Pitfalls (preserved from prior sessions)

### RGB Macro Bug (wubu_theme.c:12)
**Symptom**: All colors swapped in screenshots (teal→yellow, gray→yellow)
**Root Cause**: `RGB(r,g,b)` macro defined as BGR: `(b<<16 | g<<8 | r)` instead of RGB: `(r<<16 | g<<8 | b)`
**Fix**: `#define RGB(r,g,b) ((uint32_t)((r)<<16 | (g)<<8 | (b)))`

### WSL2 Wayland Compositor
**Environment**: WSL2 lacks native Wayland compositor
**Workaround**: `Xvfb :99 -screen 0 1024x768x24 & weston --backend=x11-backend.so ...`

**X11 readback of a GL-rendered window is BLACK.** `xwd` capture of a window
weston draws with its GL renderer returns an all-black image even though the
client's SHM buffer provably holds the right pixels (verify with
`WUBU_DUMP_FRAME=1` / `WUBU_FORCE_COLOR=0x00FF0000` in
`src/hosted/hosted_wayland_shm.c`). Run weston with `--renderer=pixman` and
the window content becomes readable — this is the only reliable way to
measure "what is on the workspace" from outside.

See other `references/*.md` files for detailed patterns on:
- Wayland callback closure patterns
- Syscall bridge patterns
- File explorer implementation
- VSL modular refactor
- Desktop WM patterns
- ClipBoard implementation
- VSL syscall patterns
- HolyC codegen patterns
- Native image formats
- Math precision fixes
- Test suite status

### TLS Migration: mbedTLS → OpenSSL in OCI HTTP Client (2026-07-24)
The OCI HTTP client's mbedTLS backend was unavailable on the build system. Migrated to OpenSSL (system `libssl-dev` available). See `references/tls-openssl-migration-2026-07-24.md` for the complete pattern including:
- Shared `SSL_CTX` initialization
- `SSL_new`/`SSL_connect`/`SSL_read`/`SSL_write`/`SSL_shutdown` lifecycle
- Proper `SSL_get_error` handling for `WANT_READ`/`WANT_WRITE`
- Makefile link flag updates (`-lssl -lcrypto`)
- Test verification via `make test_oci` and `make test_pkgmgr`

## Key Implementation Patterns

### Opaque-Struct Accessor Pattern (2026—07## Opaque Struct Internal Header Pattern
```c
/* vsl_internal.h —20)
**Problem:** Tests reach into opaque structs (`CalcState`, `TaskManagerState`, `RegeditState`, `FileManagerState`, `ControlState`, `NotepadState`) → compilation errors when headers only forward-declare.

**Solution:** Add **read-only accessors** to each module's public API rather than exposing internals. This preserves opacity while giving tests verified inspection capability.

**Pattern applied across 6 modules this session:**

```c
// Public header (e.g., taskmgr.h)
int    taskmgr_get_active_tab(const TaskManagerState *tm);
int    taskmgr_process_count(const TaskManagerState *tm);
int    taskmgr_process_pid(const TaskManagerState *tm, int i);
const char *taskmgr_process_name(const TaskManagerState *tm, int i);
double taskmgr_process_cpu(const TaskManagerState *tm, int i);
double taskmgr_total_cpu(const TaskManagerState *tm);
int    taskmgr_hist_idx(const TaskManagerState *tm);

// Implementation (taskmgr.c)
int taskmgr_get_active_tab(const TaskManagerState *tm) { return tm ? tm->active_tab : 0; }
// ... etc.
```

**For leaf data structs that ARE public** (like `WubuLayer`, `RegKey`), expose the full struct in the public header — tests can then navigate `.name`, `.children`, `.child_count` directly. This mirrors `WubuLayer` in `wubu_canvas.h`.

**Test rewrite:** Convert all `state->field` pokes to accessor calls. 34 test sites converted this session, `test_apps` now 40/40 green.

### Safe String Macros
```c
#define WUBU_STRCPY(dst, src, dst_size) \
    do { if (dst_size > 0) { strncpy((dst), (src), (dst_size) - 1); (dst)[(dst_size) - 1] = '\0'; } } while (0)
#define WUBU_SNPRINTF(dst, dst_size, fmt, ...) \
    do { if (dst_size > 0) { snprintf((dst), (dst_size), (fmt), __VA_ARGS__); (dst)[(dst_size) - 1] = '\0'; } } while (0)
```

### TOCTOU-Safe Create/Open
```c
// New folder: mkdir with EEXIST check
while (mkdir(path, 0755) != 0) { if (errno != EEXIST) return false; }
// New file: open with O_CREAT|O_EXCL
while (1) { int fd = open(path, O_CREAT | O_EXCL | O_WRONLY, 0644); if (fd >= 0) { close(fd); return true; } if (errno != EEXIST) return false; }
```

### Non-blocking Pipe Read Pattern
```c
static bool ex_clipboard_read_pipe(int fd, char **out_text, size_t *out_len, int timeout_ms) {
    struct pollfd pfd = { .fd = fd, .events = POLLIN };
    if (poll(&pfd, 1, timeout_ms) <= 0) { close(fd); return false; }
    // ... realloc loop reading from fd
}
```

## VSL Multi-OS Syscall Dispatch (macOS + NT + Linux)

VSL now dispatches **three OS personalities** from a single entry point:

- **Linux (x86-64 ABI)** — `vsl_syscall_table[]`, handlers in `vsl_syscall_{proc,fileio,memory,net}.c`
- **Windows NT (ReactOS)** — `g_nt_dispatch[296]`, handlers in `vsl_nt_*.c` (10 modules) + facade
- **macOS (XNU)** — `mac_bsd_table[512]` (52 handlers) + `mac_trap_table[96]` (13 handlers) in `vsl_syscall_mac.c`, Mach-O loader in `vsl_macho.c`

`vsl_syscall_dispatch()` no longer routes by class bits -- it funnels into the
**kernel interchange** (`runtime/wubu_kernel_xchg.{h,c}` + `vsl/vsl_kernel_adapt.c`),
where each personality owns a DISJOINT number range in a `try_dispatch()` callback
and the router decides. Full pattern in
[`references/vsl-multi-os-syscall-dispatch.md`](references/vsl-multi-os-syscall-dispatch.md).

### Routing rules when several kernels share one syscall space

- **Give every kernel a DISJOINT number range.** Reserved class bytes, the other
  high-byte classes, and the bare range must each be claimed by exactly one
  kernel. Disjoint ranges make the outcome independent of registration order;
  overlapping ranges make it depend on whichever kernel was registered first --
  and the bug only shows up in one ordering.
- **When two kernels must share a range, the SELECTED kernel is authoritative.**
  NT and Linux both own bare syscall numbers, so the selected one answers and the
  other declines. Do NOT silently fall through to the unselected kernel: that
  makes selection meaningless and hides a kernel that cannot answer.
- **A kernel that cannot answer leaves the call UNHANDLED**, reported as such --
  never re-attributed to a kernel that was moved out of charge.
- **Optional link dependencies go in as `__attribute__((weak))` + an address
  test.** A personality whose bridge object does not build under the pattern rule
  must not become a hard dependency of every link that includes the facade. The
  weak declaration may be added AFTER the header's own declaration and still
  compile cleanly.
- **Sweep the link lines.** Adding a `.c` to a widely-linked path breaks every
  recipe that links the caller -- see the Link-Regression Sweep below.

New macOS VSL files:
- `src/runtime/vsl/vsl_macho.h` — Mach-O header structures, FAT binary, API
- `src/runtime/vsl/vsl_macho.c` — Mach-O loader: validate, FAT extract, segment mmap
- `src/runtime/vsl/vsl_syscall_numbers_mac.h` — ~250 macOS syscall number constants
- `src/runtime/vsl/vsl_syscall_mac.c` — Dispatch: 30+ BSD handlers + 13 Mach trap handlers

Darling reference cloned at `darling-ref/` for ongoing macOS translation work.

## Running real third-party software through the three exec personalities

WuBuOS can host Linux ELF (`wubu_exec_linux_elf`), Windows PE (`wubu_exec_win_pe` →
Wine/Proton), and macOS Mach-O (`wubu_exec_macho` → VSL loader / darling). To obtain
reputable foreign software, build/cross-compile it for all three, run each through its
`wubu_exec_*` entry point, and PROVE "full hardware usage" with a captured render on
this headless (llvmpipe-only) host — see the **`wubuos-run-third-party`** skill. It has
the mingw PE cross-compile recipe (Khronos `vkcube`), the Xvfb+lvp_icd render-proof
technique, and the honest macOS/Metal blocker write-up.

## Scheduler and timer invariants

`tasking.c` (EEVDF, RT class, sleep wheel) and `timer_wheel.c` have ordering rules
that fail as latency, not crashes: advance → cascade → fire, idle as a fallback
rather than a competitor, RT as a separate branch rather than a weight. Also: what
the hosted build CANNOT test (per-task stacks, TLS bases) and the arm/wake split
that lets `test_tasking` drive sleeps. Read
[`references/scheduler-and-timer-invariants.md`](references/scheduler-and-timer-invariants.md)
before touching the scheduler.

## Run Commands
```bash
make hosted && ./src/hosted/wubu -h            # the product: headless boot + shutdown
./src/hosted/wubu --screenshot /tmp/w.ppm      # render a real frame, no compositor
make worldspace                       # the ~WuBu~ space engine (WWW submodule, own gates)
make shell && ./src/shell/wubu_shell          # the CLI shell
make desktop_shot                       # 26-frame desktop capture (PPM -> PNG)
make test_agi_metal                     # measured-boot AGI chain (QEMU)
make window [SIZE=1280x720]              # the desktop in a nested weston window
                                        # (needs weston + an X display; pixman renderer)
make install [PREFIX=$HOME/.local]       # binary + launcher + window script + icon
make uninstall [PREFIX=...]             # remove them
./install-wubuos.sh                     # interactive installer: asks, plans, installs, verifies

# Tests (see wubuos-test-suite skill for all targets)
make test_edr          # EDR engine tests (12/12 pass)
make test_vsl          # VSL syscall bridge tests — run for live pass count
make test_vsl_nt       # NT syscall tests (uses lite builder) — run for live pass count
make test_holyc        # HolyC compiler tests — run for live pass count
make test_clipboard    # Clipboard tests (14/14)
make test_explorer  # Explorer tests (71/71)
make test_vsl_macho    # Mach-O loader tests — run for live count
make test_vsl_mac      # macOS syscall dispatch tests (20/20)
```

## Link-Regression Sweep (when a widely-linked .c gains a real dependency)

If you make a previously-stubbed/weak module into a **real** dependency of a
file that many Makefile recipes already link (e.g. `wubu_exec_dos.c` started
calling `wubu_dos_proc_*`, which every recipe linking it now needs), you WILL
break other test targets with `undefined reference to <new_symbol>`. One
`make test` pass does NOT catch this — each broken target has its own recipe.

**Sweep procedure** (do this immediately after wiring a new real dependency):
1. `grep -rn "<caller>.c" Makefile` to find every recipe that compiles the
   caller (e.g. `wubu_exec_dos.c`).
2. For EACH such recipe line, check it also links the new dependency's object
   (`wubu_dos_proc.o`). Recipes that compile `.c` directly (not via `RT_OBJS`)
   are the ones that break — they list explicit `.c` files and omit the new one.
3. Add the dependency object (e.g. `$(RT)/wubu_dos_proc.o`) right after the
   caller in each recipe, preserving TAB indentation (use a Python splice via
   `execute_code`, never `patch` on recipe lines — it mangles TABs).
4. Re-run **every** affected target, not just the one you touched:
   `test_syscall test_wubu test_styxfs` (the trio that broke when
   `wubu_exec_dos.c` → `wubu_dos_proc_*` was wired).

This is the "missing object in link line → undefined reference" fix from
`wubuos-test-suite`, generalized to **all recipes**, not just the one you're
working in. The single-target fix hides the other broken targets.

## Headless GUI / Desktop Render Harness (show the desktop without a display)

To produce a screenshot of the Win98 desktop (or any GUI surface) on a headless
host, you cannot hand-link the GUI monolith standalone — `vbe.o` was built
freestanding and fails with PIE relocation errors, and pulling `src/gui/*.o`
drags in modules needing runtime/styx/daemon objects. **Do NOT reinvent the link
line.** Instead:

1. Find a passing GUI test target that already links the WM/desktop stack
   cleanly (e.g. `test_wm` — its recipe at Makefile ~621 links
   `wm.c wm_*.o wm_desktop.c wubu_wallpaper.c wubu_theme.c
   ... $(RT)/wubu_dos_proc.o ... -lm` and builds).
2. Clone that recipe's EXACT `$(CC) ...` link line (via `execute_code`,
   preserving TABs) into a new `test_<x>` target, swapping only your new `.c`
   for the test's `.c` and adding any new module `.c`/`.o` you introduced.
3. In your harness `.c`: `#define VBE_HOSTED` + `#define WUBU_NO_LIBM` (before
   includes), init `vbe_init(w,h)` + `wm_init(w,h)`, do the desktop work
   (e.g. `wm_write_desktop_shortcut(name, exec)` + `wm_refresh_desktop()`
   to surface a `.desktop` as a live icon), then `wm_render(vbe_state()->fb, w, h)`
   + `vbe_swap()`, and save with `wubu_shot_fullscreen("/tmp/x.ppm", SHOT_FMT_PPM)`.
4. Convert PPM→PNG for display with PIL: `Image.frombytes("RGB",(w,h),data).save(png)`.
5. Set `XDG_DESKTOP_DIR=/tmp/Desktop` (and create it) so the shortcut writes to a
   temp dir, not real HOME.

**A shipped harness already exists (2026-07-20):** `src/tools/wubu_shot_apps.c`
(`make test_gui_screenshot_apps`) inits VBE + WM, spawns real Win98-framed
windows via `wm_create(...)` + a content `on_draw` callback, composites
the full desktop, and writes one PPM per app + an overview. Clone/extend it
rather than writing a new one.

### Pitfall — do NOT link `apps.c` / `startmenu.c` in a screenshot harness
Those modules pull the **entire app + daemon graph** (`notepad`, `cmd`/terminal,
`app_explorer`, `app_canvas` + `wubu_cv_*`, `wubu_dos_proc`, `edr_dash`,
`repl`, the `wm_test_stub.c` startmenu dupes, `launch_app`,
`wm_get_hosted_state`, etc.) → dozens of `undefined reference` errors.
The first attempt at `wubu_shot_apps.c` did exactly this and failed to link.
**Fix:** spawn windows directly with `wm_create()` and bind your OWN
`on_draw` callback that renders the window content (text, gradient, button grid)
— the same pattern `wm_test.c` uses. The real app engines are still
exercised by their own targets (`test_apps`, `test_control`,
`test_term`); the screenshot harness only needs to prove the **WM shell
composites correctly**, not re-link every app. Also: if you add `startmenu.c`
you MUST drop `wm_test_stub.c` from the same link line (the stub defines
duplicate `startmenu_*` symbols). Keep the harness link set == `test_wm`'s.

**Avoid `desktop.c`** in a minimal harness — it pulls the whole
`g_app_defs`/daemon/service graph (`daemon_panel_*`, `service_mgr_*`,
`archd_tray_click`, `holyd_tray_click`). Use the WM-level APIs
(`wm_write_desktop_shortcut` declared in `wm_internal.h`,
`wm_refresh_desktop`, `wm_render`) which are already linked by
`test_wm`. The `test_wm` recipe already omits `desktop.o`
for exactly this reason.

## 16-bit DOS Compat — IN-PROCESS SHIM (the correct design; boot-image is pollution)

**Standing user directive (2026-07-17):** WuBuOS BOOTS WuBuOS. A 16-bit DOS app
runs INSIDE WuBuOS as an ordinary process via an in-process 8086 interpreter
(the "compatible window") — it is NEVER booted as a separate guest OS. The
prior "FreeDOOM-in-FreeDOS" design (a real FreeDOS **QEMU guest** + rescue
chainload in `boot.S` + freedoom boot images) was **pollution** and was deleted.
Any future "DOS compat" work MUST follow the in-process shim, not re-add a
booted guest.

Shipped design (the real one):
- `src/runtime/wubu_dos_emu.{h,c}` — from-scratch 8086 interpreter (ALU with
  correct CF/OF/ZF/SF/PF/AF, segment:offset, `rep` string ops) + a DOS INT layer
  (`INT 21h` 09/2A/2C/4C, `INT 10h`, `INT 16h`), rendering the text screen to a
  640×400 RGBA frame via an embedded 5×7 font. **No QEMU, no disk image, no
  second OS booted.**
- `src/runtime/wubu_dos_proc.c` — the "compatible window" engine: owns the emu
  instance, the captured RGBA frame, and the Styx `/proc/<pid>/dos` surface
  (`status`/`screen`/`ctl`). `wubu_dos_proc_launch` reads the program bytes and
  loads them into the shim (`wubu_dos_emu_load_com`/`_exe`).
- `src/runtime/wubu_exec_dos.c` — exec backend: classifies `.COM`/`.EXE` and
  routes to `wubu_dos_proc`; loads the bytes into the shim (does NOT spawn a guest).
- `src/gui/dos_window.c` — the desktop window that blits the captured frame.

**What is NOT pollution (keep):**
- `src/runtime/iso9660.c` boot-image API — WuBuOS itself is bootable; that's
  legitimate, not "booting DOS."
- `src/apps/wubu_freedoom.c` — Arch-container prboom-plus running the real
  Doom engine (a Linux binary in a container), an unrelated feature.
- `src/runtime/wubu_ct_bwrap.c` `wubu_ct_bwrap_freedoom` — a bwrap container
  preset that sandboxes the Doom binary (Wayland + audio); unrelated to the
  deleted FreeDOS guest layer.

**Proving it works (headless, no display):** build a real 8086 `.COM`, route it
through `wubu_exec_dos` → `wubu_dos_proc` → `wubu_dos_emu`, capture the RGBA frame
(`wubu_dos_proc_frame_capture`), and export PNG via PIL. Verified recipe +
debugging notes in `references/8086-dos-shim-debug.md` (real bugs caught there:
byte-register encoding `0xB4`→AH vs `regp` SP mapping; `add ax,imm` reading the
wrong source; `INC r16` fall-through; `do_scas`/`do_cmps` function-pointer cast;
`F_DF` missing from flags). **Read that reference before touching the shim.** Also see
`references/8086-dos-shim-step-hang.md` for the `step()` prefix-loop
infinite-loop hang (the classic "smoke test hangs at timeout 124, not a
crash" bug) and the two dead public-API stubs that ship alongside it.

## Single Canonical Repo (2026-07-23 — fracture resolved)

**There is exactly ONE WuBuOS checkout: `/home/wubu/wubuos`.** It tracks
`origin/master` (https://github.com/waefrebeorn/WuBuOS). The former
`.hermes/profiles/mind-palace/home/myseed` checkout was a **fractured
duplicate** (two working trees of the same repo at different commits, with
divergent uncommitted work) and has been DELETED. Never recreate a checkout
under the Hermes profile path — it caused the fracture.

Integrity checks to run after any move/merge (all must pass):
- `cd /home/wubu/wubuos && git rev-parse --show-toplevel` → `/home/wubu/wubuos`
- `git fsck --quiet` → no errors
- `make runtime && make shell` → both print `✅ ... built`
- `make test` → `ALL PASSED` (all tiers)

## P3 /n/background — the session + message-bus runtime (2026-11-06)

Shipped, green: **10 primitives / 174 checks / ~30 runtime source files**
(`src/runtime/wubu_*`), modeling the Mint-baseline background runtime
(`os-studies/linuxmint_background_baseline.md`) as tested C11 modules exposed
through the `/n` namespace. Full module map + test-pattern notes in
[`references/p3-background-runtime.md`](references/p3-background-runtime.md).
The five service contracts: D-Bus activation (`wubu_bus`), socket activation
(`wubu_svc_socket`), XDG autostart (`wubu_xdg_autostart`), session/seat
(`wubu_logind`), polkit auth (`wubu_auth`); composed by the session boot
(`wubu_session_boot`), the role-up daemon (`wubu_session_daemon`, auth wired as
the login power gate), the `/n/background` publishers (`wubu_ns_background`,
`wubu_deskenv`), and the one-call session-manager glue (`wubu_session_mgr_boot`). Remaining:
desktop-wiring (feed it into `dosgui`/`hosted` boot — touches the GUI monolith,
belongs with the `cinnamon_study` chrome work).

**P3/NT module naming discipline:** the P3 module names were de-ambiguated on
creation: `wubu_login`→`wubu_logind` (it's the logind service, not a login
screen), `wubu_ns_de`→`wubu_deskenv` (a bare "de" prefix misread as delete/dé
and clashed with `wubu_deploy`; the `/n/background/de` PATH is unchanged),
`wubu_background`→`wubu_session_mgr` (the boot glue was confusable with the
`wubu_ns_background` publisher; it is the session-manager runtime), and
`wubu_auth_rule`→`wubu_auth_add_rule` (symmetric with `wubu_auth_rule_at`). Use
the NEW names; the old ones are gone.

**RENAMING a symbol across many files — do it idempotently, scoped, then verify.**
A rename is a git-tracked regular file: use `git mv` / `mv` then edit ONLY the
renamed file list — never a tree-wide bare `sed -i 's/old/new/g'` over `wubu_*.c`.
Two concrete failure modes this pass hit:
1. **Unbound prefix over-match.** `wubu_de` is a prefix of `wubu_desktop`/
   `wubu_deploy`/`wubu_detect`, so a flat `s/wubu_de/wubu_deskenv/g` silently
   corrupted pre-existing tracked files into `wubu_deskenvtect_format`. A
   replacement token must be bound on BOTH sides (trailing `[^A-Za-z0-9_]`, or
   list the full `_xyz` variants longest-first) — a leading-bound lookbehind
   alone is NOT enough when the old token is a prefix of other identifiers.
2. **Non-idempotent sequential sed.** Applying two overlapping rules one after
   another in the same file (`s/wubu_login.c/.../` then `s/wubu_login/.../`)
   re-matched the already-replaced text → `wubu_logindd.c`. Use one pass with
   longest-first full-token patterns (a scripted `re.sub` per token), never
   column-after-column `sed -i` where a later pattern can hit an earlier
   replacement.
VERIFY a rename: grep the whole tree for any remaining old token (excluding
the new files), confirm no TRACKED file acquired the new root token, and run
`make all` (it compiles the "unrelated" files a scope error would have
corrupted). After that pass the 6 files that returned to exactly-HEAD were
clean and the 3 that still differed carried only their legitimate prior-session
edits — that split is the signal the revert was exact, not "close enough".

Two recurring bug classes this work exposed (generalizable — see the reference):
1. **Enum-0-as-denial.** A bridged "deny" returning enum value 0 becomes an
   ALLOW when the other side's convention is `0=success, nonzero=deny`. Map the
   denial to a nonzero code any time you bridge two modules whose success/deny
   conventions differ.
2. **File-vs-directory namespace collision.** One publisher writing a flat
   file `x` while another `ns_mkdir`s `x/` silently fails the whole publish
   (mkdir-on-existing-file). An authoritative directory belongs to ONE
   publisher; the other's flat file must have a distinct name.

Test-pattern rule for any `/n` subtree: link `wubu_ns_fs.o` + the source
modules and re-point `g_ns_root` directly (do NOT link `wubu_ns_bridge.o` —
the memory-constrained rule); adding a dependency to a shared publisher module
breaks every recipe listing it (link-regression sweep).

The NT 6.1 / Windows-11 syscall extension work (ReactOS ordinal
transliteration) lives on the **`nt-parity-wip` branch** on origin as a
separate research line. It was NOT merged to master because the engine had
60 colliding dispatch-slot assignments and unverifiable ordinals for the
ALPC/WNF/Enclave/IoRing/Partition/WorkerFactory/KTM blocks (it segfaulted
on first run). Fix it properly there before merging — do not re-introduce
the broken half into the canonical tree.

The relocation procedure + pitfalls (git survives `mv`, the `wubucontainer`
submodule's relative path travels with it, merging an orphan same-named
tree, recovering a mistakenly-deleted tracked file) are in
`references/repo-relocation-housekeeping.md`.

### Devil's-Advocate Re-Verification After Unify/Relocation/Merge (2026-07-23)

The user requires a **triple Devil's-Advocate audit** on delivered work — never
report a consolidation/refactor "done" on the strength of your own first pass.
Two real misses were caught this way and would have shipped as "resolved":

1. **Leftover duplicate checkout.** After deleting `home/myseed`, a sibling
   `home/myseed-borked` survived because the delete targeted only the one named
   path. **Filesystem-wide sweep before declaring done:**
   `find /home/wubu -maxdepth 6 -type d -name 'myseed*' 2>/dev/null` (and any
   other known duplicate-name pattern) must return ZERO hits.
2. **"Green gate" from a stale log is not proof.** After any structural change,
   rebuild + retest FRESH: `make runtime && make hosted && make test`, and read
   the live exit codes. Do not cite an earlier session's log.
3. **Re-scan the invariant you claimed.** If you asserted "0 slot collisions" or
   "no X", re-run the scan with a fresh process. The canonical `origin/master`
   NT dispatch itself had 4 colliding slots (e.g. `vsl_nt_reset_event` registered
   at 209, colliding with `NtRequestWaitReplyPort`@209) that a passing test
   masked. Scan technique + ReactOS ordinal canonicalization:
   `references/nt-dispatch-collision-scan.md`.

## Single Canonical Repo (2026-07-23 — fracture resolved)

When the serial trace stalls (e.g. boot dies at `MPGCE`), do **NOT** trust the
gdbstub or the HMP socket monitor — both are unreliable in this environment
(gdbstub `int3` triple-faults with no guest IDT, `stepi` round-trips time out,
and the HMP socket echo-corrupts keystrokes → "invalid char" errors). Use the
**QMP JSON unix socket** to inspect live guest state instead. Ready-to-run
client + failure-mode catalog + the `entry_addr` multiboot quirk:
`references/baremetal-boot-qmp-debug.md`.

## Porting a GUI design from an external theme project

When asked to "take from" a theme/DE project (KDE themes, XP recreations,
compositor effects), the deliverable is a tested C11 primitive plus evidence,
never a copy:

1. **Check for the feature before porting it.** Read the local painter first
   (`window_chrome.c` already draws a Luna vertical caption gradient via
   `gradient_title` + `vbe_vgradient`). Porting what exists is churn; claiming it
   was missing is worse. State the correction explicitly when you find it.
2. **Take the design, not the code.** GPL/C++/QML sources do not travel into a
   C11 kernel GUI; extract the behaviour (gradient direction, animation envelope,
   timing curve) and re-express it with integer maths and no libm in the draw
   path.
3. **Prove it visually when it cannot be wired yet.** Render the effect to a PPM
   from a small demo binary, convert with PIL, and inspect it before saying it
   looks right.
4. **Do not call an effect "live" without a clock.** The GUI layer has no
   monotonic tick exposed to `src/gui/`, so a time-based effect (`t`) has nowhere
   to come from. Ship the tested library, write down the two prerequisites
   (a ms counter reachable from the GUI + a `focus_tick` set in
   `wm_set_focus`), and say plainly it is not wired.

## QEMU display bring-up and verification

Before touching `fw_gop.c`, `vbe.c`, `ramfb.c`, or any "screen is black"
investigation, read [`references/qemu-display-bringup.md`](references/qemu-display-bringup.md).
The rules that matter most:

1. **QEMU Standard VGA dispi MMIO is a flat register file**, not index/data:
   register N is at `BAR2 + 0x500 + (N << 1)`. Writing index to `0x500` and data
   to `0x502` reads back 0 and makes the window look absent. Legacy ports are
   `0x1CE`/`0x1CF` and do not exist on the legacy-free variant.
2. **Do not explain an inert card with "the option ROM never ran."**
   `OvmfPkg/QemuVideoDxe` drives `1234:1111` through the MMIO dispi path and
   never runs a ROM; compare against its sequence first.
3. **`screendump` under `-display none` is a 640x480 dummy surface** and cannot
   verify graphics. Use `tools/qemu_vnc_shot.py` against `-display vnc`.
4. **`-serial file:` delivers no stdin.** A firmware waiting at a shell will
   never boot; feed `printf 'exit\n'` through `-serial stdio`, or you are
   measuring the firmware console and calling it a display bug.
5. **Capture needs two calls:** QEMU in the background (`terminal` with
   `background=true`), then the grab after ~25 s. A foreground run consumes the
   whole boot window before the capture happens.
6. **Confirm the kernel actually linked.** A missing object in `KERNEL_OBJS`
   (e.g. `timer_wheel.o`) makes `make kernel` fail and the boot then runs the
   PREVIOUS `kernel.elf` — you debug a binary you did not build.
7. **Anything above the 1 GB identity map must be VMM-mapped before writing**
   (`0xC0000000`, `0xFD000000`): the fault is silent, not a crash.
8. **Keep framebuffer-sized buffers out of `.bss`** — the image runs from
   `0x100000` and the heap starts at `0x400000`; a multi-MB static array pushes
   the image into the heap and breaks boot. Use a fixed reserved physical
   address instead.
9. **GUI is not in the kernel.** `KERNEL_OBJS` has zero `gui/` objects; linking
   `wm_render.o` alone pulls ~11 more. Generate the closure from the
   linker's undefined-symbol list rather than hand-listing objects, and remember
   an initialising WM (`WM init rc=0`) is not proof it drew anything — checksum
   the surface before/after a render call and sample real pixel values.

## Kernel Monolith Split Status (2026-07-16)

`src/kernel/interrupt.c` was split: PIC layer (`pic_remap`/`pic_eoi`) + IRQ
routing (`IRQRoute` linked list) extracted to `interrupt_pic.{c,h}`. Pattern:
extract a ring-0 hardware concern into a self-contained sibling module, keep the
hardware poke (`ioapic_route_irq`, `outb`/`inb`) under `#ifdef MYSEED_METAL` so
the pure bookkeeping (list add/remove) is unit-testable on the host. See
`wubuos-monolithic-split` for the general procedure.

## Adding a New GUI Module — Makefile Triple-Place Pattern (2026-07-07)

When adding a new `.c`/`.h` pair under `src/gui/`, it must appear in **three**
places in the Makefile, and test targets that link the dependent GUI files must
also get the new object. Failing any one spot produces `undefined reference`
at link time.

### The Three Places

1. **`GUI_OBJS`** (line ~41) — the `.o` list for non-hosted GUI compilation.
   Add `$(GUI)/new_module.o` in alphabetical-ish position.

2. **Hosted recipe `hosted:`** (line ~173) — the source `.c` list compiled
   directly into the hosted binary. Add `$(GUI)/new_module.c \` on the
   continuation line.

3. **`HOSTED_OBJS`** (line ~157) — the `.o` dependency list for `make`
   change detection. Add `$(GUI)/new_module.o` in the appropriate section.

### Test Target Linkage

If the new module is called from a file that a test target already links
(e.g. `wm.c` → `test_wm`, `test_control`), the test target's
recipe must also add the new source. Patterns:

- **Test compiles .c files directly** (most test targets): add
  `$(GUI)/new_module.c \` to the test's `$(CC)` line.
- **Test uses pre-compiled .o files** (rare): add the `.o`.

### Verification

Always run the full gate after adding a GUI module:
```bash
make clean && make runtime && make hosted && make test
```
A `make gui` compile pass is NOT sufficient — `make hosted` compiles its own
.c list and may miss the new file, producing `undefined reference` errors
that `make gui` doesn't catch.

Reference: `references/makefile-triple-place-pattern.md`

## UX First-Run Patterns (2026-07-07 Stream E)

When adding user-facing first-run / onboarding UX, there are three proven
patterns in the WuBuOS codebase:

### 1. Bundled Default Wallpaper Chain

`load_default_wallpaper()` in `wm.c` follows a three-tier chain:
```
configured path (from settings) → bundled BMP → procedural gradient
```
The function `wubu_wallpaper_default_path()` in `wubu_wallpaper.c` locates
the shipped BMP by probing known relative paths (`screenshots/media/wubuos-default.bmp`,
then `../screenshots/...`). Returns NULL if not found → caller falls through.

**New module checklist**: add `#include "wubu_wallpaper.h"` to `wm.c`,
add `$(GUI)/wubu_wallpaper.o` to GUI_OBJS, add `.c` to hosted recipe.

### 2. First-Run Welcome Dialog

`wubu_welcome.c` implements a one-shot modal window with:
- **Marker file**: `~/.config/wubu/first-run-done` — created on first show,
  checked on every subsequent boot. File-based, not JSON-round-trip.
- **Modal window**: created via `wm_create_modal()`, sets `on_draw`
  callback that renders keyboard shortcut table with `vbe_draw_text()` at
  window-relative coordinates (`win->x + offset`).
- **Wiring**: `wubu_welcome_init()` called from `hosted_init()` after
  `startmenu_init()`.

**Key pitfall**: The `on_draw` callback receives the full framebuffer
dimensions (`fb_w`, `fb_h`) but `vbe_draw_text` uses absolute screen
coordinates. Compute absolute offsets as `win->x + border + padding`.

### 3. Status Bar Cycling Tips

Status tips cycle every 10 seconds in the taskbar area, drawn as small text
between window buttons and the virtual desktop indicators. Implemented as a
static block at the end of `taskbar_render()` in `wm.c`:

```c
static time_t last_tip_swap = 0;
static int tip_index = 0;
const char *tips[] = {"Ctrl+T = cycle theme", "Alt+F4 = close window", ...};
// Cycle index every 10s, draw at computed x position
```

The tip position must be calculated to avoid overlapping the Start button
area: `if (tip_x > start_w + 90)` guard.

Reference: `references/welcome-dialog-wiring.md`

## Gap-Closure Regression-Test Pattern (2026-07-08)

When closing a form≠function gap, ALWAYS add a test that asserts the FIXED
behavior, not just the absence of a crash. Examples from this session:
- `styxfs_opendir(".")` must return a non-NULL `DIR*` AND `readdir` must yield
  >= 2 entries; `styxfs_readdir(".")` must return > 0 with a non-NULL array.
- `bear_optimizer_step` must MOVE weights (assert sum_abs_diff > 1e-4 and a
  sane upper bound); `bear_optimizer_zero_grad` must set all grads to 0.
- `lvm_snapshot_create` must NOT return the hardcoded `-ENOSYS` (assert
  `rc != -ENOSYS`) — it now returns the real `lvcreate` exit status.

When the gap needs new state to do real work (e.g. an optimizer must remember
registered params), store those pointers at registration time rather than
duplicating logic — then dispatch to the already-correct per-element helpers.
See `references/gap-hunting-scanners-extended-2026-07-08.md` for the scanner
scripts that surface these gaps.
