# x86-64 JIT stress_fib investigation (2026-08-30 — RESOLVED)

## Test definition
- **Source**: `test_gauntlet/wubu_test_gauntlet.c:217`
- **Expression**: `{int a=0; int b=1; for(int i=0;i<10;i++) {int t=a+b; a=b; b=t;} a}`
- **Expected**: 55

## Root cause: flat VR model register clobbering across function calls

The x86-64 JIT uses a **flat register model** where the linear-scan allocator assigns
VRs to physical registers globally across ALL functions. When function A calls function B,
B's register allocation may assign the same physical registers as A's live VRs. Since there
is no save/restore at call boundaries, A's registers get clobbered.

For `stress_fib`, the global variable addresses (VRs holding constants like `&a=1`, `&b=2`,
`&i=3`) were assigned to registers `r11`, `r12`, `r13`. When the loop body executed LOAD/STORE
operations, it used those same registers as scratch, overwriting the address constants.

## The fix: save/restore all allocator registers around CALL

In `wubu_isa_x86_64.c`, the MIR_CALL case now pushes all 9 allocator registers before
the call and pops them after:

```c
case MIR_CALL: {
    static const int all_regs[] = {10, 11, 12, 13, 14, 15, 8, 9, 2};
    for (int s = 0; s < 9; s++) {
        int reg = all_regs[s];
        if (reg >= 8) { e8(&e, 0x41); e8(&e, 0x50 + (reg & 7)); }
        else { e8(&e, 0x50 + reg); }
    }
    e8(&e, 0xE8);  // call rel32
    // ... patch logic ...
    for (int s = 8; s >= 0; s--) {  // REVERSE order (LIFO)
        int reg = all_regs[s];
        if (reg >= 8) { e8(&e, 0x41); e8(&e, 0x58 + (reg & 7)); }
        else { e8(&e, 0x58 + reg); }
    }
    break;
}
```

Frame size increased by 72 bytes (`+ 72` in `e.frame` calculation) to accommodate
the 9 register saves.

**CRITICAL**: Pop in REVERSE order of push (LIFO). The `call` instruction pushes
a return address between our pushes and the callee's stack frame. After the callee
returns (popping the return address), rsp points to our last push. So pop order
must be reverse of push order.

## Why NOT per-function register allocation?

A proper fix would be per-function register allocation with calling conventions
(save/restore only caller-saved registers at call boundaries). This is a large
architectural change. The save-all-registers approach is conservative but correct
— it always works, just with slightly more stack traffic.

## Cross-function VR spill approach (ATTEMPTED, DID NOT WORK)

An alternative approach was attempted: detect VRs defined in the entry point and
used in functions, then force-spill them to stack slots. This failed because:

1. Each function has its own stack frame (own `rbp`), so spill slots are relative
   to the current function's frame, not a shared location.
2. The entry point stores VR values at `[entry_rbp - offset]`, but functions try
   to load from `[func_rbp - offset]` — different memory locations.

This approach would require a shared spill area (e.g., in `prog->mem`), which is
a bigger architectural change than just saving/restoring registers.

## Earlier fixed bugs (prerequisites for this fix)

| Fix | File | Commit | Result |
|-----|------|--------|--------|
| Remove `rbx` from `reg_x86[]` pool | `wubu_isa_x86_64.c` | `ce74442` | Eliminated segfault |
| Pre-assigned VR reservation (v0/args) | `wubu_mir_regalloc.c` | `fb9bc36` | VR 0/1 no longer share `r10` |
| 32-bit truncation via `movsxd rax,eax` | `wubu_isa_x86_64.c` | `f298900` | `stress_signed_overflow` fixed |
| Disable peephole optimizer | `wubu_isa_x86_64.c` | `fb9bc36` | 185 errors eliminated |
| VR0 skipped in linear scan | `wubu_mir_regalloc.c` | `15826a8` | VR0 always in r10 |
| Save/restore all regs around CALL | `wubu_isa_x86_64.c` | `606eece` | **stress_fib FIXED** |

## Scorecard after fix

- **Gauntlet --core x86-64**: 247/247 PASS (stress_fib now returns 55)
- **Global variables across function calls**: WORK on both interpreter and JIT
- **Core gauntlet**: 247/247 PASS
- **MIR battery**: 69/69 PASS

## Key invariants
- `wubu_mir_alloc_regs(prog, N, …)` count must match `reg_x86[]` array length.
- `rbx` is reserved by the prologue as the memory-base pointer; never include it in
  the allocator pool.
- Save ALL 9 allocator registers around CALL, pop in reverse order.
- Frame size must include `+ 72` for the register save area.
