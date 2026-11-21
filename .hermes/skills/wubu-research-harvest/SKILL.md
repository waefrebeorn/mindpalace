---
name: wubu-research-harvest
trigger: Use when harvesting 500MB research corpus across 7 steps.
description: 7-step arXiv+GitHub pipeline, 70MB per step.
---

# Research Harvest Pipeline

## The 7-Layer Research Stack
Layer 1: Core paper (e.g. Nickel & Kiela 2017 for Poincare)
Layer 2: Follow references from Layer 1 (20-30 papers)
Layer 3: Search arXiv for related papers (same topic, different year)
Layer 4: Search GitHub for implementations
Layer 5: Extract code from top 5 repos (pure text: .py, .md, .txt, .c, .h)
Layer 6: Search for tutorials and blog posts
Layer 7: Search for criticisms/limitations

## Infrastructure
- Harvest script: `tools/harvest_pond.py` (arXiv API + pymupdf + dedup)
- Config format: `ponds/<name>.json` — name, target_mb, arxiv_terms, github_repos
- Output: `work/<name>/text/` (pure text, deduped by SHA-1 prefix)
- Resume support: pre-load existing hashes, continue numbering
- Purity gate: is_pure_text() rejects binary/non-UTF-8

## 7-Step Research Plan
Each step = 70MB / 7 layers. Total: 490MB ≈ 500MB.

1. **Fractal NN** — fractal architectures, recursive weights, self-similarity
2. **KV-cache memory** — KV compression, Infini-attention, STILL, cartridges
3. **Adapters** — adapter layers, LoRA, PEFT, modular NN
4. **Self-modifying** — online NAS, progressive nets, neural module nets
5. **Poincare/hyperbolic** — hyperbolic embeddings, hyperbolic attention
6. **Density** — information density, bottleneck, Pareto, rate-distortion
7. **Hardware scaling** — hardware-aware NAS, quantization, adaptive compute

## Run
```
python3 tools/harvest_pond.py ponds/an24-step01.json --arxiv-only
```

## Verify
```
du -sh research-ponds-work/AN24-step*/  # should show ~70MB each
du -s research-ponds-work/AN24-step*/ | awk '{s+=$1} END {printf "%.1f MB\n", s/1024}'
```
