# wubu_mir_interp dispatch table was positional and silently wrong (2026-09-30)

The single highest-impact bug found in this project so far.

## The bug

`wubu_mir_interp`'s computed-goto `labels[]` table was written **positionally**
and had fallen **5 entries behind** the `wubu_mir_op_t` enum: it omitted
`MIR_TO_PTR` and the four integer-extend ops (`MIR_SEXT32/16/8`, `MIR_ZEXT32`).
Every opcode from **39 upward** dispatched to the wrong handler.

Loudest symptom: `MIR_SEXT32` (47) executed `op_fne`, so `127 + 1` evaluated
`128 != 128` → **1**.

## Why it hid so well

Every interpreted backend funnels through `wubu_mir_interp` (see
`hd_run_prog`: `if (driver->exec == WUBU_ISA_INTERPRETED) return
wubu_mir_interp(prog)`). So one table bug made **13 of 14 gauntlet targets**
fail identically — an identical **79/247** on 8086, m68k, 6502, riscv, z80,
arm64, mips, 8051, avr, pic, amdgpu and wasm. x86-64 (native JIT) was the only
one at 247/247.

**Identical scores across many "independent" backends is the tell.** It reads
like fourteen separate backends failing the same tests; it was one shared
table. When per-target results are suspiciously uniform, look for a shared
code path before blaming the backends.

## The fix

Rewrote the table with **designated initializers keyed by the enum constant**,
sized from the highest opcode:

    enum { MIR_LABEL_SLOTS = 105 };
    static void *labels[MIR_LABEL_SLOTS] = {
        [MIR_CONST] = &&op_const, /* 1 */
        ...
    };

A dropped or reordered opcode is now a compile error, not a silent
miscompile.

## Result

    gauntlet --core   before  pass=1247 fail=2211 error=0
                     after   pass=3263 fail=195  error=0

13 of 14 targets went 79/247 → **247/247**. Only `ptx` remains (52/247).

## How to audit any dispatch table like this

1. Count entries in the table. Count enum constants. If they differ, the table
   is wrong — a positional table cannot be trusted without a count check.
2. Compare by NAME, not position. The `/* NN MIR_NAME */` comments in the old
   table were themselves already wrong (it labelled `7 MIR_AND` after
   `8 MIR_UDIV`), so only the enum header is trustworthy.
3. Prefer designated initializers by enum name everywhere.

## Related

- `test_gauntlet` had never linked (see `make-test-triage.md`), so this bug was
  invisible: every quoted gauntlet number came from an older binary.
- gdb line breakpoints in `wubu_mir_interp.c` are unreliable in this build —
  `break wubu_mir_interp.c:277` (op_sext32) never fired even though the op
  definitely executed. Break on the **function** plus a condition
  (`break wubu_mir_interp if p->n == 9`) instead. Avoid `while` loops in gdb
  batch commands; they hang.