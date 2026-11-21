# x87 / SSE encoding lookup tables

Distilled from the SDM + the bugs that paid for them. Use when
implementing or auditing an instruction, or writing a test encoding.

## fxam class table (C3 C2 C0; C1 = sign bit)
| class       | C3 | C2 | C0 |
|-------------|----|----|----|
| unsupported | 0  | 0  | 0  |
| NaN         | 0  | 0  | 1  |
| normal finite | 0 | 1 | sign |
| infinity    | 0  | 1  | 1  |
| zero        | 1  | 0  | sign |
| empty       | 1  | 0  | 1  |
| denormal    | 1  | 1  | sign |

Normal is **010**, not 110 (110 is denormal). glibc __printf_fp
classifies with fxam; marking normal as denormal/zero prints 0.

## cvt / scalar operand order (ModRM.reg vs ModRM.rm)
| opcode | insn | reg field | rm field |
|--------|------|-----------|----------|
| 0F 2A (F2/F3) | cvtsi2sd/ss | XMM dest (REX.R) | GPR src (REX.B) |
| 0F 2C/2D (F2/F3) | cvt(t)sd2si | **GPR dest (REX.R)** | **XMM src (REX.B)** |
| 0F 5A (F2/F3) | cvtsd2ss/cvtss2sd | XMM dest | XMM src (distinct!) |
| 0F 58/59/5C/5E/5D/5F | add/mul/sub/div/min/max sd/ss | XMM dest | XMM/mem src |
| 0F 2E/2F | (u)comisd/ss | XMM src1 | XMM/mem src2 -> EFLAGS |

2C/2D is the trap: reg is the GPR, rm is the XMM — opposite of the
arithmetic ops. min/max return SRC (rm) when either operand is NaN.

## 66 0F 73 shift-count group (ModRM.reg digit)
/2 psrlw, /3 psrldq, /4 psraw, /6 psllw, /7 pslldq.
pslldq/psrldq are BYTE shifts; /7 is NOT psllq (psllq = 66 0F F3).
VEX vpslldq/vpsrldq use the same digits (/7, /3), dest in VEX.vvvv.
16-bit operands with masked count >= 16 are SDM-UNDEFINED — gate the
defined range only (no-fault still asserted); hardware quirks there
are not a contract.

## comisd/ucomisd flag results (OF/SF/AF always cleared)
unordered (NaN): ZF=PF=CF=1; less: CF=1; equal: ZF=1; greater: none.

## VEX scalar prefix (pp) and map
- 2-byte VEX C5: pp = byte1 & 3 (0=none/single, 1=66/double, 2=F2/sd,
  3=F3/ss). C5 F8 = single, C5 F9 = double for scalar compares.
- C5/C4 already imply the 0F map — never emit a second 0F after VEX.
- VEX.L=1 is #UD for scalar compares/conversions.
- VEX.128 zeroes the upper xmm/ymm bytes above the scalar result;
  legacy SSE keeps them (merge semantics).

## Memory addressing in 64-bit tests
modrm mod=00 rm=101 (0x05) = RIP-relative (disp32 added to next-rip).
Absolute [addr] requires SIB: modrm 0x04, SIB 0x25 (scale0,index=none,
base=101), then disp32. Getting this wrong silently probes the wrong
address (reads zeros) instead of faulting.

## x87 reset state
fninit: CW=0x037F (all exceptions masked, round-nearest), SW=0, TOP=0.
Rounding modes via CW bits 10-11: 00 nearest-even, 01 down, 10 up,
11 trunc. fistp/cvttsd2si overflow/NaN -> integer indefinite
(0x8000... for the width).
