---
name: mp-phase-plane
description: Extension phase plane: capability radius x review depth.
version: 1.0.0
author: WaefreBeorn
metadata:
  hermes:
    tags: [mind-palace, roadmap, phase-plane, extension]
    related_skills: [mp, mp-review-1000]
---

# mp-phase-plane — extension roadmap

## When to Use

Use when asked to "roadmap the extension phase plane", choose the next
capability to build, or decide whether a change is real progress.

## The two axes

- **Capability radius** R0 file → R1 module → R2 repo → R3 ecosystem.
- **Review depth** D0 shape → D1 negative control → D2 differential oracle →
  D3 cross-config/statistical → D4 formal proof.

A capability is not real at R2 because it passes at D0. Move both axes.

| Phase | Radius | Depth | Exit condition |
|---|---|---|---|
| P0 Orient | R0-R1 | D0-D1 | every named path exists, claim falsifiable |
| P1 Attack | R1-R2 | D2 | old code fails the new gate |
| P2 Close | R2 | D2-D3 | narrow + full + product gates green |
| P3 Prestige | R2-R3 | D3 | fresh agent can continue from written state |

## Extension directions

1. **Depth** — extend the 1000-step review from review into planning.
2. **Breadth** — attach new document types besides the slate.
3. **Automation** — make `.hermes/mindpalace` queryable/scriptable (`mp` CLI).
4. **Velocity** — throughput without reducing coverage.
5. **Skill depth** — add a skill only after one full four-phase loop; record
   author, version, trigger.
6. **Index / oracle / prestige depth** — full index coverage, native oracles,
   verifiable handoffs.

## Principles

Every script writes real outputs; nothing synthetic. Every new axis maps to a
documented phase. Naming follows existing canon casing. Never claim a phase
exit without its gate output.
