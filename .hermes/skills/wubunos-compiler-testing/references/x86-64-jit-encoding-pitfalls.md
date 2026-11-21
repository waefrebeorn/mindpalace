# x86-64 JIT Encoding Pitfalls

This document captures encoding-specific bugs that silently produce wrong results or crashes in the HolyD x86-64 JIT (`wubu_isa_x86_64.c`).

## 1. Forward Jump Position Truncation (uint8_t bug)

**Symptom:** Code works for small functions (<255 bytes) but crashes for larger ones. Crash looks like random memory corruption or illegal instruction.

**Root cause:** Declaring jump patch position as `uint8_t` instead of `size_t`:
```c
uint8_t jp_patch_pos = e.n;  // BUG: truncates when e.n > 255
```

**Fix:** Always use `size_t` for jump patch positions:
```c
size_t jp_patch_pos = e.n;  // CORRECT
```

**When it matters:** Any forward jump (JP, JMP, JZ, JNZ) where the jump target is more than 255 bytes away. Common in NaN handling (JP jump), large functions, and complex control flow.

## 2. REX Prefix Byte Ordering for SSE2

For `movq xmm, rax` (opcode `66 0F 6E /r`), BOTH orderings work:
- `66 48 0F 6E C0` (legacy prefix first) — works
- `48 66 0F 6E C0` (REX first) — also works

**Do NOT "fix" this** — both are valid. The current JIT uses REX-first.

## 3. ModRM Byte Encoding for XMM Registers

The ModRM byte encodes `reg` (destination) and `rm` (source) register fields:
- `C0` = reg=000 (xmm0), rm=000 (rax) → `movq xmm0, rax`
- `C8` = reg=001 (xmm1), rm=000 (rax) → `movq xmm1, rax`
- `C1` = reg=001 (xmm1), rm=000 (xmm0) → `ucomisd xmm0, xmm1`

**CRITICAL:** Do NOT use REX.B (0x49) for `movq xmm1, rax`. REX.B extends the RM field to r8 instead of rax. Use plain REX.W (0x48) with ModRM `C8`.

**Verification:** `66 48 0F 6E C0` = movq xmm0, rax ✓; `66 48 0F 6E C8` = movq xmm1, rax ✓; `66 0F 2E C1` = ucomisd xmm0, xmm1 ✓.

## 4. cvtsi2sd vs cvttsd2si Opcode Confusion

Two different SSE2 conversion opcodes:
- `F2 0F 2A /r` = `cvtsi2sd xmm, r/m64` — signed integer TO double (MIR_DITOF)
- `F2 0F 2C /r` = `cvttsd2si r64, xmm` — double TO signed integer (MIR_DTOI)

Using `0F 2C` when you mean `0F 2A` silently converts in the wrong direction.

## 5. NaN Handling via JP Jump

SSE2 `ucomisd` sets PF=1 (parity flag) when either operand is NaN. All ordered comparisons return false for NaN; only `!=` returns true.

Implementation pattern:
```
ucomisd xmm0, xmm1
jp nan_case          ; 0F 8A rel32 — jump if NaN
; ordered case:
setcc al             ; normal comparison
jmp end              ; E9 rel32
nan_case:
mov al, 1            ; for DNE (NaN != anything = true)
; or
mov al, 0            ; for all others (NaN compared = false)
end:
movzx rax, al
```

**CRITICAL:** Both JP and JMP positions MUST be `size_t` (see pitfall #1).

## 6. Shift Count Mask

For 64-bit shifts, use `b & 63` (not `b & 31`). The x86-64 SHL/SHR instructions mask the shift count to 6 bits (0-63) for 64-bit operands.

## 12. VR_ENC_SAFE Must Return False for DTOI/DTOI_U/FTOI (2026-09-15)

**Symptom**: Double-to-int conversion produces wrong results (e.g., `(unsigned long)3458764513821589504.0` gives 2048 instead of the correct value).

**Root cause**: `VR_ENC_SAFE(vr)` determines whether a VR holds a double value. It was listing `MIR_DTOI`, `MIR_DTOI_U`, and `MIR_FTOI` as producing doubles (returning `true`), but these ops CONVERT from double TO integer — their result is an integer.

**Fix**: `VR_ENC_SAFE` must return `false` for `MIR_DTOI`, `MIR_DTOI_U`, and `MIR_FTOI`:
```c
case MIR_DTOI: case MIR_DTOI_U: case MIR_FTOI:
    /* double/float-to-int: result is integer, not double */
    return false;
```

**Why this matters**: When the JIT emits `MIR_DTOI`, it first loads the source VR into rax. If `VR_ENC_SAFE` returns true (wrong), it uses `emit_mov_rax_from_vr` which loads from a register. If the VR was spilled to the stack, the register doesn't have the value. Returning false correctly uses `emit_load_rbp` to load from the spill slot.

**Also affects**: The `MIR_DITOF`/`MIR_DITOF_U` cases must return `true` (they produce doubles). `MIR_F32_TO_F64` and `MIR_F64_TO_F32` must return `true` (they produce floats).

## 14. Large 64-bit Constant Truncation via sext32 (2026-09-16)

**Symptom:** Large constants (e.g., `unsigned long x = 4884153795883304960UL`) return wrong values (2048 instead of the correct value). Double constants passed to external functions (like `ldexp`) are truncated to 0.0 or denormals. This is the root cause of BOTH the `function_calls_standard_library_call` gauntlet failure AND large-unsigned-constant failures.

**Root cause:** The IDENT handler or `mir_truncate_to_type` applies `sext32` (sign-extend 32-bit) truncation to U64 variables. The MIR shows `and v10 = v8, 0xFFFFFFFF` + `sext32` applied to a U64 variable. This zeros the upper 32 bits of the constant.

**Why this matters:**
- `ldexp(1.0, 2)` returns 0 instead of 4.0 — the double constant 1.0 (bit pattern 0x3FF0000000000000) is truncated to 0x0000000000000000 = 0.0 because the VR is spilled and the spill slot holds the truncated value
- `unsigned long x = 4884153795883304960UL` returns 2048 (the low 32 bits) instead of the full value
- Any double constant with non-zero upper 32 bits is corrupted
- Even with a correct mixed calling convention (XMM0+RSI), ldexp produces wrong results because the input value is already truncated before the call

**Diagnosis:** Look for `and vX = vY, 0xFFFFFFFF` followed by `sext32` in the MIR for U64 variables or double constants. The `mir_truncate_to_type` function should NOT apply I32 truncation to U64-typed variables. Check the variable's declared type before applying any truncation in the IDENT handler.

**Fix location:** `holyd_mir_eval.c`, IDENT handler and/or `mir_truncate_to_type`. Check the variable's type before applying truncation. **Fixing this single bug unblocks ldexp AND large unsigned constants — high priority.**

**Confirmed (2026-09-16 late):** The ldexp special-calling-convention code path in the JIT IS reached and emits correct x86-64 code. The ONLY reason ldexp fails is the truncated constant. Fix constant truncation → ldexp works without any JIT calling-convention changes.

## 15. Interval Splitting Requires JIT Spill/Reload Emission (2026-09-16)

**Symptom:** Enabling interval splitting in `wubu_mir_regalloc.c:446` (changing `if (0 && ...)` to `if (victim_vr >= 0 && victim_end > cur_end)`) causes score to drop from 1238→1056 (182+ new crashes/errors).

**Root cause:** The register allocator's split code sets `spill_after`, `stack`, and `split_until` fields on split fragments, but the JIT NEVER emits the actual spill-store or reload-load instructions at split points. `VR_ENC_SAFE` checks `spill_after` and returns -1 (spilled) past the split point, so the tail fragment reads garbage from a spill slot that was never written.

**Fix:** Before enabling interval splitting, implement JIT spill/reload emission: at each split point, emit a store from the register to the spill slot (spill) and a load from the spill slot back to a register (reload). This is a significant JIT change — not a one-line fix.

## 16. Static Local Hoisting Destabilizes Register Allocator (2026-09-16)

**Symptom:** Hoisting `static` local variable initializers to function top (for correct C semantics with `switch_skip_static_initializer`) breaks 9 tests.

**Root cause:** Allocating VRs and memory cells in the hoist phase shifts all subsequent VR numbering. The linear scan register allocator's choices are sensitive to VR numbering — different numbers produce different spill decisions, which cascade into different register assignments. Even though the hoisted init is semantically correct, the renumbering changes allocation decisions for unrelated VRs.

**Fix:** If hoisting static inits, either (a) allocate hoisted VRs from the HIGH VR range (above normal VRs) so numbering of existing VRs is unchanged, or (b) accept that hoisting requires a full gauntlet re-tune of the register allocator. Option (a) is lower-risk.

---

When making multiple JIT changes (NaN handling + float conversion + call-site conversion), test each change individually before combining. Interactions between changes cause regressions that are impossible to debug when bundled.

**Discipline**: Commit change A → run gauntlet 3x → commit change B → run gauntlet 3x → etc. Only combine after each change is verified neutral/positive.

**Why**: The gauntlet has ±3-6 test noise. A single run showing a -6 regression might be noise OR a real regression. Running 3x at each commit isolates the actual cause.

## 9. MIR_DITOF_U Low Part Zeroing Pitfall

**Symptom:** `MIR_DITOF_U` produces 0 for the low 32 bits of unsigned values, giving wrong results (e.g., `9223372036854776833ul` → `9223372036854775808.0` instead of `9223372036854777856.0`).

**Root cause:** Using `xor edx, edx` to zero-extend the low 32 bits before `cvtsi2sd`. This destroys the low part value:
```c
mov ecx, eax          ; load low 32 bits into ecx
xor edx, edx          ; BUG: zeros edx, losing the low bits!
cvtsi2sd xmm1, rdx    ; converts 0, not the low bits
```

**Fix:** Use `mov edx, ecx` to zero-extend from 32 to 64 bits:
```c
mov ecx, eax          ; load low 32 bits into ecx
mov edx, ecx          ; zero-extend to 64 bits (preserves value)
cvtsi2sd xmm1, rdx    ; converts the actual low bits
```

**addsd vs subsd:** Use `66 0F 58 C1` (addsd), NOT `66 0F 5C C1` (subsd). They differ by one byte.

## 11. MIR Pool Index vs x86-64 Register Encoding (2026-09-14)

**Symptom:** External function calls load arguments from wrong registers (e.g., `mov rax, rbx` instead of `mov rax, r13`), producing garbage values.

**Root cause:** `assign[vr].reg` stores the MIR allocator pool index (0-8), NOT the x86-64 register encoding. The mapping is:

| MIR pool index | x86-64 register | x86-64 enc |
|----------------|-----------------|------------|
| 0 | r10 | 10 |
| 1 | r11 | 11 |
| 2 | r12 | 12 |
| 3 | r13 | 13 |
| 4 | r14 | 14 |
| 5 | r15 | 15 |
| 6 | r8 | 8 |
| 7 | r9 | 9 |
| 8 | rdx | 2 |

When loading a VR into a specific register (e.g., for XMM staging), you MUST convert via `reg_x86[assign[vr].reg]` to get the x86-64 encoding. Using `assign[vr].reg` directly (e.g., 3) emits `mov rax, rbx` (x86 enc 3 = rbx) instead of `mov rax, r13` (x86 enc 13 = r13).

**Fix:** Use `VR_ENC_SAFE(vr)` (returns x86-64 encoding, but requires `i` loop variable in scope) or manually convert: `int vr_enc = reg_x86[assign[vr].reg];`

```c
// CORRECT: convert pool index to x86 encoding
int vr_reg = assign[vr].reg;
int vr_enc = (vr_reg >= 0) ? reg_x86[vr_reg] : -1;
emit_mov_rax_from_vr(e, vr_enc);  // emits mov rax, r13

// WRONG: uses pool index directly
emit_mov_rax_from_vr(e, assign[vr].reg);  // emits mov rax, rbx (BUG!)
```

**Symptom:** Nested `for` loops crash (segfault/illegal instruction) when the inner loop uses an assignment expression in BOTH the update AND the body. Examples that crash:
```c
for (int i = 0; i < 3; i++) { for (int j = 0; j < 3; j = j + 1) { ans = ans + 1; } }
```
Examples that work:
```c
for (int i = 0; i < 3; i++) { for (int j = 0; j < 3; j++) { ans = ans + 1; } }  // j++ not j=j+1
for (int i = 0; i < 3; i++) { for (int j = 0; j < 3; j = j + 1) { ans++; } }  // ans++ not ans=ans+1
while (i < 3) { while (j < 3) { ans = ans + 1; j++; } i++; }  // while loops work
```

**Root cause:** The register allocator assigns each spilled VR a unique stack slot via `-(next_spill_slot+1)*8`. But VRs that have NO interval (constants, memory addresses that are never loaded/stored as MIR operations) keep their initial values: `reg=-1, stack=0`. The `spill_off()` function maps ALL `stack=0` VRs to the same `spare_off` emergency slot. When multiple such VRs are live simultaneously (common in nested loops with many constants), they overwrite each other's spilled values, corrupting computation.

**Diagnosis:** Use `WUBU_DEBUG_REGS=1` to dump register assignments. Look for many VRs with `reg=-1, stack=0` — these all share the same spill slot.

**Fix:** After the main allocation loop in `wubu_mir_regalloc.c`, assign unique spill slots to all spilled VRs with `stack=0`:
```c
for (uint32_t v = 0; v < n_vr; v++) {
    if (assign[v].reg < 0 && assign[v].stack == 0) {
        assign[v].stack = -(next_spill_slot + 1) * 8;
        next_spill_slot++;
    }
}
```
Also verify the frame-sizing code in `wubu_isa_x86_64.c` (lines ~560-570) counts these new slots into `n_spilled` for the stack frame allocation.
