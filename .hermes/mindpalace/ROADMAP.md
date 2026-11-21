# Extension phase plane

Two axes, not a to-do list:

- **Capability radius** R0 file -> R1 module -> R2 repo -> R3 ecosystem.
- **Review depth** D0 shape -> D1 negative control -> D2 differential oracle
  -> D3 cross-config / statistical -> D4 formal proof.

A capability is not real at R2 just because it passes at D0. Move both axes
deliberately.

## Phase plane

| Phase | Radius | Depth | Exit condition |
|---|---|---|---|
| P0 Orient | R0-R1 | D0-D1 | every named path exists, every claim falsifiable |
| P1 Attack | R1-R2 | D2 | old code fails the new gate |
| P2 Close | R2 | D2-D3 | narrow + full + product gates green |
| P3 Prestige | R2-R3 | D3 | fresh agent can continue from written state |

## 1000-step cadence

Steps are numbered 0001..1000. Each step consumes one finding, runs all four
phases (Locate / Argue AGAINST / Argue FOR / Decide), appends the finding
template to `STEPLOG.md`, increments the slate, and takes the next step
immediately. The count is a review budget, not permission to stop early: at
1000 with reachable work remaining, continue at 1001.

Packs: `pack-001` .. `pack-250`, four passes each, generated idempotently by
`tools/review_1000.py` into `sessions/review-1000/`.

## Extension directions

- **skill depth**: add a skill only when the procedure has survived one full
  four-phase loop; record author, version and trigger. (aggregated: mp + 5)
- **index depth**: `tools/index_repo.py` covers every file, including new
  skills; a dead path in any doc fails `verify_mindpalace.py`.
- **oracle depth**: prefer native/cross-toolchain oracles over self-checks.
- **prestige depth**: the next agent must be able to verify, not merely trust.
- **automation depth**: `commands/mp` makes the palace queryable and scriptable.

## Delivery status

- [x] Scaffold `.hermes/mindpalace` and canon docs
- [x] Slate, index, 4-phase loop, phase plane, 1000-step review spec
- [x] 1000-pass review generator (250 packs, idempotent)
- [x] `mp` CLI wired (was "Not yet wired")
- [x] All mindpalace skills aggregated (router + 5 companions + 8 references)
- [x] Hermes skill interface (`mp` alias and family installed locally)
- [ ] Observer mode via cronjob (watch dirty `slate_id`, orphan `stages_run`)
- [ ] CI schema validation on fresh clone
