# Four-Phase Devil's Advocate loop

The explicit adversarial structure. Never condensed, never abbreviated, always
in this order. Each run is one **devils pass**; multiple passes form a **cycle**.

## Phases

1. **Locate** — subject, scope, success criteria, falsifiable claim.
2. **Argue AGAINST** — strongest possible negative case; attack the metric.
3. **Argue FOR** — strongest possible positive case, with evidence.
4. **Decide** — synthesize, select direction, record rationale.

State machine: `LOCATE -> AGAINST -> FOR -> DECIDE -> REPEAT or DONE`.

## Output fields

`phase`, `pass`, `claim`, `evidence`, `confidence`, `decision`.

## Finding template

```
### Step NNNN -- <title>
- Claim:
- Evidence (command + real output):
- Negative control (old code / forced failure):
- Smallest real increment:
- Gate run (exact target + result):
- FOR case / AGAINST case:
- STATUS: CLOSED | IN-FLIGHT(owner, worktree, gate) | VERIFIED_NEGATIVE
- Next phase-plane coordinate:
```

## Anti-patterns

- Skipping FOR because AGAINST is "obviously correct".
- Bypassing DECIDE because AGREE was reached early.
- Conflating multi-issue and single-issue subjects.
- Re-running against evidence that has already been re-scoped.
- Ending on a list of absences instead of CLOSE / IN-FLIGHT / VERIFIED_NEGATIVE.
