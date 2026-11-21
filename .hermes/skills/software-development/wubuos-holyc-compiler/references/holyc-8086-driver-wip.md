# 8086 driver — WIP state + diagnosis (2026-08-04, prestige handoff)

## Status (verified at handoff)
- `src/compiler/wubu_isa_8086.c` EXISTS, compiles, links into
  `make test_drivers`, and RUNS through the repo's in-process DOS
  emulator (src/runtime/wubu_dos_emu.c — 22/22 tested standalone).
- Battery: **2/33 pass on the 8086 driver** (x86-64 and m68k both
  33/33). The 8086 driver is NOT yet correct — it is a diagnosed WIP.
- `1+2` → 206 (0xCE), `7*6` → 5601, `-5+10` → 5 (passes), `1||0` → 1
  (passes). Passing = simple non-branching, no memory-heavy paths.
- NOT committed (only the driver-space files that predate it are in git
  history). Commit as WIP with this file as the diagnosis.

## The verified encoding table (objdump -m i8086)
- MOV ax,imm16 = B8 iw ; MOV bx,imm16 = BB iw
- MOV ax,[bp+d16] = 8B 46 d16 (mod=10 rm=110 reg=000)
- MOV [bp+d16],ax = 89 46 d16
- MOV bx,[bp+d16] = 8B 5E d16
- MOV ax,bx = 89 D8 ; MOV bp,sp = 89 E5 ; MOV sp,bp = 89 EC
- ADD ax,bx = 01 D8 ; SUB = 29 D8 ; AND = 21 D8 ; OR = 09 D8 ; XOR = 31 D8
- MUL bx = F7 E3 (unsigned, DX:AX=AX*BX) ; IMUL = F7 EB
- DIV bx = F7 F3 (unsigned, needs xor dx,dx = 31 D2 FIRST) ; IDIV = F7 FB
- NEG ax = F7 D8 ; NOT ax = F7 D0 ; CMP ax,bx = 39 D8
- PUSH bp = 55 ; POP bp = 5D ; RET = C3 ; INT 20h = CD 20
- 8086 conditional jumps are **rel8 ONLY**: JZ=74 JNZ=75 JG=7F JGE=7D
  JL=7C JLE=7E (rel16 form 0F 84 is 386+, NOT valid on 8086)
- JMP rel16 = E9 iw ; JMP rel8 = EB cb

## Diagnosed bug (hypothesis — UNVERIFIED, re-run before trusting)
`1+2` = 0xCE = 206. The likely culprit: **the RET-terminated program
returns to garbage**. The DOS emu's COM convention: program loads at
CS:0x100, SP/stack is set by the emulator, and a .COM must terminate
with `INT 20h` (CD 20) — NOT `ret` (C3). Our driver's MIR_RET emits
`mov sp,bp; pop bp; ret` — the `ret` pops a garbage return address from
the PSP/stack area and jumps into zeroed memory → AX ends up as whatever
the emulator last executed. Fix candidates (try in order):
1. MIR_RET should emit: load result into AX, then `INT 20h` (CD 20) —
   the emulator handles vec 0x20 → TERMINATED (per the 8086-dos-emu
   skill: "int 20h must terminate"). Read AX after run.
2. If the emu doesn't preserve AX through termination, emit the result
   to a known memory cell (e.g. ds:0x400) and peek16 it after run
   (wubu_dos_emu_peek16(e, seg, off)).
3. Check the prologue: `push bp; mov bp,sp; sub sp,N` — the emu's SP at
   COM entry points at the PSP; sub sp may underflow if N too big
   (16-bit SP wraps!). Frame must be small (< 32KB) and the stack
   region valid. Slot disp is (vr+1)*2 NEGATIVE below bp — verified
   pattern from m68k, but confirm the emu's memory map.
4. `-7%3` → 7: DIV is UNSIGNED — need IDIV (F7 FB) for signed, and
   `-2*-3` → 2: MUL unsigned too. The driver currently emits unsigned
   MUL/DIV; the battery has negative operands. Either emit IMUL/IDIV
   (F7 EB/F7 FB) or sign-extend through the type-set ladder.
5. `100/7` → 100: DX wasn't zeroed (xor dx,dx = 31 D2 must precede
   DIV) — partially added; verify placement.

## The emu API (reused, not re-downloaded — the repo already had it)
```c
void *wubu_dos_emu_create(void);
int wubu_dos_emu_load_com(void *e, const uint8_t *data, size_t size);
int wubu_dos_emu_run(void *e, uint64_t max_steps);  /* bounded! */
void wubu_dos_emu_regs(const void *e, uint16_t *ax, uint16_t *bx, ...);
uint16_t wubu_dos_emu_peek16(const void *e, uint16_t seg, uint16_t off);
void wubu_dos_emu_destroy(void *e);
```
Link the SIX emu files (wubu_dos_emu.c, _alu.c, _decode.c, _int.c,
_mem.c, _regs.c) — do NOT also link .o files (duplicate defs).

## What was learned (the methodology that stays)
- **Check the repo's existing interpreters BEFORE downloading or
  writing new ones** — the 8086 emulator (wubu_dos_emu.c, 22/22 tests)
  was already in src/runtime. The user corrected this hard: "check our
  skill sets, you were re-downloading things we already have."
- No QEMU needed for the driver space: each driver carries its own
  interpreter (m68k interp, dos emu) — the bundled interpreter IS the
  verification oracle, plus tools/verify_isa.sh against GNU objdump.
- The multiarch objdump at ~/opt/binutils-multiarch covers: riscv,
  aarch64, arm, mips, powerpc, sparc, s390, loongarch, i386, m68k —
  the free encoder oracle for every new driver.
- User doctrine: NO temporary directories for tools; everything lives
  in the repo (tools/) or ~/opt/. Check skills first.
