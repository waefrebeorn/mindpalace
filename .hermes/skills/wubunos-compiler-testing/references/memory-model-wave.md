# MIR memory-model wave (2026-08-23) — ALLOC/LOAD/STORE via hostcall bridges

Commit `29886fe`, 171/171 green. Pattern for adding a new MIR op family to every
interpreted backend at once, plus the five backend-specific traps found.

## The uniform pattern

MIR memory model: addresses are CONST vrs holding small cell indices
(`wubu_mir_alloc` returns `const vr = total_mem+1`); cells are int64 in the
canonical interpreter's flat `mem[]`. On slot-machine backends, LOAD/STORE go
through each backend's existing hostcall escape — no new opcode space needed:

- 6502: opcode 0x02, fns 25=MEM_LOAD / 26=MEM_STORE (4 bytes: fn,dst,sa,sb)
- z80: 0x0B, same fn numbers (16-bit slot addrs)
- 8051/avr/pic: new EXT/MEMOP opcode 0x23 (fn, cell_slot, s2)
- riscv/mips (OS runtime interps): fns 25/26 in existing hostcall switch
- m68k: extend the 0x0B00 escape with fns 25/26
- 8086: dos_emu had NO escape → decode undefined opcode 0xF1 as WUBU_HOSTCALL

8-bit targets are byte-machines: LOAD returns the low byte of the int64 cell,
STORE writes the low byte. Document this in-code; differential tests must use
byte-range values. Compiler emits `emit_fhostcall(fn, dst_slot, addr_slot, …)` —
operands come from ZP/slots at RUNTIME (no const-imm lookup needed).

## The five traps (each cost a debug cycle)

1. **dst==0 write-back clobber (6502):** the generic hostcall epilogue writes
   the 4-byte result to `mem[dst+0..3]`. MEM_STORE passes dst=0 → it zeroed
   mem[0..3], wiping the cell-index slot mid-program → LOAD read 0. Fix:
   guard `if (dst != 0)` around every hostcall write-back.
2. **Slot-width mismatch (z80 SIGBUS):** interp read a 16-bit LE cell index
   from the slot pair, but CONST only stores ONE byte there → garbage high byte
   → `cell*8` far out of bounds. Match the read width to what CONST actually
   writes (1 byte on z80).
3. **VR_BASE offset (pic):** some interps index slots as `ram[VR_BASE+vr]`
   (MVF adds the base itself), others take raw indices. MEMOP must match its
   own backend's convention — pic needed `ram[PIC_VR_BASE + slot]`.
4. **Endianness lane (m68k):** big-endian 4-byte slots — STORE must read the
   value from `mem[va+3]` (LSB lane), not `mem[va]` (MSB = always 0).
5. **Segmented memory (8086/dos_emu):** raw `e->mem[bp+off]` is WRONG — real
   addressing is `phys(e, e->ss, bp+off)` (seg<<4 + off). Symptom: RD16 of a
   slot the program definitely wrote returns 0.

## Debug method that worked

Standalone 6-file link per backend (mir.c + softfloat.c + tgemm.c +
isa_<target>.c + <target>_interp.c + tiny main that dumps code bytes + runs).
Decode the emitted byte stream by hand against the interp's fetch order before
touching the interp — 4 of 5 bugs were visible in the hex dump or in the
interp's operand conventions, not in logic. For dos_emu, fprintf tracing inside
a copied decode .c isolated the segmented-memory bug in one run.

## Test

`test_isa_driver.c::test_memory`: alloc(4), const 77, store, load, ret.
Differential across all drivers — any backend whose slot model disagrees with
canonical mem[] semantics fails loudly here.
