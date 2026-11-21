---
name: mp-prestige
description: Prestige handoff: verified claims, not narrative.
version: 1.0.0
author: WaefreBeorn
metadata:
  hermes:
    tags: [mind-palace, prestige, handoff, verification]
    related_skills: [mp, mp-devils-advocate]
---

# mp-prestige — controlled handoff

## When to Use

Use at a session boundary, before a push, when asked for a prestige handoff, or
whenever a fresh agent must continue from written state.

## The ritual

1. Commit and push both the palace and the project it reviews.
2. Record local and remote SHAs — they must match after every push.
3. Update `slate.md` with the current step, not a vague "needs focus".
4. Rebuild `INDEX.md`; a path named in a doc that does not exist is a defect.
5. Re-run `tools/verify_mindpalace.py` and paste the real output.
6. Never claim a gate you did not run; mark UNVERIFIED if trusted.
7. Write the next concrete step, then take it. Writing the handoff is not
   completion.

## Status discipline

A gap is never parked as an "honest remaining gap". It is:

- **CLOSED** with the exact gate and output;
- **IN-FLIGHT** with owner, worktree and differential gate; or
- **VERIFIED_NEGATIVE** with the exact refusal/failure output.

## Handoff claim rule

A handoff is a **claim**, not evidence. The receiving agent re-runs the gate:
verify paths, SHAs, skill state and the running artifact before repeating any
assertion. Tests are not correctness — run the negative control on pre-fix code.
