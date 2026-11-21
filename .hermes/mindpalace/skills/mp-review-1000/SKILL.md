---
name: mp-review-1000
description: 1000-pass review engine: packs, passes, four phases.
version: 1.0.0
author: WaefreBeorn
metadata:
  hermes:
    tags: [mind-palace, review, 1000-steps, loop]
    related_skills: [mp, mp-devils-advocate]
---

# mp-review-1000 — the looping 1000-step review

## When to Use

Use when asked to "consider and control this as a goal", run a 1000-step review,
generate review packs, or keep a Devil's Advocate loop going across sessions.

## Contract

- A **review** is a series of **passes**; a **pass** is one four-phase loop
  (Locate / Argue AGAINST / Argue FOR / Decide).
- 1000 passes = full cycle. Divided into 250 packs of 4 passes.
- 250 x 4 x 4 = 4000 phase steps, counted at pass granularity as 1000.
- Statuses: `pending | running | done | skipped | failed`.
- Modes: Eager (in-order), Observing (from live activity), Batch (in
  `sessions/review-1000/`).

## Run it

```
mp review --passes=1000        # idempotent pack generation
mp status                      # slate + review progress
```

`tools/review_1000.py` writes `pack-001.md` .. `pack-250.md`,
`review-state.json` and `REVIEW.md`. Generation is deterministic and
idempotent — re-running reproduces identical files.

## Cadence (one finding per step)

1. Pick the highest-leverage reachable finding from the slate.
2. Run ORIENT, ATTACK, CLOSE, PRESTIGE — all four phases.
3. Append the finding template to `STEPLOG.md`.
4. Increment the slate (`pass_count`, `loop_state`, `summary`).
5. Take the next step immediately; do not pause at a status report.

The number is a discipline, not a wall: at 1000 with reachable work left, go
to 1001. The 1000-step list is regenerated if it diverges.

## Output fields per pass

`phase`, `pass`, `claim`, `evidence`, `confidence`, `decision`, `STATUS`,
`next phase-plane coordinate`.
