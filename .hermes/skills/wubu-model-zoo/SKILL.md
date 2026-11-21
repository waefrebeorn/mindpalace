---
name: wubu-model-zoo
description: WuBu model zoo - ethos stages, tiers, formats, disk budget.
---

# WuBu Model Zoo — the amoeba's growth ladder

Every model we hold is an **ethos stage** — a quality-density lesson at a
scale. The amoeba grows VIA the zoo: the zoo is both food supply (data,
distillation teachers, RLHF oracles) and the test bed (each big-brother
model proves a mechanism we then own in C11). Load this skill whenever the
task touches "which model", "download X model", "disk space", or "format".

## The one-sentence doctrine

**The zoo is a ladder, not a pile.** Each tier is a scale stage of the
same ethos: make it tiny, make it dense, make it ours.

| Tier | Stage | Models (current zoo) | Size | Verdict |
|---|---|---|---|---|
| **T0** | THE SEED — our own, we train it | WuBu body, checkpoint-native geometry (35,073,216 params; `models/wubu/`, 140MB) + corpus (31G) + .st checkpoints | ~32G | **ACTIVE — never touch** |
| **T1** | Small (sub-10B, cheap/fast) | nanbeige4.1-3b Q4_K_M (2.3G), Agents-A1-4B (8.5G) | 11G | keep (test bed) |
| **T2** | Mid workhorse 27B | Qwen3.6-27B (52G) + BTL-3 LoRA (0.9G) | 53G | **KEEP — the daily driver** (3.8-27B next week slots here) |
| **T3** | 35B powerhouse (tiny-but-dense) | Qwen3.6-35B-A3B IQ2_M (12G) → **REPLACED by Escha W2 (12.3G)** | 12G | archive the 35B gguf to SD; Escha takes the slot |
| **T4** | MoE mega | KAT-Coder-V2.5-Dev 256-exp (68G), DeepSeek-V4-Flash-ConfigI 284B/21B-active 2.88bpw (95G) | 163G | KAT → SD cold; DeepSeek → SD cold until the box can run it |
| **VIS** | Vision leg | moondream3 (18G) + mmproj-F16 (0.86G) | 19G | SD cold (not in the current training loop) |
| **RL** | World-model leg | cartpole/dr_ppo zips (~3M) | ~0 | keep |

## Format doctrine — GGUF vs safetensors (the "run everything" rule)

- **safetensors = the TRAIN/CANONICAL format.** Our trainer writes it
  (`wubu_save`, 137-tensor release layout, JSON header padded to 8,
  mmap zero-copy, SHA-256 verified). HF hosts WuBu-35M as safetensors.
  WE MUST UNDERSTAND IT — our model runs everything, so the trainer,
  the bridge (`wubu_model_safetensors_bridge.c`), and HF all speak it.
- **GGUF = the INFERENCE/QUANTIZED format.** llama.cpp family; carries the
  quant types (Q8_0, Q4_K_M, IQ2_M, TQ3_1S, Q2_0...). The big-brother zoo
  arrives mostly as GGUF (KAT shards, Qwen ggufs, DeepSeek ConfigI).
  wubuwizard loads BOTH: legacy `wubu_model.c` (GGUF) + the safetensors
  bridge; `gen_text` runs both.
- **Conversion paths:** `.st` → safetensors via `wubu_save` (HF upload);
  safetensors → GGUF via llama.cpp's convert tools (a quantized inference
  copy of WuBu-35M is a nice-to-have for serving). Do NOT re-host a
  GGUF-only zoo — keep the safetensors canonical copy of OUR model, GGUF
  for the borrowed big brothers.
- **Before downloading ANY zoo model:** check the HF card for a known-issue
  notice. DeepSeek-V4-Flash-ConfigI shipped with a broken Q2_0 type field
  (ggml id 47 vs 42) on 2026-08-03 — "hold off until the notice is
  removed." Also check the runtime fork requirement (it needs
  TheTom/llama-cpp-turboquant `tom/merge-upstream-dsv4`; stock llama.cpp
  cannot load deepseek4).

## Disk reality (WSL df LIES — the thin-vhdx trap)

- The WSL filesystem is a thin-provisioned vhdx on the Windows **C:** drive.
  `df -h` inside WSL reports the VIRTUAL size (~1007G, "716G free") — the
  physical disk is 447.6G total. The REAL budget is Windows' free space.
- Measured 2026-08-03 (PowerShell): **C: 31.9 GB free** · D: (SD card,
  exFAT, = /home/wubu/sdcard) **204 GB free**.
- Check real space with:
  `powershell.exe -NoProfile -Command "Get-Volume | Select-Object DriveLetter,@{n='SizeGB';e={[math]::Round(\$_.Size/1GB,1)}},@{n='FreeGB';e={[math]::Round(\$_.SizeRemaining/1GB,1)}}"`
- **SSD = ACTIVE tier** (/home/wubu/models/). **SD = COLD tier** (archive
  tar.gz or raw model dirs; drvfs-slow, no chmod — git clone fails there).

## The 2026-08-03 budget math (models/ = 192G on SSD)

To fit the 95.3 GiB DeepSeek KAHUNA on ACTIVE: archive KAT (68G) +
moondream (18G) + 35B-A3B gguf (12G) ≈ 98G → frees C: to ~132G, DeepSeek
fits with ~30G headroom. OR: park DeepSeek on the SD directly (fits:
204G free) and archive SSD models only when C: pressure demands it.

Safe deletions (already executed where trivial): wubuwizard-root debug
blobs (A_*.bin, ssm_in_*.bin, chunk_*.bin, scal_delta.bin), err.log,
benchmark_f16*.log, stale test_* binaries at repo root (rebuild via make).

## Rules

1. The seed + corpus are sacrosanct — never archive mid-training.
2. SD is cold: model dirs move there as tar.gz or raw; restore = copy back.
3. When a model is superseded (35B gguf → Escha), archive the old one —
   the SD is our cheap second disk while "we are poor."
4. Verify each download by expected size (content-length) and check the
   known-issues notice — broken re-uploads happen.
5. The zoo ledger lives here + `research/INDEX.md` (WB themes) + STATUS.md.
