---
name: mp
description: Mind palace router: index, DA loop, prestige.
version: 2.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [mind-palace, prestige, devil-advocate, router, review-1000]
    related_skills: [mp-devils-advocate, mp-review-1000, mp-phase-plane, mp-prestige, mp-index]
---

# mp — Mind Palace (router / alias)

The palace is not memory. Memory evaporates between sessions; the palace is
the written structure a fresh agent can verify and continue. Every state
claim in it is a **hypothesis until gated**.

## When to Use

Say `mp`, "mind palace", ask for a prestige handoff, a Devil's Advocate
review, a 1000-step review run, a project index, or the durable skill layer
of another agent.

## Commands

- `mp orient [repo]` — read `slate.md`, rebuild `INDEX.md`, verify every named
  path exists, list state claims as hypotheses.
- `mp attack <claim>` — run the four phases in `DEVILS_ADVOCATE.md`:
  ORIENT, ATTACK, CLOSE, PRESTIGE (canonical: Locate / Against / For / Decide).
- `mp close <finding>` — implement the smallest real increment with a negative
  control and a differential gate; record STATUS, never "honest gap".
- `mp prestige` — update slate, step log and handoff; verify SHAs and gates.
- `mp index [--write]` — SHA-256 index of every file with provenance.
- `index_project.py` — git-aware index of all tracked source files in a repo
  (excludes generated gates/binaries) -> `PROJECT_INDEX.md`.
- `mp verify` — hard gate: required files, dead doc paths, skill contract.
- `mp review --passes=1000` — generate idempotent review packs (4 passes/pack).
- `mp status` / `mp skills ls|view` — inspect state and the skill family.

## The four phases (never condensed, never reordered)

1. **Locate** — subject, scope, success criteria; write a falsifiable claim.
2. **Argue AGAINST** — the strongest negative case; attack the metric itself.
3. **Argue FOR** — the strongest positive case, with evidence.
4. **Decide** — synthesize, choose, record rationale and next coordinate.

A pass that skips a phase is an opinion, not a pass.

## The 1000-step loop

Steps 0001..1000. Each consumes one finding, runs all four phases, appends the
finding template to `STEPLOG.md`, increments the slate, and takes the next
step immediately. The count is a discipline, not a wall: at 1000, continue at
1001 if reachable work remains.

## Phase plane (two axes, move both deliberately)

- **Capability radius** R0 file → R1 module → R2 repo → R3 ecosystem.
- **Review depth** D0 shape → D1 negative control → D2 differential oracle →
  D3 cross-config / statistical → D4 formal proof.

Exit conditions: P0 every path exists and claim falsifiable; P1 old code fails
the new gate; P2 narrow + full + product gates green; P3 a fresh agent can
continue from written state.

## Rules

1. A handoff is a claim, not evidence. Re-run the gate yourself.
2. Tests != correct: run the negative control against the pre-fix code.
3. Never end on a list of absences. CLOSE, mark IN-FLIGHT with owner/worktree/
   gate, or VERIFIED_NEGATIVE with exact refusal output.
4. Skill descriptions must be <=60 chars. Dead paths in docs are failures.
5. Write the next step before stopping; writing the handoff is not completion.
6. **Repo-view DA:** before believing any port claim, check object symbols
   (`nm -g`), callers, and the running artifact. A green leaf oracle on a dead
   object is not progress.
7. Rebuild the index after every change; a stale SHA is a defect.
8. Prefer native / cross-toolchain oracles over self-checks.

## Skill family (aggregated)

`mp` is the router. The procedure modules are also standalone skills:
`mp-devils-advocate`, `mp-review-1000`, `mp-phase-plane`, `mp-prestige`,
`mp-index`. Load the one matching the current phase.

## References

- `references/repo-view-da.md` — evidence ladder, dead-credit guard, continuous execution.
- `references/four-phase-da.md` — canonical Locate/Against/For/Decide loop.
- `references/review-1000.md` — 1000-pass engine and pack bookkeeping.
- `references/phase-plane.md` — extension phase plane and exit conditions.
- `references/slate-schema.md` — slate YAML schema and round-trip rules.
- `references/stage-system.md` — multi-stage direction grammar and signals.
- `references/prestige.md` — handoff discipline.
- `references/index-system.md` — SHA-256 index and dead-path verification.
