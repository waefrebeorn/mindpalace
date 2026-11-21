# Wave 3b/4 — MIR_CALL on 9 backends + x86-64 native SSE floats
(2026-08-24, commits 29886fe → e3fd01d; supersedes the "no MIR_CALL blocker" section of SKILL.md)

## The CALL convention (now real, not a gap)
One pattern across retro backends:
1. Compiler emits an **entry trampoline** (JMP over callee bodies) so top-level code starts after all functions.
2. Func start code-offsets are recorded during emission (`i == funcs[f].start`).
3. Absolute targets patched in a second pass before label patches.
4. Interp hostcall fns **27 = CALL** (push return pc, jump), **28 = FUNC_RET** (write vr0 slot, pop; halt if sp==0).

Per-backend quirks that each cost a debug cycle:
- **6502**: hostcall dst=0 must skip write-back (else zeroes the cell slot).
- **z80**: vr0 slot is address 0 (vr*2 layout); CONST stores 1 byte/slot.
- **8051**: LJMP target is BIG-ENDIAN → use EXT_JMP 0x26 / EXT_CALL 0x24 with BE abs16.
- **avr/pic**: MEMOP-style subop opcodes; PIC FUNC_RET must read result via `PIC_VR_BASE+slot`.
- **m68k**: trampoline must come AFTER the global LINK prologue (A6 frame shared); FUNC_RET writes vr0 at disp −4 (slot_disp(0)), LSB lane; JMP $abs needed a real interp handler.
- **8086/dos_emu**: escape opcode 0xF1; slots SS-relative via `phys(e, ss, off)`; targets BE abs16.
- **riscv**: JAL offsets are PC-RELATIVE (encode `entry_off − jmp_pos`); FUNC_RET must also write vr0's frame slot because main's RET reloads a0 from it; hostcall slot offsets must be sign-extended `(int32_t)`.
- **mips**: word-addressed func offsets (matches label convention); abs24 BE target byte.

## THE big interpreter bug: riscv x0 hardwired-zero
The riscv interp's JAL handler did `cpu.x[rd] = cpu.pc` unconditionally. The entry
trampoline is `JAL x0, …` → **x0 became 16**, breaking the hardwired-zero invariant.
Symptom: every `addi x5,x0,imm` computed `16+imm` (37→53, 5→21, 42→74). Fix:
guard `if (rd != 0)` AND enforce `cpu.x[0] = 0` at the top of every fetch loop.
Lesson: any new jump/trampoline feature can violate x0; enforce the invariant per-loop,
not per-handler.

## x86-64 native SSE floats (FADD/FSUB/FMUL/FDIV/FRET)
Values are f32 BITS in the normal int pipeline. Emission via GPR staging:
```
movd xmm0, eax   66 0F 6E C0
movd xmm1, edi   66 0F 6E CF
opss xmm0, xmm1  F3 0F 58|5C|59|5E C1   ← F3 = single-precision; F2 would be ADDSD (double)!
movd eax, xmm0   66 0F 7E C0
```
FRET aliases RET (bits in rax). Verified: 1.5+2.25=3.75, 10.5−4.25=6.25, 6×7=42, 100/8=12.5.

## Root cause of the x86-64 frame corruption: regalloc `op_has_dst()` gaps
`op_has_dst()` in `wubu_mir_regalloc.c` omitted ALL float ops → FADD's dst never got a
live interval → `reg=-1, stack=0` → emitter stored to `[rbp+0x0]` = saved RBP →
`leave/ret` jumped into the void. Symptom looked like a bad SSE encoding but the
disassembly showed `addss` fine with the store clobbering rbp. Fix: added
MIR_FADD/FSUB/FMUL/FDIV/FNEG/FEQ/FNE/FLT/FLE to op_has_dst. Also: unimplemented ops in
the x86-64 switch now `return -1` instead of falling through default:break (garbage bytes).

## Debugging technique that cracked both bugs
Dump the emitted machine code to a file and disassemble:
```sh
objdump -D -b binary -m i386:x86-64 -M intel /tmp/float_code.bin
```
Reading the actual bytes beats tracing interpreters blind — both the F2/F3 mistake and
the `[rbp+0]` store were obvious in the disassembly. For per-pc interpreter traces,
insert fprintf BEFORE the main decode branch you suspect (prints placed after an
earlier `if (opcode == X)` branch never fire for that opcode).

## Standalone-build status of the real x86-64 driver
Linking the REAL `wubu_isa_x86_64.c` into standalone test_isa_driver works for simple
programs ("42 OK") but segfaults on multi-spill programs: WUBU-ABI-v1 frame setup
corrupts x86_run's stack (needs prologue audit in OS repo before enabling; Makefile
reverted to jit_stubs.c + documented). For float verification use the minimal harness
pattern: link only wubu_isa_x86_64.c + jit_stub.c + jit_stub_x86.c (clear_cache shim)
+ mir/regalloc/peephole files, call the driver struct directly via `extern`.

## Scorecard after this wave
179/179 ISA driver tests; T_GEMM 576/576; selfhost 155; gauntlet clean.
CALL verified on: 6502 z80 8051 avr pic m68k 8086 riscv mips. arm64/amdgpu still open.
