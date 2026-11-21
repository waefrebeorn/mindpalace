# 1000-Review — Review Roadmap

## Operator contract

- A **review** is a series of **passes**.
- A **pass** is one execution of the four-phase loop over the subject.
- Four phases per pass:
  1. Locate
  2. Argue AGAINST
  3. Argue FOR
  4. Decide
- 1000 passes is the full 1000-review cycle.
- Passes are either:
  - **Eager**: run immediately and in-order.
  - **Observing**: recorded from live activity.
  - **Batch**: consolidated in `sessions/review-1000/`.

## Pass bookkeeping

Uses `pack` numbering:
```
pack-001 to pack-250
```
Each pack contains 4 passes. Four phases per pass. That makes:
- 250 packs x 4 passes x 4 phases = 4000 phase steps.
- But we count at pass granularity,
- so the review is 1000 passes.

## Generation rules

- Packs are generated from this document.
- Generation is **idempotent**.
- Generated files are stored under `.hermes/mindpalace/sessions/review-1000/`.

## Status codes

- `pending` — not started.
- `running` — currently in progress.
- `done` — completed.
- `skipped` — explicitly omitted.
- `failed` — failed; retains partial state.

## Operator cheat sheet

- `mp begin review` — initialize a new review run.
- `mp status` — show current progress.
- `mp run --passes=N` — run N passes.
- `mp report` — write final report.
- `mp reset --hard` — drop review state; use with caution.
