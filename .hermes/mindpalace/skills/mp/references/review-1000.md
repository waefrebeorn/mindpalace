# 1000-Review engine

## Operator contract

- A **review** is a series of **passes**; a **pass** is one four-phase loop.
- Four phases per pass: Locate, Argue AGAINST, Argue FOR, Decide.
- 1000 passes = full cycle. Passes are **Eager** (immediate/in-order),
  **Observing** (recorded from live activity), or **Batch** (consolidated in
  `sessions/review-1000/`).

## Bookkeeping

Pack numbering: `pack-001` .. `pack-250`, four passes each.
250 packs x 4 passes x 4 phases = 4000 phase steps, counted at pass granularity
as 1000 passes. Statuses: `pending | running | done | skipped | failed`.

Generation is idempotent: `mp review --passes=1000` regenerates the packs and
`review-state.json` deterministically. Each pass carries the finding template
and a status field; nothing is synthetic and nothing is pre-closed.

## Cadence

1. Pick the highest-leverage reachable finding from the slate.
2. Run ORIENT, ATTACK, CLOSE, PRESTIGE (all four phases).
3. Append the finding template to `STEPLOG.md`.
4. Increment the slate.
5. Take the next step immediately.

The count is a review budget, not permission to stop early. At 1000 with
reachable work remaining, continue at 1001.
