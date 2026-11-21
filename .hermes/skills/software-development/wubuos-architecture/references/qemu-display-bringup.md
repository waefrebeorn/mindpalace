# QEMU / bare-metal display bring-up and verification

Read this before touching `src/firmware/fw_gop.c`, `src/kernel/vbe.c`,
`src/kernel/ramfb.c`, or any "the screen is black" investigation.

## 1. Ground truth: QEMU Standard VGA (device `1234:1111`)

From the QEMU Standard VGA spec (docs/specs/standard-vga.rst), not from guessing:

| region | contents |
|---|---|
| PCI BAR0 | framebuffer memory, 16 MB by default (`vgamem_mb`) |
| PCI BAR1 | reserved (64-bit BAR option) |
| PCI BAR2 | MMIO, 4096 bytes |
| PCI ROM | holds the vgabios |

MMIO layout at BAR2:

```
0000-03ff  EDID blob
0400-041f  VGA ioports (0x3C0-0x3DF) remapped 1:1
0500-0515  bochs dispi registers, FLAT, no index/data pair
0600-0607  QEMU extended registers (framebuffer endianness)
```

**dispi MMIO addressing: register N lives at `0x500 + (N << 1)`.** That is a
direct 16-bit register, NOT an index/data pair. Writing index to `0x500` and
data to `0x502` (the natural but wrong assumption) reads back 0 and makes the
window look absent.

| index | register | MMIO offset |
|---|---|---|
| 0 | ID | 0x500 |
| 1 | XRES | 0x502 |
| 2 | YRES | 0x504 |
| 3 | BPP | 0x506 |
| 4 | ENABLE | 0x508 |
| 6 | VIRT_WIDTH | 0x50C |
| 7 | VIRT_HEIGHT | 0x50E |

Legacy I/O path (only when the device is NOT the legacy-free variant):
index `0x1CE`, data `0x1CF`, second data port `0x1D0`, x86 only.
The spec says the ports do not exist on `secondary-vga`.

Mode-set sequence (both windows): ENABLE=0 → XRES/YRES/BPP/VIRT_W/VIRT_H →
ENABLE = 0x01 (enabled) | 0x40 (LFB).

## 2. The authoritative reference implementation

`OvmfPkg/QemuVideoDxe` (tianocore/edk2) is the code that makes QEMU display a
mode under UEFI **without ever running the VGA option ROM**. It matches on PCI
`1234:1111` and drives the flat MMIO dispi path above. Consequences:

- Do NOT theorise that a missing option ROM explains an inert card — OVMF proves
  the UEFI path needs no ROM.
- When a mode does not take effect, compare against this driver's exact register
  sequence before inventing a new explanation.

## 3. Verification: what actually measures the guest

- `screendump` under `-display none` returns a **640x480 dummy surface**, even
  when the guest programmed 1024x768. It cannot verify a graphics path.
- Use a real framebuffer read: `tools/qemu_vnc_shot.py` (dependency-free RFB 3.8
  client, 32bpp truecolour, raw encoding, writes a P6 PPM) against
  `-display vnc=127.0.0.1:N`.
- `-serial file:PATH` does **not** deliver stdin. A firmware that waits at an
  interactive shell will sit there forever and the grab shows the shell's text
  console — a meaningless 640x480 frame that looks like a display bug.
  Use `-serial stdio` and feed `printf 'exit\n'` to boot the OS.

Canonical headless capture (note TWO calls — the first must be background):

```bash
# call 1: terminal(background=true)
{ sleep 2; printf 'exit\n'; sleep 45; } | timeout 60 qemu-system-x86_64 \
  -machine q35 -bios wubufw.fd \
  -drive file=build/agi-esp.img,format=raw,if=none,id=esp \
  -device ahci,id=ahci -device ide-hd,drive=esp,bus=ahci.0 \
  -m 512 -serial stdio -display vnc=127.0.0.1:5 -no-reboot

# call 2: after ~25 s
python3 tools/qemu_vnc_shot.py 127.0.0.1 5905 /tmp/shot.ppm
```

Run QEMU in the foreground and the boot window is gone before you can grab —
the capture always needs a background run plus a separate grab call.

## 4. Kernel-side traps (silent failures, no crash)

1. **Stale kernel binary.** A missing object in `KERNEL_OBJS` (e.g.
   `timer_wheel.o`) makes `make kernel` fail, and `run-agi.sh` then boots the
   PREVIOUS `kernel.elf`. Always confirm the link succeeded and the binary size/
   timestamp changed; never debug a boot whose binary you did not just build.
2. **Writes above the 1 GB identity map fault silently.** `0xC0000000`
   (firmware-reported LFB) and `0xFD000000` (QEMU std-VGA scanout) both live
   outside it. Map the range through the VMM before the first write:
   `wubu_vmm_map_page(addr, addr, 3)` per 4 KB.
3. **Large static buffers corrupt the heap.** Kernel image grows from
   `0x100000`; the heap starts at `0x400000`. A 3 MB static array in `.bss`
   pushed the image into the heap and broke boot. Put framebuffer-sized buffers
   at a fixed free physical address (e.g. `0x5000000`, above the heap window)
   and treat it as reserved.
4. **`klog_printf` has no `%llx`.** An unsupported conversion prints literally
   and consumes no argument, so every later field shifts and the values lie.
   Use `%x` with an `(unsigned long)` cast.
5. **Do not gate the firmware handoff on `g_limine_ok`.** It is truthy even
   without Limine, so the guard skips the handoff and the framebuffer is
   ignored. Gate on the handoff struct's own `version`/`fb_addr` fields.

## 5. Ordering rule for display discovery

Prefer a framebuffer the platform already produced (UEFI GOP handoff,
multiboot2 framebuffer tag, QEMU ramfb) over programming card registers.
Programmed modes depend on the platform's POST/option-ROM state; a handed-over
linear framebuffer does not. Keep the dispi path as the fallback, and log which
path won (`dispi=mmio|ports`) so the next run is diagnosable.

## 6. GUI in the kernel is a separate problem from display

`GUI_OBJS` in `mk/objects.mk` is HOSTED-ONLY: `KERNEL_OBJS` contains zero `gui/`
objects, so `wm_init` exists only in hosted builds and tests. Linking the
WM bare-metal takes a subset (`gui_dbuf`, `wm`, `wubu_wm`) plus stubs for
the hosted-only pieces (wallpaper uses stdio; settings read from disk; a11y and
Bonzi are optional overlays). Adding `wm_render.o` alone pulls ~11 more
objects. Generate the closure from the linker's undefined-symbol list instead
of hand-listing objects; a partial set leaves a dead render path.

An initialising WM is NOT proof it draws. Checksum the surface before and
after a render call and print both: `pre == post` means nothing was painted.
A checksum alone is not enough either — if every sampled pixel differs from the
desktop colour, the surface may simply be untouched/zeroed; sample actual pixel
values too.
