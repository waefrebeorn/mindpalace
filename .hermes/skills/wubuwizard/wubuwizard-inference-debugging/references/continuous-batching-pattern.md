# Continuous Batching & Deterministic Scheduler Pattern

## Context
wubuwizard targets CPU-only decode on WSL2 (6 P-cores, ~13 GB RAM).
The decoder processes one request at a time, but a future scheduler
must support continuous batching across multiple concurrent requests.

## Key Pattern: Deterministic Scheduler
- `src/wubu_scheduler.c` / `include/wubu_scheduler.h`
- Two policies: FIFO (strict arrival order) and ROUND_ROBIN (fair share)
- Per-request state: `wubu_sched_request_t` with priority, remaining_tokens,
  and a `next` pointer for the run queue.
- The scheduler is fed by `wubu_model_forward` returning tokens for any
  request that has completed its current forward pass.

## Integration Point
At the top of `gen_text`'s decode loop (after `wubu_model_forward_from_embd`
returns logits), instead of the single-token greedy path, the scheduler
dequeues all requests ready for a forward pass, runs them in batch (T>1),
and collects results. This is the same pattern used by vLLM scheduling
but simplified for a single-host CPU engine.

## Pitfall: position-unstable T>1 forward
`wubu_model_forward`'s multi-token (T>1) path carries SSM/conv/GQA state
across tokens in the same call. This state carry is currently
position-unstable and non-deterministic (argmax differs between T=8 and
T=9 for the same prefix). Fix this BEFORE wiring continuous batching,
because batched speculative decoding depends on reproducible T>1 state.
See `wubu_model_reset_state()` for the zero-state helper that makes
cross-run comparisons clean.