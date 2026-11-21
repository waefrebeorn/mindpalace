# x86-64 JIT Backend — Hard-Won Bug Fixes

Session-derived fixes for the native x86-64 JIT backend (`wubu_isa_x86_64.c`),
2026-08-28 through 2026-08-30.

## Bug #1: NULL Mem Base — `p->mem` is NULL at Compile Time

**Symptom:** JIT code crashes on first LOAD/STORE with SIGSEGV at address 0.

**Root cause:** `wubu_mir_init()` zeroes the `wubu_mir_prog_t` struct, so `prog->mem`
is NULL. The x86-64 JIT embeds `p->mem` as an immediate in `movabs rsi, imm64`
instructions during compilation. At runtime, LOAD/STORE dereference NULL.

**Fix:** Pass the mem base from `x86_run()` to the JIT code via a global variable:

```c
static int64_t *wubu_jit_mem_ptr = NULL;  // global

static int64_t x86_run(const uint8_t *code, size_t size, int64_t arg) {
    ...
    wubu_jit_mem_ptr = (int64_t*)arg;  // set before calling JIT code
    ...
}

// In JIT prologue:
rex(&e,1,0,0,0); e8(&e, 0xBB); e64(&e, (uint64_t)&wubu_jit_mem_ptr); // movabs rbx, &wubu_jit_mem_ptr
rex(&e,1,0,0,0); e8(&e, 0x8B); e8(&e, 0x1B);  // mov rbx, [rbx]
```

**CRITICAL REX PREFIX DETAIL:** The prologue must use `rex(1,0,0,0)` (0x48)
NOT `rex(1,0,0,1)` (0x49). The former encodes `movabs rbx, imm64`; the latter
encodes `movabs r11, imm64` (REX.B extends the RM field from rbx to r11). Using
0x49 loads the mem base address into r11 instead of rbx, causing all subsequent
memory accesses via rbx to use garbage. This was discovered in the 2026-08-30
session and cost significant debugging time.

**Why not pass via `rdi`?** The JIT code is called as `int64_t (*)(void)`, so
it receives no arguments. The mem base must be in a global or register set
before the call.

## Bug #2: CALL rel32 Off-by-One

**Symptom:** Function calls jump to the wrong address (1 byte past the target).

**Root cause:** The CALL fixup computed `rel = target - (pos + 4)`, but the rel32
is relative to the NEXT instruction (after the 5-byte CALL), not the current byte.

**Fix:** `rel = target - (pos + 5)`

```c
int32_t rel = (int32_t)(t - (pos + 5));  // NOT (pos + 4)
```

## Bug #3: ModRM Encoding for MOV — `89 F3` ≠ `mov rsi, rbx`

**Symptom:** `mov rsi, rbx` instruction overwrites rbx (the mem base) with rsi.

**Root cause:** The emitter used `89 F3` which decodes as `MOV rbx, rsi` (the r/m
operand is the destination in `89 /r`). The comment said `mov rsi, rbx` but the
encoding was backwards.

**Fix:** Use `89 DE` for `mov rsi, rbx` (reg=rbx, rm=rsi):

```c
rex(&e,1,0,0,0); e8(&e, 0x89); e8(&e, 0xDE);   /* mov rsi, rbx */
```

**General rule:** `89 /r` = `MOV r/m64, r64`. The r/m field is the DESTINATION.
ModRM byte `11:reg:rm` — reg goes INTO rm.

## Bug #4: Register Allocator Fails for High VR Numbers (PARTIALLY FIXED)

**Symptom:** Function calls produce wrong results (not crashes) in the JIT.

**Root cause:** The HolyD codegen uses `g->next_vr++` starting at 65536 for
function body slot addresses. The register allocator assigns physical registers
to ALL VRs 0..assign_count. With VR 65538, the spill frame needs 65538*8 =
524KB, which overflows the stack.

### Fix (2026-08-30): High VR remapping

The `x86_remap_vrs()` function compresses sparse high VRs (>= 4096) into a
dense range starting after the max low VR. This keeps the allocator's assign[]
array small. The remapping is applied in `x86_compile()` before allocation.

**Status:** Interpreter fully works. JIT works for simple programs and loops.
JIT still has issues with global variables across function calls (see Bug #6).

## Bug #5: Entry Trampoline Not Emitted

**Symptom:** `entry_off` stays at `(size_t)-1` even when functions exist.

**Root cause:** The condition `p->n_funcs > 0 && p->funcs[0].start == 0` is wrong.
In the HolyD MIR layout, main code comes FIRST (indices 0..N), then function
bodies (indices N+1..M). So `funcs[0].start > 0`, and no trampoline is needed.

**Fix:** Only emit trampoline if `funcs[0].start == 0` (function bodies before
main code). For HolyD layout, no trampoline is needed.

## Bug #6: Global Variables Across Function Calls (FIXED 2026-08-30)

**Symptom:** Global variable modifications inside functions are not visible to
the caller. E.g., `void setw(int v) { w = v; }` followed by `return w;` returns
the old value.

### Interpreter fix (2026-08-30)

The interpreter was saving/restoring the ENTIRE mem array on function call/return.
This undid global variable changes. Fix: removed `memcpy(mem, f->mem_save, ...)`
from the RET handler. Globals and locals use disjoint addresses (allocated by
`mir_new_vr` at 65536+), so memory changes persist across calls correctly.

**Caveat (CORRECTED — the JIT DOES support single-call recursion):** the flat
memory model with per-frame rbp-relative spill slots supports single-call
recursion — `fact`, `sum`, and mutual recursion all pass on x86-64. Each
recursive call gets its own rbp via the prologue `push rbp; mov rbp,rsp`, so
rbp-relative spills do not collide across frames. The remaining recursion gap
is TWO calls to the SAME function in one expression (see Bug #15), not
recursion in general.

### JIT fix — caller-saved register save/restore (2026-08-30)

The JIT uses a flat memory model (no save/restore), so globals persist correctly.
BUT: caller-saved registers (r10, r11, r8, r9, rdx) are clobbered by CALL.
If a global variable's address VR is assigned to a caller-saved register, the
address is lost after the call.

**Fix:** Save/restore all caller-saved registers around CALL instructions:
```c
static const int caller_saved[] = {10, 11, 8, 9, 2}; /* r10,r11,r8,r9,rdx */
for (int s = 0; s < 5; s++) { /* push */ }
e8(&e, 0xE8); /* call rel32 */
/* ... patch ... */
for (int s = 4; s >= 0; s--) { /* pop */ }
```

### JIT fix — entry-point constant spill (2026-08-30)

Even with caller-saved save/restore, the register allocator might assign a
global variable's address VR to a register that gets clobbered by an
intermediate function call. The definitive fix: identify constants defined in
the entry point (before the first function) that are used inside functions, and
force-spill them to stack slots. Each function loads them from the slot.

```c
/* In x86_compile(), after register allocation */
if (prog->n_funcs > 0 && prog->funcs[0].start > 0) {
    uint8_t *entry_def = calloc(assign_count, sizeof(uint8_t));
    /* Mark MIR_CONST results in entry point */
    for (size_t i = 0; i < prog->funcs[0].start && i < prog->n; i++) {
        if (prog->ins[i].op == MIR_CONST && prog->ins[i].dst < assign_count)
            entry_def[prog->ins[i].dst] = 1;
    }
    /* Force-spill any entry-constant used in any function */
    for (int f = 0; f < prog->n_funcs; f++) {
        for (size_t i = prog->funcs[f].start; i < prog->funcs[f].end; i++) {
            uint32_t srcs[2] = {prog->ins[i].a, prog->ins[i].b};
            for (int j = 0; j < 2; j++) {
                if (srcs[j] < assign_count && entry_def[srcs[j]] && assign[srcs[j]].reg >= 0) {
                    int slot = next_slot++;
                    assign[srcs[j]].stack = -(int32_t)((slot + 1) * 8);
                    assign[srcs[j]].reg = -1;
                }
            }
        }
    }
    free(entry_def);
}
```

**Result:** Global variables across function calls work correctly on JIT.
`int w; void setw(int v){w=v;} int main(){setw(42); return w;}` returns 42.

### JIT fix — save/restore ALL allocator registers around CALL (2026-08-30, SUPPLEMENT)

The entry-point constant spill alone doesn't cover all cases (e.g., `static int
count = 0` with initializer generates STORE in entry point, not just CONST).
Supplement with save/restore of ALL 9 allocator registers around every CALL:

```c
case MIR_CALL: {
    static const int all_regs[] = {10, 11, 12, 13, 14, 15, 8, 9, 9, 2};
    for (int s = 0; s < 9; s++) { /* push all_regs[s] */ }
    e8(&e, 0xE8); /* call rel32 */
    /* ... patch ... */
    for (int s = 8; s >= 0; s--) { /* pop all_regs[s] */ }  // REVERSE order (LIFO)
    break;
}
```

**CRITICAL:** Pop in REVERSE order of push (LIFO). After `call` pushes the return
address and the callee's `ret` pops it, rsp points to the LAST pushed register.
Popping in same order reads the return address as a register value.

**Frame size:** Add 72 bytes (9 registers × 8 bytes) to the stack frame to
accommodate the saves: `e.frame = n_spilled * 8 + 16 + 72;`

**Trade-off:** This approach is simple and correct but adds 18 instructions
(9 pushes + 9 pops) per function call. For hot loops, this is expensive.
Prefer the entry-point constant spill for the common case and only use
save/restore-all when spill alone is insufficient.

**Combined result:** Both approaches together fix ~23 additional gcc_torture
tests (globals across calls, static globals with initializers). Core gauntlet
remains 247/247. Some gcc_torture tests still fail due to pointer/array
cross-function passing (needs deeper per-function register allocation).

### FAILED APPROACHES (documented to avoid repeating)

1. **Save/restore caller-saved only (5 regs):** Insufficient — callee may
   reassign VRs to caller-saved registers, clobbering global addresses.
2. **Cross-function VR spill (broad):** Detecting ALL VRs used in multiple
   functions and spilling them caused 23 regressions — too aggressive, spills
   argument VRs that should stay in registers.
3. **Save/restore with same-order pop:** Popping in same order as push reads
   the return address as a register value, producing garbage (0xFFFFFFFF).
4. **Removing interpreter mem save/restore alone:** Fixed interpreter but JIT
   still failed because registers were clobbered.

### VR Address Collision Fix (2026-08-30)

`wubu_mir_alloc()` returned a low VR (instruction index) for variable addresses.
This collided with argument registers (v1..vN) when a function with parameters
accessed globals. Fix: use `mir_new_vr(g)` (high VR >= 65536) for variable
addresses and emit `wubu_mir_const_to()` to store the constant address.

## Bug #7: Loop-Aware Live Range Extension (2026-08-30)

**Symptom:** `stress_fib` returns 512 instead of 55 on x86-64 JIT.

**Root cause:** The linear scan register allocator computed `last_use` without
accounting for loop back-edges. VRs used inside a loop body (e.g., variable
addresses like &a, &b) had their `last_use` set to the last instruction in the
linear sequence, not the loop's back-edge. This allowed the allocator to assign
the same register to a loop-carried VR and a VR defined inside the loop.

**Fix:** After computing initial `last_use`, find all backward branches
(JMP/JZ/JNZ to an earlier label) and extend the `last_use` of every VR used
in [label, branch] to the branch position.

**Result:** stress_fib returns 55. Core gauntlet: 247/247.

## Bug #8: VR0 Pre-Assignment Skipped by Linear Scan (2026-08-30)

**Symptom:** Entry point reads return value from wrong register (e.g., `mov rax, r12`
instead of `mov rax, r10`).

**Root cause:** VR0 (return register) is pre-assigned to physical reg 0 (r10)
but the linear scan was processing VR0 like any other VR, potentially
reassigning it when its interval appeared to expire.

**Fix:** Skip VR0 in the linear scan (same as argument VRs):
```c
if (vr == 0 || (vr >= 1 && vr <= n_args)) continue;
```

## Bug #9: REX Prefix Error in Prologue (2026-08-30)

**Symptom:** JIT loads memory base into r11 instead of rbx, causing all memory
accesses to use garbage.

**Root cause:** The prologue used `rex(1,0,0,1)` (0x49 = REX.WB) instead of
`rex(1,0,0,0)` (0x48 = REX.W) for `movabs rbx, imm64`. The REX.B bit extends
the RM field from rbx (011) to r11 (1011).

**Fix:** Use `rex(1,0,0,0)` for both instructions in the prologue:
```c
rex(&e,1,0,0,0); e8(&e, 0xBB); e64(&e, (uint64_t)&wubu_jit_mem_ptr); // movabs rbx, imm64
rex(&e,1,0,0,0); e8(&e, 0x8B); e8(&e, 0x1B);  // mov rbx, [rbx]
```

## Bug #10: MIR_SHR Emits `shr` (Logical) Instead of `sar` (Arithmetic) — 2026-09-01

**Symptom:** `(char)(-2)` returns 254 instead of -2. Char/short casts don't
sign-extend properly. `(int)(char)(-2)` returns 254, expected -2.

**Root cause:** The interpreter's `op_shr` is `vr[in->a] >> (vr[in->b] & 63)`.
On `int64_t`, C's `>>` is arithmetic shift for signed values. The JIT was
emitting `shr rax, cl` (logical shift) which fills with 0s, not `sar rax, cl`
which fills with the sign bit.

**Fix:** Change the JIT's MIR_SHR emission from `0xD3 0xE8` (shr) to
`0xD3 0xF8` (sar). ModRM byte changes from `0xE8` to `0xF8` (mod=11, reg=7=sar):
```c
if (in->op == MIR_SHL) { rex(&e,1,0,0,0); e8(&e, 0xD3); e8(&e, 0xE0); }
else { rex(&e,1,0,0,0); e8(&e, 0xD3); e8(&e, 0xF8); }  /* sar rax, cl */
```

**Why it matters:** The sign-extending truncator pattern `(val & mask) << N >> N`
requires arithmetic right shift for the final step. Without it, `(char)x` where
x has bit 7 set produces a non-negative value instead of the correct negative
sign-extended value.

## Bug #11: Shared `assign[]` Table Breaks Multi-Parameter Calls — 2026-09-01

**Symptom:** `int test(int *p, int i) { return p[i]; }` returns `i` instead of
`p[i]`. Function calls with 2+ parameters produce wrong results; first
parameter's stored value gets overwritten by subsequent stores.

**Root cause:** The JIT uses ONE shared `assign[]` table for ALL VRs across
ALL functions. When the callee has multiple parameters, the callee body
emits `MIR_STORE addr_p, v1` then `MIR_STORE addr_i, v2`. Both addr_p and
addr_i are HIGH VRs (>= 65536) holding memory addresses. The shared `assign[]`
table maps addr_p and addr_i to the SAME physical register (e.g., both map
to r13 because the allocator assigned them sequentially). When `MIR_STORE`
emits `mov rax, addr_p` then `mov rdi, addr_i`, but both addr_p and addr_i
are in r13, rdi gets the SAME value as rax — both stores go to the same
memory location. The second store overwrites the first.

**Why the prior fixes (Bug #6) didn't catch this:** Bug #6 focused on
single-parameter calls and global variable cross-calls. The multi-parameter
case within a single function is a different failure mode — the shared
register allocator assigns overlapping registers to independent memory
address VRs.

**Fix (partial):** Per-function register allocation. Each function body
should get its own `assign[]` table. Until then, a workaround is to
allocate parameter address VRs at MUCH higher offsets so the allocator
spreads them across registers:
```c
/* Use incrementing high VRs for each param address, not shared slots */
for (int pi = 0; pi < fn->n_params; pi++) {
    wubu_vr_t addr = mir_new_vr(&g);  /* unique VR per param */
    ...
}
```
This already works (each `mir_new_vr` returns a unique number), but the
allocator still assigns them to the same register because it sees them as
independent VRs with non-overlapping live ranges (they're all live from
function entry to exit). **The real fix is per-function `assign[]` tables.**

**Status:** 30 gcc_torture tests still fail on x86-64 full gauntlet due to
this issue. Core gauntlet (247/247) and MIR battery (69/69) pass.

## Bug #12: Implicit `main()` Return Not Initialized — 2026-09-01

**Symptom:** `main()` with no explicit `return` returns a stack pointer value
(e.g., 140733314107360) instead of 0. Affects `gcc_torture_000007_pr110115`,
`_000639_pr108064`, `_000644_pr119071`, `_000762_20001009_1`.

**Root cause:** `fn_ret_vr` is allocated via `mir_new_vr(&g)` but never
initialized. If `main()` has no `return` statement, the epilogue moves
`fn_ret_vr` to vr0, but `fn_ret_vr` holds whatever garbage was in that
register slot.

**Fix:** Initialize `fn_ret_vr` to 0 at function entry:
```c
g.fn_ret_vr = mir_new_vr(&g);
wubu_mir_const_to(prog, g.fn_ret_vr, 0);  /* default return = 0 (C11 convention) */
```

**Why C11:** Per ISO C11 §5.1.2.2.3, "reaching the `}` that terminates the
`main` function returns a value of 0." This matches the test framework's
expectation that `expected=0` for tests without explicit return.

## Bug #13: Struct Brace Initializer Offset Mismatch — 2026-09-01

**Symptom:** `struct S { char *p; } s = {"hello"}; s.p[0]` returns 0 instead
of 'h' (104). String literal initialization of struct pointer fields fails.

**Root cause:** The brace initializer at `HD_AST_VAR_DECL` stored each
element at sequential cell index `e` (offset 0, 1, 2...). But member access
via DOT/MEMBER used `mir_struct_member_offset()` which returned the BYTE
offset from `n->type->members[i].offset` (e.g., 8 for a pointer member after
a char). Cell 1 ≠ byte 8, so reads went to wrong memory locations.

**Fix:** In the brace initializer, for struct types, look up the e-th member's
BYTE offset instead of using sequential index:
```c
if (is_struct_var && struct_type_name[0]) {
    int moff = mir_struct_member_offset_by_index(g, struct_type_name, (int)e);
    if (moff >= 0) offset = moff;
}
```
Also added `mir_struct_member_offset_by_index()` helper that returns the
byte offset of the e-th member in the struct definition.

**Also needed:** `mir_address_of` had no handler for DOT/MEMBER/ARROW, so
`s.p[0]` (INDEX over DOT) failed. Added a DOT/ARROW case that loads the
member value (for use as the base of an INDEX/DEREF):
```c
if (n->kind == HD_AST_DOT || n->kind == HD_AST_MEMBER) {
    /* s.a as a value: load the member value (e.g. pointer for s.p[0]) */
    ...return wubu_mir_load(g->prog, member_addr);
}
```

## Bug #14: Pointer-to-Struct Parameter Tracking — 2026-09-01

**Symptom:** `void f(struct t1 *ps) { ps->a = 42; }` called from main: `ps->a`
assignment doesn't work. `f(&s); return s.a;` returns 0 instead of 42.

**Root cause:** `mir_bind_var()` was called for function parameters with
`is_unsigned=0` and no struct type info. When the callee accessed `ps->a`,
`mir_find_var_struct_name("ps")` returned NULL because `g->vars[i].is_struct`
was false (ps is a pointer, not a struct instance). Without the struct name,
`mir_struct_member_offset()` returned -1, and `->a` access fell back to the
default case (returning 0).

**Fix:** In `mir_bind_var`, detect pointer-to-struct parameter types and set
`is_ptr_struct=1` and `struct_name` from the type's base struct name:
```c
if (fn->param_types[pi] && fn->param_types[pi]->kind == HD_TYPE_PTR &&
    fn->param_types[pi]->base &&
    (fn->param_types[pi]->base->kind == HD_TYPE_STRUCT || ...)) {
    g->vars[gi].is_ptr_struct = 1;
    strncpy(g->vars[gi].struct_name, fn->param_types[pi]->base->name, ...);
}
```
Also added `is_ptr_struct` field to `mir_var_t` and updated `mir_address_of`
for ARROW to look up the struct type from the pointer variable's metadata.

## Bug #15: Two Calls to the SAME Function in One Expression (ROOT-CAUSED, NOT FIXED)

**Symptom:** `fib(n-1)+fib(n-2)` returns 0 (fib(2) should be 1). Sequential
`a=fib(2); b=fib(2)` also fails. Single-call recursion (`fib(n-1)+0`) and two
calls to DIFFERENT functions (`f(1)+f(0)`, `g(1)+g(0)`) both work. The last
global store before the second same-function recursive call is dropped:
`g=fib(n-1); h=fib(n-2);` leaves `h` unchanged.

**Root cause (traced via MIR dump — the MIR is CORRECT):** the MIR emits
`store mem[g]=v46; call fib; mov v65544=v0; store mem[h]=v59` in the right
order, so the bug is purely x86 codegen of two sequential calls to the same
function. Suspect: the internal-call register save/restore (`caller_saved[]`
8-reg push before / pop after, ~line 1594) interacting with the recursive
callee's own frame, and whether r10 (VR0 return reg, deliberately EXCLUDED from
the save list) survives the second same-function call. NOT yet fixed — next
probe is the 8-reg push/pop balance vs the callee prologue/epilogue.

**What did NOT fix it (documented to avoid repeating):** forcing call-result
VRs to callee-saved r12-r15; and the called-function full-epilogue change
(making every function invoked via `call rel32` run `mov rsp,rbp; pop r15..rbx,
rbp; ret` instead of a bare `ret`). The epilogue change DID fix fib(2) but
REGRESSED `x=5; y=f(); return x` (the second call's result leaked into x) —
gauntlet FAIL 142→588. REVERTED: the recursion bug and the local-store-before-
call bug are DIFFERENT bugs, and the epilogue fix trades one for the other.
Do not ship a blanket full-epilogue change.

## Regalloc: Spill VRs Whose Live Range Crosses a MIR_CALL (SHIPPED — 57% FAIL reduction)

Any VR live across a call may land in a caller-saved physical reg (r10/r11/
r8/r9/rdx) that the callee clobbers. In `wubu_mir_regalloc.c` Step 5, when
`range_crosses_call(p, start, end)` is true, force the VR to a unique stack
spill slot (`reg=-1`, `stack=-(slot+1)*8`) instead of a register — the chibicc
discipline: values live across a call live in memory.

**MEASURED IMPACT:** this single change dropped the x86-64 gauntlet FAIL count
from **329 → 142** (a 57% reduction, confirmed on a clean rebuild). It did NOT
fix the narrow Bug #15 fib case (that MIR is already correct — the defect is in
the call save/restore codegen), but it fixed a large class of call-result-VR
clobbering across other tests. Highest-leverage regalloc fix; ship it.

**Caveat when measuring:** `make gauntlet_runner` can report "up to date" and
skip the rebuild after a source change (dependency tracking misses it) → stale
binary → identical FAIL count. Force `rm -f gauntlet_runner && make gauntlet_runner`
before trusting any before/after FAIL delta.

## Debugging Recipe for x86-64 JIT

1. **Dump JIT code:** Set `WUBU_CALL_DEBUG=1` env var to print emitted bytes
2. **Decode manually:** Compare against x86-64 reference (Intel SDM vol 2)
3. **Check mem base:** Verify rbx holds a valid pointer at crash time
4. **Check CALL targets:** Verify rel32 lands on the first byte of the callee
5. **Check ModRM:** Verify `89 /r` has the correct direction (rm = destination)
6. **Check REX prefixes:** `0x48` = REX.W (no B), `0x49` = REX.WB (extends RM to r8-r15)
7. **Use gdb:** `gdb -batch -ex 'run' -ex 'info registers' -ex 'x/20i $rip'`
8. **For function call wrong results:** 
   - Check if global address VRs are in caller-saved registers → add save/restore around CALL
   - Check if interpreter also fails (if yes, it's a MIR issue; if no, it's a JIT codegen issue)
   - Check if entry-point constants are spilled (entry-point constant spill fix)
   - Check if ALL registers need save/restore around CALL (for complex cross-function cases)
9. **For loop-related wrong results:** Check if loop-carried VRs are assigned
   to the same register as VRs defined inside the loop (live range extension fix)
10. **For return value wrong:** Verify entry point reads from VR0's register (r10)
11. **For globals across calls:** 
    - First try entry-point constant spill (cheap, covers most cases)
    - If that fails, add save/restore ALL 9 allocator registers around CALL
    - Verify pop order is REVERSE of push (LIFO)
    - Increase frame size by 72 bytes for the register saves
12. **For save/restore-all causing regressions:** The 18 extra instructions per
    call can cause stack alignment issues or timeouts in deep recursion. Prefer
    targeted spill over blanket save/restore when possible.

## Test Commands

```bash
make gauntlet && ./gauntlet_runner --core --target x86-64
make test_mir_battery && ./test_mir_battery
```
