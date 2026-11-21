---
name: wubuwizard-weight-pipeline
description: 'Add weight codecs to wubuwizard universal pipeline.'
version: 1.1.0
author: Hermes Agent
license: MIT
tags:
  - wubuwizard
  - weight-codec
  - safetensors
  - gguf
  - tbe
  - backburner
  - memory-optimization
  - c11
related_skills:
  - rea
  - c-systems-programming
  - wubuwizard-inference-debugging
  - wubu-revolver-pattern
---

# wubuwizard Weight Pipeline Integration

## When to Use

- Adding a new storage format (TBE, K-quants, custom codecs) to wubuwizard
- Wiring safetensors-loaded weights into the existing F32 forward path
- Extending `wubu_weight_to_f32()` or `quantized_matmul()` with a new type tag
- Making a model checkpoint load through the universal `wubu_weight_t` contract
- Reducing peak RSS for large-model inference on memory-constrained systems

---

## Backburner: Per-Layer Page Cache for Memory-Efficient Loading

### The Problem

`gguf_buffer_data()` calls `madvise(blob, 17GB, MADV_WILLNEED)` on the
entire mmap'd GGUF blob. On systems with ≤16 GB RAM, this alone pushes
RSS past the OOM threshold before a single token is generated.

### The Solution

Replace eager prefetch with per-layer page-cache management:

1. After `gguf_buffer_data()`, call `gguf_backburner_init(ctx)` to scan
   tensors and compute per-layer byte ranges (by `blk.N` prefix).
2. At the start of each layer forward pass, call `gguf_backburner_warm()`
   to `MADV_WILLNEED` only that layer's pages.
3. At the end of each layer forward pass, call `gguf_backburner_cool()`
   to `MADV_DONTNEED` them — the kernel evicts clean pages first.
4. On model unload, call `gguf_backburner_free()`.

Enable with `WUBU_BACKBURNER=1`. When active, `gguf_buffer_data()` uses
`MADV_RANDOM` (no read-ahead) instead of `MADV_WILLNEED`; the backburner
handles precise prefetching per layer.

### Files

| File | Purpose |
|---|---|
| `include/gguf_reader.h` | `gguf_layer_range_t` + backburner API declarations |
| `src/gguf_backburner.c` | Backburner implementation (init/warm/cool/free) |
| `src/wubu_model.c` | Hooks in model init, forward loop, and model free |
| `src/gguf_reader.c` | Modified `gguf_buffer_data()` for conditional madvise |

### Hook Points in wubu_model.c

```c
// After gguf_buffer_data(), before weight pointer setup:
gguf_backburner_init(ctx);

// Start of each layer forward:
gguf_backburner_warm(model->gguf_ctx, l);

// End of each layer forward (before closing brace of layer loop):
gguf_backburner_cool(model->gguf_ctx, l);

// In wubu_model_free(), before gguf_close:
gguf_backburner_free(model->gguf_ctx);
```

### RSS Impact

| Config | Peak RSS (27B model, Q4_K_M) |
|---|---|
| Default (MADV_WILLNEED full blob) | ~12.8 GB |
| Backburner (WUBU_BACKBURNER=1) | ~2–3 GB |

The reduction is proportional to `max(layer_size, non-weight tensors)`.
Embedding + LM head + KV cache still resident; only transformer layer
weights are cycled.

---

## The Universal Contract

Every weight in wubuwizard flows through exactly two functions:

```c
void wubu_weight_to_f32(const wubu_weight_t *w, float *out);  // materialize
void wubu_weight_matmul(const float *x, const wubu_weight_t *w,
                        int64_t n_rows, int64_t n_cols, float *y); // dispatch
```

`wubu_weight_t` is `{ const uint8_t *data; int type; int64_t n_elems; }`.
No per-format branches in the forward. Adding a new codec means touching
only these two functions plus the type enum.

---

## Integration Steps

### 1. Add GGML_TYPE tag

In `include/gguf_reader.h`, add the new type after the last float type:

```c
GGML_TYPE_BF16    = 30,
GGML_TYPE_TBE     = 31,  // Manifold-Enhanced TBE codec
```

Order matters: the materializer and matmul switch on this enum.

### 2. Add ST_DTYPE tag (safetensors path)

In `include/safetensors_reader.h`, add the dtype:

```c
ST_DTYPE_TBE  = 10,  // Manifold-Enhanced TBE codec
```

In `src/safetensors_reader.c`, add the string mapping:

```c
if (strcmp(s, "TBE")  == 0) return ST_DTYPE_TBE;
```

### 3. Implement decode in `wubu_weight_to_f32`

In `src/wubu_weight.c`, add a case to the materializer. The decoder must
produce `n_elems` F32 values into `out`.

**Critical:** the TBE codec decodes to BF16 bit patterns (uint16_t), NOT
directly to float. Decode into a temp uint16_t buffer, then convert each
BF16 word to F32 by shifting into the upper 16 bits of a uint32_t and
memcpy into the float output.

```c
case GGML_TYPE_TBE: {
    const wubutbe_header_t *h = (const wubutbe_header_t *)w->data;
    uint32_t T = h->tiles;
    size_t planes_bytes = (size_t)T * WUBUTBE_TILE_BYTES;
    size_t smb_bytes    = (size_t)T * WUBUTBE_TILE;
    const uint8_t *ptr     = w->data + sizeof(wubutbe_header_t);
    const uint8_t *planes  = ptr;
    const uint8_t *smb     = ptr + planes_bytes;
    const uint8_t *esc     = smb + smb_bytes;
    uint16_t *bf16 = malloc((size_t)w->n_elems * sizeof(uint16_t));
    uint8_t *codes = malloc((size_t)T * WUBUTBE_TILE);
    if (!bf16 || !codes) { free(bf16); free(codes); return -1; }
    wubutbe_unpack_codes(planes, T, codes);
    uint8_t inv_perm[64];
    wubutbe_compute_inverse(WUBUTBE_MMA16_PERM, inv_perm);
    uint32_t esc_pos = 0;
    wubutbe_decode_tiles(codes, smb, esc, h->n, h->k, h->mode, h->base,
                         inv_perm, bf16, &esc_pos);
    for (int64_t i = 0; i < w->n_elems; i++) {
        uint32_t f32 = (uint32_t)bf16[i] << 16;
        memcpy(&out[i], &f32, 4);
    }
    free(bf16); free(codes);
    return 0;
}
```

**Pitfall:** `unpack_codes` must `memset(codes, 0, n_tiles * TILE)` before
bit-packing. Unset bits retain stack garbage if the codes array is not
zero-initialized.

**Pitfall:** pass `esc_pos` as a caller-owned parameter, never `static`
inside the decode loop. Static escape positions break reentrancy and
produce garbage on the second decode call.

### 4. Add matmul dispatch

In `quantized_matmul`, add a TBE case. Two valid strategies:

**Simple (decode-then-SGEMM):** decode to a temporary F32 buffer, then
run the existing SGEMM path. Correctness first.

**Fast (decode-during-matmul):** decode tiles on-the-fly inside the matmul
loops. TBE's 64-element tile maps to a GEMV micro-kernel. Profile before
optimizing; the simple path is fast enough for 1.4x-compressed weights.

### 5. Add weight descriptor fields to layer structs

In `include/wubu_ssm.h`, add `wubu_weight_t` TBE descriptors to both
`ssm_layer_weights` and `gqa_layer_weights`:

```c
// SSM struct
wubu_weight_t attn_qkv_weight_desc;
wubu_weight_t attn_gate_weight_desc;
wubu_weight_t ssm_out_weight_desc;

// GQA struct
wubu_weight_t attn_q_weight_desc;
wubu_weight_t attn_k_weight_desc;
wubu_weight_t attn_v_weight_desc;
wubu_weight_t attn_output_weight_desc;
```

Also add lazy BF16 raw pointer fields (mmap'd safetensors bytes) to both
structs so the bridge can store either TBE or BF16 lazy paths:

```c
const uint8_t *attn_qkv_weight_raw;
int lazy_dtype;   // safetensors dtype for lazy-loaded weights
int f32_mode;     // 1 = materialize, 0 = direct
```

**Pitfall:** tests and tools reference `attn_qkv_weight_f32` but the actual
struct field is `attn_qkv_weight` (no `_f32` suffix). When renaming struct
fields, grep the entire tree (`src/ include/ tools/`) for the old name and
update every reference — hand-rolled mocks reimplement the old shape and
fail on a shard you did not run.

### 6. Wire the safetensors bridge

In `src/wubu_model_safetensors_bridge.c`:

1. Add `#include "wubutbe.h"`
2. Add `probe_tbe()` helper before `raw_try2`
3. In each GQA weight block, check `probe_tbe()` before the BF16 check
4. In each SSM weight block, check `probe_tbe()` before the BF16 check

```c
static int probe_tbe(wubu_shard_ctx_t *sc, const char *name,
                     wubu_weight_t *desc) {
    int dtype = 0; int64_t row = 0;
    const uint8_t *raw = raw_try2(sc, name, &dtype, &row);
    if (raw && dtype == ST_DTYPE_TBE) {
        desc->data = raw;
        desc->type = GGML_TYPE_TBE;
        const wubutbe_header_t *h = (const wubutbe_header_t *)raw;
        desc->n_elems = (int64_t)h->n * (int64_t)h->k;
        return 1;
    }
    return 0;
}
```

**Pitfall:** the bridge's existing BF16 path uses `ly->ssm.attn_qkv_weight_f32`
field names in some places but the struct actually defines `attn_qkv_weight`
(no `_f32`). Align all references to the actual struct field names before
building.

### 7. Add `wubu_ssm_ensure_f32`

The GQA path has `wubu_gqa_ensure_f32()` in `src/wubu_poincare_gqa.c`.
The SSM path needs an equivalent. Create it in `src/wubu_ssm.c`:

```c
void wubu_ssm_ensure_f32(ssm_layer_weights *w, int d_model, int conv_dim, int value_dim) {
    if (!w) return;
    // TBE first, then GGUF quant, then lazy BF16 raw
    if (!w->attn_qkv_weight && w->attn_qkv_weight_desc.type == GGML_TYPE_TBE) { ... }
    if (!w->attn_qkv_weight && w->attn_qkv_weight_q) { ... }
    if (!w->attn_qkv_weight && w->attn_qkv_weight_raw && w->lazy_dtype == ST_DTYPE_BF16) { ... }
    // Same pattern for attn_gate_weight and ssm_out_weight
}
```

Declare the prototype in `include/wubu_ssm.h` after `wubu_ssm_forward()`.

### 8. Wire ensure calls into the model forward

In `src/wubu_model.c`, inside the layer loop before the SSM/GQA forward
call, add:

```c
if (layer->is_ssm)
    wubu_ssm_ensure_f32(&layer->ssm, D_MODEL, CONV_DIM, VALUE_DIM);
else
    wubu_gqa_ensure_f32(&layer->gqa, D_MODEL);
```

### 9. Update `wubu_gqa_release_f32`

Free F32 buffers materialized from TBE decode the same way as GGUF quant:

```c
if (w->attn_q_weight_q || w->attn_q_weight_desc.type == GGML_TYPE_TBE)
    { free(w->attn_q_weight); w->attn_q_weight = NULL; }
```

---

## Verification

After wiring:

1. `make test_codec` — unit test the TBE decode against known-good bytes
2. `MAX_LAYERS=1 make test_real_load` — load the model, check bridge init
3. `tools/gen_text "Hello"` — single-token decode to verify forward passes

Bit-exactness: TBE is a lossless codec. After materialization, the F32
weights must match the raw-BF16 path within float conversion precision.
Use `memcmp` on the BF16 representations before materialization.

---

## Pitfalls

### Adding a new .c file to wubuwizard

Adding a new source file requires BOTH a `CORE_OBJ` entry AND an explicit
Makefile compilation rule. Without the explicit rule, GNU make's built-in
suffix rule (`%.o: %.c`) applies, which may miss required flags like
`-DWUBU_ENABLE_CUDA` or `-I include` paths. Add:

```makefile
src/gguf_backburner.o: src/gguf_backburner.c include/gguf_reader.h include/wubu_gguf_tensor.h
	$(CC) $(CFLAGS) -DWUBU_ENABLE_CUDA -c -o $@ $<
```

### Avoid duplicate symbols — use a new file, not an existing one

`gguf_reader.c` already defines `gguf_buffer_data`, `gguf_raw_size`,
`gguf_read_tensor_f32`, and dequant functions. Adding backburner code to
that file causes `multiple definition` link errors. Create a new file with
a distinct name (`gguf_backburner.c`) instead.

### Quantization defines must be shared via the header

New quantization block sizes (`QK4_NL`, `IQ4_NL_BLOCK_SIZE`) must be
added to the shared header (`include/gguf_reader.h`), not just in one
source file. Multiple files (`wubu_gguf_tensor.c`, `quantized_matmul.c`,
`quantized_dot_generic.c`) include the header and need the same values.

**Pitfall:** naming convention must match across files. `IQ4_NL_BLOCK_SIZE`
(underscores) is the standard form; do not use `IQ4NL_BLOCK_SIZE` (no
underscore) — sed-renaming across files after a mismatch is the fix.

### `wubu_weight_nbytes` must know the new type

Add a `case GGML_TYPE_TBE` that returns the container's actual byte length
(from header), not `n_elems * 2`. The generic fallback of `n_elems *
sizeof(float)` is wrong for compressed blobs.

### `wubu_weight_direct_ok` must return 0 for compressed types

TBE cannot run direct SGEMM on compressed bytes; it must materialize first.
Returning 1 causes `quantized_matmul` to read garbage.

### BF16→F32 must use a temp buffer

Casting `float* out` to `uint16_t*` and writing BF16 bit patterns into it
produces 2 bytes per 4-byte slot. Decode to `uint16_t* bf16`, then
convert each word with `(uint32_t)bf16[i] << 16`.

### Safetensors bridge lazy path uses `raw_try2`, not `wubu_shard_raw`

`raw_try2` appends `.weight` as a fallback; TBE tensors in checkpoints
may or may not carry that suffix. Probe both.

### `lazy_embd_raw` / `lazy_lmhead_raw` are BF16-only fast paths

Do not route TBE tensors through them. Store TBE blobs in the weight
descriptor and materialize via `wubu_weight_to_f32`.

### Delta-encoded per-tile bases are metadata, not part of the tile stream

The decoder reads them as a separate section after the escape array.
The container header must declare whether bases are global or per-tile.

### Struct field names: SSM uses `attn_qkv_weight`, not `attn_qkv_weight_f32`

Tests and tooling often write `_f32` suffixes that don't exist on the
struct. Grep the full tree for the old name before renaming, otherwise
hand-rolled mocks reimplement the old shape and fail on a shard you did
not run.

### CUDA in wubuwizard uses `-DWUBU_ENABLE_CUDA`, not `__CUDACC__`

The repo compiles `.c` files with gcc plus the CUDA runtime headers.
Guard CUDA includes with `#ifdef WUBU_ENABLE_CUDA` and include
`<cuda_runtime_api.h>` (not `<cuda_runtime.h>`).

### Stager link recipes: prefer explicit objects over `$(MODEL_OBJ)` when
the test only needs a subset.

`$(MODEL_OBJ)` expands to 100+ objects; linking it for a small test
causes `multiple definition` errors from `wubu_dense_ffn.o` and other
duplicates.

### Subagent verification pattern

Spawn a subagent with `delegate_task` for independent build-and-run
verification. Monitor the live transcript at
`~/.hermes/profiles/<profile>/cache/delegation/live/<id>/task-0.log`.
The subagent should report build status, per-test results, and anomalies.
This catches issues the parent session missed (stale objects, env diffs).

---

## Hardware-Accelerated Offload (Maya Stager Pattern)

### The Problem

Qwen3.8 27B-scale weights exceed single-GPU VRAM. The CPU decode path
(`wubu_weight_to_f32`) is correct but blocks the GPU while it runs.

### The Solution

Port Project Maya's 3-tier memory hierarchy + 256-slot DMA ring buffer to
wubuwizard. CPU decode runs in parallel with GPU compute; the DMA ring
hides PCIe latency.

### Files

| File | Purpose |
|---|---|
| `include/wubu_stager.h` | Public API: stager + SSD reader + tier helpers |
| `src/wubu_stager.c` | Implementation (CPU-only + CUDA-accelerated paths) |
| `include/wubutbe.h` | TBE codec (encode/decode, standalone C11) |
| `docs/MAYA-STAGER-DOX.md` | Architecture + integration plan |

### Stager API

```c
wubu_stager_t* stager = wubu_stager_create(256, (void*)cuda_stream);
wubu_stager_enqueue(stager, &job);       // submit decode+copy job
wubu_stager_wait(stager, gen, -1);       // wait for slot completion
wubu_stager_finish(stager);              // drain + streamsync
wubu_stager_destroy(stager);
```

### Compiling with CUDA

This repo does not use nvcc for the stager. Compile the `.c` with gcc and
`-DWUBU_ENABLE_CUDA`; the header `<cuda_runtime_api.h>` provides the
runtime API declarations. Link against `-lcudart -lcublas`.

```makefile
# Makefile recipe for a CUDA-enabled test
CUDA_TEST = tools/verify_maya_stager.c
$(CUDA_TEST): $(MODEL_OBJ) src/wubu_stager.o include/wubutbe.h include/wubu_stager.h
	$(CC) $(CFLAGS) -DWUBU_ENABLE_CUDA -o $@ $(MODEL_OBJ) src/wubu_stager.o $(LDFLAGS)
```

**Pitfall:** `MODEL_OBJ` expands to 100+ object files. When a CUDA test
only needs `wubu_weight.o` + `wubu_stager.o`, link those explicitly
instead of `$(MODEL_OBJ)` to avoid pulling in unrelated symbols that
produce `multiple definition` errors.

### Tier Promotion API

```c
wubu_tiered_promote(weight, to_tier, stager);   // SSD->HRAM->VRAM
wubu_tiered_evict(weight);                       // VRAM->HRAM->SSD
```

Tiers: `WUBU_TIER_VRAM` (hot, on GPU), `WUBU_TIER_HRAM` (warm, page-locked
host RAM), `WUBU_TIER_SSD` (cold, compressed blob file).

### GPU DMA

The stager allocates pinned host buffers via `cudaHostAlloc` (falling back
to `malloc` on failure). When a `cuda_stream` is provided, DMA completion
is tracked via per-slot `cudaEvent_t`. Without CUDA, the stager is a
no-op ring buffer (CPU decode only).

### Verification

Run the multi-scale test:
```bash
make verify_maya_stager    # builds + runs 5 tensor sizes
```

Expected output: 5/5 PASS, bit-exact roundtrip at each size, real CUDA
DMA bandwidth on a CUDA-capable machine.

---

## Reference

- `include/wubu_weight.h` — universal weight descriptor contract
- `src/wubu_weight.c` — materializer + matmul dispatcher
- `src/wubu_model_safetensors_bridge.c` — lazy-BF16 wiring pattern
- `src/wubu_poincare_gqa.c` — `wubu_gqa_ensure_f32` / `wubu_gqa_release_f32`
- `src/wubu_ssm.c` — `wubu_ssm_ensure_f32` (SSM counterpart)
- `include/wubutbe.h` — standalone TBE codec (C11, zero external deps)
- `include/wubu_stager.h` — Maya-style tiered offload API
- `src/wubu_stager.c` — stager + SSD reader + tier promotion
- `docs/MAYA-STAGER-DOX.md` — architecture + integration plan
- `REA-Prompts/rea-TBE-findings.md` — TBE container layout reverse-engineering
- `references/cuda-offload-pattern.md` — CUDA build/test recipes for wubuwizard
- `references/backburner-pattern.md` — per-layer page cache design + hook points

## Related Skills

- [rea](../rea/SKILL.md) — reverse-engineering methodology for C11 codecs
- [c-systems-programming](../software-development/c-systems-programming) — C11/CUDA systems for AI inference
- [wubuwizard-inference-debugging](../wubuwizard/wubuwizard-inference-debugging/SKILL.md) — live decode debugging
- [wubu-revolver-pattern](../software-development/wubu-revolver-pattern/SKILL.md) — configurable constants for allocation limits
