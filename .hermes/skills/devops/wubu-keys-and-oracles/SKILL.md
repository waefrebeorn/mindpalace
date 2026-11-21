---
name: wubu-keys-and-oracles
description: Use stored API keys — NVIDIA NIM, OpenRouter, HF oracles.
category: devops
version: 1.0.0
tags: [keys, secrets, nvidia, openrouter, huggingface, oracles]
---

# WuBu Keys and Oracles

The keys are STORED and must be REFERENCED, never copied into code.
For the full vault (inventory + live verification + rotation), see the
`wubu-vault` skill and `~/.hermes/profiles/mind-palace/vault/`.

## Where the keys live
**File: `~/.hermes/profiles/mind-palace/secrets/hf.env`** (0600, gitignored)
```
export HF_READ_TOKEN="hf_SnPLzxl..."      # HuggingFace read (datasets)
export HF_WRITE_TOKEN="hf_SUmXdx..."      # HuggingFace write (model uploads)
export NVIDIA_API_KEY="nvapi-KU2_..."     # NVIDIA NIM free tier (primary)
export NVIDIA_API_KEY_2="nvapi-mFTI..."   # spares
export NVIDIA_API_KEY_3="nvapi-tLid..."
export OPENROUTER_KEY_1..6="sk-or-v1-..." # OpenRouter free-tier RLHF keys
```
Load: `source ~/.hermes/profiles/mind-palace/secrets/hf.env` or read
the file in Python/scripts. NEVER hardcode a key literal in any repo
file — GitHub push protection blocks the push AND the history must
then be scrubbed (git-filter-repo; done 2026-08-03 for the
OpenRouter keys that were briefly hardcoded).

## NVIDIA NIM (build.nvidia.com free tier) — VERIFIED LIVE
- Endpoint: `https://integrate.api.nvidia.com/v1` (OpenAI-compatible)
- Client: `wubuwizard/tools/nvidia_nim.py` (reads the env/key file)
- **Embeddings (live-stream embedding):** `nvidia/nv-embed-v1` →
  4096 dims ✓; `nvidia/nemotron-3-embed-1b` → 2048 dims ✓
- **Chat (the oracle / RLHF judge):** `minimaxai/minimax-m3` ✓,
  `z-ai/glm-5.2` ✓, `deepseek-ai/deepseek-v4-pro` ✓
- **WARNING: most listed model names 404/410** (deprecated). The
  three chat models + two embed models above are the verified-live
  ones as of 2026-08-03. Always verify a new model before relying on it.
- `score_draft(draft, prompt)` → (score 0-100, critique, err) — the
  R1-style oracle that scores WuBu's drafts (the RLHF reward).
- ~1000 free credits (one credit ≈ one call); rotate to key 2/3 when
  rate-limited.

## OpenRouter free tier — ALL 6 KEYS VERIFIED LIVE (2026-08-06)
- Endpoint: `https://openrouter.ai/api/v1`
- Client: `wubuwizard/tools/openrouter_rlhf.py` — 6 keys round-robin,
  `rlhf_improve(draft, prompt)` → (score, critique, improved_draft)
- 337 models, 14 `:free` (google/gemma-4-31b-it:free,
  nvidia/nemotron-3-super-120b-a12b:free, etc.)
- **2026-08-03 they 429'd at first use; 2026-08-06 all 6 returned 200
  (auth/key endpoint) with real usage counters** — the keys are live
  now. Run `vault.py verify` for the current status.

## HuggingFace
- Read token: datasets (smollm-corpus, finemath, fineweb-edu,
  openmath, dclm — all accessible)
- Write token: WaefreBeorn org — the model repo `WaefreBeorn/WuBu-35M`
  (weights + tokenizer + config + umbrella LICENSE + NOTICE +
  AGI-disclosure README). Repo was renamed from WuBu-Seed-35M.
- Upload: `python3` + `huggingface_hub` HfApi (see the training skill)
- Xet storage rejects binary-IO uploads — fall back to HTTP (the
  client handles it automatically)

## The AGI disclosure (standing order)
The WuBu-35M card discloses: it is an AI, being built to be general,
human-centric (the human keeps the mouse), accountable (prestige
ledger), not ready for autonomy. Never remove that disclosure.

## Verification
```bash
source ~/.hermes/profiles/mind-palace/secrets/hf.env
cd /home/wubu/wubuwizard
python3 tools/nvidia_nim.py embed   # expect: embed OK: 4096 dims
python3 tools/nvidia_nim.py chat    # expect: a reply from minimax-m3
python3 tools/openrouter_rlhf.py    # may 429 — keys are still valid
```

## Pitfalls
- NEVER echo a key into a commit message, a doc, or a paste.
- NEVER `git add -A` after touching anything that mentions keys —
  stage explicit paths.
- If a push is rejected with "Push cannot contain secrets", find the
  literal in the tree/history and scrub (see git-secret-scrub skill).
- The secrets file is OUTSIDE both repos — it survives prestige.
