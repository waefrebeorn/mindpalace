# Live Decode Root Cause Reference

## Symptoms Observed
- `gen_text /home/wubu/models/Agents-A1-4B "Hello" 8` exited silently.
- Debug traces showed `n_prompt=1`, `first_token=9419`, `lazy_embd_raw != NULL`, `d_model=2560`, `vocab=248320`.
- The failure was not silent because embeddings were missing; `test_real_load` already proved the same shard loads and SSM layer 0 forward runs.
- Tokenizer path bug produced `hf_path=/home/wubu/models//tokenizer.json`, missing the model dir; fixed by explicit `strlen`-based append.
- HF tokenizer encode returned 1 token whose ID equals `bos_id`; the issue was in the HF tokenizer path, not the model.

## Current Blocking Failure
After fixing the tokenizer path, `gen_text` segfaults inside `wubu_model_forward_from_embd()`.
- Debug prints confirm SSM layers 0-2 complete: residual, post-attention norm, and streaming-free release all succeed.
- Layer 3 is the first GQA layer; `wubu_gqa_ensure_f32()` materializes Q/K/V/O F32 pointers successfully.
- Crash occurs AFTER that, before the "after layer 3, freeing" marker.

## Diagnosis Update
The original skill note that all-embedding-sources-NULL caused silent zero-embeddings is NOT the active failure mode for Colonel safetensors models. The active failure is a runtime forward bug in the GQA path after weight materialization on the first GQA layer.

## Instrumentation Pattern That Worked
1. Add one trace print at the TOP of the layer loop.
2. Add one trace print BEFORE and AFTER each risky sub-step within a known-bad layer:
   - `wubu_ssm_release_f32`
   - `wubu_gqa_release_f32`
   - residual add
   - `wubu_rms_norm` for post-attention norm
3. Rebuild with `touch src/wubu_model.c && make -j$(nproc) MAX_LAYERS=2 gen_text`.
4. If failure lands between two A-B prints, the bug is the code between them.

## Fixes Applied So Far
- Tokenizer path bug in `tools/gen_text.c` (`strlen`-based append with trailing-slash check).
- `wubu_model.c` pre-attention norm: NULL `attn_norm_weight` now identity fallback instead of hard return.
- `include/wubu_model.h` KIVI V dequant: cast to `const uint8_t *` to match API.

## Remaining Work
- Localize the exact GQA sub-step that crashes on layer 3 for Agents-A1-4B with `MAX_LAYERS=2`.
- Do not claim “just a compile fix” — the encoder now prints non-finite outputs; the next step is forward-path/data correctness.
- Once layer 3 executes cleanly, run timing prints around SSM+GQA blocks and capture tok/s for all target models.

## Repo Anchors
- Live decode: `tools/gen_text.c`
- Stable regression: `tools/test_real_load.c`, `tools/test_tok_hf.c`
- Forward baseline: `tools/test_st_bridge.c`, `tools/test_btl3_lora.c`

## Session Artifacts
- `research/LIVE_DECODE_ROOT_CAUSE.md`
- `research/002-triple-da-staging.md`
- `research/007-7step-plan.md`
- `tools/test_tok_hf.c`
- `tools/test_decoder_paths.c`