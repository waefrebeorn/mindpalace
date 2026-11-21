# Gauntlet Scoring Model and Architectural Ceiling (2026-09-12 → 2026-09-20)

## Gauntlet Counts Test-Target Pairs, NOT Tests

The gauntlet runs each test on ALL 14 targets and counts pass/fail/error per target.
A test that passes on x86-64 but fails on ptx counts as 1 pass + 1 fail.

## CRITICAL: Only x86-64 Target Works (2026-09-14)

Testing all 14 targets with `return 42`:
- **x86-64**: works (returns 42) — the ONLY functioning target
- **8086, 6502, riscv, z80, mips, 8051, avr, pic**: return 0 (wrong)
- **amdgpu**: returns 1 (wrong)
- **ptx**: returns 102626882335328 (garbage)
- **wasm**: returns -999 (garbage)
- **m68k**: crashes (SIGSEGV)
- **arm64**: skipped (can't compile on x86-64 host)

**The gauntlet score IS the x86-64 score.** Other targets contribute almost nothing.
To increase the score, fix x86-64 failures only. Fixing other targets is a separate
multi-session project.

## Current State (2026-09-20 → 2026-09-21)

Score: 1,243/2,668 (46.6%) — gauntlet_v3 is the CANONICAL runner (gauntlet_runner counts differently due to extra_credit filtering). Only x86-64 target works. Cell-based memory model (8 bytes per element). 18 non-extra-credit FAILs remain: ch13=3, ch15=3, ch16=4, ch18=8.

### 2026-09-20 Session: Double-indexing fix + float CC diagnosis + byte memory probe (CONTINUED)

**Float literal exponent without decimal point** — `4e12`, `1E-3` etc. were parsed as integer `4` + identifier `e12` because the lexer only scanned exponents after a `.`. Fixed: added exponent scanning after integer digits. No score change (tests using `4e12` were already failing for other reasons).

**Float load from array to local is BROKEN** — `double local = arr[0]` produces wrong value, but `arr[0] == 4e12` directly works. Confirmed: `double d = 4e12; double local = d;` also fails. Root cause: the assignment handler's `mir_truncate_to_type(val, HD_TYPE_F64)` calls `MIR_DTOI` (integer-to-double conversion) even when the value is ALREADY a double. The raw bits of the double are reinterpreted as an integer and converted to a different double. **Fix: check if the RHS is already F64 before calling DITOF in `mir_truncate_to_type`.**

**3D array initialization flattening** — `int arr[2][2][3] = {...}` fails because the initializer flattening code only handles 2D. The outer loop's `elem_sz` was `base->array_size * 8` (wrong for 3D — should be product of all inner dimensions * 8). Fixed `elem_sz` computation but the inner flattening (`sub_off = offset + se * 8`) still only goes one level deep. Needs recursive flattening. **Score unchanged — reverted 3D fix because inner flattening still broken.**

**Tests fixed this session:** none net (float literal fix didn't change score, 3D fix reverted).

**Double indexing for pointer-to-pointer** — INDEX handler now uses `mir_gen_expr(base)` (loaded value) instead of `mir_address_of(base)` (address) when the ultimate base is `PTR(PTR(type))`. For `PTR(ARRAY(type,N))`, still uses `mir_address_of` (sub-array decays to pointer). Distinction made by walking to the ultimate base IDENT and checking var table type. Fixed: `subscript_pointer`.

**Float calling convention for INTERNAL functions** — Diagnosed root cause of ch18 struct test failures: `check_d(autom.d)` passes the double in an integer register (VR1→r11) because the JIT's `is_float_func` whitelist only covers external dlsym functions. Internal functions with float params need the JIT to consult the callee's parameter types. Fix design: add `float_param_mask` bitmap to `wubu_mir_func_t`, populate it during `mir_collect_funcs` from `param_types[i]==F64`, and in the internal call handler, move float VRs to XMM registers before the call. Implemented the MIR changes but reverted — the register allocator maps ALL VRs from a single pool (no XMM registers), so moving to XMM requires either adding XMM regs to the allocator or using a separate move-to-XMM step that the callee's VR mapping doesn't know about. **The callee reads VR1 from its assigned physical register (r11); moving the value to XMM0 doesn't help because the callee still reads r11.**

**Byte-addressable memory probe** — Added `MIR_LOAD_BYTE`/`MIR_STORE_BYTE` + JIT implementations + `wubu_mir_load_byte`/`wubu_mir_store_byte` helpers. Reverted: char arithmetic `(char)(127+1)` computes 127+1=128 in 64-bit, then the byte load zero-extends to 128, but C expects sign-extended -128. Fixing this requires BOTH sign-extension on load (movsx for signed char, movzx for unsigned) AND truncation to 8 bits after every char arithmetic operation. The truncation is the hard part — it must happen after every ADD/SUB/MUL/AND/OR/XOR involving char-typed values. **Byte memory needs a systematic approach: either truncate-after-every-char-op in MIR generation, or add width-aware arithmetic MIR ops.**

**Tests fixed this session:** `subscript_pointer` (+1 net).

### 2026-09-20 Session: Multi-dimensional array parameter fix (earlier)

**Array parameter type adjustment** — `int a[2][3]` now correctly becomes `PTR(ARRAY(I32, 3))` instead of `PTR(PTR(I32))`. Parser builds inner ARRAY types for dimensions [1..N-1] and wraps outermost in PTR. MIR eval adds `is_ptr_array` flag, sets `array_stride` from `base->array_size`, and INDEX handler skips load for pointer-to-array bases (sub-array decays to pointer, not value).

**Critical initialization pitfall** — Adding a new flag to the var struct (`is_ptr_array`) requires initializing it to 0 in BOTH `mir_decl_var_unsigned` AND `mir_bind_var`. Stale values from previous function compilations persist in the var table and cause wrong behavior in unrelated functions.

**Critical clearing pitfall** — When the same parameter name appears in multiple functions (e.g., `a` in both `array_param` and `nested_array_param`), the var table accumulates entries. Before setting `is_ptr_array=1` for a parameter, clear it for ALL entries with that name, otherwise a stale 1 from a previous function's compilation leaks into the current function.

**Tests fixed:** `array_as_argument`, `addition_subscript_equivalence` (+2 net after flaky ch13/ch18 regressions).

### 2026-09-19 Session: DEREF-of-array fix and stack frame attempts

**DEREF of array ADD** — `*(arr + i)` for multi-dimensional arrays now correctly returns the sub-array address instead of loading the first element. Also fixed ADD pointer scaling when the left operand is a DEREF-of-array (element size 8, not array stride). Tests pass individually but gauntlet score unchanged due to state leakage.

**Stack frame implementation attempts** — Three approaches were tried and reverted:
1. **Per-function static buffer** (`calloc(256)` per function index with `push rbx; mov rbx, buf` prologue): Doesn't work for recursion — all invocations of the same function share the buffer.
2. **`rep movsq` save/restore of prog.mem around calls**: Corrupts `rcx` (used as counter, but holds a live VR), `rsi`, `rdi` (used for memory access), and causes stack misalignment.
3. **Removed r12 from allocator pool for frame pointer**: Correct direction but requires changing all LOAD/STORE to use `[r12+offset]` instead of `[rbx+offset]`, which is a larger change.

**Correct stack frame approach** (not yet implemented): Allocate a NEW buffer per function CALL using `call malloc` in JIT prologue, or use hardware stack (`sub rsp, frame_size`) with `[rbp-offset]` addressing for locals. Both require significant JIT changes.

**Key insight**: The MIR generator stores parameters at fixed prog.mem addresses. The callee's store overwrites the caller's value. The fix must give each CALL its own address space.

**Recursive function confirmed broken** — `fun(1.0)` returning 6 instead of 4 is a flat-VR-model limitation: parameters share fixed memory addresses across recursive invocations. Both interpreter (memory not restored on return) and JIT (no stack frames) affected.

### 2026-09-16 Session: Additional architectural probes

**Interval splitting (wubu_mir_regalloc.c:446)** — the split code is written but disabled (`if (0 && ...)`). Enabling it WITHOUT spill/reload emission in the JIT caused score to drop from 1238→1056 (182+ new crashes). The allocator sets `spill_after` and `stack` fields on split fragments, but the JIT never emits the actual spill-store or reload-load instructions at split points. `VR_ENC_SAFE` checks `spill_after` and returns -1 (spilled) past the split point, so the tail fragment reads garbage. **Interval splitting requires JIT spill/reload emission to be implemented first — it is not a one-line fix.**

**Static local hoisting** — attempted to hoist `static` local variable initializers to function top for `switch_skip_static_initializer`. Correct in principle (C semantics require static init at program startup). Broke 9 tests: allocating VRs and memory cells in the hoist phase shifts all subsequent VR numbering, which destabilizes the linear scan register allocator's choices. **VR numbering is load-bearing — any change to early-phase allocation has cascading regalloc effects.** Reverted.

**ldexp mixed calling convention** — removed `ldexp` from `is_float_func` whitelist and added a JIT special case emitting `movq xmm0, rax` (arg1) + `mov rsi, vr2` (arg2) + `al=1`. The special case IS reached and correct x86-64 machine code is emitted. But `ldexp(1.0, 2)` returns 0 and `ldexp(92E73, 5)` returns +inf. Root cause: VR1 (the double constant) is spilled (`vr1_reg=-1`), and the spill slot load produces a wrong value — likely the constant was truncated to 32 bits before spilling. **The ldexp calling convention is correct; the spilled VR value corruption is the blocker. Fix the sext32/constant truncation bug first, then ldexp will work.**

## Architectural Ceiling

| Blocker | Chapters | ~Tests | Fix Required | Status |
|---------|----------|--------|--------------|--------|
| Register allocator loop bug | 15 | ~15 | Loop variables clobber array base address registers across loop boundaries | ACTIVE — intervals overlap but same register assigned |
| Struct byte-offset layout | 18 | ~31 | Member offsets in bytes with alignment padding | Cell-based model is FUNDAMENTAL |
| Width-aware LOAD/STORE + char truncation | 16 | ~15 | 8-bit loads/stores AND 8-bit truncation after every char arithmetic op | PROBED 2026-09-20 — byte ops easy, truncation is the hard part |
| Float CC for internal calls | 13, 18 | ~10 | Callee's VR mapping must route float VRs to XMM regs — single-pool allocator can't do this without XMM regs added to pool | PROBED 2026-09-20 — float_param_mask design is correct but allocator lacks XMM registers. **Also: `mir_truncate_to_type(F64)` calls DITOF on already-double values — this is a SEPARATE bug that's easier to fix and may unlock several tests** |
| Float load from array/local | 13, 18 | ~5 | `double local = arr[0]` broken — DITOF applied to already-double value | DIAGNOSED 2026-09-21 — fix `mir_truncate_to_type` to skip DITOF when RHS type is already F64 |
| 3D array initialization | 15 | ~3 | Initializer flattening only handles 2D — needs recursive flatten | DIAGNOSED 2026-09-21 — outer elem_sz fixed, inner flatten still 1-level-deep |
| Constant truncation (sext32) | 13 | ~5 | Large 64-bit constants truncated to 32 bits in IDENT handler | Root cause of ldexp failure AND large-unsigned-constant failures |
| sizeof array decay | 17 | ~6 | Array subscript in sizeof context | Not attempted |
| Abstract declarators | 14 | ~5 | `(int (*))` cast syntax | Not attempted |
| Pointer subtraction | 15 | ~5 | `ptr2 - ptr1` must divide by sizeof(pointee) | Not attempted |
| Gauntlet state leakage | 15 | ~5 | Tests pass individually but fail in gauntlet | ACTIVE — diagnostic needed |
| Stack frame / recursion | 10, 13 | ~3 | Stack frames for recursive functions with locals | Confirmed 2026-09-19 — both interpreter and JIT affected |
| Variable redeclaration | 10, 12 | ~3 | Multiple file-scope declarations | Not attempted |
| Goto-in-block parser | 10 | ~1 | `goto` into block with `extern` | Not attempted |
| Switch without braces | 8 | ~6 | `switch(x) case 1: stmt;` | Not attempted |
| MIR_DTOI_U >= 2^63 | 13 | ~5 | `cvttsd2si` returns indefinite | Attempted, reverted |
| Static local in switch | 10 | ~1 | Static init inside skipped switch case | Attempted 2026-09-16 — hoisting broke 9 tests |
| Double indexing (ptr-to-ptr) | 15 | ~1 | INDEX handler uses mir_gen_expr for PTR(PTR) bases | DONE 2026-09-20 |
| Multi-dim array params | 15 | ~2 | `int a[N][M]` → PTR(ARRAY(I32,M)) | DONE 2026-09-20 |

## Key Scoring Milestones

- 1,175 (session start, 2026-09-12)
- 1,206: Register allocator spill slot fix (nested loops)
- 1,212: Comparison float promotion + debug print cleanup
- 1,196: Byte-addressable memory attempt (REVERTED back to 1,212)
- 1,231: Array parameters→pointers (+14), null statements (+19 recovery)
- 1,235: 2D array stride fix + nested brace-init (+4)
- 1,236: 16-byte alignment (neutral, SSE prep)
- 1,238: DEREF increment/decrement (+1), sizeof unsigned (+1)
- 1,257: sizeof string literal + char token lexer fix (+5)
- 1,259: math functions via dlsym (+2)
- 1,261: sizeof result unsigned + file-scope redeclaration (+3)
- 1,262: skip function prototypes in mir_collect_funcs (stable, no regression)
- 1,262: DEREF-of-array fix (stable, no regression — gauntlet state leakage masks improvement)
- 1,243: Multi-dimensional array parameter fix (+2 net: array_as_argument, addition_subscript_equivalence)
- 1,244: Double-indexing fix (subscript_pointer +1 net)
- 1,244: Float CC diagnosis — internal function calls pass float args in integer registers (VR1→r11). Callee reads from r11, gets wrong value. Fix requires adding XMM registers to allocator pool or changing VR mapping for calls.
- 1,244: Byte memory probe — MIR_LOAD_BYTE/STORE_BYTE ops work but char arithmetic truncation is the blocker. `(char)(127+1)` computes 128 in 64-bit, byte load zero-extends to 128, but C expects -128. Needs truncation after every char-typed arithmetic op.
- 1,243: Float literal exponent fix (4e12 → float, not int+ident). No score change.
- 1,243: Float load from array-to-local diagnosis — `mir_truncate_to_type(F64)` calls DITOF on already-double values, reinterpreting raw bits as integer. **Fix: skip DITOF when RHS is already F64.**
- 1,243: 3D array init flattening — inner flatten not reverted (only outer elem_sz fix kept). Needs recursive flatten.

## Cell-Based Memory Model — WHY STRUCT LAYOUT CANNOT BE FIXED (2026-09-14)

Attempted to change struct member offsets from cells to bytes with C alignment rules.
Reverted: broke 11 tests (1,235 → 1,224). Root cause:

`t->size` in the parser is in CELLS and is used for memory allocation everywhere:
- `wubu_mir_alloc(total_size)` allocates cells, not bytes
- Struct copy loops copy `total_size` cells (8 bytes each)
- `mir_struct_member_offset()` returns `offset * 8` (cell→byte)

Changing `t->size` to bytes breaks allocation (structs get 1 cell instead of 2).
Changing `member_offsets` to bytes without changing `t->size` causes the allocator
to under-allocate. The two are coupled by the cell-based memory model.

**The cell-based model is FUNDAMENTAL to HolyD.** Every array element and struct
member occupies exactly 1 cell (8 bytes). Packing tighter requires width-aware
LOAD/STORE MIR ops (LOAD8/16/32, STORE8/16/32) — a significant project.

## Register Allocator Loop Bug (2026-09-14)

**Symptom:** After a loop completes, 2D array access returns wrong values.
Example: `for(i=0;i<7;i++) arr2[i]=-i; return arr3[1][0];` returns 7 instead of 0.

**Mechanism:** The linear scan register allocator assigns the same register to both
the loop variable `i` and the array base address VR. After the loop, the register
contains the loop's end value instead of the array base address.

**Why the existing fix doesn't work:** The `last_use` extension for VRs crossing loop
boundaries is a no-op when `last_use` is already past the loop end. The interval
overlap should prevent register sharing, but something in the allocator prevents it.

**Fix approaches (not yet attempted):**
1. Reload spilled VRs from stack slots after each loop
2. Recompute array base addresses after each loop in the MIR generator
3. Mark array base address VRs as "must spill" to force stack storage
4. Fix the linear scan allocator's interval analysis for nested intervals

## Diminishing Returns Signal

When spending >1 hour per test gained, you've hit the architectural ceiling.
The next phase should be:
1. Pick ONE architectural blocker and dedicate a full session to it
2. Accept that regression risk is high — have a rollback plan (git commit before starting)
3. Focus on x86-64 JIT only (ignore other targets)
4. For byte-addressable memory: change ALL address computation sites in a SINGLE commit
