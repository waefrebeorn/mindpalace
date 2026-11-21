---
name: wubu-design-philosophy
description: Amoeba body on nested spheres. Load before model work.
---

# WuBu Design Philosophy (the amoeba on nested spheres)

> The user's standing design doctrine, distilled 2026-08-04. THEORY/01
> (geometry IS the architecture), THEORY/03 (WuBu nesting), and
> docs/wubu-amoeba-design.md are the canonical texts. research/050
> (lab convergence) + research/051 (Triple-DA) are the audits. This
> skill is the operating summary — reload it before ANY model work.

## The one-sentence doctrine

WuBu is an **amoeba**: a colony of cells that starts very small, grows
very large, absorbs information, and adapts to the task — running its
core system needs on the most dense layers, structured by a **nested
sphere** (product of K Poincaré balls with learnable curvatures) system
because *the geometry IS the architecture*.

## The four layers (the operating doctrine)

| Layer | What it is | The mechanism |
|---|---|---|
| **Metabolism** (from the labs, research/050) | how cells LEARN | Muon (2D matrices, NS5) + AdamW (1-D); WSD or warmup→const→cosine→ANNEAL-to-0 on upsampled quality data; data mix ~50/25/17/8 (general/math/code/multi); SFT cold-start at LOW lr (~1e-5); GRPO verifiable rewards; MTP λ=0.3; stability gate (no rollbacks) |
| **Skeleton** (the spheres, THEORY/03) | the SPACE the body lives in | product of K Poincaré balls, K curvatures, Möbius addition, exp/log maps, per-ball weight w_k (softmax); the Lean prover guards geometric invariants (Möbius closure, exp∘log, gyroassoc). The Poincaré ball is the base manifold per the user's doctrine ("the Poincaré sphere is a basic manifold math network base; nesting is a sphere thing"). For the radial/nesting dimension specifically, the Klein chart is the candidate — straight-line geodesics make scalar-multiply and parallel transport plain tangent-space ops (no exp/log pair per op); other shapes (Klein-bottle nested shapes) fit other concerns, not the sphere nesting. Math is treated as a full dynamic system, not static structure (external overlap notes: wubuwizard/vault/external-findings/). |
| **Spine** (the dense core) | the SYSTEM-critical layers | the most dense layers carry core needs; wubu_bi (block importance) identifies them; function-preserving grow splits them when overworked |
| **Body** (the amoeba loop, wubu-amoeba-design.md) | the growth/shrink lifecycle | TRAIN → DIAGNOSE (utilization, grad norm, loss-delta, route entropy, wubu_bi) → MUTATE (grow=split overworked, shrink=prune dead, stasis) → VALIDATE (prover + held-out loss + safety kernel) → ARCHIVE/ROLLBACK (5+1 recovery + wubu_priority ledger) → repeat |

## The lifecycle (one epoch)

```
1. TRAIN: the colony learns (Muon + real backprop, the RC01 recipe)
2. DIAGNOSE: immune system measures every cell
3. MUTATE: plateau-triggered grow/shrink (RARE, not per-step)
4. VALIDATE: held-out loss + the prover + safety invariants
5. ARCHIVE or ROLLBACK: fitness up -> keep + archive; down -> 5+1 restores
6. REPEAT: the body is a different size (e.g. 35M → 70M → 30M params —
   sizes it wears, not its name). It adapts to the task, not to a fixed config.
```

## Model identity: the body is never named by a parameter count

**WuBu is a runtime-dimensioned body.** Geometry comes from
`WUBU_RUNTIME_DIMS`; `wubu_parameter_count()` is a pure function of it. Two
geometries are real and measured (`tools/test_runtime_dims.c` asserts both):

| geometry | params | meaning |
|---|---:|---|
| checkpoint-native (the legacy `WuBu-35M` release) | **35,073,216** | tensor layout of the first published checkpoint |
| aligned (current default) | **56,376,832** | dim 512 · ffn 2048 · 12 layers · vocab 16384 · 3 selectors |

Rules:
- Never write "WuBu is a 35M model" or use a parameter count as the model's
  name. Qualify by geometry when a number is needed.
- `include/wubu.h` still carries `WUBU_DIM 448` / `WUBU_FFN_DIM 1228` — retired
  prototype constants that DISAGREE with the runtime 512/2048. Do not read model
  shape from them; a new file that does inherits a 35M assumption.
- Canonical statement: `wubuwizard/docs/MODEL-IDENTITY.md`. When a doc disagrees
  with it, the doc is the bug — fix the doc, not the numbers.

## The Triple-DA verdict (research/051) — what the labs CONFIRM and what they DON'T cover

**Confirmed (transfer directly):** Muon+AdamW split, WSD/anneal schedule,
data mix shape, SFT cold-start at low lr, GRPO, MTP, stability gate,
fine-grained MoE cells, small-models-train-longer.

**NOT lab-covered (our own claims, carry own risk):**
1. Dense-core + sparse-shell topology — validate with wubu_bi
2. Hyperbolic SSM blocks — the FD-verified backward is what makes the
   standard recipe usable on curved blocks; LR may not transfer, measure
   (the HAKMEMQController meta-tuner is the answer)
3. The prover gate — guards GEOMETRY (spheres stay spheres); loss gates
   FITNESS. Two gates, one per concern.

**The single biggest risk: under-training.** Labs train small models on
trillions of tokens; at ~6.7B tokens WuBu-35M is under-trained by lab
standards. Growth to 70M must come with MORE data (the ponds, SFT,
agentic packs are the food supply). Grow the corpus WITH the body.

## The "diagnostic" double meaning (the model's self-knowledge)

1. The model diagnoses ITSELF (the immune system) — watches its own health.
2. The model diagnoses THE WORLD — the route pattern (which cells fired)
   IS its explanation of its reasoning: the transparent, verifiable trace.

The two are the same loop. **The route trace is the diagnosis; the
diagnosis is the model's self-knowledge.**

## Non-negotiables (the user's standing rules)

- Geometry is not a feature — it IS the architecture (hyperbolic space
  from the start, not bolted on).
- The body adapts to the task, never to a fixed config.
- Growth is function-preserving (forward-before == forward-after);
  shrinkage is fitness-gated (BI-informed + loss tol + prover + FD).
- Mistakes roll back (5+1 recovery); every accepted variant is archived
  (the DGM branch tree — the lineage ledger).
- The lab recipe is the metabolism — never regress to momentum-SGD
  "Muon" or skip the anneal phase.
- The philosophy is CORPUS CONTENT too: the model learns how to build
  AGIs (Tier-3 methodology tier, tools/build_methodology_tier.py).

## The routing doctrine (2026-08-04 — the user's vision, verbatim-intent)

> "If you can figure out how to get everything routed correctly, we can
> train the best model at home... using our video game methodology of N64
> Rambus, making our laptop train and inference as an AGI in our own
> operating system, making our own kernels, our own bootable — by learning
> from the other models."

**Everything in the system IS a routing problem.** Get every route right
and a laptop becomes an AGI foundry:

| Route | Mechanism | Module |
|---|---|---|
| token → expert | learner-free hash routing (DeepSeek) | `wubu_hashrouter` |
| query → KV block | coarse-to-fine indexer (DSA) | `wubu_dsa` |
| signal → residual stream | hyper-connections (mHC) | `wubu_mhc` |
| data → fast channel | N64 Rambus: NARROW bus, HIGH clock, serial bursts | `wubu_rambus` |
| compute → backend | compile-once dispatch (PSO: table lookup hot path) | `wubu_kernel` |
| state → precision | Escha ladder (per-family bits) | `wubu_precision_plan` (AM03) |
| process → OS personality | VSL syscall routing (Linux/NT/Mac/toast) | wubuos `vsl_syscall*` |
| bytes → memory tier | hot/warm/cold KV tiering | `wubu_kv_tier` |

The game-hardware lens applies to EVERY optimization: (1) can it be
pre-compiled for the exact config? (2) can data be stored as formula
parameters? (3) can access be serialized through a narrow channel?
The home-foundry goal: own the whole stack (kernel → boot → train →
infer) and absorb every zoo model's mechanism into our own C11.

## Absorbing an external research framework — C11 or bust

Standing preference: a framework's ideas are absorbed, its Python never runs the
loop. "Added to the system" means OUR binary executes it.

1. **Vendor as reference only.** Clone into `third_party/<name>/` with the
   upstream commit in `UPSTREAM_SHA`, upstream LICENSE intact, and a doc section
   saying explicitly that it is documentation, not an execution path. Never wire
   a benchmark's Python launcher into the product loop.
2. **Reimplement the parts that decide behaviour**, not the prose: scoring,
   composition, the ledger, the executor argv. Each lives behind a
   `make test_<name>` target with assertions on the fail-closed paths (empty,
   duplicate, full table, bad index, unparseable record). "58 checks, ALL PASSED"
   is the only acceptable form of "integrated".
3. **Name the regime difference in the fidelity claim.** If the source composes
   by behavioural contrast with *no ground-truth verifier*, and our controller
   scores probes by a check command's exit status, that is a verifier and a
   different regime — write it in the doc next to the implementation, never let a
   module called "the loop" imply paper parity. Multi-edit evidence is
   `confounded`, not credited, when one run cannot isolate an edit.
4. **Triple devil's advocate before claiming done, and let each round change
   code:** (a) algorithm fidelity against the paper (read the primary, not the
   README); (b) measurement credibility — does the number come from a binary that
   actually ran, and what did the change cost (struct size, RSS)? (c) implementation
   defects — dangling harness pointers, fields the API promises but never writes,
   unescaped JSON, a timeout that kills the shell but leaves its children.
   Each of those three is a normal finding once you look; finding none means you
   did not look.

## The KV-namespace doctrine (2026-08-05 — "THE KV CACHE IS A FILE SYSTEM")

The user's revaluation of design from the ground up, written down in
`THEORY/05-kv-cache-filesystem.md`, proven in
`research/061-kv-cache-filesystem-7hop.md`, carried in
`docs/wubu-model-blueprint.md` §2.7. The model is OURS, so it can be
modality-agnostic: all files are data, all inputs are encoded (single
encoder — Gemma 3 12B SigLIP 400M is the closest base), and the KV
cache is a NAMESPACE, not a context window: downloads (/kv/in) live in
the same space as synthesized data (/kv/synth), memory persists
(/kv/mem). The serving world already proved every mechanism
(PagedAttention blocks, RadixAttention paths, MemGPT self-paging,
Mooncake disaggregated pool, LMCache persistent KV-chunk files,
Infini-attention compressive writes) and half is in-tree (wubu_kv_tier,
wubu_lmcache, wubu_dsa, wubu_orbits, paged/ring KV). The gap = the
address layer (G1 wubu_kvfs namespace, G2 mounts, G3 single-encoder
head, G4 compressive write-back, G5 Styx export at /n/kv/, G6
self-paging loop). Load this doctrine before any KV/memory/model-base
work.

## The Revolver Doctrine (2026-08-08 — "make it revolver", the iGBA lens)

The user's standing directive: cross-check the ENTIRE system for anything
static and make it revolver. Full doctrine: THEORY/06-revolver-doctrine-
adaptive-hotswap.md, the 7-hop: research/062-igba-hotswap-revolver-7hop.md.

**The one-liner: WuBu is a Lego body on a revolver chassis — every
subsystem is a slot, every payload is a swappable cartridge, every
consumer probes the live contract. THE STATIC ASSUMPTION IS THE
UNIVERSAL PITFALL.**

The GBA lineage (iGBA → VBA-M → Game Pak slot → MBC banking → save-type
probe → mGBA adaptive timing → adaptive ML) proves it:

1. **The slot precedes the module.** Design the socket first (Game Pak
   slot), the payload second. No registration seam = no grow/shrink/rotate.
   Reference: wubu_kernel_register, AN23-2 adapter framework.
2. **Probe, don't assume.** GBA probes cartridge shape + save chip + bank
   layout. WuBu probes: active layers (done), backend (done), dims (WuBu1
   done), precision, expert count. Any constant describing the WORLD (not
   the code) is a static assumption to be probed.
3. **Ask-and-adapt, never ask-and-hardcode.** The VBA-M bug: negotiated
   SDL audio format, then `(uint16_t*)` cast anyway = silent corruption.
   A consumer casting a negotiated buffer to a fixed type is a bug.

The five disciplines (standing rules):
1. **No fixed geometry** — dims are runtime (WUBU_DIMS); `#define` model
   shape is a violation. S1: wubu.h still #define-static (the 448-dim prototype
   constants), which is tracked debt, not a source of truth.
2. **No fixed capacity** — counts are banked (MBC-style). Flat N_EXPERTS=256
   with no bank register dies when tasks outgrow the cylinder (S3).
3. **No static policy tables** — allowlists/anticheat/name tables are
   registries (S7-S11: seccomp allowlists, anticheat_db, styx_names,
   colonel g_apps, image arch names).
4. **No hardcoded schedule** — lr/anneal is a negotiated object from the
   tuner (S12); a constant schedule is the 300ms ring buffer.
5. **No casts on negotiated buffers** — read the returned contract.

The revolver vocabulary: body (frame, never rebuilt) / cylinder (the
swappable set, fixed chambers) / cartridge (self-describing payload) /
slot (the registration seam) / trigger (router probes live state) /
hammer (gate fails closed on unknown cartridge).

Rotation beats replacement: continual learning (EWC + merging + Revolver-
style parameter rotation) rotates trained experts in/out; the amoeba
grow/shrink is body-level rotation; expert-level rotation is the missing
piece. The GBA proves whole-bus switching is necessary (GBC shape
detector re-wires CPU/joypad/WRAM) — the VSL toast personalities ARE this.

## The manifold training stack (pre-train / post-train / fine-tune)

The geometry is already proven; the training layer is what uses it. Read
`/home/wubu/wubumath/docs/LINKAGE.md` FIRST (read-only — another agent owns
that repo): it maps 17 Lean theorems (0 `sorry`) to capabilities. Where the
C11 and the Lean disagree, the Lean is right and the C is the bug. The three
load-bearing facts: Möbius addition preserves the ball (nD), gyration pre-
serves the inner product (it is a rotation), and parallel transport is a
Riemannian isometry.

**Stage map.** Pre-train: token embeddings as ball points (`wubu_exp_map`),
hierarchy loss (child closer to parent than to a sibling), radius
regulariser, φ-curvature nesting schedule — R is fixed by the proven
progression, never learned per batch. Post-train: preferences as geodesic
relations (`σ((d(b,r) − d(a,r))/τ)`), GRPO steps via parallel transport,
KL measured on the manifold. Fine-tune: Möbius LoRA (below). Serve: KV in
tangent charts, Euclidean only at the final softmax.

**The gradient rule (this cost a debugging cycle).** Return and apply the
TANGENT-space gradient, not the ambient Euclidean one. For a hyperbolic
classifier with `logit_k = −‖u−v_k‖²/(2R²)`, the gradient is
`dL/du = Σ_k (p_k − y_k)·(−(u−v_k)/R²)`; step `u ← u − lr·dL/du` then
`x ← exp_map(u)`. Feeding the ambient `dL/dx` into a tangent step is
dimensionally wrong: it diverged (loss 1.07 → 30) and pushed the point out of
the ball. Test: one step must reduce loss, 300 steps must cut it >80%, and
the optimised point must still satisfy `‖x‖ < R`.

**Möbius LoRA.** `u = log_map(h)`, `u' = u + B(Au)`, `h' = exp_map(u')`.
Properties that must hold and be tested: `B = 0` is the exact identity;
the output never leaves the ball (ExpMapBall.lean).

**Merge rule — transport first.** Adding tangent updates before the exp map is
correct ONLY when the adapters share a base point. Adapters trained from
different snapshots sit at different anchors, and tangent vectors at different
points are not summable:

```
for each ball k:
    v_i = P_{h_i→h}( log_{h_i}(h_i ⊕ Δ_i) )   # parallel transport
    v   = Σ_i w_i,k · v_i                     # w from curvature × BI × Fisher
    h'  = exp_h(v)                            # stays inside the ball
```

Consequences to enforce:
- Merge **per ball**, with that ball's curvature; a single global average is the
  flat-space assumption (CAMEx, arXiv:2502.18821) our design rejects.
- There is no parallel-transport implementation in the tree
  (`grep parallel_transport src include` is empty) — `wubu_hypmom` is
  deliberately transport-free as a momentum approximation, which is NOT a merge
  rule. Multi-anchor merging stays blocked until transport exists.
- Test the asymmetry: same-anchor merges commute, different-anchor merges must
  not. A test expecting commutativity across anchors is wrong.

Literature convergence (full pass in `wubuwizard/docs/MANIFOLD-MERGING.md`):
task arithmetic (2212.04089) → TIES (2306.01708) → DARE (2311.03099) → Fisher
weighting (2111.09832) → Lie-algebra merging (OrthoMerge 2602.05943) →
curvature-aware experts (CAMEx 2502.18821). One rule: **merge in a shared
tangent frame at a common base point, weighted by curvature/importance.**

**Canonical geometry lives in `src/wubu_mobius.c`.** `wubu_exp_map` and
`wubu_log_map` are declared in `wubu_mobius.h` and defined there; other
files must not carry copies (they once did, in the GGUF bridge and reader).

Shipped: `src/wubu_manifold_train.c` (head + LoRA), `wubu_hyperbolic_output_proj`,
`wubu_poincare_gqa`, `wubu_nested_ssm`. Design doc: `docs/MANIFOLD-TRAINING.md`.

## References

- THEORY/01-foundational-philosophy.md (geometry IS architecture)
- THEORY/03-wubu-nesting-paper.md (the nested spheres math)
- THEORY/05-kv-cache-filesystem.md (the KV namespace)
- THEORY/06-revolver-doctrine-adaptive-hotswap.md (the revolver doctrine — static→revolver conversion checklist + the five disciplines)
- research/062-igba-hotswap-revolver-7hop.md (the 7-hop + the P1-P15 pitfalls + the S1-S12 audit)
- docs/wubu-amoeba-design.md (the body + the loop)
- research/050-training-methodology-7hop.md (the lab convergence)
- research/051-triple-da-amoeba-spheres-vs-labs.md (this audit)
- src/wubu_amoeba.c, src/wubu_nested_ssm.c, src/wubu_bi.c,
  src/wubu_priority.c (the shipped mechanisms)
- `docs/MANIFOLD-TRAINING.md` (the pre/post/fine-tune design + the
  WuBuMath theorem map)
- `/home/wubu/wubumath/docs/LINKAGE.md` (read-only: proven theorem → capability)
- `wubuwizard/docs/HARNESS2-INTEGRATION.md` (worked example of absorbing an
  external research framework: vendored reference tree, C11 controller with its
  check count, attribution verdicts, three devil's-advocate rounds)
