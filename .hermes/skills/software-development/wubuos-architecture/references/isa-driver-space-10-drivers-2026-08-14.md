# ISA Driver Space — 10 Drivers (2026-08-14)

Reference for `wubuos-architecture` skill.

## Driver Inventory

| Driver | Type | Host-testable | Status |
|--------|------|---------------|--------|
| x86-64 | Native JIT + regalloc + peephole | ✅ | Fully tested |
| ARM64 | Native JIT + regalloc | ❌ (needs ARM64 hw) | Driver correct, untestable on x86-64 |
| MIPS | Interpreter | ✅ | Registered, not fully tested |
| 8051 | Interpreter | ✅ | Registered, encoding bugs remain |
| 8086 | DOS emulator | ✅ | Fully tested |
| M68K | Interpreter | ✅ | Fully tested |
| 6502 | Interpreter | ✅ | Fully tested |
| RISC-V | Interpreter | ✅ | Fully tested |
| Z80 | Interpreter | ✅ | Fully tested |
| PTX | ptxas + CUDA | ⚠️ (needs GPU) | Works on RTX 4050 |

## Key Insight

**ARM64 native JIT cannot run on x86-64 hosts** — it emits ARM64 machine
code. This is expected, not a bug. The `test_isa_driver` only tests 6
interpreter-based drivers on x86-64. When adding new drivers to the test
battery, use the `WUBU_ISA_NATIVE` exec flag to skip native JITs on
non-native hosts:

```c
#if !defined(__aarch64__) && !defined(__arm__)
    if (d->exec == WUBU_ISA_NATIVE) {
        /* skip — native JIT needs native host */
        return -1;
    }
#endif
```

## Optimizer Infrastructure (2026-08-14)

The MIR optimizer (`src/compiler/wubu_mir_opt.c/h`) runs 6 passes:

| Pass | Flag | What it does |
|------|------|--------------|
| Constant folding | `MIR_OPT_FOLD` | Eval binops on constants at compile time |
| Strength reduction | `MIR_OPT_STRENGTH` | x*2→x<<1, x/2→x>>1, x*1→x, x+0→MOV |
| Dead code elimination | `MIR_OPT_DCE` | Remove instructions whose result vr is never used |
| Loop-invariant code motion | `MIR_OPT_LICM` | Hoist pure computations out of loops |
| Loop unrolling | `MIR_OPT_UNROLL` | Unroll loops with small constant trip counts |
| Instruction combining | `MIR_OPT_COMBINE` | Placeholder — merge chains of binops |

The fold+DCE runs to fixpoint (fold creates dead code, DCE removes it).

## Register Allocation (2026-08-14)

`src/compiler/wubu_mir_regalloc.h/c` — linear-scan allocator on SSA-form MIR.

- API: `wubu_mir_alloc_regs(prog, n_phys_regs, &count)` → `wubu_reg_assign_t*`
- Each assignment has `.reg` (physical reg index, or -1 if spilled) and `.stack` (spill offset)
- Pre-assigns v1..n_args to phys regs 0..n_args-1 (NOT v0 — it's the implicit return reg)
- v0 is NOT pre-assigned (it's the return register that RET reads from)

**x86-64 driver**: 10 physical regs (r10-r15, rbx, r8-r9, rdx). rax reserved
as accumulator, rdi as 2nd-operand scratch, rcx for shifts.

**ARM64 driver**: 20 physical regs (X8-X27). X0 = return/accumulator.

## Peephole Optimization (2026-08-14)

`src/compiler/x86_peephole.c` — post-codegen pass over emitted bytes:

1. `eliminate_self_mov` — remove `mov r,r` (same register)
2. `shrink_movabs` — `movabs reg, imm64` → `mov r32, imm32` when imm fits in 32 bits
3. `eliminate_store_reload` — remove `mov dst,rax; mov rax,dst` pairs

The `shrink_movabs` uses a separate output buffer (not in-place) to avoid
corrupting overlapping patterns.

## Store-Reload Elimination (2026-08-14)

In the x86-64 driver's compile loop, a lookahead skips the store when the
next instruction is RET consuming the same dst vr:

```c
int result_in_rax = 0;
// In binary op handler:
if (NEXT_IS_RET(in->dst)) { result_in_rax = 1; }
else { STORE_VR(rax, in->dst); }
// In RET handler:
if (!result_in_rax) { LOAD_VR(in->a, rax); }
```

This eliminated the `mov r12,rax; mov rax,r12` pair (29% code size reduction
on `7*6`: 49→35 bytes).

## x86-64 Encoding Bugs Fixed (2026-08-14)

1. **emit_mov_reg modrm**: `0x89` is `MOV r/m64, r64` — reg field is SOURCE,
   rm field is DESTINATION. The modrm byte must be `0xC0 | (src<<3) | dst`,
   NOT `0xC0 | (dst<<3) | src`. REX.R extends reg (src), REX.B extends rm (dst).

2. **Shift encoding**: `shl rax, cl` needs `mov rcx, b` first. The `mov rcx, src`
   encoding: `rex(1, reg_needs_rex(src), 0, 0); 0x89; 0xC0 | ((src&7)<<3) | 1`.
   The `1` in the rm field is rcx's encoding.

3. **movabs shrink**: Only match `0x48`/`0x49`/`0x4C`/`0x4D` + `0xB8+rd`.
   Do NOT match `0x41 0xB8+rd` (that's already a 32-bit `mov r8d, imm32`).

## ARM64 Encoder Bug Fixed (2026-08-14)

`warm64_stp_pre`/`warm64_ldp_post` used `(imm7 / 8) & 0x7F` — C integer
division truncates toward zero, so `-2 / 8 = 0`. Fixed to `(imm7 & 0x7F)`
since callers already pass the value in units of 8 bytes.

## Workflow Pitfalls (2026-08-14)

1. **Subagent duplication**: Subagents were dispatched to build MIR interpreters
   that ALREADY EXISTED (m68k_interp.c, z80_interp.c). Always survey existing
   code BEFORE dispatching subagents. Check `src/runtime/wubu_*_interp.c` and
   `src/compiler/wubu_isa_*.c`.

2. **Force-push to shared branch**: NEVER force-push to `wubu-integration`
   (shared with buddy agent). Always `git pull --rebase` then fast-forward push.

3. **8-bit overflow**: 8-bit drivers (6502, Z80, 8051) truncate results to 8 bits.
   The album test accounts for this with `expected_8bit = value % 256`.

4. **Test battery coverage**: The `test_isa_driver` has a hardcoded name list.
   Adding new drivers to the list without fixing their encoding bugs will
   crash the test. Fix drivers BEFORE adding them to the battery.

## Benchmark Results

- x86-64 JIT compile: 0.5 μs (no toolchain needed)
- x86-64 JIT run: 7.6 ns/iter (3x faster than 8086 interpreter)
- GCC -O2: ~0.4 ns/iter (18x faster, but needs full compile+link)
- 7*6 code: 49 bytes → 35 bytes (29% smaller) after store-reload elimination
