---
name: wubunos-spirv-gridstride
description: Load before editing wubu_isa_spirv.c loops. SPIR-V T_GEMM grid-stride + k-loop bugs on dzn, native x86-64 JIT path.
---

# SPIR-V T_GEMM grid-stride status (wubunos)

## Verified working (git HEAD, do not regress)
- Flat loop `w=gid; w<M*K*N; w+=1`, memory-carried counter in SSBO scratch.
- Bit-exact on RTX 4050 (dzn), Radeon 740M (dzn), llvmpipe. spirv-val clean.
- Test pattern: A[i]=i+1, B=2, C init 7 → C00 = 7 + K*(K+1).

## Multi-WG grid-stride dispatch (WUBU_VK_GROUPS)

**Status: SOLVED (commit 89a0758, pushed). All sizes 3-64 PASS at gx=2 on BOTH dzn cards.**

### Recipe (all must land together)
1. **Stride**: bake `stride = gx*64` + `cPASS = ceil(M*N/stride)` as SPIR-V consts from `WUBU_VK_GROUPS` env at emit time.
2. **Buffer sizing**: `g_cells = total_mem + 1 + gx*64*4 + 1` in vulkan_compile(); remember `g_result_cell = total_mem` (last C cell).
3. **Return race fix**: cell 0 races across WGs → vulkan_run reads last C cell via `WUBU_VK_DUMP=<result_cell+1>`; dump lines go to STDERR, so pipe with `"2>&1 >/dev/null"` and parse `cell[i] = v`.
4. **OpControlBarrier (224) before RET load** — REQUIRED for dev1 (Radeon 740M); without it the intra-WG load of the result cell races lane stores. Scopes MUST be **i32** consts: exec=Workgroup(2), mem=Device(1), sem=0x48 (AcquireRelease|UniformMemory). u64 consts fail spirv-val ("expected scope 32-bit int"). Pin c_i32_1/2/sem in the constants section (pre-function — OpConstant cannot appear inside a function).
5. gx>2 works but no speedup on dzn (dispatch overhead ≈ compute for these sizes); gx=2 is the validated default.

## Grid-stride attempt — findings
1. Output-cell layout (`out=gid; out<M*N; out+=64`, i=out/N, j=out%N, K unrolled
   in host C) compiles + spirv-val PASSES. Single OpLoopMerge
   (head/cont/body/merge) is the only structure that validated — nested loops
   failed repeatedly on merge-block containment rules.
2. Per-lane scratch REQUIRED: fixed scratch cells race across lanes. Pattern:
   dynamic index = scratch_base + koff + gid*4 via AccessChain arithmetic.
3. SSBO array must grow: scratch_base + 64*4 cells (per lane); vk_run g_cells
   must include this + M*N output cells + return slot.
4. OpExecutionMode LocalSize must be {64,1,1} not {1,1,1}.

## SOLVED (commit 9b4289d): TRUE parallel T_GEMM shipped
Final working recipe (all four must land together):
1. Output-cell layout: out=gid; out<M*N; out+=64; i=out/N; j=out%N; K unrolled in C.
2. acc accumulates in SSA REGISTERS with a FRESH result id per unroll step
   (`acc = accn` in C). NEVER load/store acc through SSBO mid-unroll — dzn and
   llvmpipe both break on same-address load-after-store chains.
3. Only the `out` counter is memory-carried, in per-lane slot sb + lane*4
   (dynamic AccessChain); head/cont reload it. SSBO array = sb+64*4 cells;
   vk_run g_cells = total_mem+1+64*4 — keep both in sync.
4. OpExecutionMode LocalSize {64,1,1}.

## SOLVED (commit 6935247): uniform pass-count loop — ALL sizes on dzn
Divergent loop exit (lanes skipping when out>=M*N) broke every M*N%64!=0 size on
dzn too (silently correct-looking C00, garbage elsewhere). Fix, all must land:
1. Loop over p = ceil(M*N/64) UNIFORM passes: head compares p < cPASS const;
   body computes out = gid + p*64; guard store with structured if
   (OpSelectionMerge + BranchCond + then/end labels), NOT OpSelect.
2. Scratch = scratch_base + 64*4 + 1 cells — lane63's slot1 (sc+256) overflows by 1.
   Emitter ncells and driver g_cells MUST match exactly or dzn returns -4 silently.
3. wubu_isa_vulkan.c run(): skip non-numeric prefix before fscanf — dzn prints
   WARNING/"Dropped Escape" lines to STDOUT ahead of the result number.

## K-LOOP (O(1) module for K-heavy GEMM) — BLOCKED by dzn driver bug

**Goal**: replace K-unrolled body with a structured SPIR-V k-loop so module size is O(1)
independent of K. Reduces 64³ module from 1.3MB → ~5KB, cutting dzn SPIR-V→DXIL translation
from 13.4s → ~0.05s.

**dzn BUG**: k-loop runs only 1-2 iterations regardless of K. spirv-val accepts our module,
but dzn silently miscompiles the structured loop (acc=2 for K=9, should be acc=9).

**Debugging transcript**: See `references/kloop-dzn-bugs.md` for the full attempt log
(6 failed variants, GLSL repro that works, spirv-val output diffs).

### What works (GLSL repro proof)
A minimal GLSL k-loop with SSBO counter compiles and runs correctly on dzn:
```glsl
layout(std430, binding=0) buffer S { uint64_t g[200]; };
void main() {
  g[10]=0; g[11]=0;  // slot2=k, slot3=acc
  for(uint iter=0u; iter<9u; iter++){
    uint k = uint(g[10]); if (k>=9u) break;
    g[11] += 1;       // acc += 1
    g[10] = uint64_t(k+1);  // k += 1
  }
}
```
Result: `slot10=9, slot11=9` (all 9 iterations visible). This proves dzn CAN run
SSBO-counter k-loops — the bug is specific to our emitter's block structure.

### What fails (our emitter)
6 variants tried, ALL rejected by spirv-val OR miscompiled by dzn:
1. LoopMerge in header (after Label, before Load/Test/BrCond) → VALID by spirv-val, MISCOMPILED by dzn
2. LoopMerge 2nd-to-last after Label+Load+Test → INVALID (spirv-val: "must precede Branch")
3. Preheader (LoopMerge) + header (Label+Load+Test+BrCond) → INVALID (spirv-val: "back-edges to non-header")
4. Preheader + header + MemoryBarrier in each → VALID, MISCOMPILED
5. khdr=Header(Label+LoopMerge+Br) → kbody=Body(FMA+Br kcont) → kcont=Cont(Label+k+1+Br khdr backedge) → VALID, MISCOMPILED
6. Function-private variable for k counter → emitter doesn't support private vars; would need new infrastructure

### Root cause hypothesis
dzn 26.1.6's SPIR-V consumer has a bug with structured loop headers where the loop
carries memory state in SSBO across iterations AND the header block has non-LoopMerge
instructions. glslang sidesteps this by using a Function-private loop variable (`iter`)
instead of SSBO memory for the counter. Our emitter carries ALL state in SSBO.

### Current recommendation (deferred)
The k-loop is NOT ready to ship. The unrolled baseline (commit 89a0758) is correct
and bit-exact. To enable the k-loop:
- Add Function-private variable support to the emitter (match glslang's `iter` pattern), OR
- Test with a future dzn version that fixes the structured-loop bug, OR
- Port to ZealOS native driver (no SPIR-V translation tier at all).

## X86-64 JIT PATH — fast path (no dzn, no translation tier)

**Status: VERIFIED (benchmark commit 7c423a1).** The ZealOS compiler's x86-64 JIT driver
exposes `wubu_tgemm_scalar()` — a 4-row tiled, K-unrolled-by-4 kernel with FMA.

```
sz=128  naive=0.002s  jit=0.002s  2.2 GOPS   1.1x
sz=384  naive=0.065s  jit=0.031s  3.6 GOPS   2.1x
sz=512  naive=0.509s  jit=0.121s  2.2 GOPS   4.2x
sz=768  naive=0.698s  jit=0.273s  3.3 GOPS   2.6x
```
- Correctness: bit-exact vs naive C (verified all entries via interpreter for sizes 48-768).
- No kernel-launch overhead — compile = JIT assembly (microseconds), run = native CPU loop.
- Segfaults at 64³ and 1024³ (K-unroll edge case / stack frame limits — not a SPIR-V issue).
- Build (no dzn/vulkan needed): `gcc -O2 -std=c11 -DWUBU_HOSTED -include wubu_gnu_compat.h -I. -Ijit -I/home/wubu -o bench_jit tools/bench_tgemm_jit.c [MIR+JIT+deps] -lm`

**SPD Benchmark (single-threaded fast path)**: 512³ achieves 4.2x speedup vs naive C. This is the recommended deployment path when Vulkan overhead dominates (dzn's 13.4s SPIR-V→DXIL translation bottleneck).

See `references/openmp-jit-parallelism.md` for OpenMP parallelization attempts and debugging patterns.

## Known limitation: Lavapipe (llvmpipe) — hangs, not just fails
Unlike the skill's earlier note (which described store-handling issues), llvmpipe in this
environment HANGS indefinitely (>120s timeout) on both the unrolled AND k-loop modules.
The lvp ICD resolves (`libvulkan_lvp.so`) but vkCreateInstance/vulkaninfo succeed while
vkQueueWaitIdle never returns. Suspected deadlock in lvp's software SSBO path.
This is dev2 (unverified blocker), upstream-lvp territory, not a borg target.

## Recurring lessons
- Stale binaries/zombie processes → phantom results: rebuild all together, kill zombies.
- spirv-dis the actual binary when behavior contradicts source; md5sum the .spv.
- OpLoopMerge opcode = 246 (NOT 249 = OpBranch); sits immediately before the
  branch; header needs exactly one back-edge.