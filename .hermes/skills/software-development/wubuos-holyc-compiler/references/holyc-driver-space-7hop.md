# Multi-ISA Driver Space — 7-hop Research + Build (2026-08-04)

## The directive

> "continue and make this the best compiler because this is how you're gonna
> unlock all of the hardware performance across all of the hardware you
> need to think about this and how it's going to run on everything by
> expanding it as a driver space"

Translation: one frontend (HolyC → MIR) + N ISA drivers, each verified to
emit bytes that actually execute. The AGI runs on a 68000.

## The 7-hop ISA ladder (wubuwizard research/ISA_7HOP.md)

1. **6502 (1975)** — MOS 6502, $20 CPU, 8-bit. Spun out of the Motorola 6800.
2. **Z80 (1976)** — Zilog, 8080-compatible superset, IX/IY, CP/M/Spectrum.
3. **8086 (1978)** — Intel, 16-bit + segmentation, little-endian. "Quick hack"
   that became x86-64.
4. **68000 (1979)** — Motorola, 16/32-bit, big-endian, flat 24-bit, 8D+8A,
   56 instructions. Mac/Amiga/Atari ST/Genesis.
5. **ARM (1985)** — Acorn RISC, load-store, ARM1→ARM64.
6. **RISC-V (2010)** — Berkeley open RISC, RV64I.
7. **VAX/Itanium/PowerPC (dead)** — Itanium died because the compiler
   wasn't clever enough. LESSON: compiler quality IS the unlock.

## Architecture (wubu_isa_driver.h)

Each ISA is a driver: `{name, exec, compile, run, describe}`. `wubu_isa_find`
maps "x86-64"/"riscv"/"m68k"/"68000" → driver. `exec = NATIVE` (mmap JIT) or
`INTERPRETED` (bundled decoder proves the bytes). The MIR (AST→`wubu_mir_prog_t`)
is the hourglass neck shared by all backends.

## 68000 encoding table (VERIFIED against GNU objdump)

| Instr | Encoding | |
|-------|----------|-|
| LINK A6,#-frame | `4E56` + s16 | linkw %fp |
| UNLK A6 | `4E5E` | unlk %fp |
| RTS | `4E75` | rts |
| MOVE.L Dn,Dm | `2000 nnn mmm 4` | |
| MOVE.L #imm,Dm | `3C00 mmm 4` + imm32 | |
| MOVE.L (d16,A6),Dm | `2C00 6 mmm 4` + d16 | |
| ADD/SUB/AND/OR/EOR/CMP.L | `op nnn mmm 4` | |
| MULS/DIVS.W | `C0C0/C800 n n m` | |
| NEG/NOT/TST.L Dn | `4480/4680/4A80 nnn` | |
| MOVEQ #imm,Dn | `7000 nnn imm8` | |
| SUBQ.L #1,Dn | `5380 nnn nnn` | |
| LSL.L #1,Dn | `E108 nnn 0` | |
| BRA/BEQ/BNE/... .s | `60xx/67xx disp8` | |

Verify: `objdump -D -b binary -m m68k:68000` (binutils-multiarch .deb at
`/home/wubu/wubuos/`, extract with `dpkg -x`).

## Two blocking bugs (same pitfall — see holyc-macro-patch-pitfall.md)

1. `wubu_isa_m68k.c`: `#define PATCH / PATCH_AT / BRA_CC(cc)` reference
   function-local `e, patches, np, cp` and collide with struct-member names
   and a local `uint16_t cc`. → Replace with inline `patch_push(…)` helper.
2. `wubu_isa_x86_64.c`: `PATCH_PUSH` references `.e` on `x86_patch_t`.
   Same macro-in-function-body class.
