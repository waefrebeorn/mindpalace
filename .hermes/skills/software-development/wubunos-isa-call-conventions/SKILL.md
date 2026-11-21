---
name: wubunos-isa-call-conventions
description: Use when adding/debugging MIR_CALL in a wubunos ISA backend.
---

# WUBUNOS ISA Call Conventions

Load when adding MIR_CALL/MIR_RET support to a wubunos ISA backend, debugging
a backend's function calls, or porting the differential `test_call` battery to
a new target. Verified working on 9 backends: 6502, z80, 8051, avr, pic,
m68k, 8086, riscv, mips (179/179 gauntlet, commit e540f09).

## The shared architecture

Every interpreted/JITed retro backend uses the same three-part scheme:

1. **Entry trampoline** — if `p->n_funcs > 0`, emit an unconditional jump at
   code offset 0 over the callee bodies to the main-line code. Without this,
   execution starts at the callee and the program returns garbage immediately.
2. **Func-offset recording** — during the main emission loop, when
   `p->funcs[fi].start == i` and not yet recorded, save `e.n` into a
   `func_off[fi]` array (calloc'd to n_funcs, pre-filled with -1).
3. **Second-pass fixups** — after emission, patch every CALL's reserved
   operand bytes with the callee's recorded offset, then patch the trampoline
   target with `entry_off` (the e.n at loop-top of instruction index
   `max_func_end`).

Calls themselves emit a **hostcall**: opcode byte(s) + fn=27 + reserved
target bytes. FUNC_RET emits fn=28; the interp pops its call stack, writes
the result into vr0's slot, and halts if the stack is empty.

Interp side needs: a `call_stack[32]` + `call_sp` on the CPU struct, and
fn-27/fn-28 cases in the hostcall switch.

## Per-backend quirks (each one cost a debugging session)

| Backend | Quirk |
|---------|-------|
| 6502 | Hostcall write-back must skip when dst==0 (MEM_STORE passes dst=0); unconditional write-back zeroed live slots |
| z80 | vr0's slot address is 0 (slots are vr*2), so FUNC_RET writes mem[0], not mem[1] |
| 8051 | Real LJMP opcode is big-endian — don't use it for trampolines; EXT_JMP 0x26 / EXT_CALL 0x24 read BE abs24 |
| avr | Same EXT-style opcodes (AVR_CALL/FUNC_RET/JMP), LE targets, VR_BASE-relative slot reads |
| pic | FUNC_RET must read the result slot via PIC_VR_BASE-relative addressing (raw index reads stale RAM) |
| m68k | Trampoline must be emitted AFTER the global LINK prologue (A6 frame is shared); FUNC_RET writes vr0 via slot_disp(0)=-4, LSB lane of BE word; no halted flag — set pc=size to exit loop |
| 8086 | dos_emu decodes undefined opcode 0xF1 as hostcall; slot displacements are SS-segment relative — use phys(e, ss, bp+off), never raw mem[] indexing |
| riscv | See x0 hazard below; JAL trampoline is PC-relative (rel = entry_off - trampoline_pos); FUNC_RET writes vr0 frame slot at +8; load_d/store_d offsets are int32 sign-extended in interp hostcalls |

## Pitfalls

- **riscv x0 hardwired-zero hazard**: the interpreter's JAL handler wrote
  `cpu.x[rd] = cpu.pc` unconditionally. The entry trampoline's `JAL x0`
  corrupted x0 with the return pc (16), silently turning every
  `addi x5, x0, imm` into `x0+imm`. Symptom: constants read back as
  stored_value+16. Fix: guard `rd != 0` AND enforce `cpu.x[0] = 0` at the
  top of each dispatch loop iteration. Any new riscv-like backend needs both.
- **Trampoline placement**: on targets with a global frame-setup prologue
  (m68k LINK, riscv fp/sp setup), emit the trampoline AFTER the prologue,
  not before — jumping over callees must not skip frame setup.
- **Dead epilogue bytes shift entry_off**: if the in-func RET path emits
  extra unreachable bytes after the hostcall, every later offset (entry
  target, CALL targets) shifts and jumps land mid-instruction. Emit only
  what executes.
- **Endianness**: 8051 LJMP and mips custom jump are big-endian; z80/avr/
  riscv targets are little-endian. Verify by decoding the emitted binary
  against a manual trace before blaming the interp.
- **Word vs byte addressing**: mips records label offsets as `e.n / 4`;
  func offsets and CALL targets must use the same units as the interp's
  jump handler expects.
- **A callee's return value can be correct and still be destroyed by the
  epilogue.** Read `op_ret` in the interpreter before debugging a return
  convention: it restores frame memory wholesale, so anything the callee
  allocated above the globals boundary does not survive. Check where your
  result buffer lives before assuming the ABI is broken.
- **Struct layout in this tree is cell-granular** (`mir_struct_t.total_size`
  counts int64 cells, one cell per member), so `sizeof(struct{int;int})` is 16,
  not C's 8, while `struct{char;int;double}` happens to agree at 16. Do not
  "fix" a `sizeof` probe against the cell model — byte-exact sizes need a
  layout change (byte offsets + padding, then `cells = ceil(bytes/8)`), which
  also governs nested-struct return copies.

## Struct returns vs the call-frame restore (interpreter)

**A struct-return buffer must live BELOW `globals_end`, or the caller reads
zeros.** The interpreter's `op_ret` restores every cell at or above
`globals_end` to its call-time snapshot (that is what makes recursion
reentrant). A struct-return buffer allocated during body emission sits above
that boundary, so the callee's copy is wiped one instruction after `v0`
receives the buffer address — every struct-return expression then evaluates to
exactly `0`, never garbage.

The fix is allocation placement, not the return convention: reserve the arena
(`wubu_mir_alloc` for N slots x M cells) **before** `prog->globals_end` is fixed
at the start of the function loop, and hand out slot addresses from it with
`MIR_ADD(arena_base, slot * M * 8)`. Verified: six struct-return probes flipped
together, battery 106 -> 115.

Symptom to recognise: several probes returning the SAME exact value (`0`) means
one shared mechanism, not several bugs. A value that differs per case means the
convention itself is wrong.

## Debugging recipe

When a call test fails with a wrong constant:
1. Dump the emitted code bytes and decode by hand against the interp's
   decoder (offsets drift between compiler revisions — always decode the
   binary you're actually running).
2. Add per-instruction fprintf traces to the interp's decode loop and the
   hostcall entry (`[pc=%u op=%02X]`, `[HC fn=%u]`).
3. Check the three usual suspects in order: trampoline target lands past
   the prologue? CALL target points at the callee's first byte? FUNC_RET
   writes the result where main's RET will read it?
4. For garbage-constant symptoms specifically, verify the hardwired-zero
   register invariant first.

## References

- `references/per-backend-detail.md` — exact opcode encodings, emitter and
  interp code snippets per backend, and the test_call battery structure.
- `references/x86-64-jit-bug-fixes.md` — hard-won native JIT backend fixes:
  NULL mem base, CALL rel32 off-by-one, ModRM encoding direction, register
  allocator failures for high VR numbers, entry trampoline logic. Load when
  debugging x86-64 JIT crashes or wrong results.
