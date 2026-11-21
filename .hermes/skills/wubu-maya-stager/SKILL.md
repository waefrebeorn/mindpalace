---
name: wubu-maya-stager
description: Use when wiring Maya-style TBE DMA stager in WuBuWizard.
---

# Maya-Style TBE Stager

Adapts Project Maya's Stager pattern to wubuwizard TBE compression: 256-slot ring buffer, pinned host staging, CUDA DMA ring, per-slot completion events.

## Critical Gotchas
1. Makefile: src/wubu_stager.o needs explicit -DWUBU_ENABLE_CUDA rule
2. Stage buffer must grow on demand (512KB default too small for 33M tensors)
3. CUDA events must be cudaEventCreateWithFlags in create, not just calloc
4. Stage buffer copy: use memcpy (host-to-host), DMA uses cudaMemcpyAsync
5. Stager stores void* stream, casts to cudaStream_t before CUDA calls

## Verification
make test_tbe_codec test_maya_stager test_maya_stager_gpu verify_maya_stager

## Results (RTX 4050/WSL2)

Verified on 5 tensor sizes matching Qwen3.8 27B distributions:

| Test | Size | Elements | TBE ratio | GPU DMA | Stager DMA | Status |
|---|---|---|---|---|---|---|
| attention_head | 128×128 | 16K | 1.409× | 0.1 GB/s | 0.5 ms | PASS |
| mlp_intermediate | 512×1024 | 512K | 1.411× | 4.4 GB/s | 3 ms | PASS |
| ffn_gate | 1024×4096 | 4M | 1.411× | 4.4 GB/s | 19 ms | PASS |
| embed_tokens | 4096×1024 | 4M | 1.411× | 5.5 GB/s | 19 ms | PASS |
| lm_head | 512×65536 | 33M | 1.411× | 4.5 GB/s | 137 ms | PASS |

All 5/5 tests pass: bit-exact TBE roundtrip + GPU DMA roundtrip + Stager DMA roundtrip at every scale.

**Stager bandwidth**: ~1 GB/s (two-stage copy: host→pinned stage→GPU). Direct `cudaMemcpyAsync` is ~5 GB/s.
**TBE throughput**: encode 158–224 MB/s, decode 531–881 MB/s.