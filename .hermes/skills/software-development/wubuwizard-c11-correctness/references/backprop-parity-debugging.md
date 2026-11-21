# The backprop parity-debugging playbook (2026-08-03)

How the recording forward (wubu_backprop) was proven equal to the
released forward (wubu), the five bugs found, and the debugging
discipline that found them — including the debug-tool mistakes that cost
the most time.

## The setup: forward parity as a bug detector

Two implementations of the SAME model forward existed: the released path
(`wubu_forward`, buffer-reusing scratch) and the recording forward
(`wubu_bp_forward`, one dedicated buffer per activation). A test compared
their losses for the same tokens. When they disagreed (9.00 vs 9.71 —
suspiciously, ln(16384)=9.70, so the released path was near-random), the
parity test was RIGHT and the released forward was WRONG.

Rule: **the recording forward (dedicated buffers) is the correctness
anchor.** When a parity test fails, assume the released/buffer-reusing side
has an aliasing bug — not the dedicated-buffer side.

## The five bugs (all buffer-aliasing, all found via parity)

1. `b->ffn_gate` allocated `[seq, FF]` but gate_up is `[seq, 2*FF]` — the
   matmul computed only the gate half (`out_n = WUBU_FFN_DIM`), the SwiGLU
   read `g[d+FF]` out of bounds; calloc zeros made the up branch silently
   DEAD (the model "worked" on attention alone).
2. `checkpoint = b->x2` — aliased the buffer the o_proj matmul writes every
   layer, so the residual-selector checkpoint was the previous layer's
   o_proj output from layer 1 on.
3. The attention `osum` scratch (`b->x2`) was never zeroed per position —
   every head output included the previous layer's stale o_proj output
   (`osum[h*64+d] += ...` onto garbage).
4. `matmul(b->gate, g_proj, b->gate)` — in-place matmul: output row o
   clobbers input element o while the inner loop still reads it.
5. SwiGLU row stride `s * WUBU_FFN_DIM` on a `2*FF`-wide buffer — the
   gate/up halves scrambled (`g[d+FF]` = next row's gate half).

Plus: the WuBu-mode forward never computed the gate projection at all
(used the raw attn-norm output as the gate).

## The debugging discipline (in order)

1. **Bisect by input size.** Run both forwards on seq=1, 2, 3… — `seq 1:
   matches; seq 2: diverges` pinpoints that the bug involves the SECOND
   position's interaction (here: anything reading/writing row 1, or the
   attention window > 1 key).
2. **Replicate the released forward VERBATIM into a debug tool** (copy the
   code, same buffer reuse, independent scratch) and compare per-stage
   buffers against the recording forward's stored activations, layer by
   layer. This isolates WHICH stage first diverges.
3. **Compare the residual stream, not just the stage buffers.** The stage
   buffers (q/k/v/o/g/fo) can all match while the residual stream differs —
   check `x` itself per layer.
4. **Print the EXACT values at the divergence point** (both sides, every
   component: entry, o, g, fo, the recomputed sum). One print at the right
   element ended the hunt for the SwiGLU bug: "recompute u=-0.129 vs replay
   wrote u=-0.226" — the write didn't match the formula → stride bug.
5. **Self-consistency recomputation.** If `x_in[l] == x_in[l-1] + o·σ(g) + fo`
   recomputed from the recorder's OWN buffers (1e-8), the recorder is
   internally consistent and the OTHER side is wrong.

## Debug-tool bugs that wasted the most time (learn these)

- **Variable shadowing**: `double d = 0; for (int d = 0; d < 448; d++)` is
  legal C — the inner `int d` shadows the outer, the max never updates, the
  print never fires. Rename one of them. (Also: an array named `o` vs a
  loop var named `o`.)
- **Wrong strides when comparing recorder buffers**: a recorder allocated
  with `cap_seq=64` but indexed `l * seq * D` (seq=24) — comparing against
  `l * cap_seq * D` mixes layers and reports garbage "divergence" that
  isn't there. GET THE STRIDE RIGHT BEFORE TRUSTING ANY COMPARISON. When
  you "fix" a stride, verify which indexing the producer actually uses.
- **Reading a buffer after it was overwritten**: a debug block placed after
  `memcpy(cp, bl, ...)` compared the blend against itself. Put the print
  BEFORE the destructive write, or save a pre-write copy.
- **Row-offset bugs in the debug print**: `bl[d]` instead of `bl[s*448+d]`
  compares row 0 against every row — "matches to 1e-7" was a lie.
- **Grep patterns missing indented output**: the comparison prints started
  with two spaces; `grep -E "^relL"` matched NOTHING, so "no diffs" was
  wrong for many turns — the diffs were printing all along. When checking
  for output lines, don't anchor `^` unless you know the column. This was
  the single most expensive mistake of the session.
- **Interpreting a recomputed value as the buffer value**: printing
  `silu(gv)*uv` (recomputed from inputs) instead of the actual written
  buffer element masked the stride bug for several turns.

## The NS5 divergence (found when the training test went NaN)

After the backprop was correct, `test_wubu_train` went loss=NaN at step 2
with only k_proj (448×64, tall → transposed NS path) going NaN. Replicating
the NS iteration on the real gradient showed `max|M|: 0.32 → 1157 → inf`
across 5 iterations — the (3.4445, −4.7750, 2.0315) polynomial escapes its
attraction basin for spread singular-value spectra in fp32. Fix: Frobenius
re-normalize M after EVERY iteration (ratios are scale-invariant). See
P25 in SKILL.md. Verify with a synthetic tall matrix before trusting the
optimizer.

## Checklist for the next parity hunt

- [ ] Both forwards run on the same tokens; losses compared to 1e-3
- [ ] Bisect by seq (1, 2, 3…) — the first diverging size localizes the bug
- [ ] Per-stage buffer comparison at the PRODUCER's stride
- [ ] Residual stream compared (not just stage buffers)
- [ ] Exact-value print at the max-diff element, ALL components, both sides
- [ ] Self-consistency recomputation from the recorder's own buffers
- [ ] No debug-tool shadowing / row-offset / overwritten-read / grep-anchor
      mistakes (the list above)
