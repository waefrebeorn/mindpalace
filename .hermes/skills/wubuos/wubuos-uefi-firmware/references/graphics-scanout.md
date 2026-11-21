# Graphics scanout: isolating a black screen

## When to Use

Use when the guest logs a correct mode and a completed paint but the display is
still black or stale, or before claiming GUI pixels work. Work top-down: each
step removes a whole layer (measurement, boot path, device, firmware).
The goal is to answer *which layer* is lying: the mode registers, the address, or
the card's initialisation. Each step below removes a whole layer.

## 1. Grab the real framebuffer, not the monitor's opinion

`-display none` + monitor `screendump` returns a 640x480 dummy surface even when
the guest programmed 1024x768. Use `scripts/qemu_vnc_shot.py` (RFB 3.8, stdlib
only):

```
qemu ... -display vnc=127.0.0.1:9
python3 tools/qemu_vnc_shot.py 127.0.0.1 5909 /tmp/shot.ppm
# then count distinct colours in the PPM; 1-2 colours = nothing was drawn
```

## 2. Boot the OS, not the firmware shell

Manual QEMU runs that never send `exit` to the WuBuFW shell stay at the text
shell: a 640x480 two-colour grab that looks like a graphics failure but is just
the console. Pipe `exit`, and use `build/agi-esp.img` (the image `run-agi.sh`
builds) rather than an older `build/wubu-esp.img`.

## 3. Isolate with a minimal payload (no firmware, no loader, no kernel)

`src/firmware/vbe_probe.c` is a ~3 KB multiboot payload that only does the dispi
sequence and paints, then halts:

```
gcc -m32 -ffreestanding -nostdlib -fno-pic -no-pie \
    -Wl,-T,build/probe.ld -Wl,--build-id=none -o build/vbe_probe.elf vbe_probe.c
qemu-system-x86_64 -machine q35 -kernel build/vbe_probe.elf -m 128 \
    -display vnc=127.0.0.1:9 -no-reboot
```

Requirements for the payload itself: multiboot header must sit within the first
8 KB of the file (put `*(.multiboot)` first in the linker script), link with
`-no-pie` so the ELF is `EXEC` not `DYN`, and set `ENTRY(_start)`.

On q35 this yields **1024x768, one colour** — proving QEMU can switch modes and
that the painted LFB address is really scanned out.

## 4. Read the result correctly

| probe | firmware->kernel | conclusion |
|---|---|---|
| visible | visible | path works |
| visible | black | defect is in the firmware boot path, not the kernel |
| black | black | QEMU/device cannot switch; change the display device |

When the probe works everywhere and the firmware path stays black, the card is
accepting dispi writes without ever entering graphics scanout — so
"readback == written" proves nothing about pixels.

The option-ROM explanation was tested and is WRONG: `OvmfPkg/QemuVideoDxe` makes
QEMU display graphics under UEFI with no legacy option ROM, driving `1234:1111`
through the flat BAR2 dispi registers. Do not repeat that theory and do not
build a V86 shim on its strength. What remains unexplained is why the same
kernel-side writes move the scanout under SeaBIOS but not through WuBuFW; the
decisive experiment is a 32-bit multiboot stub or a GRUB ISO, because QEMU
refuses an x86-64 ELF with `Cannot load x86-64 image, give a 32bit one`.

## 5. Things already ruled out (do not re-run these)

- VGA PCI command register: already `7` (I/O + memory decode on).
- MMIO dispi: BAR2 registers are FLAT at `0x500 + (index << 1)`, not an
  index/data pair. Probing with index→`0x500`, data→`0x502` reads `0` and looks
  like a missing window; that probe was wrong, so "no MMIO" is not a finding.
  Legacy ports answer ID `0xB0C5` on the non-legacy-free variant.
- Sequencer unlock (0x3C4/5 idx 1, clear 0x20) + CRTC protection clear
  (0x3D4/5 idx 0x11, clear 0x80): no change.
- Adopting `0xFD000000` as the scanout address instead of the firmware-reported
  `0xC0000000`: no change under the firmware boot path.

## The two real ways forward

1. Execute the VGA option ROM from WuBuFW (ROM BAR on 0:1.0 + a real-mode shim,
   or a faithful reimplementation of the mode-set sequence). Keeps the
   fully-own firmware chain.
2. Boot the kernel multiboot-style under SeaBIOS and keep WuBuFW as an
   alternate platform. Fastest visible GUI; costs the own-firmware chain.

Both are design decisions, not bug fixes — surface the choice instead of
silently switching boot paths.
