---
name: wubu-density-planning
trigger: Use when implementing the density planner that decides what data gets absorbed into model weights vs stays in KV cache vs gets pruned.
description: AGI resource allocator. Density = coherence score per token.
---

# WUBU Density Planning — AGI Resource Allocator

## Core Principle
**density = coherence_score / n_tokens** (bits of understanding per token)

Three bands:
- **ABSORB** density >= absorb_threshold: promote to model weights
- **KEEP** density >= keep_threshold: remain in KV cache at reduced precision
- **PRUNE** below keep: scheduled for wubu_kv_shrink

Guarantees user experience always + AGI always.

## Cycle
files in KV namespace → forward → attention → coherence → density → absorb / tier / prune

## Modules
- wubu_density_planner.c: Resource allocator — computes density, classifies bands
- wubu_kv_coherence_diag.c: Provides coherence scores
- wubu_model_scalable.c: Fractal model — mark_hot promotes regions to weights
- wubu_kv_tiering.c: Tier KV cache regions to lower precision
- wubu_kv_shrink.c: Prune dead KV regions
- wubu_kv_embedding.c: File-to-KV bridge — file_count, get_path, region, get_fs

## File layout
- Header: include/wubu_density_planner.h
- Impl: src/wubu_density_planner.c
- Tests: tools/test_density_planner.c (5 tests)
- Makefile: test_density_planner target

## Build and test
make test_density_planner — 5 tests
make test_all — all green
