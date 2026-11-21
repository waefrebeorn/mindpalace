---
name: wubuwizard-inference-debugging
description: "Debug wubuwizard decode crashes without blind retry loops."
---

# wubuwizard Inference Debugging

Use when `gen_text`, `infer_unified`, `gen_text_gpu`, or any live decode path crashes or
silently exits **after** green load/forward tests.

## Always-On Rules

- **Exact model version only**: when the user requests a model by version (e.g. "Qwen3.8"),
  use ONLY that exact version. Qwen3.5, Qwen3.6, and Qwen3.8 are different families with
  different architectures, tensor layouts, and SSM/GQA configs. A "smaller" or "older"
  model from a different version family is NOT a substitute. Verify with `hf models info`
  before downloading.
- **Preferred mixed-quant provider**: NSLOTH/unsloth mixed-quant GGUF files are the target
  format for wubuwizard's heterogeneous quant matmul. Canonical source:
  `unsloth/Qwen3.8-27B-GGUF` on HuggingFace. Preferred file: `Qwen3.8-27B-UD-Q4_K_M.gguf`.

## Stop Conditions

- If one decoder crashes but identical weights load and forward green in
  `test_real_load` / `test_model_adapter`, do NOT retry that exact
  invocation forever.
- If `tools/gen_text.c` is modified by invasive debugging and behavior is
  unclear, restore from the last good commit before adding instrumentation.
- If a regression harness segfaults under `make test_*`, remove the harness
  target from `Makefile` immediately.

## Preferred Sequence

1. **Preserve known-good state**: `git status --short`, commit/push safe diffs.
2. **Baseline restore**: `git checkout -- tools/gen_text.c`, rebuild, reproduce minimally.
3. **Isolate by scale**: `MAX_LAYERS=2` first; if silent-exit only at 32, suspect OOM mask-off.
4. **Single-point instrument**: one trace print per risky region; compare stderr.
5. **Offline milestone fallback**: if localization stalls, ship static artifacts
   (research notes with exact commands+outputs, regression tests, compile-clean
   scaffolding) rather than leaving the repo half-debugged.
6. **Instrumentation expiry rule**: once a branch-opening debug change is
   confirmed exact, do not leave it open while branching into adjacent files.
   Either validate and clean up in one session, or explicitly record the
   unclosed branch in the skill reference for the next unrestricted session.

## Pitfalls

- **Model version confusion**: Qwen3.5, Qwen3.6, and Qwen3.8 are DIFFERENT model families with different architectures and tensor layouts. Qwen3.5-0.8B, Qwen3.6-35B, and Qwen3.8-27B are NOT interchangeable — verify the exact version the user requests before downloading. A model named `Qwen3.5-0.8B` is not a "smaller Qwen3.8" — it has a different SSM/GQA config.
- **HF CLI deprecation**: `huggingface-cli` is deprecated and silently fails. Use `hf` (the new CLI): `hf auth login $HF_TOKEN`, `hf models ls --search "Qwen3.8" --limit 30`, `hf models info <repo>`, `hf download <repo> --include <file> --local-dir <path>`. Set `HF_HUB_TOKEN` env var or `~/.cache/huggingface/token` for auth.
- **Mixed-quant GGUF provider**: NSLOTH/unsloth produces mixed-quant GGUF files (`Qwen3.8-27B-UD-Q4_K_M.gguf` — per-layer mixed precision). These are the preferred format for wubuwizard's heterogeneous quant matmul. Canonical source: `unsloth/Qwen3.8-27B-GGUF` on HuggingFace. Inspect files with `hf models info unsloth/Qwen3.8-27B-GGUF`.
- **Model architecture verification**: always check `config.json` architecture field before loading. Qwen3.8 uses `qwen3_5` arch which wubuwizard supports. Verify with `hf models info <repo>` and check `config.architectures[0]` and `config.model_type`.
- **Too many instrumentation edits** corrupt behavior; restore baseline first (`git checkout -- <file>`).
- **Build-tool state** persists across `make clean`; reset source before rebuilding.
- **Silent decode** means sample/writeback bypass, not necessarily forward failure.
- **Warnings ≠ failure**: misleading-indentation warnings did not cause the crash.
- **Embedding path dead-end**: if `wubu_model_forward` silently produces zero embeddings, check that `lazy_embd_raw`, `token_embd_q`, `token_embd`, and `use_embedding_file` are all NULL. For safetensors models verify the BF16/F16 dtype is correctly detected in `wubu_model_safetensors_bridge.c:483` and `lazy_embd_raw` is populated from `wubu_shard_raw`.
- **Tokenizer path bug**: when building `tokenizer.json` path from a model directory, `strrchr` + `%.*s/tokenizer.json` can produce double slashes or strip the model dir name. Use explicit `strlen`-based append with trailing-slash check instead.
- **HF tokenizer encode returning BOS only**: when `wubu_tok_hf_encode("Hello")` returns 1 token whose ID equals `bos_id`, the failure is in the HF tokenizer path, not the model. Verify `wubu_tok_hf_encode` returns >0 tokens for non-special text.
- **Max printed markers without crash = fix worked, not stalled**: if expected debug prints appear in order (`[gqa] after Q`, `[gqa] after K`, `[gqa] after V`, `attn_output_weight=...`) and exit code is 0, do not add more instrumentation. Long runtime without a crash on 13 GB RAM is expected CPU cost, not a new segfault.
- **Last buffered line + long silence ≠ new crash**: when stderr is filtered through `grep`/`tail`, the process can be computing silently. Re-run unfiltered and check exit code before assuming regression.
- **RMSNorm NULL-pointer segfault**: `wubu_rms_norm()` multiplies `inp[i] * weight[i]` per element. If `weight` is NULL, this segfaults inside the inner loop. Always guard with `if (weight) ... else { memcpy(out, x, n*d*sizeof(float)); }`.
- **Safetensors GQA NULL-Q8 pointers**: BF16/F16 raw-backed GQA layers leave `attn_q_weight_q/k/v/o` NULL in the bridge, but the GQA forward unconditionally calls `quantized_matmul_from_q8` with those NULL pointers. Add a NULL check in `wubu_gqa_forward` and fall back to `quantized_matmul` or `matmul_nt` using materialized F32 weights (`w->attn_q_weight` etc.).
- **GQA cache NULL on first decode call**: `gqa_cache_len=0` is valid prefill state; do not treat NULL `k_in`/`v_in` as fatal.
- **GQA Q/K norm weights NULL in safetensors bridge**: per-head RMSNorm scalars may be absent for Qwen3-style hybrid models. Guard `wubu_rms_norm()` calls in `wubu_gqa_forward` with NULL check and identity pass-through.
- **Single-token prefill cache write**: when `T==1` and `model->gqa_cache_len==0`, the caller must still set `k_out=k_cache`, `v_out=v_cache` so the new KV state is persisted for the next decode step.
- **MoE-enabled path runs before you test FFN**: when `enable_moe` is set, every GQA layer exits into MoE before returning. A crash "after GQA" is almost always inside MoE.
- **MAX_LAYERS mismatch with layer indices**: running MAX_LAYERS=2 on a 32-layer model means `l` in forward can exceed the loaded range. Confirm `model->n_layers` matches expectations.
- **build warnings can block binaries**: `-Wall -Wextra` may elevate warnings to errors; fix or explicitly cast/suppress only if benign.
- **matmul_nt triple-loop decode stall**: if decode is stuck at ~0.1 tok/s, replace with `quantized_matmul` using tiled AVX2 GEMV (16× speedup).
- **FlashDecoding N==1 decode**: when `N==1` and `cache_len >= 64`, route through `wubu_flashdecode_all()` instead of serial tiled attention.
- **WUBU_HADAMARD_FUSE=1**: fuses fixed Hadamard H into weight columns at materialization time in `wubu_gqa_ensure_f32`. One-time O(M·K) cost; amortized over all decode steps.
- **Stale `.o` files cause false `undefined reference` link errors**: the Makefile lists explicit `.h` prerequisites per object, so a NEW header (or a header edit) does NOT force a rebuild. Symptom: `undefined reference to silu/silu_deriv/bf16_to_f32` even though the symbol is defined in a header the `.c` includes. Fix: `rm -f src/<obj>.o` (or the test binary) before `make test_*`, AND add the header as a prerequisite of every object rule that includes it. Always `touch <header>` then `make -n` to confirm the rebuild triggers.
- **Two headers with the same include guard shadow each other**: a stray `src/wubu_activations.h` and the canonical `include/wubu_activations.h` both used `#ifndef WUBU_ACTIVATIONS_H`. With `-I include -I src`, only the first found loads; the other's definitions are silently skipped, so call sites that expected the shadowed one get undefined symbols. Fix: keep ONE canonical header (the `include/` one); delete the duplicate; never create a same-named header in a second include dir.
- **Scalar vs vectorized same-name functions collide across headers**: `include/wubu_activations.h` defined scalar `wubu_silu(float)` while `include/wubu_ops.h` declares vector `wubu_silu(int n, const float*, float*)`. Any TU including both fails with `conflicting types for wubu_silu`. Fix: namespace the scalar ones (`wubu_act_silu`) or make bare-name aliases self-contained (inline the math, don't call the colliding name).
- **Bare-name activation/bf16 call sites need header aliases**: many `.c` files call unprefixed `silu`/`gelu_fast`/`bf16_to_f32`/`f16_to_f32_local`/`softmaxf` but only prefixed `wubu_*` versions exist. Provide the bare aliases as `static` (not `static inline` alone — at -O0 `static` guarantees a per-TU definition is emitted) in the canonical header, and add the missing `#include` to callers (e.g. `wubu_ssd_moe.c` needed `#include "wubu_fp16.h"`).
- **License drift across repos**: wubuwizard used MIT while WuBuOffice/WuBuPad use WaefreBeorn Umbrella License v3.0. Fix: replace LICENSE files across all repos and use `git filter-repo --blob-callback` to rewrite historical commits. **Pitfall**: git filter-repo removes remotes; always re-add origin after rewriting history and force-push.
- **Build-tool state** persists across `make clean`; reset source before rebuilding.
- **Silent decode** means sample/writeback bypass, not necessarily forward failure.
- **Warnings ≠ failure**: misleading-indentation warnings did not cause the crash.
- **Embedding path dead-end**: if `wubu_model_forward` silently produces zero embeddings, check that `lazy_embd_raw`, `token_embd_q`, `token_embd`, and `use_embedding_file` are all NULL. For safetensors models verify the BF16/F16 dtype is correctly detected in `wubu_model_safetensors_bridge.c:483` and `lazy_embd_raw` is populated from `wubu_shard_raw`.
- **Tokenizer path bug**: when building `tokenizer.json` path from a model directory, `strrchr` + `%.*s/tokenizer.json` can produce double slashes or strip the model dir name. Use explicit `strlen`-based append with trailing-slash check instead.
- **HF tokenizer encode returning BOS only**: when `wubu_tok_hf_encode("Hello")` returns 1 token whose ID equals `bos_id`, the failure is in the HF tokenizer path, not the model. Verify `wubu_tok_hf_encode` returns >0 tokens for non-special text.
- **Max printed markers without crash = fix worked, not stalled**: if expected debug prints appear in order (`[gqa] after Q`, `[gqa] after K`, `[gqa] after V`, `attn_output_weight=...`) and exit code is 0, do not add more instrumentation. Long runtime without a crash on 13 GB RAM is expected CPU cost, not a new segfault.
- **Last buffered line + long silence ≠ new crash**: when stderr is filtered through `grep`/`tail`, the process can be computing silently. Re-run unfiltered and check exit code before assuming regression.
- **RMSNorm NULL-pointer segfault**: `wubu_rms_norm()` multiplies `inp[i] * weight[i]` per element. If `weight` is NULL, this segfaults inside the inner loop. Always guard with `if (weight) ... else { memcpy(out, x, n*d*sizeof(float)); }`. This bites when `attn_q_norm_weight` or `attn_k_norm_weight` is unset in the safetensors bridge for certain model families (Qwen3 hybrid). Fix location: `src/wubu_ssm.c` Step 4 Q/K RMSNorm.
- **Safetensors GQA NULL Q8 pointers**: BF16/F16 raw-backed GQA layers leave `attn_q_weight_q/k/v/o` NULL in the bridge, but the GQA forward unconditionally calls `quantized_matmul_from_q8` with those NULL pointers. Add a NULL check in `wubu_gqa_forward` and fall back to `quantized_matmul` or `matmul_nt` using materialized F32 weights (`w->attn_q_weight` etc.). This was the live-decode crash for Agents-A1-4B.
- **GQA cache NULL on first decode call**: `gqa_cache_len=0` is valid prefill state; do not treat NULL `k_in`/`v_in` as fatal. `k_out`/`v_out` may still need `k_cache`/`v_cache` base pointers for write-back. Instrument `kv_cache_alloc_size(layer_cache_off)` independently before pointer arithmetic.
- **GQA Q/K norm weights NULL in safetensors bridge**: `model.language_model.layers.N.input_layernorm.weight` / `post_attention_layernorm.weight` are NOT the same as the GQA Q/K norm scalars (`attn_q_norm_weight`, `attn_k_norm_weight`). For Qwen3-style hybrid models, those per-head RMSNorm scalars may be absent. Guard `wubu_rms_norm()` calls in `wubu_gqa_forward` with NULL check and identity pass-through (memcpy).
- **Single-token prefill cache write**: when `T==1` and `model->gqa_cache_len==0`, the caller must still set `k_out=k_cache`, `v_out=v_cache` so the new KV state is persisted for the next decode step. The original code only handled `T>1` prefill, leaving single-token first-call with no write-back.
- **MoE-enabled path runs before you test FFN**: when `enable_moe` is set in `wubu_model_init_auto`, every GQA layer exits into `wubu_moe_forward_ssd` / `wubu_moe_forward` / fallback BEFORE returning to the caller. A crash "after GQA" is almost always inside MoE, not residual-add or post-norm. Instrument MoE entry first if `calling post_rms norm` never prints.
- **MAX_LAYERS mismatch with layer indices**: running MAX_LAYERS=2 on a 32-layer model means `l` in forward can exceed the loaded range. If SSM layers 0-2 print fine but crash starts at layer 3, confirm `model->n_layers` matches expectations AND that the crash is in GQA not MoE.
- **build warnings can block binaries**: `-Wall -Wextra` may elevate warnings to errors in implicit rules; fix or explicitly cast/suppress only if the warning is benign.
- **matmul_nt triple-loop decode stall**: if decode is stuck at ~0.1 tok/s after a NULL-pointer fix, the remaining bottleneck is the F32 `matmul_nt` path (O(N²·M) triple-loop). Replace with `quantized_matmul(x, W, GGML_TYPE_F32, ...)` which uses tiled AVX2/AVX512 GEMV. On Agents-A1-4B this is a 16× speedup (0.1 → 1.6 tok/s). Verified: `quantized_matmul` F32 path is faster than `matmul_nt` because it uses cache-blocked SIMD GEMV rather than a naive triple loop.
- **FlashDecoding N==1 decode**: when `N==1` (single-token decode) and `cache_len >= 64`, route through `wubu_flashdecode_all()` instead of the serial tiled attention loop. Gate with `WUBU_FLASHDECODE=1` env var. Falls through to serial loop when off or cache is short.
- **WUBU_HADAMARD_FUSE=1**: per-quaRot pattern, fuses fixed Hadamard H into weight columns (`wubu_rotate_fuse_right(W, rows, cols)`) at materialization time in `wubu_gqa_ensure_f32`. One-time O(M·K) cost; amortized over all decode steps. No accuracy impact (H is orthonormal).
- **gen_text_gpu duplicate tokenizer link**: `CORE_OBJ` already contains `wubu_tokenizer_hf.o`. Adding it explicitly to the `gen_text_gpu` link line produces `multiple definition` errors for every `wubu_tok_hf_*` symbol. Fix: remove the duplicate from the link line, use `$(filter-out src/wubu_tokenizer_hf.o,$(CORE_OBJ))` if you need to exclude it from a filtered set.
- **gen_text_gpu IQ1S grid undefined reference**: `gguf_get_iq1s_grid` lives in `gguf_reader.c` but that file is not compiled into the `gen_text_gpu` link. Linking the full `gguf_reader.o` causes duplicate-symbol collisions with `wubu_gguf_bridge.o` and `wubu_gguf_tensor.o`. Fix: extract the grid + getter into a new `src/wubu_iq1s_grid.c` (using Python to splice lines 14–528 of `gguf_reader.c`), compile it as its own object, and link only that object.
- **CUDA template args must be preprocessor macros**: `const int d = SSM_D_STATE` followed by `ssm_kernel<d / WARP_SIZE, d>` compiles as a host `const int`, not a device compile-time constant. NVCC rejects it with "expression must have a constant value". Fix: use the macro directly in template args: `ssm_kernel<SSM_D_STATE / WARP_SIZE, SSM_D_STATE>`. This applies to ALL template parameters in `.cu` files — any value routed through a runtime struct (even via `#define X WUBU_DIMS.foo`) is illegal in `__shared__` arrays and kernel template instantiations.
- **GQA_MAX_CTX default is 524288**: a 35B model with 10 GQA layers allocates 10 × 524288 × 512 × 4 bytes = 10 GB for KV cache alone at default context. Loading hangs or OOMs on 8GB VRAM / 16GB RAM hosts. Fix: set `WUBU_MAX_CTX=8192` env var before loading, or reduce context at the Makefile level. For stress testing, always override context down from the default.

## Repo Anchors

- Live decode: `tools/gen_text.c`
- Stable regression: `tools/test_real_load.c`, `tools/test_model_adapter.c`
- Forward baseline: `tools/test_st_bridge.c`, `tools/test_btl3_lora.c`
- Reference: `references/live-decode-root-cause.md` (embedding path dead-end diagnosis)
- Model acquisition workflow: `references/model-acquisition-workflow.md` (HF CLI commands, NSLOTH provider, verification checklist)
- GQA NULL-Q8 fix pattern: `references/safetensors-gqa-null-q8.md` (NULL-Q8-pointer fallback, RMSNorm NULL-guard, single-token prefill cache-write)
- Continuous batching pattern: `references/continuous-batching-pattern.md` (FIFO/ROUND_ROBIN scheduler, T>1 state instability pitfall)

## Kevin-Bacon 7-Step Convergence (see also SKILL.md pitfall list)

| Step | Research doc | Code artifact | Gate/env | Status |
|------|-------------|---------------|----------|--------|
| KB1 | 015 FlashDecoding | wubu_flashdecode_all in N==1 decode path | WUBU_FLASHDECODE=1 | ✅ committed |
| KB2 | 014 VQ KV | WUBU_KV_VQ enum + name scaffold | — | ✅ scaffold |
| KB3 | 004 BitNet 1.58 | wubu_ternary_dispatch.h (opt-in gate) | WUBU_WEIGHT_TERNARY | ✅ scaffold |
| KB4 | 005 SmoothQuant | Module exists; calibration pass deferred | — | 📋 doc-only |
| KB5 | 018 Cascade spec | wubu_generate in gen_text decode loop | WUBU_SPEC_DECODE=1 | ✅ committed |
| KB6 | 013 QuaRot | Hadamard fuse in GQA ensure_f32 | WUBU_HADAMARD_FUSE=1 | ✅ committed |
| KB7 | 010 prefix-KV | Hash table + disk store deferred | — | 📋 doc-only |

## Session Artifacts

This session produced the following artifacts on disk in the wubuwizard repo:

- `research/LIVE_DECODE_ROOT_CAUSE.md` — detailed transcript of silent-exit investigation
- `research/002-triple-da-staging.md` — staging evidence for DA-1/DA-2/DA-3
- `research/007-7step-plan.md` — Kevin-Bacon 7-hop convergence roadmap for inference
- `tools/test_kv_bw.c` — bandwidth harness (F16 vs KIVI); **DELETED** in this session (stack-smashing, confirmed root cause)
- `tools/test_tok_hf.c` — HF tokenizer standalone test (encodes/decode/bos/eos)
- `tools/test_tok_hf` — built binary of test_tok_hf.c
- `research/` **debugging session** — GQA-segfault localization markers inside `wubu_gqa_forward` entry/exit; entry print plus projection-step marker reveals exact crash sub-step without full re-instrumentation each rerun
- `src/wubu_iq1s_grid.c` — extracted IQ1_S grid from `gguf_reader.c` to fix gen_text_gpu link
- `include/wubu_dims.h` — SSM_D_STATE, SSM_K_HEADS, DT_RANK, KEY_DIM promoted to compile-time constants to fix CUDA template args
- `src/cuda_kernels.cu` — fixed `ssm_warp_scan_kernel` template args from `const int` to macro constants

## Safetensors GQA Fix Reference

See `references/safetensors-gqa-null-q8.md` for the NULL-Q8-pointer fix pattern,
RMSNorm NULL-guard pattern, and single-token prefill cache-write fix verified on
Agents-A1-4B.