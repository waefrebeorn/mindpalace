# Model Acquisition Workflow for WuBuWizard

## Authoritative Source for Qwen3.8

Canonical mixed-quant GGUF provider: **unsloth/Qwen3.8-27B-GGUF** on HuggingFace.
Preferred file: `Qwen3.8-27B-UD-Q4_K_M.gguf` (per-layer mixed precision).
For new deployments, prefer `Qwen3.8-27B-UD-Q4_K_XL.gguf` (Unsloth Dynamic 3.0)
when it exists in the repo — it is newer, smaller, and more accurate than `_M`.

## Required HF CLI Commands

```bash
# Auth (token cached at ~/.cache/huggingface/token)
export HF_HUB_TOKEN=$(cat ~/.cache/huggingface/token)

# Search for Qwen3.8 models (sorted by downloads/likes)
hf models ls --search "Qwen3.8" --limit 30

# Inspect repo contents (architecture, file sizes, quant types)
hf models info unsloth/Qwen3.8-27B-GGUF

# Download specific quant file
hf download unsloth/Qwen3.8-27B-GGUF \
  --include "Qwen3.8-27B-UD-Q4_K_M.gguf" \
  --local-dir /home/wubu/models
```

## Model Verification Checklist

1. Check `config.architectures[0]` == `qwen3_5` (wubuwizard-compatible)
2. Check `config.model_type` == `qwen3_5`
3. Verify GGUF file size matches expected (Q4_K_M ~14GB for 27B)
4. Load with `MODEL=<path> ./gen_text_cpu "test" 8 4 0.7` and confirm tensor count matches

## Pitfalls

- **Do NOT substitute** Qwen3.5-0.8B or Qwen3.6-35B when user asks for Qwen3.8 — different architectures, tensor layouts, and SSM/GQA configs.
- **Do NOT use old/obsolete quant formats** when the user specifies mixed-quant — UD-series (per-layer mixed) is the target.
- **`huggingface-cli` is deprecated** — it silently fails. Use `hf` (new CLI) exclusively.
- **Incomplete downloads** show as `.incomplete` blobs in HF cache — check file size before assuming success.
- **Always verify architecture** via `hf models info` before downloading large files.
- **Dynamic version selection**: when a repo offers both `_M` (Dynamic 2.0) and `_XL` (Dynamic 3.0) suffixes, prefer `_XL` for new deployments. Dynamic 3.0 is newer and more accurate at the same or smaller size. Confirm which suffix exists in the repo before downloading; do not grab an older `_M` file when `_XL` is available.
