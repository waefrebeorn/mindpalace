# Mind Palace core

The palace is not memory. Memory evaporates between sessions; the palace is
the written structure that a fresh agent can verify and continue.

- `slate.md` — what is being worked on RIGHT NOW.
- `INDEX.md` — every file in this repo, with SHA-256 provenance.
- `DEVILS_ADVOCATE.md` — the four-phase attack loop and finding template.
- `ROADMAP.md` — extension phase plane and 1000-step cadence.
- `PRESTIGE.md` — controlled handoff, not reset.
- `STEPLOG.md` — one finding per step, with gate and STATUS.

## Skill family (aggregated)

- `skills/mp/SKILL.md` — the router / alias. Load this first.
- `skills/mp-devils-advocate` — four-phase loop + evidence ladder.
- `skills/mp-review-1000` — 1000-pass review engine.
- `skills/mp-phase-plane` — extension phase plane.
- `skills/mp-prestige` — handoff discipline.
- `skills/mp-index` — index + dead-path gate.
- `skills/mp/references/` — eight procedure references.

## Working tools (not stubs)

- `commands/mp` — CLI: orient, attack, close, prestige, index, verify, review,
  status, skills.
- `tools/index_repo.py` — SHA-256 index generator.
- `tools/verify_mindpalace.py` — hard gate: paths, SHAs, skill contract.
- `tools/review_1000.py` — idempotent 1000-pass / 250-pack generator.
- `slates/active.yaml` — the live slate.

A handoff is a **claim**, not evidence. Verify paths, SHAs, gates and skill
state against the artifact before repeating them.
