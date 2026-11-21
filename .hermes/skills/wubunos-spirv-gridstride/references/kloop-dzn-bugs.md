# K-LOOP DZN BUG: Debugging Transcript

## The problem
Replacing K-unrolled T_GEMM body with a structured SPIR-V k-loop to shrink module size
from 1.3MB → ~5KB (cutting dzn SPIR-V→DXIL translation from 13.4s → 0.05s).

All k-loop variants produce VALID spirv-val modules, but dzn 26.1.6 silently miscompiles
them: the loop runs 1-2 iterations then exits, regardless of K.

## Timing proof (vk_run_time.c instrumented)
```
64³ unrolled dzn:  shader=0.001s  pipe=13.365s  dispatch_wait=0.004s  total=13.370s
64³ trivial dzn:   shader=0.000s  pipe=0.025s   dispatch_wait=0.000s  total=0.025s
```
→ 99.7% of wall time is vkCreateComputePipelines (SPIR-V→DXIL translation of 1.3MB module).
Kernel execution is 4ms.

## Pipeline cache attempt
VkPipelineCache to persist compiled DXIL pipeline between runs:
- Build: ✅ clean
- Run: SIGSEGV (exit 139) — dzn 26.1.6 segfaults when passing VkPipelineCache to
  vkCreateComputePipelines, even with an empty cache.
→ dzn does not support pipeline caching for compute shaders. Dead end.

## GLSL repro (works, isolates the bug)

### GLSL source:
```glsl
#version 450
layout(local_size_x = 1) in;
layout(std430, binding = 0) buffer S { uint64_t g[200]; };
void main() {
  g[10] = 0; g[11] = 0;  // slot2=k counter, slot3=acc
  for (uint iter = 0u; iter < 9u; iter++) {
    uint k = uint(g[10]);
    if (k >= 9u) break;
    g[11] += 1;            // acc += 1 (FMA equivalent)
    g[10] = uint64_t(k+1); // k += 1
  }
}
```
### Result on dzn (sz=9, K=9):
```
cell[10] = 9   ← loop counter reached 9 (ran 9 iterations)
cell[11] = 9   ← acc = 9 (all 9 FMAs accumulated)
```
→ dzn CAN execute SSBO-counter k-loops correctly.

### GLSL-generated SPIR-V loop structure (glslang):
```
%24 = OpLabel                           ; loop header
      OpLoopMerge %26 %27 None          ; merge=%26, continue=%27
      OpBranch %28
%28 = OpLabel                           ; body entry
      %29 = OpLoad %uint %iter          ; load loop counter (FUNCTION variable)
      %32 = OpULessThan %bool %29 %uint_9
      OpBranchConditional %32 %25 %26   ; k<K → body(%25), else merge(%26)
%25 = OpLabel                           ; accumulate
      %34 = OpAccessChain ... %int_10   ; g[10] (k counter, SSBO)
      %35 = OpLoad %ulong %34
      %36 = OpUConvert %uint %35        ; k = uint(g[10])
      %37 = OpLoad %uint %k             ; k (function var)
      %38 = OpUGreaterThanEqual %bool %37 %uint_9
      OpSelectionMerge %40 None
      OpBranchConditional %38 %39 %40   ; if(k>=9) break → merge
%39 = OpLabel
      OpBranch %26                      ; break
%40 = OpLabel                           ; main work
      ... acc += 1, k+1, store ...
      OpBranch %27                      ; continue
%27 = OpLabel                           ; loop continue
      %52 = OpLoad %uint %iter          ; iter++
      %54 = OpIAdd %uint %52 %int_1
      OpStore %iter %54
      OpBranch %24                      ; back-edge → header %24
%26 = OpLabel                           ; merge (loop exit)
      OpReturn
```

### KEY OBSERVATION
glslang uses a **function-private variable** `%iter` (OpVariable in Function scope) for
the loop counter, NOT SSBO. The SSBO (g[10]) holds the k value read each iteration.
So the loop counter `iter` is in private memory, while `k`/`acc` values are in SSBO.

Our emitter carries ALL state in SSBO (no function-private variables).

## Our emitter attempts (all failed)

### Variant 1 (initial, committed at 6941c2a):
```
khdr = Label, AC(kptr), LD(kload), ULessThan, LoopMerge, BranchCond  ; header has LoopMerge mid-block
kbody = Label, FMA, Store acc, Branch kcont
kcont = Label, k+1→kptr, Branch khdr  (back-edge)
kmer  = Label, LD acc  (merge)
```
- spirv-val: ✅ RC=0
- dzn: ❌ acc=2 (ran 1 iteration, K=16); slot2(k)=2

### Variant 2 (moved LoopMerge to right after Label):
```
kpre = Label, LoopMerge, Branch khdr
khdr = Label, AC, LD, ULessThan, BranchCond
```
- spirv-val: ❌ "OpLoopMerge must immediately precede Branch" (instructions between L and M)

### Variant 3 (preheader + header, back-edge to khdr):
```
kpre = Label, LoopMerge(kmer,kcont), Branch khdr
khdr = Label, AC, MB, LD, ULessThan, BranchCond(kbody|kmer)
kbody = Label, FMA, Branch kcont
kcont = Label, k+1, Branch khdr  ← back-edge to khdr
```
- spirv-val: ❌ "Back-edges can only be formed between a block and a loop header"
  (the body→continue edge is forward, but spirv-val sees the structure wrong)

### Variant 4 (added MemoryBarrier in kcont):
Same as Variant 3 + OpMemoryBarrier before back-edge.
- spirv-val: ✅
- dzn: ❌ acc=2 (MB doesn't fix the structural issue)

### Variant 5 (kpre IS header — LoopMerge + Branch kbody):
```
kpre  = Label, LoopMerge(kmer,kcont), Branch kbody  ; header
kbody = Label, LD k, ULessThan, FMA, Branch kcont   ; body (with test inside!)
kcont = Label, k+1, Branch kpre                      ; back-edge
kmer  = Label, LD acc
```
- spirv-val: ❌ (back-edge rules violated, kbody mixes header test into body)

### Variant 6 (Function-private variable for k):
Would require adding OpVariable(Private) support to the emitter — NOT currently
supported. The emitter emits all variables as SSBO. This is the glslang approach
but needs new infrastructure (private pointer types, variable declaration in entry).
- Status: NOT ATTEMPTED (would need significant emitter changes)

## Hypothesis
dzn 26.1.6 has a SPIR-V validation/consumption bug where structured loops carrying
memory state in SSBO scratch cells across iterations are miscompiled when the header
block has any instructions between Label and LoopMerge (other than the glslang pattern
with function-private iter counter).

The only proven-working patterns:
1. glslang's function-private-variable counter (requires emitter change)
2. Unrolled body (1.3MB module, 13.4s translation — works correctly)

## llvmpipe (lvp_icd.json) — also broken
```
VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json
vulkaninfo --summary  → ✅ llvmpipe device found
vk_run → hangs (120s timeout), no result, no error
```
lvp resolves and starts execution but vkQueueWaitIdle never returns.
Both unrolled and k-loop modules hang identically on lvp.

## References
- dzn ICD: `/usr/share/vulkan/icd.d/dzn_icd.json` (driverID=MESA_DOZEN, Mesa 26.1.6)
- lvp ICD: `/usr/share/vulkan/icd.d/lvp_icd.json` (llvmpipe, pure software)
- vk_run.c timing instrumentation: `/tmp/vk_run_time.c`
- GLSL repro shader: `/tmp/kloopt.comp` → `/tmp/klssbo.spv`
