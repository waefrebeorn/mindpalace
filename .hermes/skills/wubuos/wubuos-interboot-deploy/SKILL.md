---
name: wubuos-interboot-deploy
description: Build the bootable WuBuOS image and boot it in QEMU.
---
# WuBuOS interboot deploy: machine-ready bootable image

## Boot status: HEALTHY — long mode, console, heartbeats (soak-verified)
Boot reaches the `WuBuOS>` interactive COM1 console + AGI task heartbeats,
27/27 consecutive boots with zero scheduler crashes. The historical boot
bugs below are FIXED and kept as regression references: a trace stuck at
38/106/303 bytes means one of them (or a new fault) regressed.
- **GRUB multiboot (BOOTS TO THE C ENTRY, THEN HANGS).** `src/kernel/crt0.S` carries
  a real multiboot header (`0x1BADB002`) plus a Limine request list. Both
  `qemu -kernel kernel.elf` and the GRUB ISO boot to the same 38-byte serial trace
  `010203040506070811121314\n15task:` and then STOP. `kernel_main`'s very first byte
  is `'16'` (metal_main.c:217, an outb to 0x3F8) and it NEVER appears -- so the C
  kernel does not run; the `call *%rax` to `kernel_main` at the end of crt0.S
  (entry transition) hangs before line 1. This is NOT an idle wait: `15task:` is
  crt0.S's stage-15 label, not "task/session init reached" as previously believed.
  Measured 2026-11-16: both paths, 30s and 60s captures, 38 bytes each (QEMU 128MB,
  no-reboot). Next debugging target: the crt0→kernel_main long-mode entry
  (stack preamble, Limine .response pointers / g_limine_ok, or the final call ABI).

### FIXED (commit 7eeb9f3, verified 2026-11-16)
Kernel builds now pass **-fno-jump-tables** (mk/pattern-rules.mk KERNEL_CFLAGS) so
GCC never emits a byte-indexed switch jump table for the freestanding kernel.
Before: `jmp *CSWTCH.21(,%rax,8)` had 0xFFFFFFFF/non-canonical holes -> char 's'
jumped to RIP=0xFFFFFFFF -> #PF -> double-fault at the very first %-format in klog.
After: 38->106 serial bytes, kernel_main prints real klog. Hosted stays green.

### FIXED (commit 61e4da6): multiboot header base + SSE enable (106 -> 3934 bytes)
1. **mb1 header address fields were wrong.** The limine request structs precede
   mb1_hdr inside .text, so mb1_hdr is at .text offset 0x10c, not 0. With
   header_addr=0x100000, QEMU's address-fields loader anchors the header at phys
   0x100000 -> loads .text 0x10c EARLY (phys 0xffef4). crt0 image_base=0x100000
   maps VA-256 to phys 0x100000 = .text+0x10c, so every higher-half VA reads
   content 0x10c late; the first RIP-relative global ref misses the unmapped page
   below the image (CR2 0xffffffff800fff1c, RIP 0x801007b1) -> #PF. Fixed by
   setting the header's TRUE phys (header_addr=0x10010c, entry_addr=0x10012c).
   Proof: in_asm shows the kernel's first instruction at phys 0x00100020; _start
   is at file offset 0x112c, so .text base was 0xffef4 (0x10c early). 106->2625.
2. **SSE not enabled.** CR0.EM/TS left set + CR4.OSFXSR/OSXMMEXCPT never set, so
   the -O2 compiler's SSE (`pxor %xmm0` in wubu_apic_enable) raised #UD at
   RIP 0x8010fd97. crt0 now clears CR0.EM+TS (bits 2,3) at entry and sets
   OSFXSR+OSXMMEXCPT (bits 9,10) in both CR4 writes. 2625->3934, tasks spawn.

## (Historical, resolved) the every-boot scheduler #GP -- root-caused, then made non-fatal
Boot reaches `WuBuOS>` interactive COM1 console + AGI Bonzi Buddy /
live-console tasks (BSS/heap/interrupts/APIC/VBE 1920x1080/PS2/tasking/FAT/ACPI).
Measured 3700-4600 serial bytes. (The "rare flaky crash" framing was a
misread: it was a **PROVEN every-boot #GP**, and is now RESOLVED -- see the
STABLE-ceiling section below.) **PROVEN crash (every boot, 6/6 soak): a `#GP
(err=0, rflags=13)` at `task_schedule_next+0x38` (RIP 0xffffffff801022d8, mov
0x4(%rax),%ecx) -- `t = g_current->next` is a NON-CANONICAL garbage pointer, so
dereferencing `t->state` #GPs.** `g_current` itself is valid (the +0x2e8 load of
its `next` succeeded); the corrupted field is the CURRENT task's `CTask->next`
(offset 0x2e8=744). The FAULTING TASK varies (agi-agent in 4/6, bonzi in 2/6)
and the crash TIME varies wildly (0 to 22 healthy heartbeats) -> a timing-
dependent HEAP overwrite that periodically lands garbage in whatever task's
`next` happens to be current. Consistently masks as a heartbeat cut mid-
`attest=` because the last klog_printf is interrupted. This is NOT the vsprintf
`#PF` the enriched dump was built to catch (36190ec) -- it is a #GP in the
scheduler (`#PF=0 #GP=1 #DF=0`).

Prime corruption suspect (unproven): klog.c lock-free TX ring with multiple
producers, and wubu_agi_kernel.c REMOVED the AGI ring spinlock (:76-78, timing
stall). The panic writer masked the true fault -- commit 23b686d made
wubu_crash_dump NEVER lazily init the crash disk from panic context (was
ahci_sim_disk_create -> calloc(8MB) on a corrupt heap -> secondary DF fake
double-fault), so crashes now surface the real #GP. Next: hunt the write that
Next: hunt the write that clobbers a CTask->next (CTask + stack are mem_alloc'd;
g_agi is static bss).

**Decisive (commit 65b4259 full-width GP + task-struct byte dump, 6/6 soak):**
the corrupted region is a SOLID PAINT ROW. The 16 uint32 words from
CTask+0x2d0 through +0x2f0 (spannap the `next` field at +0x2e8) are ALL
`0x53f000ff` (bytes `ff 00 f0 53`) -- a contiguous 4-byte-fill, NOT a lone
field overwrite. This is a RUNTIME-computed value (absent tree-wide as a
literal). The buddy SPRITE draw (historical; the buddy is the live shader orb now, see
wubu-buddy-orb) uses only CLIPPED vbe_set_pixel and brown-sea palette colors (gorilla_fur 0x00806040, etc.), so the vbe/framebuffer surface
is NOT the writer (fb/back are heap-adjacent at ~4MB/12MB, far from the task
structs at ~38MB; vbe_clear is bounded by width*height == the 8MB alloc).
The exact routine that paints `0x53f000ff` over the CTask region is STILL
UNKNOWN. The GP dump now prints full-width regs + the task bytes so a next
catch shows the pattern and register state to tie the writer.
- **Bare-metal display WORKS (commit 91c765f, verified by QEMU screendump).**
  Previously the bare-metal GUI rendered into RAM buffers never attached to the
  panel -> pure black screen ("bonzi looks broken"). Now: drive Bochs VBE
  (DISPI, ports 0x1CE/0x1CF) from long mode to latch a linear-framebuffer mode
  (no int 0x10 needed), read the REAL LFB base from VGA PCI BAR0 (dev 00:02.0
  reg 0x10 -- under QEMU std vga +tool: it is 0xFD000000, NOT 0xE0000000),
  map the 8MB LFB via wubu_vmm_map_page (lfb_va 0xffffffff90000000), and
  vbe_set_render_target so fb==back==LFB. Screendump shows the WuBu Buddy
  mascot + desktop at 1920x1080@32. Fail-soft: absent DISPI/BAR0 keeps RAM-buffer
  behaviour. NOTE: vbe_bochs_id correctly masks the version nibble (QEMU
  reports 0xB0C5 = Bochs VBE v1.5+); PCI config is I/O ports 0xCF8/0xCFC
  (outl/inl, never a memory store); DISPI needs a disable-then-enable cycle.
## Clock source: the LAPIC timer must have a handler (fixed 4001a34)
RULE: a timer configured on an interrupt vector is worthless until a HANDLER IS
REGISTERED ON THAT SAME VECTOR. After any change that calls `*_timer_init(hz,
vector)` / `interrupt_register` pair, grep the tree for the vector number and
confirm exactly one handler is bound -- a configured-but-unhandled vector
fails SILENTLY (no log, no crash): the clock simply stops after whatever legacy
IRQ slips through. A second rule from the same hunt: firmware may leave the
8259 masked (IMR 0xff), so never make liveness depend on PIC-delivered IRQs.
Booted through WuBuFW the kernel lost its tick ~3 interrupts in: uptime_ms froze
at 10 ms, task_sleep spun instead of sleeping, Bonzi never printed a heartbeat,
and `make test_agi_metal` failed on 'MISSING: bonzi heartbeat' while attestation
VALID + AGI promotions kept flowing. Cause: `interrupt_init_full()` called
`lapic_timer_init(100, 240)` but NOTHING registered vector 240, and WuBuFW leaves
the 8259 IMR at 0xff, so IRQ0 only slipped through a couple of times. Fix: shared
`wubu_clock_tick()` called by `pit_handler` and `apic_timer_handler`;
`wubu_clock_use_apic()` registers vector 240 (metal-only -- hosted tests link
interrupt.c without interrupt_apic.c and will fail on lapic_* refs otherwise).

Diagnostic technique that found it: log ISR dispatch per vector (only 3x vec 32),
read PIC IMR from port 0x21 (`ff`), then trap `outb` to 0x21 to see every writer.
A fast-sampling diagnostic misled once (bonzi tick #1..#100 all read uptime=10
because task_sleep was not sleeping) -- sample over seconds, not iterations.

Boot reaches `WuBuOS>` interactive console **27/27 consecutive boots (soak-verified)
with ZERO scheduler #GP crashes** -- the every-boot crash is RESOLVED by the
scheduler guard (commit 5680b16): task_schedule_next validates every task
pointer (task_ring_ptr_ok: canonical + non-NULL) BEFORE dereferencing t->state
in both the priority walk and idle search, logging corruption and keeping the
current task instead of #GP-ing.

**The bare-metal display WORKS (commit 91c765f).** Drive Bochs VBE (DISPI, ports
0x1CE/0x1CF) from long mode to latch a linear-framebuffer mode (no int 0x10), read
the REAL LFB base from VGA PCI BAR0 (dev 00:02.0 reg 0x10 -- QEMU std vga =
0xFD000000, NOT 0xE0000000), map the 8MB LFB via wubu_vmm_map_page (lfb_va
0xffffffff90000000), and vbe_set_render_target (fb==back==LFB). QEMU screendump
shows the WuBu Buddy mascot + desktop at 1920x1080@32. Bonzi start-up no longer
double-renders its greeting (commit b011e39).

Unresolved: the solid-0x53f000ff heap-fill writer is STILL unknown -- the guard
made the system tolerate it (or its code-layout shift moved timing), so it is
no longer fatal, but the root overwrite is not root-caused.

- **Legacy floppy (BROKEN).** `src/kernel/boot.S` is a 16-bit BIOS bootsector that
  loads the ELF, enters 32-bit pmode, and jumps to `_start` expecting crt0.S to
  finish long mode -- but crt0.S is a Limine/multiboot stub, not a self-contained
  long-mode transition. That path triple-faults on `#UD` (qemu `-d int` shows
  `check_exception new 0x6` in a loop, no serial output). Do NOT build the floppy
  path into a deployment; keep it only as the legacy `boot:`/disk.img target.

## The deployable artifact
```
make iso   # GRUB multiboot image -> src/kernel/wubuos.iso (14 MB, *.iso) gitignored
make qemu  # boots it under QEMU, serial boot trace on stdout (uses -cdrom, NOT -fda)
```
The ISO is the interboot/deployment image: bare metal, QEMU/KVM, and any VM/OS that
runs GRUB all load it (Linux, Windows, macOS). `mk/targets.mk` owns these.

## Verify a boot
GRUB path: `timeout 35 qemu-system-x86_64 -kernel src/kernel/kernel.elf -serial
file:/tmp/trace.bin -display none -m 128 -no-reboot; wc -c /tmp/trace.bin`.
Better: `python3 tools/ci_boot_assert.py src/kernel/kernel.elf --kernel` —
the shared gate (works on any host, configurable window via WUBU_BOOT_WINDOW).
Healthy boot = the trace reaches the interactive `WuBuOS>` console + task
heartbeats. Byte volume DRIFTS with the tree: ~3700-4600 pre-PMM-refactor,
~2000-2900 after the WuBuKernel PMM consumption. The gate therefore asserts
>= 1500 bytes AND the `WuBuOS>` marker — the marker is the truth, the count
is a regression tripwire. Anything stuck around 38 (`...15task:`) or 106
(`...interrupts initialized`) means one of the FIXED boot bugs regressed.
Recalibrate the count threshold when a refactor legitimately changes log
volume; never delete the marker assertion to make a gate pass.

### Fault vs slow: diagnose before widening the window
Identical byte counts across DIFFERENT window sizes + a sub-second QEMU
exit mean the guest FAULTED, not that the window is too short — widening
it again wastes a CI cycle. With `-no-reboot`, an early exit rc=0 is a
triple fault (QEMU exits cleanly on guest reset). Instrument the assert
script to capture the early-exit returncode + QEMU stderr tail, upload
serial traces with `if: always()` (a failed step otherwise skips the
upload and the evidence is lost), and echo `qemu-system-x86_64 --version`
in the step. Runner images drift: a kernel that boots on the dev box's
QEMU can triple-fault on a newer runner QEMU at the same trace point.
Bisect with `WUBU_QEMU_EXTRA` variants (`-machine pc-i440fx-<older>`,
`-cpu qemu64`) and `-d int,guest_errors -D ci_qemu_int.log` — the fault
vector + CR2/RIP map to a symbol via `nm kernel.elf`. The exception log
stays small precisely because the guest dies early.

### Freestanding ISA drift: the CI-only triple fault (root-caused class)
Freestanding code (kernel, firmware, boot stubs) must PIN its ISA baseline:
`-march=x86-64 -mtune=generic` in every freestanding CFLAGS set. Distro
compilers drift their DEFAULT march (Ubuntu 26.04 gcc14 defaults to
x86-64-v3), so an unpinned build emits AVX2 (e.g. gcc vectorizes memset
with vmovd/vpbroadcastb) that qemu64 TCG and older real CPUs cannot decode
-> #UD -> #DF -> triple fault before the IDT exists. Signature: boots on
the dev box, identical short trace + sub-second exit on the runner, and
machine-type/CPU bisection changes NOTHING (the compiler, not the machine,
is the variable). `-mno-sse` also blocks vector codegen (firmware relies on
it) — keep the explicit pin anyway as drift insurance.
Diagnosis chain that closes it:
1. `-d int,guest_errors -D ci_qemu_int.log`: first `check_exception new 0x6`
   is #UD; the escalation chain (0x6 -> 0xd e=IDT-selector -> 0x8) confirms
   pre-IDT death. Upload the log AND `kernel.elf` with `if: always()`.
2. Symbolize with the CI-BUILT elf, not the local one (different compiler =
   different layout): `addr2line -e kernel.elf <fault RIP>` then
   `objdump -d --start-address=... --stop-address=...` — VEX-prefixed
   opcodes (c4/c5 bytes, vmovd/vpbroadcastb/ymm) at the fault site are the
   proof.
3. Reproduce the runner compiler locally WITHOUT root:
   `apt-get download gcc-14 cpp-14 libgcc-14-dev gcc-14-x86-64-linux-gnu
   cpp-14-x86-64-linux-gnu; for d in *.deb; do dpkg -x "$d" root; done`
   then run `root/usr/bin/gcc-14` with `GCC_EXEC_PREFIX=$PWD/root/usr/lib/gcc/`
   `COMPILER_PATH=$PWD/root/usr/lib/gcc/x86_64-linux-gnu/14:$PWD/root/usr/bin`
   `LIBRARY_PATH=...14:/usr/lib/x86_64-linux-gnu`. Full `make -B kernel
   CC=<that gcc>` + boot gate reproduces (or clears) the compiler variable.
4. Fix = pin the baseline in KERNEL_CFLAGS, the kernel-strict recipe, and
   src/firmware/build.sh; verify zero VEX opcodes in the rebuilt elf and
   green boots on BOTH compilers.

## CI boot matrix (the multi-host proof)

`.github/workflows/boot-verify.yml` in wubuos: build kernel+ISO ONCE on
ubuntu, then boot the SAME artifact under QEMU on ubuntu AND windows AND
macos runners, asserting the healthy trace on each. Free and unlimited
(public repo); this is the "one artifact interboots everywhere" claim made
checkable on every kernel push. Recipe facts:
- `grub-mkrescue` needs **mtools** (mformat) besides grub-pc-bin/xorriso.
- Windows runner: QEMU via `choco install qemu`, add `/c/Program Files/qemu`
  to PATH in bash steps; macOS: `brew install qemu`. TCG everywhere (no KVM).
- **CI TCG is ~8x slower than a dev box**: a 45s boot window catches ~300
  bytes there. WUBU_BOOT_WINDOW=300 in CI; keep 45 local.
- Runner gcc is NEWER than the dev box (gcc14 vs gcc13): implicit
  declarations and int/pointer conditionals are ERRORS there. The kernel
  is strict-clean and the workflow runs `make kernel-strict` as a permanent
  ratchet — keep it clean (see wubu-tree-standardization, gcc14 campaign).
- `make kernel`/`make iso` need NO submodules; `test_kernel_bridge` compiles
  WuBuKernel sources, so the workflow inits that submodule — which only
  works because the repo is PUBLIC. A private submodule breaks anonymous
  CI clones and fresh source clones alike.

### Pitfall: hosted-green is not kernel-green

Metal-only TUs (SMP, APIC boot paths) never compile in the hosted build.
A header change can break `make kernel` while `make hosted` and every
hosted test stay green (e.g. local accessor names colliding with inline
accessors in a newly-included header). After touching kernel headers or
kernel-only sources, run `make kernel` AND the boot gate — not just hosted.

### Debug tooling lessons
- **objdump -dS is UNTRUSTWORTHY** for this `-mcmodel=kernel` binary (16-bit
  `66`-prefixed outb emit-rows desync its decode -> misleading attributions).
  Believe **QEMU `-d in_asm -D file`** (instruction trace with phys addresses) and
  gdb x/i. readelf -S/-l/-s and `nm` ARE trustworthy.
- **Never `pkill -f <pattern>` in a shell command that also mentions the pattern**:
  it matches your own `bash -c` command line and SIGTERMs the shell mid-command.
  Kill by executable name (`pkill -x qemu-system-x86_64`) or by explicit PID from
  `pgrep -x`, never `-f`.
- **Hardware breakpoints (gdb hbreak) kill this kernel**: #DB (vec 1) is unhandled, so
  the breakpoint itself triple-faults the guest (gdb prints the line then
  "Inferior exited normally"). Don't stop mid-kernel with hbreak; use passive
  in_asm traces. A `-S`-paused QEMU returns all-zeros on HMP `xp` (loader not yet run).

## L1 persistent storage (virtio-blk) + two boot-volume bug classes (fixed 9d563b6)
- Real disk: `src/kernel/wubu_virtio_blk.c` (legacy virtio-pci, one split
  virtqueue, polled). Gate: `make virtio-persist-gate` (write -> fresh-QEMU
  reboot -> byte-verified read-back, PERSIST-OK). Unit: `make test_virtio_blk`.
- Legacy virtio-blk PCI ID is **0x1001** (0x1000 + type - 1, block type 2),
  NOT 0x1000 (that is legacy NET on spec-correct QEMU; VirtualBox uses 0x1000
  for blk). Match class 0x01 too. QEMU: `-device virtio-blk-pci,disable-modern=on`.
- Legacy config window is 0x14 unless the driver ENABLES MSI-X (cap present
  is not enough). Queue PFN register is 32 bits: queue phys must be < 2^44
  (hosted malloc addrs are NOT -- tests need a low arena + -no-pie).
- Heap is identity-mapped only below 1 GB (crt0 PD_ident); FAT32 passes STACK
  buffers to blk ops -> a real driver must bounce through heap memory.
- **GAS `.fill` in .bss clamps size to 8** ("Warning: .fill size clamped to 8"):
  `.fill 256,16,0` reserved 2048 not 4096 -> IDT gates 128+ overwrote
  g_current_task / FAT32 boot volume / g_agi. Use `.skip N` for BSS reserves.
  This was the long-hunted g_current_task corruption class.
- **glibc ctype.h toupper(c) = (*__ctype_toupper_loc())[c] with INT32[384]
  entries** (index 0 == -128). The kernel stub returned a 1-element u16 table
  -> OOB garbage -> mangled FAT32 8.3 names, find never matched. libc.c now
  builds the real int32 table. Any kernel symbol backing a glibc macro must
  match glibc's REAL type/size, not a plausible-looking one.
- Symptom signature of both: fat32_boot_attach returned 0 WITHOUT mounting
  (garbage vol->mounted early-return); "mounted" banner lied. When a storage
  leg misbehaves, dump the boot volume's blk ops + check the image from the
  host (python FAT parse) before blaming the new driver.

## Beyond this stage (unresolved / next)
- The `task:` trace stops after task init; if a later boot step needs serial/VGA
  output, add a kernel serial marker after session launch to prove more.
- "Full circle" = HolyD (RFC) compiling the OS into a bootable image; currently the
  image packs gcc's `kernel.elf`. See wubunos-selfhost-loader for the loader-stage
  self-host progress and swap the packed ELF for a HolyD-emitted one when ready.
- Cross-host legs: macOS Metal shader leg = metal2vulkan (see wubuos-macos-leg-proof);
  Windows GPU = gfxstream/dxg (see wubuos-gpu-shim). The bootable ISO is the one
  artifact that interboots across all of them.
