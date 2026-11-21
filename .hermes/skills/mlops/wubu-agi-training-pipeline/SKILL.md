---
name: wubu-agi-training-pipeline
description: "Train the WuBu body: corpus, Muon, amoeba, RLHF."
category: mlops
version: 1.0.0
tags: [agi, training, wubuwizard, muon, backprop, amoeba, rlhf]
---

# WuBu AGI Training Pipeline

The AGI's name is **WuBu**. Two repos: `wubuwizard` = THE BRAIN
(model/training/research/oracles/corpus), `wubuos` = THE BODY
(kernel/firmware/GUI/recovery). This skill is the BRAIN's training
pipeline.

## The feedback loop (the standing directive)
```
corpus -> train -> diagnose -> mutate -> validate -> archive -> RLHF oracle -> repeat
```
Every batch closes gaps ON THIS LOOP. Never present completion as a
stop; at 0 open gaps spawn a fresh 7-hop research axis.

## Model facts (the body is runtime-dimensioned)

- **Model shape is NOT a #define.** Geometry comes from `WUBU_RUNTIME_DIMS`
  (`include/wubu_dims.h`); `wubu_parameter_count()` is a pure function of it.
- **Aligned geometry (current default):** 12 layers / 8 Q heads / 1 KV head
  (GQA) / 512 dim / 16384 vocab / 2048 FFN / 2048 max seq = **56,376,832
  params**, asserted in `tools/test_runtime_dims.c`.
- **Checkpoint-native geometry** (the legacy HF release, historical name
  "WuBu-35M"): 12 layers / 7 Q heads / 448 dim / 1228 FFN = **35,073,216
  params**. Same body, different tensor layout.
- `include/wubu.h` still carries `WUBU_DIM 448` / `WUBU_FFN_DIM 1228` as
  **retired prototype constants** — never read model shape from them (tracked
  debt, see `wubuwizard/docs/MODEL-IDENTITY.md`).
- hybrid attention: every 4th layer full, rest local-window
- gated attention residual + bounded SwiGLU FFN + residual selectors
- embed+head TIED (vocab 16384 × 448 = 7.3M ≈ 21% of params)
- THE IDENTITY IS WUBU — the barun name is purged everywhere (2026-08-04
  identity purge: identifiers, docs, license, HF). Files are
  src/wubu.c (forward), src/wubu_train.c (trainer), src/wubu_backprop.c
  (the REAL backward + REAL Muon — COMPLETE, test_backprop FD-verified,
  2026-08-03). No barun anywhere — do not reintroduce it.
- model dir: models/wubu/

## The training recipe (research/041-wubu35m-training-recipe.md, RC01)
| knob | value |
|---|---|
| tokens | ≥2B; repeat ≤4 epochs (overtrain 10-100× Chinchilla) |
| batch | 0.5-1M tokens/step (256-512 seq × 2048) |
| optimizer | **Muon for 2D matrices, AdamW for embed/head/norms** |
| Muon | NS5, coefs (3.4445, -4.7750, 2.0315), mom 0.95, Nesterov, fp32 buffer, NO bias corr, lr 2e-2 |
| AdamW | lr 2e-3, betas (0.9, 0.95), wd 0.1 |
| wd / clip | 0.1 both groups / grad clip 1.0 |
| schedule | warmup ~2000 steps (or 1%), cosine to 10% of peak (or WSD) |
| context | 1024 → extend to 2048; warm the local window |
| eval | held-out loss every 125-500 steps (trust loss, not benchmarks at 35M) |

**CRITICAL: the old `muon_update` in wubu_train.c was momentum
SGD — NOT real Muon.** Real Muon orthogonalizes the momentum with
Newton-Schulz 5 iterations. The real implementation lives in
wubu_backprop.c (BP4: wubu_bp_muon_step). Do not regress to
the SGD version.

**Measured caveat on the C11 path:** the NS5 quintic with per-step Frobenius
renormalization BOUNDS the update but does not orthogonalize it —
‖MᵀM − I‖_F ≈ 7.9 on a 64×64 probe and flat across 1..8 iterations, because
unit Frobenius pins the spectral norm at 1/√n and the polynomial has no fixed
point at σ=1 (f(1)=0.701, then 1.114, then 0.722). If you need a true polar
factor, use `wubu_muon_orthogonalize` in `src/wubu_muon.c` (normalize once,
then `X ← 0.5X(3I − XᵀX)`; 25 iterations → 2.35e-07, 5 iterations → 5.05).
Do not swap it into `wubu_bp_muon_step` without an ablation: every existing run
was trained with the bounded quintic, so changing it changes the recipe.

## The real backprop milestone (wubu_backprop — COMPLETE)
- BP1 recording forward == the RELEASED forward EXACTLY (loss parity
  to 1e-7). The parity test (in tools/test_backprop.c) is what caught
  FIVE real buffer-aliasing bugs in the released wubu.c:
  1. `b->ffn_gate` allocated [seq, FF] but the tensor is [seq, 2*FF] —
     the matmul computed only the gate half, the up half was OOB;
  2. `checkpoint = b->x2` aliased the buffer the o_proj matmul writes
     every layer — the residual-selector checkpoint was garbage;
  3. the attention `osum` scratch (b->x2) was never zeroed — every
     head's output included the previous layer's stale o_proj output;
  4. `matmul(b->gate, g_proj, b->gate)` — an IN-PLACE matmul: the
     output clobbered the input while it was being read;
  5. the SwiGLU row stride was `s*FF` but ffn_gate rows are 2*FF wide —
     the gate/up halves were scrambled.
  Lesson: any buffer REUSE in a forward pass is a latent aliasing bug;
  dedicated buffers (the bp recorder has one per tensor) are the fix.
  Also the WuBu-mode forward was missing the g_proj gate entirely.
- BP2 the backward: per-layer reversed chain (rope -> qk-norm ->
  softmax -> GQA -> o/g proj -> gated residual -> SwiGLU -> gate_up/
  down -> ffn/attn norms -> residual selectors -> final norm -> tied
  head). Every projection gets its own gradient; layers specialize
  (the test asserts layer-0 != layer-1 grads — the old shared proxy
  gave every layer the identical update).
- BP3 the REAL Muon: Nesterov momentum (0.95) -> NS5 -> scaled step.
  **PITFALL: the (3.4445, -4.7750, 2.0315) NS5 polynomial DIVERGES in
  fp32 for spread singular-value spectra** (a 448x64 k_proj grad went
  0.32 -> 1157 -> inf across 5 iterations). The paper's bf16 rounding
  masks this; in C11 fp32, add a per-iteration Frobenius
  renormalization (scale-invariant dynamics, bounded norm). Use the
  Moonlight RMS-0.2 scale for the step (then muon_lr ~ adam_lr, e.g.
  2e-3 both — the sqrt(max-dims) form oversteps).
- BP4 the finite-difference verifier: tools/test_backprop.c perturbs
  ONE weight of every parameter type (17 checks), re-forwards, and
  compares (L(w+h)-L(w-h))/2h against the analytic grad. The FD test
  is what proved the backward REAL (tests != correct). Run it after
  ANY change to the forward or backward.
- trainer wiring: wubu_train_microbatch runs bp_forward+bp_backward;
  wubu_train_step -> wubu_bp_muon_step (Muon for the 2D matrices,
  AdamW betas (0.9,0.95) for embed/norms/selectors — 1-D params are
  AdamW per the recipe). The norm/selector grads live in
  tr->norm_g[WUBU_NORM_SLOTS] ([4l+0..3] = attn/ffn/q/k norms,
  [4L] = final_norm, [4L+1+i] = selectors).
- the trainer's bp recorder (tr->bp_rec) grows on demand; seq 2048
  needs ~730MB of activation buffers (ffn_gate is the big one).

## The data pipeline (research/042-data-curation-pipeline.md, RC02)
1. normalize/flatten → 2. hard filters (length, boilerplate) →
   3. exact dedup → 4. MinHash near-dedup → 5. quality score →
   6. decontamination (10-13 gram) → 7. mix + seeded shuffle →
   8. tokenize → 9. pack; final ~10% annealing with math upsampled.
- **global dedup is HARMFUL — per-crawl/per-source only**
- mix for our seed: cosmopedia 50-60% + finemath 20-25% + openmath 15-20%
- corpus ACTIVE copy lives on the SSD: /home/wubu/models/corpus/
  ({text,tokens,checkpoints} + CORPUS.md manifest). The SD card
  (/home/wubu/sdcard/corpus/) is COLD STORAGE only — drvfs-slow.
  Copy the shard you are training on to /home/wubu/models/corpus/
  first, point --tok and --out at the SSD copies.
- shard 0 = ~135M tokens (271MB .tok); finemath-live streaming (~572MB)
- **SFT cold-start pack** (research/048): /home/wubu/models/corpus/sft/
  wubu-sft-pack.jsonl = 19,473 conversations (GSM8K 7.4k math CoT +
  UltraChat 6k + SlimOrca 6k), 48.5MB, deterministic seed 48. Build tools:
  /home/wubu/research-ponds-work/tools/{fetch_sft_data.py,build_sft_pack.py}.
- tokenizer: our C11 byte-level BPE (tools/wubu_tokenc.c), vocab 16384

## The SFT cold-start run + the live learning loop (2026-08-03/04)
- **SFT run LAUNCHED**: `./wubu_train_gpu --resume
  /home/wubu/models/corpus/seed-48.st-0500.st --tok
  /home/wubu/models/corpus/sft-tok/wubu-sft.tok --steps 2000 --seq
  2048 --muon-lr 1e-5 --adam-lr 1e-5 --ckpt 200 --out
  /home/wubu/models/corpus/checkpoints/seed-sft.st` — loss 8.04 @
  step 495 → ~7.3 @ step 1000 (real learning). Checkpoints land in
  checkpoints/seed-sft.st-NNNN.st; log at checkpoints/sft-run.log.
  After this run the base model should emit MEANINGFUL text (the
  under-trained model latched onto token 205 — decode empty-draft was
  an under-training symptom, NOT a code bug).
- **Live feedback loop built**: tools/wubu_live_learn.c + .py
  (prompt → WuBu draft via wubu_generate → NVIDIA score_draft →
  critique becomes SFT data). `make wubu_live_learn`. The oracle
  (tools/nvidia_nim.py: chat/embed/score_draft) is verified LIVE.
  Drafts become worth scoring only AFTER the SFT run finishes.

## Micro-pretrain corpus gathering (raw text, budget-bounded)

SFT/eval packs and raw pretraining text are different corpora; never train on
the eval-only set. Budget from the body, not from vibes: Chinchilla is ~20
tokens/param, so the aligned 56,376,832-param geometry is ~1.13B tokens; a
first honest micro run targets 150-300M tokens (~600MB-1.2GB of text at ~4
chars/token). `wubuwizard/tools/gather_micro_pretrain.py` implements this with
`--budget-mb`, a per-shard `MANIFEST.json` (licence, bytes, rows, sha256) and a
licence gate that refuses non-commercial sources (CC BY-NC research shards are
never training data).

Gathering pitfalls, each of which cost a run:

1. **Write the shard to `.part` and rename on success.** Opening the output
   `wb` before the fetch means a mid-run HTTP error truncates a previously good
   shard to zero bytes. Rename only after rows > 0.
2. **Prefer direct file streaming over the HF rows endpoint.**
   `datasets-server/rows` 429s after a few thousand rows; a repo that ships raw
   text (e.g. a `*-train.txt`) can be fetched with ONE HTTP Range request of
   `bytes=0-<budget-1>`, with no rate limit and an exact byte bound. Retry the
   rows path with exponential backoff only as a fallback.
3. **Parquet-only datasets need a real parquet reader.** Without pyarrow the
   honest options are installing it or writing the reader - do not claim a
   parquet source was gathered when only its metadata was read.

## The amoeba (the diagnostic self-evolving model)
`wubu_amoeba` — THE HIVE IS THE BODY. Cells ARE hive slots:
- **GROW** = wubu_hive_insert (freelist pop or new block — mitosis)
- **SHRINK** = wubu_hive_erase (skip-mark + freelist push — apoptosis)
- **DIAGNOSE** = wubu_hive_foreach (jumps skips, sees only live)
- immune system: utilization / grad-norm / loss-delta (quadratic approx
  -||g||²/n) / route entropy; classify by mean-relative thresholds
- fitness gate: held-out loss tolerance + the Lean prover (wubu_prover2:
  Möbius closure, exp∘log, gyroassoc) + floor/ceiling
- DGM pattern: accepted → archive; rejected → 5+1 rollback
- DA CAUGHT: mutate signals must match diagnose (loss_delta sign is NOT
  the grow signal); absolute grad floor needed for all-dead colonies;
  feed_grads is REGISTRY-order not hive-visit-order
- lifecycle demo: tools/amoeba_lifecycle.c (colony 8→2→3→2, capacity
  stable at 64 — the freelist recycles)

## The RLHF oracle (research/043-rlhf-rlvr-implementation.md, RC03)
- GRPO: G=8, ε=0.2, β=0.01, lr 1e-6, KL in the LOSS not the reward,
  advantage = (r-mean)/std, same Â for all tokens in a response
- R1's small-model finding: **distillation > RL for ≤32B** — skip RLVR
  at 35M unless distilling from a bigger teacher
- cold-start SFT needed before RL; anti-hacking: hidden tests, KL
  early-stop, group degeneracy guard
- oracles: tools/nvidia_nim.py (score_draft), tools/openrouter_rlhf.py
  (rlhf_improve) — see the wubu-keys-and-oracles skill

## Commands
```bash
cd /home/wubu/wubuwizard
# train (the REAL analytic backward + REAL Muon, GPU-accelerated)
./wubu_train --model models/wubu/model.safetensors \
    --tok /home/wubu/models/corpus/cosmopedia-v2-00000.tok \
    --steps 40 --seq 128 --muon-lr 1e-3 --adam-lr 1e-3 --ckpt 1000
# speed (RTX 4050, 2026-08-03): fwd+bwd 0.64s, optimizer 0.3s, ~1.1s/step
# (was 18s + 38.5s CPU). 40 steps on the real corpus: loss 9.32 -> 7.69.
# The GPU rides the weak-symbol dispatch in wubu_backprop.c; the
# Muon NS5 is cuBLAS (see c-systems-programming for the row-major trap).
make wubu_train_gpu && ./wubu_train_gpu ...   # same CLI
# tests
make test_hive test_amoeba test_moe2 test_hyper test_nest test_deltanet \
     test_prover2 test_wubu test_wubu_save test_backprop test_wubu_train
make test_all          # the full gate
# amoeba lifecycle
gcc -O2 -Wall -std=c11 -I include tools/amoeba_lifecycle.c \
  src/wubu_amoeba.c src/wubu_hive.c src/wubu_moe2.c src/wubu_prover2.c \
  src/wubu_hyper.c -o /tmp/amoeba -lm && /tmp/amoeba
# stream live data (needs HF read token — see keys skill)
python3 tools/wubu_stream.py --stream finemath --tok models/wubu/tokenizer.json \
  --out /home/wubu/sdcard/corpus/tokens/finemath-live.tok
```

## Checkpoint export, GPU backend, corpus pipeline, publishing
(absorbed from the former wubuwizard-model-training skill)

### Checkpoint export (safetensors writer)
- Writer emits the REAL format: `[8B header_len][header JSON padded to 8][blob]`.
  The padding MUST be inside `header_len` (append spaces so `(8+len)%8==0`).
- `wubu_save` writes all 137 tensors with the released names
  (embedding.weight, layers.N.attn.*, layers.N.ffn.*, selectors.*).
- VERIFY with the official reader (`from safetensors import safe_open; f =
  safe_open(path, framework='np')`) — our own C reader round-tripping is NOT
  sufficient (both sides can share a layout bug). Round-trip: save → reload →
  byte-identical (test_wubu_save).

### GPU training backend (gpu_wubu.cu)
- cuBLAS SGEMM computes `out = x @ w^T` for the engine's row-major [out,in]
  weights — use `CUBLAS_OP_T` on the weight with `lda=K`. Verify vs the CPU
  loop with tools/gpu_matmul_check.c (max_diff < 1e-4) before trusting results.
- Weak-symbol dispatch (`__attribute__((weak))` decls in wubu.c) means CPU-only
  links (no -lcublas -lcudart) still work; caller checks the symbol non-NULL.
- Build: `nvcc -O2 -c src/gpu_wubu.cu -o gpu_wubu.o -Xcompiler -fPIC` then link
  `-L/usr/local/cuda-13.1/lib64 -lcublas -lcudart -Wl,-rpath,/usr/local/cuda-13.1/lib64`.
  WSL2: see cuda-utilities skill for the libcuda.so.1 pathing trap.

### Corpus pipeline (SSD active / SD cold)
1. `python3 tools/wubu_stream.py --stream <ds>` — stream HF rows → .tok live
2. `python3 tools/wubu_extract.py <ds> <a> <b>` — parquet → text
3. `./wubu_tokenc models/wubu/tokenizer.json text/*.txt tokens/*.tok` — C11 BPE
   (65× faster than the Python encoder; the pair→rank hash made it fast)
4. `./wubu_train_cli --tok tokens/*.tok --steps N --lr 1e-4` — train
Pitfalls: drvfs (SD) writes are slow and can stall in D state — chunk, background
with notify_on_complete; `getline` needs `_POSIX_C_SOURCE 200809L` FIRST.

### Publish to HuggingFace
- Repo `WaefreBeorn/WuBu-35M` (was WuBu-Seed-35M). Tokens in
  `~/.cache/huggingface/token` (0600) — NEVER commit; the HF config dir is
  gitignored. README carries the mandatory AGI disclosure; LICENSE is the
  WaefreBeorn Umbrella License v3.0. Verify a published model by re-downloading
  and checking SHA-256.

## Verification
- `make test_all` → "=== ALL TESTS PASSED ==="
- ASan: compile with -fsanitize=address (the hive/amoeba/moe2 all
  pass under ASan)
- Triple DA: tests ≠ correct — verify a bug is REAL before patching,
  else say clean

## Pitfalls
- drvfs SD card writes are SLOW (D state) — background long jobs
  with notify_on_complete
- the tokenizer needs local_strdup under -std=c11 (implicit decl bug)
- GPU matmul orientation: cuBLAS needs CUBLAS_OP_T on the weight
  (x@w^T, matches CPU to 7e-7)
- safetensors padding: (8 + header_len) % 8 == 0, spaces INSIDE header
- .st checkpoints ≠ safetensors — convert via wubu_save for HF upload
