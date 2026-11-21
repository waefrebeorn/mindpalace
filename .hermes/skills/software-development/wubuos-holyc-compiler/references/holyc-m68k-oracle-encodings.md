# m68k oracle-verified encodings + the driver-space methodology (2026-08-04)

Source of truth: `tools/verify_isa.sh` in wubuos — packs hex words and
disassembles them with GNU binutils objdump (m68k:68000). The rule:
**no guessed opcodes**. The oracle caught a wrong MOVE layout in
minutes that hand-derived "folk" encodings would have shipped.

## The oracle tool

```bash
# permanent, in-repo: ~/wubuos/tools/verify_isa.sh
tools/verify_isa.sh m68k 4e56 ffb0 203c 0000 0001 4e75
# -> linkw %fp,#-80 / movel #1,%d0 / rts
```

It finds the multiarch objdump at (in order): `$WUBU_BINUTILS`,
`~/opt/binutils-multiarch/usr/bin`, `/opt/...`, `/tmp/bmu/...`.
Extract without root:
```bash
cd /tmp && apt-get download binutils-multiarch \
  && dpkg -x binutils-multiarch_*.deb ~/opt/binutils-multiarch
```

## VERIFIED MOVE format (the hard-won bit)

`0x2000` = `movel %d0,%d0` — the folk pattern `0x2000|n<<9|m<<3|4` is
WRONG on three fields. The real word:

```
00 ssss ddd mmm eee gg 0
  15-14 = 00
  13-12 = size  (01=B, 10=L, 11=W)
  11-9  = DEST register
  8-6   = DEST mode
  5-3   = SRC mode
  2-0   = SRC reg
Modes: 000=Dn 001=An 010=(An) 011=(An)+ 100=-(An) 101=(d16,An) 111=imm
```

`MOVE.L Dn,Dm = 0x2000 | (m<<9) | n`.

## Verified table (driver subset)

| instr | encoding | objdump says |
|---|---|---|
| MOVE.L Dn,Dm | 0x2000\|(m<<9)\|n | movel %d1,%d0 |
| MOVE.L #imm32,Dm | 0x203C\|(m<<9) + imm32 | movel #5,%d0 |
| MOVE.L Dn,(d16,A6) | 0x2D40\|n + d16 | movel %d0,%fp@(-4) |
| MOVE.L (d16,A6),Dm | 0x202E\|(m<<9) + d16 | movel %fp@(-4),%d0 |
| ADD.L Dn,Dm | 0xD080\|(m<<9)\|n | addl %d1,%d0 |
| SUB.L Dn,Dm | 0x9080\|(m<<9)\|n | subl %d1,%d0 |
| AND.L Dn,Dm | 0xC080\|(m<<9)\|n | andl %d1,%d0 |
| OR.L Dn,Dm | 0x8080\|(m<<9)\|n | orl %d1,%d0 |
| CMP.L Dn,Dm | 0xB080\|(m<<9)\|n | cmpl %d1,%d0 |
| EOR.L Dn,Dm | 0xB180\|(n<<9)\|m | eorl %d1,%d1 |
| MULS.W Dn,Dm | 0xC1C0\|(m<<9)\|n | mulsw %d1,%d0 |
| DIVS.W Dn,Dm | 0x81C0\|(m<<9)\|n | divsw %d1,%d0 |
| NEG.L Dn | 0x4480\|n | negl %d1 |
| NOT.L Dn | 0x4680\|n | notl %d1 |
| TST.L Dn | 0x4A80\|n | tstl %d1 |
| MOVEQ #imm8,Dn | 0x7000\|(n<<9)\|imm | moveq #1,%d0 |
| SUBQ.L #1,Dn | 0x5380\|n | subql #1,%d1 |
| LSL.L #1,D0 | 0xE388 | lsll #1,%d0 |
| LSR.L #1,D0 | 0xE288 | lsrl #1,%d0 |
| LINK A6,#-N | 0x4E56 + s16 | linkw %fp,#-80 |
| UNLK A6 | 0x4E5E | unlk %fp |
| RTS | 0x4E75 | rts |
| BRA.s | 0x6000\|d | bras |
| BEQ/BNE/BGT/BGE/BLT/BLE.s | 0x6700/0x6600/0x6E00/0x6C00/0x6D00/0x6F00\|d | beqs… |

Notes:
- ALU size lives in bits 7-6 (10=long); the src Dn mode is bits 5-3,
  src reg 2-0, DEST reg 11-9.
- EOR is `EOR Dn,<ea>` — operand order REVERSED (src at 11-9).
- MULS/DIVS are .W (16-bit signed) on the 68000; DIVS leaves the
  remainder in D1 (the driver copies it to D0 for MIR_MOD).

## Frame strategy (the SIGSEGV class)

`LINK A6,#-N` allocates N bytes BELOW A6. Slots MUST be negative
displacements: `(A6 - (vr+1)*4)`. Positive offsets point ABOVE the
frame into the caller's stack → crash on return. The x86-64 driver had
the identical bug: slots at `[rbp+off]` instead of `[rbp-off]` →
SIGSEGV at `leave; ret`. **A frame pointer means NEGATIVE offsets,
always.** Result in D0 on RTS.

## The battery catches what the oracle can't

The oracle verifies each opcode in isolation; `make test_drivers` (the
33-expression differential battery, x86-64 JIT + m68k interp, expected
values from gcc) verifies whole programs. Two real bugs it caught:
1. `5^3`=0 on BOTH drivers → `bitxor_ops[]` used `HC_AST_XOR`, a name
   that does NOT exist in the enum (`HC_AST_BITXOR` is correct). C
   enum misspelling = silent wrong constant, not a compile error.
2. `1<2`=0 on m68k only → SUB/CMP flag math reused the ADD overflow
   formula with `~a+1`, computing V=1 for 1−2 (NO overflow) → LT broke.
   Subtraction's V = `(dst^src) & (dst^res) & 0x80000000`.

## Where this lives

- wubuos: `src/compiler/wubu_isa_m68k.c` (encoder),
  `wubu_m68k_interp.c` (interpreter), `tools/mir_driver_test.c`
  (battery), `tools/verify_isa.sh` (oracle), `make test_drivers`.
- corpus: `wubuwizard/research/M68K_DRIVER_7HOP.md` (AN14),
  `ISA_7HOP.md` (AN13).
