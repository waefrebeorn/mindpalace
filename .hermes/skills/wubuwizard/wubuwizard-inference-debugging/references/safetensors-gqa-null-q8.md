# Safetensors GQA NULL-Q8 Pointer Fix Pattern

## Root Cause
BF16/F16 safetensors models leave `attn_q_weight_q/k/v/o` NULL in the bridge
because the safetensors path does not pre-quantize to Q8_K. The original
`wubu_gqa_forward` unconditionally called `quantized_matmul_from_q8()` even
when these pointers were NULL, causing a segfault inside the first GQA projection.

## Fix: NULL guard + F32 fallback in wubu_gqa_forward
```c
// Q projection
if (w->attn_q_weight_q) {
    quantized_matmul_from_q8(gqa_q8_buf,
        w->attn_q_weight_q, w->attn_q_weight_type,
        d_model, q_dim * 2, 0, Q_full + q_offset);
} else {
    quantized_matmul(x_s, w->attn_q_weight, GGML_TYPE_F32,
        d_model, q_dim * 2, 0, Q_full + q_offset);
}
```
Same pattern for K, V, and output projections (replace NULL-pointer check
with `w->attn_k/v/o_weight_q`). The `quantized_matmul` F32 path is faster
than the old `matmul_nt` (1.6 tok/s vs 0.1 tok/s on Agents-A1-4B).

## Also guard RMSNorm NULL weights
`attn_q_norm_weight` / `attn_k_norm_weight` can be NULL in Qwen3 hybrids.
The safetensors bridge doesn't load these per-head RMSNorm scalars.
```c
if (w->attn_q_norm_weight) {
    wubu_rms_norm(N, head_dim, q_dim, x, w->attn_q_norm_weight, 1e-6f, Q_norm);
} else {
    memcpy(Q_norm, x, N * q_dim * sizeof(float));
}
```

## Also guard KV cache prefill write-back
When T==1 and model->gqa_cache_len==0 (single-token decode, empty cache),
`k_out` and `v_out` must still point to `k_cache`/`v_cache` base so the
new KV is written. The original code only handled T>1 prefill.

## Verified on
- Agents-A1-4B (safetensors, Qwen3 hybrid, 2560-dim, 32 layers)
- KAT-Coder-V2.5-Dev (safetensors, 13 shards)
- Qwen3.6-27B (GQA, large context)

## Speed impact
matmul_nt → quantized_matmul(F32): 0.1 → 1.6 tok/s decode (16×).