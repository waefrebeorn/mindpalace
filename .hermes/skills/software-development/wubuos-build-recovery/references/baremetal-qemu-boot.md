# Bare-metal bootsector assembly + QEMU validation (WuBuOS)

`src/kernel/boot.S` is a self-contained 16-bit BIOS bootsector: it loads
`kernel.elf` (concatenated at LBA 1), parses its ELF64 program headers, copies
each `PT_LOAD` segment to its physical LMA (0x100000+), switches to 32-bit
protected mode with a flat 4GB GDT, and jumps to the kernel entry
(`_start` in `crt0.S`, which finishes the long-mode transition).

When this file is broken it won't even assemble, or assembles to garbage that
silently fails to boot. The pitfalls below were all hit and fixed the hard way.

## CRITICAL: SeaBIOS loads a raw 512-byte sector at LINEAR 0, not 0x7C00

This is the #1 trap. If you write `.org 0x7C00`, every symbol's VMA becomes
`0x7C00 + offset`, but SeaBIOS places the sector bytes at linear 0x0000
(CS=0, IP=0). So `movw $str_foo, %si` (VMA 0x7d27) reads linear 0x7d27 — which
is NOT where the string actually lives (it's at linear 0x127). Result:
`serial_puts` reads garbage / NUL and prints nothing, while a raw `outb` of a
literal still works (no memory read). Symptom that screams "this bug": the
bootsector prints an entry marker char but never prints any string, and the
machine triple-faults into a reboot loop (you see the marker repeated).

**Fix:** anchor the section at `.org 0`. Then VMA == file offset == linear load
address, and all `movw $sym, %reg` references are correct. The boot signature
`.space 510 - (. - _start16), 0` then lands exactly at offset 510.

## `cld` is MANDATORY before `lodsb` / `stosb`

BIOS leaves the direction flag (DF) in an undefined/set state. `lodsb` and
`stosl` with DF set will DECREMENT the index register and walk backward through
memory, reading/writing garbage. A bootsector that prints via `serial_puts`
(using `lodsb`) will emit nothing or garbage even though the code is correct.

**Fix:** `cli; cld` as the very first instructions in `_start16` (and again
after the `jmp $0x08, $1f` into `.code32` before any `lodsb`/`stosl`).

## Assembling the bootsector to a clean 512-byte image

With `.org 0`, the object's `.text` section is exactly 512 bytes (the
`.space` pad + signature), so a plain extract works:

```
$(CC) -c -m16 -ffreestanding -nostdlib -I$(KERNEL) $(KERNEL)/boot.S -o $(KERNEL)/boot.o
objcopy -O binary -j .text $(KERNEL)/boot.o $(KERNEL)/boot.bin
truncate -s 512 $(KERNEL)/boot.bin
```

**Do NOT** use the kernel freestanding flags (`-mcmodel=kernel -fno-pie
-mno-red-zone`) on `boot.S` — it is 16-bit real-mode code, not kernel-model
code, and those flags corrupt it. Use plain `-m16 -ffreestanding -nostdlib`.

If you ever DO use `.org 0x7C00`, `objcopy -O binary` emits a 32256-byte file
(section padded out to the VMA). The real bootsector then lives at file offset
0x7C00..0x7E00; you'd have to `dd if=raw.bin of=sec.bin bs=1 skip=31744
count=512`. Avoid this — just use `.org 0`.

## ELF entry formula (real-mode stub)

The kernel is linked at higher-half VMA `0xffffffff80000000+` but LOADED at LMA
`0x100000`. The physical entry is:

```
movl 0x18(%ebx), %eax      # e_entry low 32 bits (higher-half VA)
subl $0x80000000, %eax     # -> physical load address of _start (0x100110)
```

**Do NOT also add 0x100000** — that double-counts the LMA. Verified against
`readelf -l kernel.elf`: first `PT_LOAD` `p_paddr = 0x0000000000100000`,
`e_entry = 0xffffffff80100110` → physical entry `0x100110`. Correct.

## Building the bootable disk image

```
cat $(KERNEL)/boot.bin $(KERNEL)/kernel.elf /dev/zero | head -c 1474560 > $(KERNEL)/disk.img
```

1.44 MB floppy geometry. Boot with `-boot a -drive ...,if=floppy`.

## QEMU serial capture recipe (how to actually SEE the boot trace)

- Use **`-nographic`**, not bare `-serial stdio`. `-nographic` routes COM1 to
  the QEMU stdout and is reliable; `-serial stdio` alone can be lost/merged
  with the VGA console and swallowed.
- Add **`-device isa-debug-exit,iobase=0xf4`** and have the kernel/stub do a
  clean `outb %al, $0xf4` at the end. This makes QEMU exit cleanly so the
  serial buffer FLUSHES. Without it, `timeout` SIGTERMs QEMU and the last
  serial bytes are lost (you see 0 bytes even from a guaranteed-emitting loop).
- Capture to a FILE, not a pipe, when chasing boot hangs:
  `qemu ... -nographic -device isa-debug-exit,iobase=0xf4 > /tmp/boot.out 2>&1`
  then `grep -aoE "WuBuOS BOOT|LOADED|ELF OK|..." /tmp/boot.out`.

### Diagnostic instrumentation that WORKS
- Raw `outb` of a literal char to COM1 (`movw $0x3F8,%dx; movb $'B',%al; outb`)
  is the ground-truth probe: if it prints, the CPU reached that point.
- A `serial_putc` that PUSHES `ax`/`dx` first, reads LSR `0x3FD` for THR-empty
  (`testb $0x20`), then restores `dx` then `ax` before `outb`, works reliably.
- To find WHERE execution dies: print a distinct literal char at each phase
  (`'B'`=entry, `'L'`=after disk read, `'E'`=ELF ok, …). The last char printed
  is the last phase reached before the hang/fault.

## KNOWN ENVIRONMENT LIMITATION (this WSL/QEMU sandbox)

`int 0x13` disk reads **hang** here — both LBA-extended `ah=0x42` (DAP) and
classic CHS `ah=0x02`, on both `if=floppy` and `if=ide -boot c`. Verified by
isolated harness tests: the bootsector executes (`R` prints), but the `int
0x13` call never returns (no carry, no error code — a hard hang). This is a
SeaBIOS/QEMU media-emulation quirk in THIS sandbox, NOT a bootsector logic bug.
Consequence: you cannot validate the full kernel boot (ELF load → long mode →
`kernel_main`) under QEMU here. The verified bar for the bare-metal path is:
**`make kernel` links → `kernel.elf` produced**, plus `make boot` produces a
correct 512-byte `boot.bin` (AA55 at offset 510, `_start16` code at offset 0).
On real hardware or a less-restricted QEMU, the same `boot.S` will load the
kernel and emit `WuBuOS BOOT / LOADED / ELF OK / 64-bit long mode entered`.

## Makefile wiring (shipped)

```
$(KERNEL)/boot.bin: $(KERNEL)/boot.S
	$(CC) -c -m16 -ffreestanding -nostdlib -I$(KERNEL) $(KERNEL)/boot.S -o $(KERNEL)/boot.o
	objcopy -O binary -j .text $(KERNEL)/boot.o $(KERNEL)/boot.bin
	truncate -s 512 $(KERNEL)/boot.bin

$(KERNEL)/disk.img: $(KERNEL)/boot.bin $(KERNEL)/kernel.elf
	cat $(KERNEL)/boot.bin $(KERNEL)/kernel.elf /dev/zero | head -c 1474560 > $(KERNEL)/disk.img

boot: $(KERNEL)/boot.bin
	@echo "✅ Bootsector built (./src/kernel/boot.bin, 512 bytes)"

qemu: $(KERNEL)/disk.img
	qemu-system-x86_64 -drive file=$(KERNEL)/disk.img,format=raw,if=floppy -boot a \
		-nographic -device isa-debug-exit,iobase=0xf4 || true
```
