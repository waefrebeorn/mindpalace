---
name: wubuos-uefi-firmware
description: Build WuBuFW UEFI firmware from C11, no EDK2/OVMF.
---

# WuBuFW — WuBuOS own UEFI firmware (C11, no EDK2/OVMF)

## What it is
A 256KB custom UEFI 2.10 firmware built from scratch in C11, replacing OVMF for WuBuOS QEMU boot.

## Project layout
`src/firmware/` — all firmware source:
- `fw_*.c/.h` — modular C11 implementation (console, memory, PCI, ACPI, block layer, AHCI, NVMe, XHCI, e1000, GOP, TPM, Secure Boot, shell, PE loader, etc.)
- `fw.ld` — flash image layout (256KB ROM at 4GB boundary, LMA→VMA copy in reset.S)
- `reset.S` — 16-bit real-mode entry → long mode → flat identity map → C entry
- `build.sh` — compiles all .c → `fw.elf` → `wubufw.fd` (256KB raw flash)
- `run.sh` — builds + creates ESP + boots under QEMU (q35, AHCI/NVMe/XHCI/e1000/GOP)
- `tools/mkpe.c` — PE32+ EFI image builder (self-contained C11)
- `tools/mkesp.c` — FAT32 GPT ESP image builder (self-contained C11)
- `payload/` — test EFI application (hello.c) with 28 conformance checks

## Key architecture decisions
- No third-party deps: all tools (mkpe, mkesp) written in-house C11
- Block device abstraction (`fw_block.c/h`) so FAT/GPT works across IDE/AHCI/NVMe uniformly
- fw_cfg table-loader execution produces real ACPI (RSDP, MCFG, etc.) — QEMU delivers tables this way, not in memory
- PCI resource assignment (`fw_pcires.c`) programs BARs at boot (QEMU leaves them unassigned)
- Measured boot: PCR0 (CRTM+firmware), PCR5 (GPT), PCR7 (SecureBoot policy), PCR4 (boot image)
- Secure Boot verifier (`fw_secureboot.c`): Authenticode hash vs db/dbx, PCR7 extend. db/dbx enrollment, setup-mode→user-mode transition via PK. **`fw_sb_selftest`** (policy-engine unit) + **`fw_sb_selftest-pe`** (end-to-end): builds a signed PE (`mkpe -cert`) and an unsigned one, enrolls the test signer in db, flips to user/enforce mode, then asserts the signed image verifies and the unsigned is rejected. Also runs at boot.
- **omarchy/sbctl-style enrollment (PK/KEK/db/dbx as real UEFI variables)**: `fw_sb_enroll_esl("PK|KEK|db|dbx", esl, len)` parses an EFI_SIGNATURE_LIST (EFI_CERT_X509_GUID + owner GUID + DER cert), updates the db/dbx hash policy, stores the list via the runtime variable service (EFI_GLOBAL_VARIABLE for PK/KEK, EFI_IMAGE_SECURITY_DATABASE for db/dbx), and on PK writes SecureBoot=1/SetupMode=0 and flips setup→user. `fw_sb_create_platform_key()` = sbctl create-keys; shell `sbstatus`/`sbpk`/`sbenroll <which> <file.esl>`; `fw_sb_selftest_esl()` gates the round-trip + transition at every boot.
- **Host tool `tools/mksb.c` (sbctl equivalent)**: `create-keys <dir>` writes SB.DER + DB.ESL/PK.ESL/KEK.ESL; `sign <cert.der> <in.efi> <out.efi>` attaches a WIN_CERTIFICATE_EFI_GUID entry; `verify <efi> <db.esl>` checks the embedded cert hash; `selftest` covers round-trip + tamper rejection. Built by build.sh. Gate: `make test_secureboot` (src/firmware/sb-gate.sh).

### Secure Boot enrollment: the omarchy/sbctl model

WuBuFW verifies images against db/dbx but enrolls policy as in-memory arrays
with a flag-flip PK -- no real UEFI variables yet. The expansion target is the
omarchy/sbctl model: PK/KEK/db/dbx as EFI_SIGNATURE_LIST variables, setup->user
transition on PK, enforcement requiring PK+db, an sbctl-style host key/sign
tool, and shell enrollment commands. See
`references/secure-boot-enrollment.md` for the variable/ESL format, GUIDs, the
WuBuFW gap, and the expansion design (not yet implemented).
- TPM 2.0 (`fw_tpm.c`): TIS/FIFO + CRB transports, ACPI TPM2 table parsing, PCR extend math self-test against the TCG SHA-256 vector (SHA256(0^32 || 0^32) = f5a5fd42…), software-only fallback that mirrors HW PCRs for attestation when no TPM is present
- `mkpe` now emits the PE certificate table (WIN_CERTIFICATE_EFI_GUID / EFI_CERT_TYPE_RSA2048_SHA256) at the correct DataDirectory[4] offset; **`-cert <der>`** option attaches a test cert so Secure Boot can be exercised
- Interactive shell (`fw_shell.c`): `ls`, `cat`, `pci`, `drivers`, `map`, `devices`, `mem`, `tpm`, `net`, `mm`, `boot`, `ver`, `exit`. Always drops to shell on boot; `exit` launches the payload

## Chainloader: booting the REAL kernel as a measured payload (2026-08-02)

`src/firmware/loader/` is a self-made PE32+ EFI chainloader that boots
`src/kernel/kernel.elf` through WuBuFW's attest-and-boot:

- `loader.c` — LocateHandleBuffer+SFS → read `\EFI\BOOT\KERNEL.ELF` (≤4MB) →
  validate ELF64 → copy every PT_LOAD to its physical LMA (0x100000) + zero
  BSS → SHA-256 the kernel → write loader handoff block → GetMemoryMap key →
  ExitBootServices → `wubufw_handoff(entry_phys)`.
- `teardown.S` — 64→32-bit exit: lgdt (flat 32-bit CS), lretq into .code32
  compat mode, clear CR0.PG then CR4.PAE, `jmp` to the kernel's physical
  `_start` (e_entry − 0xffffffff80000000 = 0x10012c — the ELF e_entry, NOT
  the multiboot entry_addr 0x100020 which is only valid for `qemu -kernel`).
- Handoff wire format is SHARED: `fw_agi_attest.h` (firmware) ↔
  `src/kernel/wubu_attest.h` (kernel duplicates layout + static-asserts
  size 288/80). Fixed low-RAM addresses: 0x90040 = handoff ptr,
  0x91000 = handoff {magic,version=2,kernel_size,kernel_sha256,attest_addr,
  fb_addr,fb_width,fb_height,fb_pitch}, 0x92000 = attestation struct.
  Kernel's `wubu_attest_load_scratch()` reads them (identity-mapped by crt0's
  0..1GB PD). Bumping the struct means updating BOTH headers, BOTH static
  asserts, the loader's writer and any kernel test fixture
  (`test_agi_kernel.c` builds a handoff by hand).

### Framebuffer handoff (GOP → kernel): the chain the guest can actually see

Without it the kernel allocates its own VBE surface and renders into memory
nobody displays — QEMU `screendump` stays black (640x480, ~2 distinct colours)
while the kernel happily logs "Bonzi loop active (fb=1920x1080)".

1. **Firmware** publishes the GOP linear framebuffer at a FIXED low address
   right before `fw_boot_image()`:
   `0x90050` = u64 fb_addr, `0x90058` = (w<<32)|h, `0x90060` = u32 pitch,
   `0x90064` = u32 magic `0xFBFBFBFB` (guard, so a stale boot reads nothing).
2. **Chainloader** copies those four words into the handoff. It CANNOT call
   `fw_gop_fb()` — the loader is freestanding and does not link the EFI GOP
   code (`undefined reference to fw_gop_fb`). The fixed-address block exists
   precisely because of that link boundary.
3. **Kernel** prefers the Limine framebuffer when present, else the handoff:
   `vbe_set_backend(VBE_BACKEND_MALLOC, (uint32_t*)fb_addr, w, h, NULL)` —
   `vbe_init()` alone allocates a private buffer and never reaches the display.

### After the handoff: what else has to be true before pixels land

A correct handoff is necessary, not sufficient. Four independent failures sit
between "the struct is right" and "the screen shows something":

1. **Do not gate the handoff on `g_limine_ok`.** A `if (!g_limine_ok && hd && ...)`
   guard silently skips the handoff when the flag is truthy without a real
   Limine boot; the kernel then keeps its 1920x1080 private surface and every
   later symptom looks like a handoff bug. Gate on `hd->version >= 2 && hd->fb_addr`.
2. **The announcement is not the log line.** The attach is only real if the
   kernel can WRITE there. QEMU's LFB sits at `0xC0000000`, far outside crt0's
   0..1GB identity window, so the first pixel store silently faults: the log
   stops right after the "attached" line with no panic. Map the range 1:1
   (`wubu_vmm_map_page(a, a, 3)` per 4 KB page) — and do it AFTER
   `wubu_vmm_init()`, which is not idempotent (it re-zeroes the bitmap), so it
   may be called only once per boot.
3. **EFI tears its graphics console down at `ExitBootServices`**, so the mode
   the firmware set does not survive into the kernel. Re-program dispi from the
   kernel once it is past EFI: disable → xres/yres/bpp/virt_w/virt_h →
   `enable = 0x41` (VBE enabled | LFB), via index `0x1CE` / data `0x1CF`.
4. **The dispi MMIO window is a FLAT register file, not index/data.** Per the
   QEMU Standard VGA spec, BAR2 maps the registers at `0x500 + (index << 1)`:
   XRES `0x502`, YRES `0x504`, BPP `0x506`, ENABLE `0x508`, VIRT_W `0x50C`,
   VIRT_H `0x50E`. Writing an index to `0x500` and data to `0x502` reads back
   `0` and looks like "this card has no MMIO window" — that is a misread, not an
   absent window. The legacy ports `0x1CE`/`0x1CF` (plus `0x1D0`) only exist on
   the non-legacy-free variant, so prefer the flat MMIO path when BAR2 exists
   and fall back to ports otherwise. `OvmfPkg/QemuVideoDxe` drives `1234:1111`
   through exactly this flat path, which is also why the "UEFI needs the VGA
   option ROM" theory is wrong.

### Verifying pixels: screendump lies, use the VNC grab

`-display none` + monitor `screendump` returns a 640x480 dummy surface even
when the guest programmed 1024x768, so it is not evidence about the display
path. Use `scripts/qemu_vnc_shot.py` (RFB 3.8, no dependencies): boot with
`-display vnc=127.0.0.1:9`, then
`python3 tools/qemu_vnc_shot.py 127.0.0.1 5909 /tmp/vnc.ppm` and count colours.

**Do not measure the firmware's own text console and call it a display bug.**
A manual `qemu-system-x86_64` run that never sends `exit` to the WuBuFW shell
sits at the shell forever: the grab is a 640x480 two-colour TEXT screen, and
every conclusion drawn from it is false. Any manual run must drive the shell and
boot the OS image the gate builds:

```
{ sleep 2; printf 'exit\n'; sleep 45; } | qemu-system-x86_64 -machine q35 \
  -bios "$PWD/wubufw.fd" \
  -drive file="$PWD/build/agi-esp.img",format=raw,if=none,id=esp \
  -device ahci,id=ahci -device ide-hd,drive=esp,bus=ahci.0 \
  -m 512 -serial stdio -display vnc=127.0.0.1:9 -no-reboot
```

`run-agi.sh` is what rebuilds `build/agi-esp.img`; a direct run against
`build/wubu-esp.img` may carry a stale kernel. Run the gate first, then grab.

Known-open state, do not present as solved: with the handoff read correctly,
the range mapped and painted, dispi reading back `xres=1024 yres=768
enable=0x41`, and the kernel adopting the probe-verified scanout address
`0xFD000000`, QEMU still presents 640x480 black when booted through WuBuFW.
Isolate with `references/graphics-scanout.md` before changing more code — and do
not wire the GUI/window manager on top of it or claim the GUI path works until a
grab is non-black at the intended resolution.

### The GUI is not linked into the kernel by default

`mk/objects.mk` defines ~120 `GUI_OBJS` but `KERNEL_OBJS` contains ZERO `gui/`
objects, so `wm_init` exists only in hosted builds. Adding the WM means
adding objects AND stubbing the hosted-only pieces it pulls: `load_default_wallpaper`,
`wubu_wallpaper_load`/`_default_path`/`_rect` (stdio), `wubu_settings_get`
(disk-backed), `wubu_a11y_*` and `wubu_bonzi_*` draw entry points, plus a
`__strncpy_chk` shim for fortified glibc. `wm_render` additionally pulls
chrome/taskbar/icon/clock objects and `localtime`. Init the WM AFTER the
framebuffer is attached, else it sizes itself to `0x0`.

### Stale kernel.elf: a failed link looks like a successful boot

`make kernel` links against the object list in `mk/objects.mk`; a new `.c` that
is not added there fails the link, but the PREVIOUS `kernel.elf` is still on
disk. `run-agi.sh` then boots old code and prints old log lines, which reads as
"my new code had no effect". Always confirm the build's exit status (and that
`kernel.elf` is newer) before interpreting any QEMU output.

### `qemu -kernel` cannot load this kernel

QEMU's multiboot loader rejects an x86-64 ELF outright —
`Cannot load x86-64 image, give a 32bit one` — and it does not implement VBE
mode requests (`multiboot knows VBE. we don't`). Adding a multiboot header to
`crt0.S` therefore does NOT give you a `-kernel` boot path: you need either a
separate 32-bit ELF stub that performs the long-mode switch, or a GRUB ISO with
`multiboot2` + the framebuffer tag. Do not spend a cycle assuming the header
alone is enough.

Debugging rule: before forming a hypothesis about hardware behaviour, read the
vendor spec (QEMU Standard VGA) or the reference implementation
(`OvmfPkg/QemuVideoDxe`). Two hypotheses in one session — a missing MMIO window
and a never-executed VGA option ROM — were both falsified by a single spec page
and its driver source, and both had already cost boot cycles.

Debugging rule: print the handoff fields with `klog_printf` using `%u`/`%x`
only — the kernel printf does NOT implement `%llx`, so it prints the literal
specifier and shifts every later argument (a garbled diagnostic that looks
like a struct-layout bug). Print a u64 as two `%x` halves.

### Pitfalls (all real, all cost a debug cycle)
1. **mkesp path quoting**: `'\EFI\BOOT\BOOTX64.EFI'` in bash (SINGLE
   backslash). `'\\EFI\\...'` (double) makes mkesp create an EMPTY-named
   intermediate directory (`\EFI\<empty>\BOOT\...`) — firmware can't find
   the app ("no bootable EFI application found") even though `ls` shows
   `EFI`. mkesp's dir entries are non-standard: cluster HIGH word at dir
   offset 20, LOW at 26 (the firmware reads them the same way — consistent
   but not FAT-spec; a standard-layout parser will misread every cluster).
2. **Secure Boot selftest needs the ESP attached AND SIGNED.EFI on it** —
   without the ESP drive `read_path_any` finds no filesystem, so `sr != 0`.
   The self-test now distinguishes absent fixtures from broken ones: it prints
   `[sb] payload self-test: SKIP (no SIGNED.EFI/BOOTX64.EFI on medium)` and
   keeps `pass` intact, and still runs the real PASS/FAIL assertions when the
   payloads are present. Keep that split — a medium without test images must
   not read as a policy bypass, and a genuinely mis-verifying payload must not
   read as a harness gap. Build SIGNED.EFI with `mkpe -cert` like run.sh.
3. **Kernel PT_high off-by-256 (fixed in crt0.S)**: the higher-half page
   table loop wrote i=256's mapping at PT_high[0] (write ptr must start at
   PT_high + 256*8). Under WuBuFW the kernel's VA 0xffffffff80100000 then
   resolved to PA 0x200000 = the firmware image → klog text = firmware
   strings/garbage while all code ran fine (code executes at physical
   addresses via the identity map; only `movabs` data refs go through the
   higher-half map). Under `qemu -kernel` the same bug silently produced
   EMPTY strings (0x200000 was zeroed RAM) — the loader exposed it.
4. **objdump lies about .code32 in a 64-bit .o**: `47 eb da` / `47 81 ff`
   display as `rex.RXB jmp`/`cmp %r15d` but run as `inc %edi; jmp` /
   `inc %edi; cmp $0x200,%edi` in 32-bit mode. The bytes are correct;
   trust the CPU, not the disassembler.
5. **Debug-print loops**: `outb %al` destroys the value being printed —
   print from a register the UART doesn't touch (e.g. rotate ECX, emit
   via EAX/EDX), or the dump reads as all-zeros.
6. **`fw_sb_verify` reads to `base+0xA0` and computes `size-0xA0`**: feeding a
   short (<0xA0) buffer runs `pe_authentihash` out of bounds and underflows
   the length to a huge value — the firmware hangs right after the caller's
   last print. Any test that exercises the enforcement path must pass a
   full-size (>=0xA0) buffer; the policy-engine selftest's warning about not
   feeding non-PE buffers applies to every new selftest too.

## The two boot claims, and which one is a test

- `tools/boot_audit.sh` proves the artifact is **freestanding** (no PT_INTERP, no
  NEEDED, no undefined symbols, fixed entry). It says nothing about whether the
  machine boots — never report it as a boot result.
- `qemu-boot-verify.sh` (wrapped by `make boot-gate` / `tools/boot_gate.sh`) is
  the boot claim that can fail: it boots WuBuFW, drives it, and greps every
  milestone. Exit 0 only when all are observed.
- `qemu-system-x86_64 -kernel kernel.elf` is a documented **dead end**, kept
  behind `boot_gate.sh --kernel` so the next session can reproduce why instead
  of retrying it. Its output is SeaBIOS text plus a few probe bytes
  (`010203040506070811121314`), not a kernel log — do not diagnose that string
  as a kernel panic.

## Booting the REAL kernel through the chainloader (measured-boot gate)

`make test_agi_metal` / `src/firmware/run-agi.sh` boots `kernel.elf` and
asserts every hop on the QEMU serial log (attestation published → loader
FOUND → kernel sha256 → ExitBootServices → kernel_main → attestation
consumed → AGI kernel booted → attestation VALID → Bonzi loop → heartbeat).
Gate waits only ~6s after `exit`, so a slow loader reads as a hang. It now
waits **14s** (changed 2026-11-06) because the Bonzi heartbeat is paced once
per SECOND and, under the `PROMOTED span` serial flood, the single heartbeat
in a 6s window kept landing just after qemu was terminated (`MISSING: bonzi
heartbeat` while every earlier milestone greps PASS). If that check flips red
with everything else green, widen the post-`exit` sleep before touching the
kernel.

### The real "Segment Bounds / triple-fault after ELF64 ok" chain (2026-11-06)

When the boot dies at the chainloader with `ELF64 ok` then a silent triple
fault (guest `#UD`→`#GP` at an in-binary `IP` like 0x70002, not a `#PF`),
work OUTWARD from the last `[loader]`/crt0 marker — there are FIVE stacked
causes, each fixed and gate-green on 2026-11-06:

1. **Loader `segment bounds` cap 4 MiB → 32 MiB.** `loader.c` rejected a
   PT_LOAD unless `p_paddr + p_memsz <= 0x400000`. The modern kernel's
   `.bss` pushed memsz past that. `readelf -l kernel.elf` showed
   `p_paddr=0x100000 memsz=0x93DB2C` → 10.7 MiB. Raising to `0x02000000`
   cleared it. **The old "fit under 1 MiB" advice below is WRONG for the
   modern kernel** — memsz 1.3 MiB (>1 MiB) boots fine; the real bounds are
   (a) fit the loader's cap and (b) don't stomp the firmware's live page
   tables (see 4).
2. **The 8 MiB static libc heap in kernel `.bss`.** `src/kernel/libc.c`
   had `static uint8_t libc_heap_storage[8*1024*1024]` for its bump
   allocator. On metal that heap is NEVER used (`malloc` delegates to
   `mem_alloc`; `libm_heap_init` is only called by selftest binaries), yet
   the array unconditionally inflated `.bss` to 9.2 MiB. Guarded the array
   AND `libm_heap_init` with `#ifndef MYSEED_METAL` (metal gets a no-op),
   which shrank kernel `.bss` 8.4 MiB → 851 KB.
3. **Loader zeroed BSS over WuBuFW's LIVE page tables → triple fault.**
   Even after the shrink, the loader's `l_memset` of `.bss`
   (0x168080..0x230000) corrupted the firmware's ACTIVE page tables (they
   sit at ~0x168080+, right where kernel `.bss` starts) — the loader is
   STILL executing on them, so its own next fetch jumps to garbage
   (`#UD`/`#GP` at a low `IP`). Moving the load to AFTER
   `ExitBootServices` did NOT help (the loader still runs on those tables).
   **Fix: the loader copies ONLY `filesz` (code/data, ends 0x168080,
   safely below the ptables) and does NOT zero BSS.**
4. **`crt0.S` now zeroes the kernel's own `.bss`** right after setting the
   64-bit segments and installing its own CR3 (insert before the early
   stack): `movabsq $_bss_start,%rdi; movabsq $_bss_end,%rcx; sub;
   xorl; rep stosb` (push/pop `%rsi` to preserve the image base). This is
   IDEMPOTENT under every loader (qemu -kernel/limine/multiboot already
   zero it) and self-sufficient under WuBuFW. `_bss_start`/`_bss_end` exist
   in `src/kernel/kernel.ld`.
5. **`Gateway 6s window misses the paced heartbeat`** — see the note above;
   `run-agi.sh` now sleeps 14s post-`exit`.

A kernel that ''should fit'' by `readelf` but still triple-faults right
after `ELF64 ok` / a crt0 marker almost always means a write is landing on
the firmware's active page tables — find WHAT low-RAM region WuBuFW keeps
them in and keep every loader write below it, or defer the write into crt0
(the owner of the new page tables).

### Kernel-never-reaches-kernel_main debug procedure (stacked, each verified by a fresh run)
When the serial log stops inside the loader (`seg copied` but not
`bss-zeroed`) or the kernel panics mid-init, work outward from where output
STOPS — the last printed line localizes the fault:

1. **Loader stops at `seg copied`, never `bss-zeroed`** → (the 2026-11-06
   fix above SUPERSEDES the 1 MiB rule that follows: the loader no longer
   zeroes BSS at all and the kernel no longer needs to fit under 1 MiB —
   memsz 1.3 MiB boots. Read the new section first.) The old diagnosis was:
   the BSS memset
   faults because the image crosses an `EfiUnusableMemory` hole. Dump the
   UEFI memory map BEFORE the load loop (`BS->GetMemoryMap`, print
   base/pages/type per descriptor) to see the real usable ceiling — do NOT
   assume the old 4 MiB `0x400000` kernel ceiling. In q35 only ~1 MiB is
   contiguous at `0x100000` (type-5 hole at `0x200000`), so the kernel image
   (text+data+bss) MUST fit under 1 MiB. Shrink static `.bss`: per-page
   bookkeeping arrays sized for max RAM (`g_refs[BITMAP_BITS]`) and any large
   static heap buffer are the usual 100s-of-KB culprits — size them to a
   boot-appropriate range with a comment that the allocator extends at
   runtime. Confirm the fix with `readelf -l kernel.elf` (memsz < 0x100000).
2. **Kernel panics `mem_init failed` right after `firmware attestation
   consumed`** → `memory.o` was compiled with `-DWUBU_HOSTED` (a special
   Makefile rule), so `mem_init()` took the `malloc()` path, which returns
   NULL under `-nostdlib`. The bare-metal kernel needs `KERNEL_CFLAGS`
   (`MYSEED_METAL` → physical heap at `0x400000`). Check the actual object:
   `objdump -d memory.o | grep 400000` — if absent, the hosted variant was
   linked and that is the bug. Hosted consumers compile `memory.c` fresh with
   their own flags, so the shared `memory.o` must use the kernel flags.
3. **Host glibc fortified headers leak into freestanding objects** → at `-O2`
   `_FORTIFY_SOURCE` redirects `snprintf`→`__snprintf_chk`,
   `fprintf`→`__fprintf_chk`; the `-nostdlib` kernel link then fails with
   undefined refs. Add `-U_FORTIFY_SOURCE` to the kernel `.o`/`.S` compile
   rules. Only objects REBUILT after the flag change are fixed — stale `.o`
   keep the fortified symbols, so `find src/kernel -name '*.o' -delete` and
   rebuild all before concluding the fix failed.
4. **Byte-by-byte `l_memcpy`/`l_memset`** in the loader is far too slow for a
   multi-MB BSS under the 6s gate window — make them word-wise (8B at a time
   + byte tail).

A green gate prints `RESULT: PASS -- bare-metal AGI kernel booted via WuBuFW
(measured boot chain green)` with `attestation VALID`, `AGI kernel booted`,
`Bonzi Buddy loop active`, and advancing `PROMOTED span id=` lines.

### Strip debug sections before packaging
`kernel.elf` carries ~1.2MB of `.debug_*`; `objcopy --strip-debug` shrinks the
file (loaded image unchanged) so the ESP image and read stay small.

## Build & test
```
cd src/firmware && bash build.sh  # → wubufw.fd (262144 bytes)
./run.sh                          # → boots QEMU, runs payload, asserts 28/28 PASS
```

Invoke `build.sh` with **bash**, never `sh`: it sets `set -o pipefail`, and a
POSIX shell dies immediately with `Illegal option -o pipefail` (exit 2) before
compiling anything — which reads as a build failure rather than a shell
mismatch. Same for `qemu-boot-verify.sh`. This also means `make` targets that
shell out to them must name bash explicitly.
Or from repo root:
```
make firmware
make test_uefi
make test_agi_metal   # boots the REAL kernel via the chainloader (measured chain)
```

## Booting WuBuFW under QEMU (the dev target — we are QEMU dev users)

WuBuOS is developed and tested as a bare-metal QEMU guest: WuBuFW UEFI
firmware boots on `q35`, no host OS involved. `qemu-boot-verify.sh`
(added in `src/firmware/`) automates build + boot + serial-shell drive +
milestone grep and exits 0 only if every boot milestone is observed
(firmware banner, PCI probe, BAR/MMIO, AHCI ESP disk, secureboot
signed-verifies/unsigned-rejects, TPM PCR SHA-256, interactive shell,
`mem` allocator stats, ESP `ls`). Use it as the KERNEL-goal regression gate.

Manual boot (the working invocation — all three gotchas below bite otherwise):
```
cd src/firmware && bash build.sh          # writes ./wubufw.fd in the CWD, not build/
qemu-system-x86_64 \
  -machine q35 \
  -bios /home/wubu/wubuos/src/firmware/wubufw.fd \   # ABSOLUTE path (see gotcha 1)
  -drive file=/home/wubu/wubuos/src/firmware/build/wubu-esp.img,format=raw,if=none,id=esp \
  -device ahci,id=ahci -device ide-hd,drive=esp,bus=ahci.0 \   # ESP MUST be attached (gotcha 2)
  -m 512 -serial stdio -display none -no-reboot
```
Drive the interactive shell by piping commands with sleeps:
`(printf 'help\n'; sleep 1; printf 'mem\n'; sleep 1) | qemu-system-x86_64 ...`
(the first char can echo racily into the next prompt — a serial-timing
artifact, not a bug).

### QEMU boot gotchas (all real, all cost a debug cycle)
1. **`-bios` needs an ABSOLUTE path.** A relative `-bios build/wubufw.fd`
   fails with `qemu: could not load PC BIOS '...'` even though the file
   exists — QEMU resolves `-bios` against its own search path, not cwd.
   Also note `build.sh` writes `./wubufw.fd` in the CWD, NOT
   `build/wubufw.fd` — locate it with `find . -name wubufw.fd` before booting.
2. **The ESP disk must be attached or the Secure Boot selftest false-FAILs.**
   Booting with only `-bios` (no `-drive ... -device ide-hd`) reaches the
   shell but prints `[sb] signed payload verify: FAIL` and
   `[sb] unsigned-payload rejection: FAIL` — because `read_path_any` finds no
   filesystem, so `sr != 0`. This is a HARNESS gap, not a code bug: attach
   `build/wubu-esp.img` via AHCI and both flip to PASS. Do not "fix" the
   verifier in response to this.
3. **Serial console has CR (`\r\n`)** — grep boot milestones with `grep -a`
   (QEMU output is flagged binary) and expect `\r` in patterns.

## Hardware surface in QEMU (q35)
- AHCI (SATA) — 2 disks
- NVMe — 1 namespace
- XHCI USB — 1 keyboard
- e1000 NIC — MAC 52:54:00:12:34:56, link up
- GOP (1024×768 ×32 linear framebuffer)
- TPM software backend (no swtpm needed; PCR measurements are SW-only)

## Known limits (future)
- No real TPM hardware (software-only measurements)
- No AHCI port power management (ports are probed once)
- Secure Boot enforcement requires a db enrolled (setup mode allows all by default)
- Shell `boot` command uses `fw_image_create_from_path` which reads via block layer

## Triple-DA check points
- BAR sizing: 32-bit BAR inversion must stay 32-bit (was a bug that hid AHCI ABAR)
- fw_cfg table-loader must be executed for real ACPI (not just scanned)
- Block device abstraction needed because q35 has no legacy IDE
- AHCI port signature check must happen AFTER port start (PxSIG=0xFFFFFFFF before ST)
