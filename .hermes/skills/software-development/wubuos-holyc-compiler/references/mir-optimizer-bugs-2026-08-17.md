# MIR Optimizer Bugs — 3 Root Causes, 4 Failing Tests (2026-08-17)

## Summary

Three bugs in `wubu_mir_opt.c` caused 4 semantic tests to fail across 12
interpreter targets (48 total failures in the gauntlet). Each bug is a
single-line or single-section fix.

## Bug 1: MIR_JNZ destroyed by DCE

**File:** `wubu_mir_opt.c` — `fold_dce_pass()` and `dce_pass()`

**Root cause:** The DCE elimination loop excluded `MIR_JZ` but forgot
`MIR_JNZ`. Since `MIR_JNZ` has `dst=0` (unused — it uses `a` for the
condition and `label` for the target), and `used[0]` is typically 0,
DCE converted `jnz` instructions into `const v0 = 0`, silently destroying
all `!=`-based conditional jumps.

**Affected:** `ctrl_or_short` (`1 || (x=1)` — the `!=` in `||` codegen
became a no-op const, so the short-circuit fell through and `x=1`
executed).

**Fix:** Added `MIR_JNZ` to the DCE exclusion list in both passes.

```c
// Before (bug):
if (in->op == MIR_LABEL || in->op == MIR_JMP ||
    in->op == MIR_JZ || in->op == MIR_RET ||
    in->op == MIR_CONST || in->op == MIR_ALLOC ||
    in->op == MIR_LOAD || in->op == MIR_STORE) continue;

// After (fix):
if (in->op == MIR_LABEL || in->op == MIR_JMP ||
    in->op == MIR_JZ || in->op == MIR_JNZ || in->op == MIR_RET ||
    in->op == MIR_CONST || in->op == MIR_ALLOC ||
    in->op == MIR_LOAD || in->op == MIR_STORE) continue;
```

## Bug 2: SSA PHI doesn't rewrite inner PHI references

**File:** `wubu_mir_opt.c` — `ssa_pass()`

**Root cause:** When the SSA pass transforms nested ternary/if patterns,
it creates inner PHI nodes first (at the inner merge label), then outer
PHI nodes (at the outer merge label). The outer PHI's `then_val` or
`else_val` may reference the inner PHI's `merge_vr`. The SSA rewrite step
(`if (instr.a == plans[pi].merge_vr)`) only applies to **copied old
instructions**, NOT to **newly inserted PHI instructions**. So the
outer PHI `φ(v65537, v15)` should become `φ(v19, v15)` (where v19 is
the inner PHI dst), but it never gets rewritten.

**Affected:** `stress_ternary_chain` (`1?2?3:4:5`), `stress_if_chain`
(`1? (0?1:2) : 3`).

**Fix:** Added a rewrite loop in the PHI insertion code that scans all
earlier plans (inner plans always have smaller merge_label_idx) and
substitutes any reference to an inner `merge_vr` with its `phi_dst`.

```c
/* Rewrite inner PHI references */
for (size_t pi2 = 0; pi2 < pi; pi2++) {
    if (phi.a == plans[pi2].merge_vr) phi.a = plans[pi2].phi_dst;
    if (phi.b == plans[pi2].merge_vr) phi.b = plans[pi2].phi_dst;
}
```

## Bug 3: DCE kills instructions only used as LOAD addresses

**File:** `wubu_mir_opt.c` — `fold_dce_pass()` and `dce_pass()`

**Root cause:** The DCE used-marking loop did:
```c
if (in->op == MIR_STORE) { /* mark a and b */ continue; }
if (in->op == MIR_ALLOC || in->op == MIR_LOAD) continue;
```
`MIR_LOAD` was skipped entirely — its address operand (`in->a`) was NOT
marked as used. So if an instruction like `add addr = base, idx` was only
used as a LOAD address (in `load result = mem[addr]`), it was eliminated
by DCE → replaced with `const addr = 0`.

**Affected:** `mem_ptr_arithmetic` (`p[2]` — the address computation
`base + idx` was killed, so `load mem[0]` returned 0 instead of 30).

**Fix:** Split `MIR_LOAD` from `MIR_ALLOC` — mark `in->a` (the address)
as used before continuing.

```c
// Before (bug):
if (in->op == MIR_ALLOC || in->op == MIR_LOAD) continue;

// After (fix):
if (in->op == MIR_LOAD) { if (in->a < nvr) used[in->a] = 1; continue; }
if (in->op == MIR_ALLOC) continue;
```

## Debug workflow

The debug workflow that found all three bugs:

1. Built a standalone debug binary that constructs MIR + runs
   `wubu_mir_optimize` + `wubu_mir_interp`, dumping the MIR at each
   optimize pass stage.
2. Compared the BEFORE-OPT and FINAL MIR for each failing test.
3. Found:
   - `ctrl_or_short`: `jnz` → `const v0 = 0` (Bug 1)
   - `mem_ptr_arithmetic`: `add addr` → `const 0` (Bug 3)
   - `stress_ternary_chain`: `phi v20 = φ(v65537, v15)` — v65537 not
     rewritten to v19 (Bug 2)

## Test results

After all 3 fixes:
- Gauntlet: 157/157 pass on all 14 targets (was 109/157 on 12 targets)
- holyc self-tests: 84/84 pass
- ISA driver tests: 72/72 pass
