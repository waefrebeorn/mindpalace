# Global Variables Across Function Calls — Debug & Fix (2026-08-30)

## Problem
Global variables modified inside a function were not visible to the caller
in the interpreter, and caused SIGSEGV in the JIT.

**Test case:**
```c
int w = 10;
void setw(int v) { w = v; }
int main() { setw(42); return w; }  // expected 42
```

**Symptoms:**
- Interpreter returned 10 (old value) — change to `w` was discarded
- JIT crashed with SIGSEGV (code 253 bytes, valid compile)

## Root Cause Analysis

Five independent bugs combined to cause this:

### Bug 1: Interpreter memory save/restore on CALL/RET
The interpreter's CALL handler saved the entire `mem` array; RET restored it.
This discarded any changes the callee made to globals.

**Fix:** Remove `memcpy(mem, f->mem_save, ...)` from `op_ret` in `wubu_mir_interp.c`.
Only restore the VR file. Globals and locals use disjoint addresses
(`wubu_mir_alloc` assigns unique addresses), so changes persist correctly.

### Bug 2: Global variable address VR collision with argument registers
`wubu_mir_alloc` returned a low VR (instruction index) for variable addresses.
The first global got VR_1, which is ALSO the first argument register (v1..vN).
When a 1-param function accessed the global, the argument overwrote the address.

**Fix in `holyd_mir_eval.c` (VAR_DECL case):**
```c
// OLD (broken):
wubu_vr_t addr = wubu_mir_alloc(g->prog, arr_size > 0 ? arr_size : 1);

// NEW (fixed):
wubu_vr_t addr = mir_new_vr(&g);  // high VR (≥65536)
int64_t mem_addr = (int64_t)(g->prog->total_mem + 1);
g->prog->total_mem = mem_addr + (arr_size > 0 ? arr_size : 1) - 1;
wubu_mir_const_to(g->prog, addr, mem_addr);  // addr VR = actual memory address
```

### Bug 3: Parameter slot_addr VR not initialized
The old parameter allocation created `slot_addr` as a high VR but never
initialized it with the actual memory address. `base` held the VR ID of
`slot_addr`, so `mem[base]` accessed the wrong location.

**Fix in `holyd_mir_eval.c` (FUNC_DECL param binding):**
```c
// OLD (broken):
wubu_vr_t slot_addr = g.next_vr++;
wubu_vr_t base = g.next_vr++;
wubu_mir_const_to(prog, base, (int64_t)slot_addr);
wubu_mir_store(prog, base, (wubu_vr_t)(pi + 1));

// NEW (fixed):
wubu_vr_t addr = mir_new_vr(&g);
int64_t mem_addr = (int64_t)(g.prog->total_mem + 1);
g.prog->total_mem = mem_addr + 1 - 1;
wubu_mir_const_to(g.prog, addr, mem_addr);
wubu_mir_store(g.prog, addr, (wubu_vr_t)(pi + 1));
mir_bind_var(&g, fn->param_names[pi], addr, addr, 0);
```

### Bug 4: Register allocator doesn't extend live ranges across CALLs
Same pattern as loop back-edges: VRs defined before a CALL and used after it
must stay live across the call. Without this, the allocator assigns
caller-saved registers to VRs that must survive function calls.

**Fix in `wubu_mir_regalloc.c` (add Step 1c after Step 1b):**
```c
// For each CALL, find VRs defined before and used after, extend last_use
for (size_t i = 0; i < n_ins; i++) {
    if (p->ins[i].op != MIR_CALL) continue;
    for (size_t v = 0; v < n_vr; v++) {
        if (first_def[v] < 0 || first_def[v] >= (int32_t)i) continue;
        if (last_use[v] > (int32_t)i) {
            last_use[v] = (int32_t)(i + 1) > last_use[v] ? (int32_t)(i + 1) : last_use[v];
        }
    }
}
```

### Bug 5: x86-64 JIT clobbers caller-saved registers across CALL
The JIT's register pool includes caller-saved registers (r10, r11, r8, r9, rdx).
When a CALL is emitted, these are clobbered by the callee.

**Fix in `wubu_isa_x86_64.c` (MIR_CALL case):**
```c
// Save caller-saved registers before CALL
static const int caller_saved[] = {10, 11, 8, 9, 2}; // r10,r11,r8,r9,rdx
for (int s = 0; s < 5; s++) {
    int reg = caller_saved[s];
    if (reg >= 8) { e8(&e, 0x41); e8(&e, 0x50 + (reg & 7)); }
    else { e8(&e, 0x50 + reg); }
}
e8(&e, 0xE8);  // call rel32
// ... patch push ...
e.n += 4;
// Restore (same order as push — stack top is first push after ret)
for (int s = 0; s < 5; s++) {
    int reg = caller_saved[s];
    if (reg >= 8) { e8(&e, 0x41); e8(&e, 0x58 + (reg & 7)); }
    else { e8(&e, 0x58 + reg); }
}
```

**Stack layout rationale:** pushes go BELOW the return address (call pushes it).
After `ret`, rsp points to the first push. Pop in same order as push.

## Verification
```bash
# Build and run the gauntlet
cd /home/wubu/wubunos
rm -f gauntlet_runner && make gauntlet
./gauntlet_runner --core --target x86-64
# Expected: TOTAL pass=247 fail=0 error=0

# Run the MIR battery
./test_mir_battery
# Expected: PASS: 69, WRONG: 0, CRASH: 0, TOTAL: 69
```

## Honest Remaining Issues

### JIT globals-across-calls returns wrong value (UNRESOLVED)

After all 5 fixes, the interpreter works correctly but the JIT still returns
wrong values in some cases.

**Test case:**
```c
int w = 10;
void setw(int v) { w = v; }
int main() { setw(42); return w; }
# Interpreter: 42 ✓
# JIT: 0 ✗ (expected 42)
```

**Root cause analysis (2026-08-30):**

The JIT's register allocator maps `vr0` (return value register) to a physical
register. After a CALL, the code does `mov rax, <vr0_reg>` to capture the return
value. But `vr0` may have been assigned to a register that was clobbered by the
callee (if it was in a caller-saved register) or to a register that was reused
for another VR during the function call.

The specific disassembly shows:
```
; After CALL returns:
mov rax, r12    ; rax = r12 (supposed to be vr0/return value)
leave
ret
```

But `r12` was used during the function to hold the address of `w` (VR_65537).
After the function modifies `w` and returns, `r12` still holds the address (1),
not the return value. The `mov rax, r12` reads the address, not the value.

**Why this happens:** The register allocator assigns VRs to physical registers
globally across the whole program. `vr0` might be assigned to `r12` because at
the point of the `MOV vr0, <func_result>` instruction, `r12` was free. But
`r12` was also used inside the callee for the global variable's address.

**Proper fix requires:** Interprocedural liveness analysis — computing
live-in/live-out sets at function entry/exit points, and ensuring that
VRs live across calls are assigned to callee-saved registers (r12-r15) or
spilled to the stack. This is a significant redesign of the register allocator.

**Workaround:** The interpreter works correctly for all cases. The JIT works
for all 247 core gauntlet tests. Only the specific pattern of "global variable
read after function call that modifies it" fails on the JIT.

### Other unsupported features
- Function pointers not yet supported in MIR/JIT path
- Enums, structs, deep recursion not yet supported
- 30 gcc_torture tests still failing (frontend limitations)
