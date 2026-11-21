# The model-growth bring-up (wubuwizard, 2026-08-04)

The growth operator (Net2Net function-preserving doctrine + the Zhiqi Bu
progressive schedule + the NeurIPS'24 growth taxonomy) wired into the C11
WuBu engine. The DA oracle: the grown model's forward must equal the
small model's forward at init -- the function-preserving property is
directly measurable.

## The zero-init residual insertion
- A block whose weights are ALL zero is an EXACT identity at init: its
  attention output is 0 (V=0 kills the P·V path), its gate is 0, its FFN
  output is 0 -- the residual stream passes through unchanged. The
  function-preserving test measured max|pre-post| = 0.000e+00 (exact).
- The rmsnorm of a zero vector is 0·(1/sqrt(eps)) = 0 -- safe as long as
  the norm's eps > 0 (no div-by-zero/NaN).

## The per-block rhythm flags (the 7.7e-3 leak)
- Any behavior keyed by the layer INDEX shifts when layers are inserted:
  the attention's is_full rhythm AND the residual-selector firing
  ((l+1) % SELECT_EVERY) both changed the model's function after an
  insertion (the selector leak measured 7.7e-3 -- small enough to pass a
  sloppy tolerance, real enough to fail the exact oracle).
- Fix: per-block flags (is_full[], fire_sel[]) shifted ALONG WITH the
  block structs; the new zero block never fires the selector (an identity
  blend is harmless, but not firing keeps the selector ORDER aligned).
- The selector's grad-slot index (l+1)/SELECT_EVERY-1 still resolves to
  the right selector for the shifted layers because the fired layers keep
  their relative order and the zero blocks never fire.

## The active-layer-count contract
- Add m->n_layers to the model struct; the forward loops, the backprop
  recorder forward, the loss (the last-ACTIVE-layer xlast), the backward
  loop, the muon step's norm/matrix loops, and the parameter count all
  switch to it. The released model = WUBU_LAYERS at init (parity
  untouched -- the full FD suite still passes).
- The bp's selector detection must consult the per-block fire_sel (the
  recorder forward must match the released forward exactly under growth).

## The train-state growth
- The per-block grad + Muon-momentum pointers shift with the blocks (the
  same order as the model's struct shift); FREE the displaced unused
  buffer at arr[n_layers] BEFORE the shift (the pre-allocated full-model
  buffers leak otherwise); the new block's buffers zero-calloc'd.
- The AdamW norm slots [4l+0..3] shift the same way; the new block's four
  slots get fresh buffers.

## The DA tests that matter
- The zero block's OWN gradients are exactly 0 at init (its V=0 kills
  every path -- dP=dO·V^T=0, dS=P·(0-rs)=0 since rs=rowsum(dO∘O)=0 too).
  An FD on the zero block is VACUOUS (rel 0 trivially). Test the OLD
  block's weights, or the embedding.
- The embedding's grad is ~1e-2 -- measurable in the fp32 loss; the
  q_proj's grads are ~1e-5 and the ~10-scale fp32 loss swamps their FD
  (fd reads exactly 0). Sample the max-|grad| element, eps=1e-2.
- The bp's loss of the grown model must equal the small model's (the
  function-preserving property THROUGH the backward): diff 0.000e+00.
- The -ffast-math build's FP reordering makes the FD marginally noisier
  than a plain -O2 build: the masked-CE measured 8.3e-3 direct vs ~2e-2
  with -ffast-math. Keep FD tolerances fp32-honest (5e-2), not 1e-2.

## The make test_all silent-skip trap
- A test target whose BINARY exists is not rebuilt/re-run by `make
  test_all` even when its recipe changed (file-target semantics): a test
  that FAILED when built directly can be silently SKIPPED in the full
  gate, which still reports "ALL TESTS PASSED". Always `rm -f <test
  binary>` before `make`; after a direct-build failure, verify the
  test_all actually RAN the test (check its output line, not just the
  final banner).

## The 8MB-stack segfault
- A 1<<20-entry pointer hash table declared as a local array is 8MB --
  past the default 8MB stack; the process segfaults at first touch.
  Heap-alloc the hash table (and free it), not the pool alone.

## The leftover-debug-printf hygiene
- A one-off kernel printf from a debugging session can fire in a real
  run: a probe hardcoded for seq=128's failing index coincidentally
  matched at seq=256 and spammed the training output. Strip ALL debug
  printfs (host fprintf AND kernel printf) before any commit; grep the
  .cu/.c for the probe pattern, not just the host-side fprintf.
