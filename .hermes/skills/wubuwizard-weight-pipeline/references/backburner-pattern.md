# Backburner: Per-Layer Page Cache Design

## Why the default path exhausts RAM

`gguf_buffer_data()` mmaps the entire GGUF file and calls
`madvise(blob, full_size, MADV_WILLNEED)`. For a 27B Q4_K_M model the
blob is ~17 GB. On a 14 GB system this forces the kernel to fault in the
entire file before the first forward pass, pushing RSS past the OOM
threshold.

## What the backburner changes

Instead of prefetching everything, the backburner:

1. Scans tensor names to compute per-layer byte ranges (`blk.N.*` →
   layer N).
2. Uses `MADV_RANDOM` on the full blob to suppress read-ahead.
3. Calls `MADV_WILLNEED` on only the current layer's pages at the start
   of its forward pass.
4. Calls `MADV_DONTNEED` on those pages at the end of the pass.

The kernel keeps recently-used pages in the page cache. Since only one
layer's weights are accessed per pass, the working set stays bounded.

## Hook points

| Hook | Location | Purpose |
|---|---|---|
| `gguf_backburner_init()` | After `gguf_buffer_data()` in `wubu_model_init()` | Scan tensors, compute ranges |
| `gguf_backburner_warm()` | Start of each layer in `wubu_model_forward_from_embd()` | Prefault current layer |
| `gguf_backburner_cool()` | End of each layer in `wubu_model_forward_from_embd()` | Evict current layer |
| `gguf_backburner_free()` | Start of `wubu_model_free()`, before `gguf_close()` | Release range table |

## Enabling

```bash
export WUBU_BACKBURNER=1
./gen_text_gpu --model model.gguf --prompt "Hello" --max-tokens 64
```

Disable with `WUBU_BACKBURNER=0` or unset (default = eager prefetch).

## Expected RSS

| Model | Default | Backburner |
|---|---|---|
| Qwen3.5-0.8B (Q8_0) | ~3 GB | ~2–3 GB (minor) |
| Qwen3.8-27B (Q4_K_M) | ~12.8 GB | ~2–3 GB |

KV cache and activation memory are unchanged. The saving is proportional
to the largest single layer's weight footprint.

## Implementation notes

- `gguf_layer_range_t` stores `[start, end)` byte offsets per layer.
- `parse_layer()` extracts the layer index from `blk.N.` tensor names.
- Non-layer tensors (embedding, LM head, norms) are folded into the
  layer ranges that contain them.
- `madvise` is a hint; the kernel may retain some pages. Peak RSS is
  still bounded by `max(layer_size, non-layer-weight_size)`.
- On non-Linux or non-mmap'd blobs, backburner is a no-op.

## Testing

```bash
# Without backburner (baseline)
./gen_text_gpu --model Qwen3.8-27B-Q4_K_XL.gguf --prompt "Hi" --max-tokens 8
# Observe RSS via /proc/<pid>/status VmRSS during generation.

# With backburner
WUBU_BACKBURNER=1 ./gen_text_gpu --model Qwen3.8-27B-Q4_K_XL.gguf --prompt "Hi" --max-tokens 8
# Peak RSS should drop by ~75–80%.
```
