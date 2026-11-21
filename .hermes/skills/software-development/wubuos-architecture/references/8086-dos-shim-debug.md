# 8086 DOS-Shim Debugging Notes (wubu_dos_emu)

Real bugs caught while building the from-scratch 8086 interpreter + DOS-INT
layer in `src/runtime/wubu_dos_emu.{h,c}` (2026-07-17). Reusable if you extend
the emulator or write another x86 interpreter in this repo.

## 1. 8086 byte-register encoding (the big one)

`0xB4` (`mov ah, imm`) encodes register index **4 = AH** (high byte of AX), but
the interpreter's `rb`/`wb` byte-register helpers routed index 4 -> **SP** (via
`regp`). So `mov ah,9` silently wrote SP instead of AH -> `INT 21h/09` never
fired -> blank screen, exit 0, no error. Classic x86 gotcha: byte regs are
`AL, CL, DX, BL, AH, CH, DH, BH` (indices 0,1,2,3,4,5,6,7), NOT the 16-bit
order. Fix: a dedicated 8-bit accessor that maps index 0..3 -> low byte of
`AX/CX/DX/BX` and 4..7 -> high byte of `AX/CX/DX/BX`, and `AH/BH/CH/DH` must be
addressable (not just `regp[i]` which gives the full 16-bit reg).

## 2. ALU reg-dest byte path must use the 8-bit adder

For `add/sub/adc/sbb r/m8, r8` the destination is an 8-bit register, so carry
must come from the **8-bit** add (`add8`), not the 16-bit `add16`. Using
`add16` for a byte op computes the wrong carry/overflow and corrupts the
half-carry. Keep `alu8`/`alu16` separate and pick by operand size.

## 3. `INC r16` must not fall through

`case 0x40..0x47` (inc reg) shares a decode block with `dec`. If the body does
`w = (op&1) ? add16(...) : ...` and the increment branch is missing, the
dec path runs for `inc` -> register goes the wrong way. Write the inc and dec
bodies explicitly.

## 4. Function-pointer casts in string ops

`do_scas` / `do_cmps` dispatch to `sub8`/`sub16` via a ternary:
`(w ? sub16 : (void(*)(...))sub8)(...)`. The mismatched pointer types warn and
can miscompile. Use a uniform signature (`void (*)(WubuDosEmu*,uint16_t,uint16_t)`)
for both helpers, or just call `sub8`/`sub16` directly in an `if (w)` branch.

## 5. Test programs must store results to memory

The natural test "mov ax,7 ; add ax,5 ; int 21h/4C" reads AX *after* run -- but
the program does `mov ax,4C00` (the exit code) before `int 21h` terminates, so
the final AX is `0x4C00`, not the computed value. **Fix:** have the test store
the result with `mov [0x200], ax` (A3 00 02) and read it back via
`wubu_dos_emu_peek16(e, 0x1000, 0x200)` (DS = 0x1000 in the COM model). Add a
`wubu_dos_emu_peek16` public read so tests can introspect memory.

## 6. Frame capture

`wubu_dos_emu_frame_rgba` renders the 80x25 text screen through an embedded 5x7
font into a 640x400 RGBA buffer (8px cell width, 16px cell height). The test
asserts `byte_count == 640*400*4`. Text colors come from the 16-color BIOS
attribute byte per cell.

## 7. INT surface implemented

- `INT 21h`: 09 (print `$`-terminated string to screen), 2A/2C (date/time ->
  regs), 4C (terminate with AL = exit code).
- `INT 10h`: 0E (teletype char), 00/02/06/09 (mode/cursor/scroll/char+attr).
- `INT 16h`: 00/01 (keyboard -- drained from an injected key queue).

Real DOS programs that only use `INT 21h/09` + `INT 21h/4C` run and print.

## 8. Additional bugs caught this session (extend the list)
- **Missing `F_DF` (0x0400) in the flags mask.** The flag defines listed TF/IF/OF
  but omitted DF, so `std` + string ops walked the wrong direction (and the mask
  comparison for DF was dead). Add `#define F_DF 0x0400` and set/clear it.
- **`add ax,imm` / `sub ax,imm` (op 0x05 / 0x2D) shadow read.** For the 16-bit
  form keep `e->ax = add16(e, e->ax, fetch16(e), 0)` — do NOT introduce a second
  `fetch16`/intermediate that re-reads the immediate into the wrong operand.

## 9. Headless proof harness (show the compatible window without a display)
`tools/dos_shim_proof.c` assembles a real 8086 `.COM`, routes it through the
ACTUAL WuBuOS stack (`wubu_exec_dos` -> `wubu_dos_proc` -> `wubu_dos_emu`),
captures the RGBA frame (`wubu_dos_proc_frame_capture`), and `tools/make_png.py`
exports it to PNG via PIL. Build:
```bash
make runtime
gcc -O2 -std=c11 -D_POSIX_C_SOURCE=200809L -D_DEFAULT_SOURCE -Isrc/runtime \
  src/runtime/wubu_dos_emu.c src/runtime/wubu_dos_proc.c \
  src/runtime/wubu_exec_dos.c tools/dos_shim_proof.c -o /tmp/dos_shim_proof
/tmp/dos_shim_proof
python3 tools/make_png.py /tmp/dos_shim_proof.rgba /tmp/dos_shim_proof.png
```
Verified: captured frame is `640x400 (1024000 bytes)`; pixel check shows distinct
colors (blue bg `0x1F` attr, yellow/white glyphs), NOT a blank screen. The run
also mounts `/proc/<pid>/dos` (status/screen/ctl) — the real Styx surface.

## 10. Link-wiring + pollution boundary
- `wubu_dos_proc.c` + `wubu_exec_dos.c` call `wubu_dos_emu_*` — every recipe that
  compiles them needs `wubu_dos_emu.o` (or `.c`). **.o + .c double-link trap:**
  a recipe must NOT list both `wubu_dos_emu.o` and `wubu_dos_emu.c` (duplicate
  symbols). `test_dos_emu` & `test_dos_proc` link `wubu_dos_emu.c` directly.
  See `wubuos-build-recovery` "ADDING A NEW RUNTIME MODULE" for the sweep.
- **Pollution deleted (do NOT reintroduce):** `wubu_freedoom_dos.{c,h}`,
  `tools/build_freedoom_img.py`, `tools/mk_freedoom_disk.sh`, `tools/rescue*.asm`,
  `tools/mkfat12.py`, `tools/build_rescue_disk.py`, `vendor/freedos/*`,
  `src/runtime/wubu_rescue_test.c`, and the `boot.S` rescue chainload
  (`check_emergency`/`do_rescue`/`RESCUE_LBA`). WuBuOS BOOTS WuBuOS — a 16-bit DOS
  app runs IN-PROCESS as a compat shim, never as a booted guest OS. Re-adding a
  DOS-boot path regresses to pollution.
