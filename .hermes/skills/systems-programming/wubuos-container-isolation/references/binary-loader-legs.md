# Binary-format execution legs (ELF / PE / Mach-O / DOS MZ loaders)

Construction pattern for an in-kernel loader that maps a binary format into a
page-aligned arena and returns the entry point — verified against a REAL binary
produced by a real toolchain, not only hand-built fixtures.

## The pattern (every format, same shape)
1. **Validate the header** (magic, word size, endianness, machine/CPU, file
   type) in a `*_validate(buf,len)` that touches nothing else. Fail-closed with
   distinct negative status codes per failure.
2. **First pass = image extent**: walk the loadable units (ELF PT_LOAD, Mach-O
   LC_SEGMENT_64, PE sections, DOS pages) to find `lo`/`hi` page-aligned bounds;
   bail if the arena is too small BEFORE copying.
3. **`memset` the arena to 0 once**, then **second pass copies** each unit's file
   bytes at `vaddr - lo`; the `memsz - filesz` tail stays zero (BSS).
4. **Entry** = `base + (entry_field - lo)` — the arena slot 0 maps to vaddr `lo`,
   and `base` is that slot's absolute address. Getting this `- lo` term wrong is
   the classic off-by-base bug (entry lands a whole image too high).
5. Bound-check every `offset+size` against BOTH the input buffer and the arena.

## Per-format gotchas (each cost a debug cycle)
- **ELF64 LE x86-64**: `e_entry` is an offset from the load base for ET_DYN; for
  ET_EXEC vaddrs are absolute so pass base=0. Real static binary: `gcc -static`.
- **PE32+ (AMD64)**: `SizeOfRawData` is FileAlignment(512)-rounded and CAN exceed
  `VirtualSize` — clamp the copy to `min(SizeOfRawData, VirtualSize)`, do not
  treat `rawsz > vsize` as an error. Real binary: `x86_64-w64-mingw32-gcc`.
  Entry RVA is relative to ImageBase.
- **Mach-O 64 x86_64**: magic `0xfeedfacf` (bytes `cf fa ed fe`); segments are
  `LC_SEGMENT_64` load commands walked via cmd/cmdsize from offset 32. Real
  object: `clang -target x86_64-apple-darwin -c` (no linker). An `.o` has no
  segments → loader correctly reports no-entry; header still validates.
- **DOS MZ**: no `e_lfanew`; load module = `e_cp*512 - (512 - e_cblp)` bytes at
  `e_cparhdr*16`; entry linear = `load_seg*16 + e_ip`. Relocation entries
  (e_lfarlc) are `{u16 off, u16 seg}` fixups: add the load segment to the 16-bit
  word at `off` in the loaded image. Real payload: `nasm -f bin` then prepend a
  hand-built MZ header (nasm bin emits no header).

## Verify against a real binary, always
Hand-built fixtures prove the byte math; a toolchain-produced binary proves the
loader handles real layouts (many segments, debug sections, alignment padding).
Shell to the toolchain from the test, read the file, validate + load, and assert
the observable fields (segment count, entry within the mapped image, copied
bytes match). Print the load status once to confirm the real leg actually ran
and was not silently skipped.

## Rootfs container runner (composes the ELF loader)
A rootfs container = rootfs dir + entrypoint ELF. Validate the rootfs is a dir
and the entrypoint exists + is a loadable ELF; fork a child that (optionally)
unshares the mount namespace + chroots into the rootfs, then execs the
entrypoint with configured argv; parent waitpid and surfaces the exit code.
Distro-agnostic — Arch and Debian are both just a rootfs tree + entrypoint.
`chroot` needs `_GNU_SOURCE` for `CLONE_NEWNS`. A static entrypoint ELF has no
libc deps, so it runs correctly inside the chroot.
