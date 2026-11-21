---
name: mp-devils-advocate
description: Four-phase DA loop with repo-view evidence ladder.
version: 1.0.0
author: WaefreBeorn
metadata:
  hermes:
    tags: [mind-palace, devil-advocate, evidence, negative-control]
    related_skills: [mp, mp-review-1000]
---

# mp-devils-advocate — four-phase attack loop

## When to Use

Use when a claim needs adversarial review: a port claim, a coverage headline, a
green oracle, a handoff assertion, or any "done" status. Also use as phase 1 of
`mp attack`.

## The four phases (never condensed, never reordered)

1. **Locate** — subject, scope, success criteria. Write a falsifiable claim.
2. **Argue AGAINST** — strongest negative case; attack the metric itself.
3. **Argue FOR** — strongest positive case with real evidence.
4. **Decide** — synthesize, select direction, record rationale.

State machine: `LOCATE -> AGAINST -> FOR -> DECIDE -> REPEAT or DONE`.
A pass that skips a phase is an opinion, not a pass.

## Evidence ladder (highest rung wins)

1. Source/annotation → claim, never evidence.
2. Compiled object → `nm -g --defined-only`; zero symbols = dead credit.
3. Wired build graph → membership without symbols is theater.
4. Running binary → source != artifact.
5. Differential oracle against live truth → behavior, not shape.
6. Water-cup / path parity → right answer by the wrong route.
7. Negative control → pre-fix implementation must FAIL the same gate.

Never report a rung-1/2 green as rung-4+ progress.

## Procedure

- ORIENT from the body-level reality scoreboard, not a coverage headline.
- ATTACK all objects with the same shape (baseline + detector, not one-off).
- Run the negative control on the OLD code.
- CLOSE in place, in the wired, caller-bearing file; keep the C ABI.
- If reachability cannot be established, strip the claim; do not relabel it.
- STATUS must be CLOSED, IN-FLIGHT(owner, worktree, gate), or
  VERIFIED_NEGATIVE with exact refusal output. Never "honest gap".

## Anti-patterns

Skipping FOR; bypassing DECIDE; conflating multi-issue subjects; re-running
against re-scoped evidence; ending on a list of absences; counting claims
instead of gate output and running artifacts.
