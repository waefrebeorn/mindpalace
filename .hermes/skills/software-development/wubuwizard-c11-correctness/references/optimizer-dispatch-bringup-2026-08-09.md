# wubu_optim — the unified optimizer dispatch bringup (2026-08-09)

The user's optimizer research (research/069) became a real tool this session.
This is the full transcript: the design, the geometry-split, the gate, and
every bug the synthetic-geometry test surfaced.

## The design (include/wubu_optim.h, src/wubu_optim.c)

```
Muon/NS5   -> the flat (Euclidean) matrices   (the whole S7 body today)
AdamW      -> 1-D params (norms/embeddings/selectors)
RSGD       -> the non-Euclidean (Poincaré-ball) vectors (rsgd_step:
              retraction-based step, radius R + clip — when the
              hyperbolic cells wire into the body)
qlearner   -> Q-learns the LR from the loss (10 loss-bins x 3 actions)
TGT        -> the gravitational-pole odometer: polar-coordinate trajectory
              around loss-landscape basins; falls INTO ravines (r shrinks
              while loss drops), ejects from the trap (r->2.0 after ~8
              flat-but-curvy steps -> the anti-gravity LR bump)
```

KEY INSIGHT (user, 2026-08-09): "these optimizers work for you in EUCLIDEAN
space too, if you use the OPTIMIZED SGD." The RSGD/PID/TGT family is not
hyperbolic-only — with the optimized-SGD form (retraction -> GD as R->inf)
it is a general non-Muon alternative everywhere. Muon stays the flat-matrix
champ; TGT is the ravine navigator for BOTH spaces.

## The gate (tools/test_optim.c) — what it proves

1. Muon path trains on a synthetic from-scratch model (loss finite, no NaN,
   no OOB — ASan clean). The synthetic geometry: dim=256, ffn=512, layers=4,
   heads=4, kv_heads=1, head_dim=64, rope_dim=32, max_seq=128, local_win=16,
   full_every=4, select_every=2.
2. qlearner adapts the LR: 1e-4 -> 1.6e-2 after 5 steps (Q-learning moved it).
3. TGT odometer: r shrinks 1.0 -> 0.63 while falling, ejects r=2.0 on the trap.

`make test_optim` — link line (the full object chain):
```
$(CC) $(CFLAGS) -fopenmp -I include -o $@ tools/test_optim.c \
  src/wubu_optim.o src/wubu.o src/wubu_train.o src/wubu_backprop.o \
  src/wubu_moe2.o src/safetensors_reader.o src/wubu_dequant_nf4.o \
  src/wubu35_dims.o src/qlearner.o src/rsgd.o src/wubu_mobius.o \
  src/gguf_reader.o -lm
```
Missing rsgd deps: `rsgd_step` calls `wubu_exp_map` (gguf_reader.c) +
`wubu_mobius_add` (wubu_mobius.c) — link both or you get undefined refs.

## The bugs the synthetic geometry surfaced (all fixed)

### 1. wubu.h ITSELF hardcoded the dims (the deep one — P48-4)
`include/wubu.h` had `#define WUBU_DIM 448 / WUBU_FFN_DIM 1228 /
WUBU_LAYERS 12` — the compile-time constants SHADOWED the runtime
WUBU35_DIMS macros. The loader set runtime dims, but the training path ran
448-era geometry (gdb: `mm(..., out_n=2456, in_n=448)` while WUBU35_DIMS
read 512/256). Fix: wubu.h `#include "wubu35_dims.h"` FIRST; the 448/1228
block wrapped in `#ifndef WUBU35_DIMS_H`; struct array members capped
(WUBU_MAX_LAYERS 64, selectors[8], WUBU_MAX_NORM_SLOTS).
SYMPTOM to recognize: "variably modified 'q_proj_g' at file scope" = an
array sized by a runtime macro.

### 2. Two wubu_model_t types (wubu.h vs wubu_model.h)
wubu.h defines the direct-weights training model (wubu_model_init 5-arg);
wubu_model.h defines the opaque gguf-loader model (wubu_model_init 2-arg).
Including wubu_model.h from wubu_train.h -> `conflicting types for
'wubu_model_init'` breaks the whole train link. NEVER include both.

### 3. The hardcoded-64 family in wubu_backprop.c (P48-4b)
(a) wubu_bp_alloc sized k_pre/k/s_dk/s_dv as `max_seq * 64` — with kv_heads
    > 1 or head_dim != 64 the buffers are too small (5 sites -> use
    `max_seq * (WUBU_KV_HEADS * WUBU_HEAD_DIM)`).
(b) `probs[WUBU_LOCAL_WIN + 2]` VLA in cpu_attn_loop + backward is
    window-sized but a FULL-attention row (is_full=1, lo=0) fills `seq`
    entries -> dynamic-stack-buffer-overflow (ASan: `[cb]` redzone at
    offset 40). Fix: `float probs[seq + 1];`.
Both invisible at 448/7-heads/1-kv because 64 happened to be right.

### 4. From-scratch synthetic model traps
- The selectors array must be filled BEFORE wubu_model_init — init COPIES
  the pointer values, so filling after leaves `m->selectors[i]` NULL and
  the selector path segfaults in bp_forward.
- The full block must be allocated: attn/q/k/ffn norms + q/k/v/o/g/gate_up/
  down matrices (all calloc'd, zeroed).
- full_every >= 1, select_every with layers/select_every >= 1 (div-by-zero).

### 5. TGT velocity ordering bug (P49)
`vel = loss_prev - loss` computed AFTER `loss_prev = loss` -> always 0.
Snapshot prev first, compute, then store.

### 6. Meta-optimizer null-guard ordering (P50)
qlearner/TGT (loss-only) must run BEFORE `if (!m || !tr) return` — the
optimizer switch needs the model, the meta-optimizers don't.

## The takeaway rule
Build a synthetic model with a DIFFERENT-but-legal geometry and run the real
train path on it under ASan. The 448 seed's "correctness" masks every
geometry-hardcoded bug; the synthetic geometry surfaces them all at once.
