---
name: mp
description: Mind palace router: index, DA loop, prestige.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [mind-palace, prestige, devil-advocate, router]
    related_skills: [wubu-prestige-handoff, devils-advocate-audit]
---

# mp -- Mind Palace router

## When to Use

Use when the user says `mp`, "mind palace", asks for a prestige handoff, a
Devil's Advocate review, or wants the durable skill layer of another agent.

## Commands

- `mp orient <repo>` -- read `.hermes/mind-palace/slate.md`, rebuild
  `INDEX.md`, verify every named path exists, list state claims as hypotheses.
- `mp attack <claim>` -- run the four phases in
  `.hermes/mind-palace/DEVILS_ADVOCATE.md`: ORIENT, ATTACK, CLOSE, PRESTIGE.
- `mp close <finding>` -- implement the smallest real increment with a
  negative control and a differential gate; record STATUS, never "honest gap".
- `mp prestige` -- update slate, step log and handoff; verify SHAs and gates.

## Rules

1. A handoff is a claim, not evidence. Re-run the gate yourself.
2. Tests != correct: run the negative control against the pre-fix code.
3. Never end on a list of absences. Close, mark IN-FLIGHT with owner, or
   VERIFIED_NEGATIVE with exact refusal output.
4. Skill descriptions must be <=60 chars. Dead paths in docs are failures.
5. Write the next step before stopping; writing the handoff is not completion.

## References

- `.hermes/mind-palace/INDEX.md` -- all files.
- `.hermes/mind-palace/DEVILS_ADVOCATE.md` -- loop protocol.
- `.hermes/mind-palace/ROADMAP.md` -- extension phase plane.
- `.hermes/mind-palace/PRESTIGE.md` -- handoff discipline.
