# Vulkan/SPIR-V backend: known gaps and what has been ruled out

State of the GPU backend. Read before attempting a fix; the dead ends are
listed so they are not retried. Everything here is measured, not inferred.

## What WORKS (verified against x86-64 and the interpreter)

- Straight-line register arithmetic: add, sub, div, mod (incl. negative
  `%` via `OpSRem` 138, C truncation), shifts, bitwise NOT.
- The f64 core: arithmetic, the six ordered comparisons, and conversions.
  Matches x86-64 bit-for-bit. Needs the conditional `Float64` capability
  (enum 10) or `spirv-val` rejects the module.
- Scalar programs use `LocalSize 1`; `MIR_T_GEMM` programs keep 64 lanes.

## What is BROKEN

- **Any program that dereferences memory** (arrays) returns 0 where the
  interpreter returns the right value.
- `MIR_BREAK`/`MIR_CONTINUE`: not a case arm -- see below.
- `MIR_CALL`: architecturally blocked -- see below.
- f16/bf16, int8 quantize, and four tensor ops are unimplemented.

## Array indexing: the ground truth

Instrument `op_load`/`op_store` in `wubu_mir_interp.c` (the ORACLE) to print
`addr = vr[in->a]`. For `int a; a[0]=7; a[1]=9; a[0]*a[1]`:

    STORE addr_vr=7     -> byte 0 = 7
    STORE addr_vr=14    -> byte 8 = 9
    LOAD  addr_vr=20    -> byte 0     = 7
    LOAD  addr_vr=26    -> byte 8     = 9
    result = 63

**User cells live at BYTE 0 and BYTE 8.** The `addr_vr=65537 -> byte 16`
accesses that also appear are POINTER FETCHES (loading the array base), not
element accesses -- misreading those as aliasing wasted an attempt.

The emitter maps `element = addr + 1`, deliberately keeping element 0 free
as a return slot. That is right only for byte 0:

    byte 0 -> element 1   (accidentally correct)
    byte 8 -> element 9   (should be 1)

So `a[0]=7` lands and `a[1]=9` lands 8 elements out. The generated module
shows exactly one useful `OpStore`, and a cell dump shows `cell[1]=7,
cell[2]=0`. The uniform mapping is `element = addr / 8`.

## The three sizes that must agree

Changing addressing, the return slot, and the read-back together is what
produces a silent all-zeros result -- the three must be updated as one:

1. `ncells` in the emitter's `OpTypeArray` (`scratch_base + 64*4 + N`)
2. `s.scratch_base` (first scratch element)
3. `g_cells` in `wubu_isa_vulkan.c`, passed to `vk_run` as `mem_cells`,
   which becomes `bufsz = mem_cells * 8`

## Ruled out (measured -- do not retry)

- `idx = addr >> 3` alone: puts user memory at element 0, colliding with
  the return slot the epilogue writes.
- Sizing from a `MIR_CONST` scan of address VRs: addresses are computed at
  RUNTIME through `MIR_LOAD`/`MIR_ADD` chains, so the high-water mark is not
  statically knowable. `p->total_mem` is a CELL count despite its
  "BYTES" comment, so it is not a byte bound either.
- Changing all three coupled pieces in one attempt (regressed all 7 cases
  to 0 -- the sizes above went out of step).

**Open question:** after a correct image shift, only ONE of the two stores
reaches a live slot. The second store's address VR holds a runtime-computed
offset that the emitter appears to lose. That is a VR-tracking bug, not
arithmetic -- so do not try more index formulas.

## Break/continue is not a case arm

`MIR_BREAK`/`MIR_CONTINUE` are lowered to `MIR_JZ`/`MIR_JNZ` before codegen
(verified: `has_BREAK=0 has_CONTINUE=0` in the final MIR), so they never
reach a backend. An attempt to emit them directly failed structurally:
after `OpBranch` a fresh block is required, and adding one produced two
consecutive `OpLabel`s because the existing jump machinery already emits a
label there. Needs a change to the emitter's block-emission discipline, not
a new case.

## MIR_CALL is architecturally blocked

The emitter produces exactly ONE `OpFunction` (the shader entry point) and
never emits `OpFunctionCall`; all instructions are inlined flat. The
interpreter implements calls by SNAPSHOTTING the whole VM state (all
registers + all memory) and recursing, bounded by `MIR_MAX_CALL_DEPTH`. A
shader has no stack and no recursion, so calls cannot be inlined without a
static bound this IR does not carry. The subtle part: a real function call
would clobber caller registers, which the interpreter's snapshot explicitly
prevents -- a semantic difference, not an implementation detail.

## Verify like this

Run each source through THREE paths and compare: the GPU backend, the native
x86-64 backend, and `wubu_mir_interp`. When native and interpreter agree and
the GPU does not, the GPU backend is at fault. When native and interpreter
disagree with each other, suspect your probe first -- see
`references/isa-run-arg-is-a-memory-pointer.md`.
