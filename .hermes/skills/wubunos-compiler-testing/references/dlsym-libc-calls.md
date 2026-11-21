# dlsym-Based libc Calls in x86-64 JIT (2026-09-06 → updated 2026-09-16)

## Problem

Tests calling libc functions (abs, memset, memcpy, strcmp, etc.) need real results, not 0. The HolyD compiler doesn't support pointer types, so we can't implement libc functions as HolyD builtins.

## Solution

Resolve libc functions at JIT compile time via `dlsym()` and emit real x86-64 SysV ABI calls.

## Implementation

Location: `wubu_isa_x86_64.c`, MIR_CALL handler, `func_id == 0xFFFF` branch.

### Steps

1. **Resolve:** `dlsym(RTLD_DEFAULT, name)` then `dlsym(RTLD_NEXT, name)` as fallback
2. **Read VR encodings BEFORE saving:** `int vr1 = VR_ENC_SAFE(1);` etc.
3. **Save registers:** Push r11, r12, r13, r14, r15, r8, r9, rdx (8 registers)
4. **Move arguments to SysV registers:**
   - `emit_mov_reg(&e, 7, vr1)` → rdi = arg1 (x86-64 enc 7 = rdi)
   - `emit_mov_reg(&e, 6, vr2)` → rsi = arg2 (x86-64 enc 6 = rsi)
   - `emit_mov_reg(&e, 2, vr3)` → rdx = arg3 (x86-64 enc 2 = rdx)
5. **Call:** `movabs rax, <addr>; call rax`
6. **Save return:** `emit_mov_reg(&e, VR_ENC_SAFE(0), 0)` → VR0_home = rax
7. **Restore:** Pop in reverse order

### CRITICAL: Register Encoding Pitfall

`emit_mov_reg(dst, src)` expects **x86-64 register encodings** (0=rax, 7=rdi, 6=rsi, 2=rdx, 11=r11), NOT MIR allocator pool indices (where 13=rdi, 12=r10, 11=rsi).

`VR_ENC_SAFE()` returns x86-64 encodings via `reg_x86[]` mapping, so its output is directly usable with `emit_mov_reg`.

```c
// CORRECT
emit_mov_reg(&e, 7, vr1);   // rdi = VR1  (x86-64 enc 7 = rdi)

// WRONG — silently emits mov r13, r11
emit_mov_reg(&e, 13, vr1);  // 13 = r13 in x86-64, NOT rdi!
```

### x86-64 Register Encoding Reference

| x86-64 enc | Register | MIR pool index |
|-----------|----------|----------------|
| 0         | rax      | 0              |
| 2         | rdx      | 8              |
| 6         | rsi      | 11             |
| 7         | rdi      | 13             |
| 8         | r8       | 6              |
| 9         | r9       | 7              |
| 10        | r10      | 1 or 12        |
| 11        | r11      | 1 or 2         |
| 12        | r12      | 3              |
| 13        | r13      | 4              |
| 14        | r14      | 5              |
| 15        | r15      | 6              |

## Known Issues

- **1-arg integer functions:** WORK (abs, labs, putchar)
- **2-arg pointer functions:** WORK (strcmp — both args are pointers, MIR_TO_PTR converts them)
- **3+ arg functions:** CRASH (memset, memcpy — MIR_TO_PTR helps but crash persists, possibly heap corruption from JIT writing beyond buffer)
- **Float functions (all-double args):** WORK (copysign, sqrt, fma — all args double, result correct)
- **Mixed int/float functions:** FIXED (2026-09-16) — ldexp(double x, int n) now correctly passes `n` in RDI instead of XMM1. See below.

### Mixed int/float Argument Functions — ldexp FIXED (2026-09-16)

`ldexp(double x, int n)` requires a MIXED calling convention per x86-64 SysV ABI:
- `x` (double) → xmm0
- `n` (int) → **RDI** (NOT esi — esi is rsi, NOT rdi!)

**Fix implemented and verified:** Two-part approach:

1. **Treat ldexp as external call** in `holyd_mir_eval.c`: Add `"ldexp"` to the `ext_funcs[]` list. This sets `call_fid = 0xFFFF` and `is_external_call = true`, routing through the dlsym-based external call path in the JIT.

2. **Load integer arg into RDI** in `wubu_isa_x86_64.c`: In the MIR_CALL handler's `func_id == 0xFFFF` branch, check `strcmp(in->func_name, "ldexp") == 0`. If so, load VR2 (the integer `n`) into RDI via `emit_load_vr_to_xmm(&e, 2, ...)` with register encoding 6 (rdi), NOT xmm1.

**Why this works:** The external call path already handles dlsym resolution and register saving/restoring. By routing ldexp through the external call path and explicitly loading the integer argument into RDI, the SysV ABI mixed-type calling convention is satisfied. The float argument `x` still arrives in xmm0 via the float CC path.

**Verification:** `ldexp(2.0, 3)` returns 16 (correct). `ldexp(92E73, 5)` returns 2.944E76 (correct).

**Key insight:** The `ext_funcs` list approach is cleaner than the `is_ldexp` special-case approach because it reuses the existing dlsym infrastructure and doesn't require manual register encoding in the JIT compile loop. The only additional code needed is loading the integer argument into the correct register for the mixed-type case.

### MIR_TO_PTR: Converting Offsets to Pointers

MIR variables hold cell offsets into `prog.mem`, not actual pointers. When passing data to libc functions, the JIT must convert:

```
MIR_TO_PTR dst, a   // dst = wubu_jit_mem_ptr + a * 8
```

The MIR builder generates MIR_TO_PTR before external calls when:
- Argument is `HD_AST_STRING_LIT` (string literal → pointer to literal data)
- Argument type is `HD_TYPE_ARRAY` (array → decays to pointer)
- Argument type is `HD_TYPE_PTR` (pointer → needs actual address)
- `mir_var_is_array()` returns true (variable is an array)

**PITFALL:** `char src[] = "hello"` was NOT detected as an array because `is_array` was based on `arr_size > 0`, but unspecified-size arrays have `arr_size=0`. Fix in `holyd_mir_eval.c`: check `n->type->kind == HD_TYPE_ARRAY` instead. Without this, MIR_TO_PTR is never generated for string arrays, and libc functions receive garbage offsets.

### Char Type Handling Limitation

MIR uses 64-bit cells for all types. A `char` load returns the full 64-bit cell value, not the low 8 bits. This means `buf[0]` returns `0x4141414141414141` instead of `0x41`. All char comparisons and char-based logic fail. Fixing this requires byte-level load/store instructions in the MIR model.

## Build Note

`gauntlet_runner` is the binary for `--dump-asm` testing. `gauntlet_v2` for sequential runs. `gauntlet_v3` for multi-threaded. Always rebuild `gauntlet_runner` after JIT changes — it's a separate binary from `gauntlet_v2`/`gauntlet_v3`.