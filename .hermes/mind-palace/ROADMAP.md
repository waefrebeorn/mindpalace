# Extension phase plane

Two axes, not a to-do list:

- **Capability radius** R0 file -> R1 module -> R2 repo -> R3 ecosystem.
- **Review depth** D0 shape -> D1 negative control -> D2 differential oracle
  -> D3 cross-config / statistical -> D4 formal proof.

A capability is not real at R2 just because it passes at D0.Move both axes
deliberately.

## Phase plane

| Phase | Radius | Depth | Exit condition |
|---|---|---|---|
| P0 Orient | R0-R1 | D0-D1 | every named path exists, every claim falsifiable |
| P1 Attack | R1-R2 | D2 | old code fails the new gate |
| P2 Close | R2 | D2-D3 | narrow + full + product gates green |
| P3 Prestige | R2-R3 | D3 | fresh agent can continue from written state |

## 1000-step cadence

Steps are numbered 0001..1000. Each step consumes one finding:

1. pick the highest-leverage reachable finding from the slate;
2. run ORIENT, ATTACK, CLOSE, PRESTIGE;
3. append the finding template to `STEPLOG.md`;
4. increment the slate;
5. take the next step immediately.

The count is a review budget, not permission to stop early. If step 1000 is
reached and reachable work remains, continue with 1001; the number is a
discipline, not a wall.

## Extension directions

- **skill depth**: add a skill only when the procedure has survived one full
  four-phase loop; record author, version and trigger.
- **index depth**: `tools/index_repo.py` must cover every file, including new
  skills; a dead path in any doc fails `verify_mindpalace.py`.
- **oracle depth**: prefer native/cross-toolchain oracles over self-checks.
- **prestige depth**: the next agent must be able to verify, not merely trust.
