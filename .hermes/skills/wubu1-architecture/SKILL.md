---
name: wubu1-architecture
trigger: Use when building WuBu-1 fractal AGI.
description: Fractal weights, KV-FS metabolism, hot-swap adapters.
---

# WuBu-1 Architecture

## Three Cycles

### Cycle 1: Fractal Weight Tree (AN23)
Layer 0: 12M params (trunk). Layer N: 3x params of layer N-1.
Precision cascade: F32 near trunk, down to Q2_K at leaves.
Boots minimal, extends mmap as memory allows.

### Cycle 2: KV-FS Hive Mind (AN21)
```
files in /kv/in/ → forward → attention
→ coherence_diag (Triple-DA: Detect/Analyze/Act)
→ density_planner (density = coherence / n_tokens)
→ ABSORB → wubu_scalable_model.mark_hot
→ KEEP → wubu_kv_tiering (F32→F16→Q8_K→Q4_K)
→ PRUNE → wubu_kv_shrink (apoptosis)
→ GROW → wubu_grow_kv (amoeba toward incoherent files)
```

### Cycle 3: Adapter Framework (AN23-2)
```
FRAME:  wubu_adapter.h — opaque type + dispatch vtable
BUFFER: wubu_adapter_registry.c — slot map (name → adapter)
SHIM:   wubu_adapter_compat.c — version bridge (v1↔v2↔v3)
```
9 hot-swappable component types: ATTN, FFN, NORM, ACT, TOK, LR, OPT, QUANT, KVC

## Build & Test
```
make test_all — 59+ tests, all green
```
