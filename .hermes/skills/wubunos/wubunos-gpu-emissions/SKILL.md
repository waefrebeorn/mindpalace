---
name: wubunos-gpu-emissions
description: Use for WuBuNOS GPU codegen or ptxas/spirv-val debugging.
---

# WuBuNOS GPU Emissions Stack

Two GPU backends consume the same `wubu_mir_t`. Repo: `/home/wubu/wubunos` (flat, no src/).

## PTX driver (`wubu_isa_ptx.c`) — NVIDIA, real execution

- Pipeline: MIR → PTX text → `ptxas -arch=sm_89` → cubin → `gpu_host_stub` (libcuda) → result int64 via `/tmp/ptx_result_<pid>.txt`.
- **Hardware-aware**: `gpu_host_stub --probe` dumps device profile (SMs, max_threads_per_block, shmem, warp size) parsed into `g_gpu_profile`. Codegen sizing comes ONLY from probe — no hardcoded limits. Fallback = scalar profile if no GPU.
- **Parallel T_GEMM**: grid-stride row loop — row = tid, tid+S...; S = min(M, probed max threads/block). Scratch regs are a DYNAMIC window above all program VRs (`B0 = e->n_vregs; e->n_vregs += 11`) — hardcoded %r48-58 collided with program VRs in bigger programs. Block barriers (`bar.sync 0`) order fill→GEMM→consume.
- Launch config in gpu_host_stub.cu: ONE block × 1024 threads (bar.sync requires same block).
- Scalar programs stay bit-exact via redundant idempotent execution (every thread runs the same MIR stream).
- Verified: 3x3 checksum 621 PASS, fuzz 200/200 match-all, T_GEMM 576/576 vs naive C.

### GPU test memory starvation pitfall

`gpu_host_stub` itself is lightweight — it launches a single CUDA kernel and
exits. The memory hog is the **parent test process** that loads the model
weights (e.g. a 27B GGUF at 16.7 GB on disk → ~12.8 GB anon RSS once paged in)
before spawning `gpu_host_stub` to execute kernels. On a 14 GB system, the
parent + gateway (~400–660 MB RSS) together exceed available RAM.

Both the test process and the gateway share the same high `oom_score_adj`
(default 200 under the Hermes s6 service), so the OOM killer does not
distinguish them — it kills whichever is unlucky at kill time. Because the
gateway is the parent process, a kill of the child's sibling or the parent
itself crashes the entire gateway, which systemd then restarts (often mid-test,
restoring a partially-corrupted session state).

**Diagnosis**: check `~/.hermes/logs/gateway-shutdown-diag.log` for
`Killed process` lines with high `anon-rss` and `task_memcg=...hermes-gateway`;
check `errors.log` for `system memory pressure is critical` repeating across
days. See `hermes-maintenance` → "Diagnose gateway OOM / unclean exits".

**Mitigation**: run the GPU test with a cgroup memory limit or `ulimit -v` so
only the test process is killed, not the gateway. Lower the gateway's
`oom_score_adj` (or raise the test process's) so the OOM killer targets the
child exclusively.

## PTX emission gotchas (hard-won)

- f32/f64/bf16 values live as bit patterns inside .b64 VRs. PTX forbids width-mismatched `mov.b32` — use shared-memory bridge `.shared .b64 sb[4]`: `st.shared.b64 [sb[0]],%r; ld.shared.b32 %w0,[sb[0]]` etc.
- Shift counts must be `.u32`: extract low 32 bits first.
- Labels must NOT start with `.L_` (ptxas treats it as directive).
- Rounding modifiers REQUIRED: `div.rn.f32`, `cvt.rn.f64.s64`, `cvt.rni.s64.f32` (int conversions use `.rni`).
- **FMA/MAD fusion peepholes** at emission: FMUL(d1,a,b)+FADD(d2,d1,c) → `fma.rn.f32`; MUL+ADD → `mad.lo.s64`; SUB variant negates addend into rd2 first.

## PTX module + launch gotchas (apply to ANY PTX emitter, not just the ISA backends)

- **Declare EVERY register the kernel uses, including predicates.** `setp.ge.u32 p0, ...` with no `.reg .pred p0, p1;` fails to assemble (CUDA_ERROR_INVALID_PTX = 218). Put predicates in the same `.reg` block as the general registers.
- **Special registers are read-only scalars, not arithmetic operands.** Both `%ctaid.x * %ntid.x + %tid.x` and `mul.lo.u32 d, a, %ntid.x` are rejected ("Parsing error near '*'" / "Special register argument not allowed"). `mov` each special register into a general register first, THEN compute.
- **The exec path's kernel name must match the emitter's `.entry` name.** A mismatch returns CUDA_ERROR_INVALID_HANDLE (400) and looks like a PTX problem. Grep the emitter for the name it actually writes before debugging the PTX.
- **`cuLaunchKernel`'s `kernelParams[i]` is the ADDRESS OF the i-th parameter value.** If the caller hands you `void *args[]` where `args[i]` already holds `&param_i`, pass `args[i]` — NOT `&args[i]`. Passing the slot address makes the kernel treat a host stack address as a device pointer and write its results into the host stack, corrupting the heap; this surfaces later as a segfault in an unrelated `free()`.
- **`cuMemAlloc` needs a current context** — `cuCtxCreate` first, or every allocation returns CUDA_ERROR_INVALID_CONTEXT (201) / NOT_INITIALIZED (3).
- **Get the real ptxas diagnostics instead of the bare code.** `cuModuleLoadData` only returns 218; use `cuModuleLoadDataEx` with `CU_JIT_ERROR_LOG_BUFFER` + `CU_JIT_ERROR_LOG_BUFFER_SIZE_BYTES` (BYTES — there is no `..._BYTESIZE`) to receive `ptxas application ptx input, line N; error : ...`.
- **A toolkit older than the device's compute capability has no native arch.** Emit PTX only (`-gencode arch=compute_XX,code=compute_XX`) and let the driver JIT it forward; verify with a standalone host smoke kernel before blaming the emitter.
- **Host-side isolation beats guessing:** replicate the exec path's CUDA call sequence in a standalone probe (one call per step, printing each result) to find which step actually fails, instead of instrumenting the library.

## SPIR-V emitter (`wubu_isa_spirv.c`) — ALL Vulkan cards

- Hand-encoded binary SPIR-V, NO GLSL/shader compiler in codegen path. `spirv-val` is the test oracle only (same relation ptxas has to PTX driver). One emitter runs NVIDIA dGPU + AMD iGPU + llvmpipe.
- ABI: binding 0 SSBO `u64 mem[N+1]` (cell 0 = return slot), push constant `{i64 arg}`, LocalSize 64, entry "main".
- **Logical layout order (spec §5.4, spirv-val enforces)**: capabilities → memory model → entry point (+ interface list must include Input vars!) → execution mode → debug → **ALL OpDecorate/OpMemberDecorate** → types/constants → variables → function.
- Member-decorate Block structs with OpMemberDecorate(72) Offset(35).
- Storage classes: StorageBuffer=12, PushConstant=9, Input=1. ArrayStride decoration=6. Capability Int64=11 (NOT 39/41 — those are Int8/SparseResidency).
- **Opcodes verified by spirv-as round-trip** (blog numbers were wrong): IADD=128 ISUB=130 IMUL=132 AND=199 OR=197 XOR=198 NOT=200 SNEG=126 SHL=196 SHR_L=194 SHR_A=195 SDIV=135 SREM=138 EQ=170 NE=171 ULT=176 ULE=178 UGT=172 UGE=174 SLT=177 SLE=179 SGT=173 SGE=175 SELECT=169 UConvert=113 CopyObject=83.
- Constants CANNOT appear inside functions — pre-pass hoists every distinct imm to section 09, in-function uses OpCopyObject.
- Probe: `tools/vk_probe.c` enumerates all devices w/ limits. Runner: `tools/vk_run.c`.

## SPIR-V float path (verified on Radeon 740M + RTX 4050)

- MIR keeps f32 bits in the low 32 of i64 VRs. Unpack: `OpBitcast(124) u64->v2i32`, `OpCompositeExtract(81) elem 0 -> i32`, `OpBitcast -> f32`. Repack: Bitcast f32->i32, CompositeConstruct(80) `{lo, zero}`, Bitcast v2i32->i64.
- Float opcodes (spirv-as round-trip verified): FAdd=129 FSub=131 FMul=133 FDiv=136 FNegate=127 FOrdEqual=180 FOrdLessThan=184 Select=169.
- FEQ/FLT: compare to bool, then `OpSelect u64 {1, 0}`.
- TRAP: TypeFloat operands are `{result_id, width}` — swapping them silently duplicates an id.
- Fuzz oracle policy: each backend compares independently vs host ref. PTX-only divergence where Vulkan agrees with CPU = NVIDIA FP behavior (`hw-diverge` counter), not a codegen bug.

## SPIR-V control flow (forward jumps verified on GPU)

- Pre-assign one SSA block id per MIR label (two-pass: labels need ids before jump sites emit).
- JZ/JNZ → `OpIEqual/OpINotEqual` vs zero, then `OpSelectionMerge(247) merge None` + `OpBranchConditional(250)` with a fresh fall-through block as the other arm. SPIR-V REQUIRES the merge — bare BranchConditional fails validation ("Selection must be structured").
- LABEL → if current block lacks a terminator, emit explicit `OpBranch(249)` to the label block (implicit fall-through is illegal). Track `just_terminator` after branches/RET.
- Backward jumps (loops) detected in pre-pass but deferred — they need `OpLoopMerge(246)` restructuring.
- TRAP: spv_ins word count must equal actual operand words (passing n=2 for a 1-word array reads garbage and corrupts the stream).

## SPIR-V loops (verified: counted loop on Radeon 740M)

- Loop header LABEL (target of a backward jump) emits: `OpLoopMerge(246) exit continue None` + `OpBranch continue`, then the continue block label. Body follows; backward JZ/JNZ emits condition + `BranchConditional cond header exit` — **the back-edge must target the HEADER** (it owns the LoopMerge), not the continue block, else "Back-edges can only be formed between a block and a loop header".
- Backward JMP branches straight to header and emits the exit label for post-loop code.
- LOAD/STORE: MIR cell i → SSBO element i+1 via `AccessChain(ptr_u64, var_ssbo, zero32, idx64)`; cell 0 reserved as return slot.
- Int compares EQ/NE/LT/LE/GT/GE/ULT/ULE/UGT/UGE → bool via verified opcodes (170/171/177/179/173/175/176/178/172/174), then Select(169) → u64 1/0.
- Pre-existing (not SPIR-V): dtype fuzz f64 softfloat-vs-C-double rounding gaps appear/disappear depending on LCG draw order.

## SPIR-V T_GEMM status (WIP, committed 61c1b32)

- Triple structured loop with memory-carried i/k/j in SSBO scratch cells (array extended +8 when program has T_GEMM; scratch_base = total_mem+1). NO OpPhi — dzn/DXIL rejects i64 Phi.
- spirv-val accepts the full module; simpler loop tests (loop-sum 15, JZ 99) run correctly on Radeon 740M.
- OPEN: dzn AND llvmpipe both fail on the full triple-loop module (pipeline error -13 / host segfault) while simpler loops work — suspect the 64-bit loop-carried memory pattern fails DXIL translation. Next ideas: split loop vars into 2×u32 pairs, or verify per-op with tiny modules.
- TRAPS hit while building it: TG_AC/TG_LD macros must assign `res_ = nid(s)` themselves or callers pass uninitialized ids (Result Id 0); spv_ins n must exactly match operand count (AC=5 words incl. type+res+base+2 idx); every block needs explicit terminator before next label — helper-emitted labels bypass the main walker's just_terminator fixup, so set *jt correctly at every helper exit.

## SPIR-V T_GEMM status (FIXED — working on dzn, bit-exact, 2026-08-25)

- Single flat loop over M*K*N work items, UDiv/UMod decomposition to (i,k,j). Memory-carried loop
  counter in SSBO scratch cell (dzn/DXIL rejects i64 OpPhi — the probe pattern is mandatory).
- `spirv-val` clean. 1/3/5/24-bit-exact on dzn RTX 4050. `test_tgemm`: 576/576 match naive C.

### Root causes of the "T_GEMM returns 0" bug (TWO independent)

1. **Missing `BuiltIn GlobalInvocationId` decoration**: `OpDecorate %var_gid BuiltIn 28`
   was decorating the *type* id (`t_gid_input`) instead of the *variable* id (`var_gid`).
   Without the BuiltIn decoration dzn's DXIL translator loaded garbage from the input
   builtin → VK_ERROR_DEVICE_LOST (device removed).
2. **Const table miss**: `cKN = K*N` and `cMKN = M*K*N` were NOT registered in the
   ADD_CONST pre-pass → `spirv_find_const` returned **0** → loop-bound id = 0 →
   spirv-val "Id is 0" + device lost. Fix: `ADD_CONST(M_*Nn); ADD_CONST(M_*K_*Nn)`.

### Debugging methodology that cracked it

- `2>/dev/null` on the vk_run popen was hiding VK_ERROR_DEVICE_LOST as silent 0.
  Removed suppression; `vulkan_run` now returns -1 on execution failure instead of 0.
- `spirv-val -V` "Id is 0 at line 512" was misread as a line in the disassembly —
  it's an *instruction index*. The bad `OpULessThan %bool %x %ulong_1` referenced
  constant id 0 because the const lookup missed.
- `spirv-opt -O` (the production path) **merges the cont block into the body** and
  strips debug artifacts — so disassembling `/tmp/wubu_kernel.spv` showed the
  OPTIMIZED form, not the emitter output. The stale-file trap bit this session twice.

### dzn scale limitation (recorded, not fixed)

dzn's DXIL translator crashes (D3D12 device removed, error -4) on the flat loop
when M*K*N ≥ ~200 iterations (8×8×8=512 fails). 1×1×1 (9), 3×3×3 (19), 5×5×5 (37)
all pass. PTX on real sm_89 hardware handles full scale — this is a dzn/DXIL loop
budget quirk, not a codegen defect. `WUBU_VK_GROUPS` env var + `WUBO_VK_NO_OPT`
remain available for future grid-stride work.

## vk_run dzn lessons (WSL2 Vulkan-on-D3D12)

## vk_run dzn lessons (WSL2 Vulkan-on-D3D12)

- Dozen is non-conformant; compute stores to host-visible memory DON'T land directly. Fix: two HOST_VISIBLE buffers — shader writes `buf` (STORAGE|SRC|DST), command buffer does stage→buf copy, dispatch, barrier, buf→stage copy back. Works on both cards.
- dzn rejects multi-bind patterns on one allocation AND some second allocations → keep two separate simple allocations, same heap type.
- Zero-init every Vk struct; WSL exposes GPUs only via /dev/dxg (no /dev/dri, no ROCm/HIP).

## Test commands

```
make test_fuzz_diff   # differential: x86-64 + 8086 + PTX GPU + interpreter
make test_tgemm       # T_GEMM vs naive C
make test_isa_driver  # full gauntlet
cc -O2 -std=c11 -o vk_probe tools/vk_probe.c -lvulkan && ./vk_probe
/tmp/vk_run <dev> <shader.spv> <arg> <cells>
```

## 2026-08-25 T_GEMM closure (dzn RTX 4050 + Radeon 740M + llvmpipe — ALL CARDS)

### Bug #3 (the big one): vrmap hardcoded at 256 VRs
`uint32_t maxvr = 256` silently dropped `VRMAP_SET` writes for programs with
>256 MIR virtual registers; every such read returned `c_zero64`. spirv-val
stays CLEAN (the module is valid — it just computes with zeros). Symptom:
wrong results appearing between ~125 and ~130 MIR ops, looking like a random
"iteration-count cliff". It was never a dzn/DXIL limit. Fix: scan all
dst/a/b operands in the pre-pass and size maxvr from the high-water mark.

**Lesson: a valid module that computes wrong = suspect silent VRMAP/const-table
truncation first, hardware second.**

- T_GEMM now verified bit-exact on all three reachable devices
  (dzn RTX 4050, dzn Radeon 740M, llvmpipe): 8x8x8=79 and **16x16x16=279
  (4096 iterations)** PASS everywhere.
- 1000-op add chain bit-exact.
- test_isa_driver 195/195, test_tgemm 576/576.

### Debugging lessons from this session
1. Stale binaries lying about results: /tmp/vktgp3 and /tmp/vk_run were rebuilt
   at different times; interleaved testing produced phantom pass/fail flips.
   Always rebuild ALL harnesses together after emitter changes.
2. Zombie background processes: two timed-out `test_fuzz_diff 3000` runs kept
   executing in the background, overwriting `/tmp/wubu_kernel.spv` mid-test
   (caught via `stat` showing file shrink 4720→888 bytes two seconds after
   compile). Kill strays before trusting any /tmp-artifact-based test.
3. `md5sum` the .spv after every run when results look nondeterministic.
