# Mind Palace

`mindpalace` is the durable skill-and-review layer for the ~WuBu~ AGI family:
**wubuwizard = brain, wubunos = compiler, wubuos = body**. It is a repo other
agents can clone to inherit the mind palace without inheriting one session's
memory.

It contains:

- every Hermes skill in `.hermes/skills/`, indexed by `mp index`;
- a `mp` alias skill that routes into the palace;
- a **1000-step Devil's Advocate review loop** with a four-phase structure;
- `slate.md` (current focus), `INDEX.md` (all files), `DEVILS_ADVOCATE.md`
  (attack protocol), and `ROADMAP.md` (extension phase plane);
- tools that regenerate the index and verify that no documented path is dead.

## The base prompt (lilypad)

> hermes, i would like you to create a markdown mind palace in a .hermes
> directory in this project, i would like a index system of all project files
> and devils advocate details, the mind palace is a prestige prompt structure
> system that uses multi stage directions based on project needs, the mind
> palace needs a 4 phase devils advocate loop structure as well as a slate
> markdown
>
> to consider and control this as a goal, create it as a looping 1000 step
> devils advocate review process and then roadmap the extension phase plane
>
> then use this to create the mind palace skill alias mp

## Using it

```bash
git clone https://github.com/waefrebeorn/mindpalace.git
cd mindpalace
python3 tools/index_repo.py --write
python3 tools/verify_mindpalace.py
```

Ask an agent to load the skill `mp`, then give it a step number or a target:

- `mp orient <repo>` -- rebuild the index and state claims.
- `mp attack <claim>` -- run the four Devil's Advocate phases.
- `mp close <finding>` -- implement the smallest real increment with a gate.
- `mp prestige` -- write slate, handoff and next phase-plane step.

## Provenance

This repo aggregates skills authored in the Hermes skill tree for this project.
No third-party source was copied or derived. No API keys, tokens, passwords,
credentials or connection strings are stored here; skills reference secret
files by path only.

## License

WaefreBeorn Umbrella License v3.0. See `LICENSE`.


## Completed palace (2026-11-21)

The scaffold is now a working system. `.hermes/mindpalace/` is the canonical,
verifiable palace; `.hermes/skills/` carries the aggregated skill family.

- `mp` router + 5 companion skills: `mp-devils-advocate`, `mp-review-1000`,
  `mp-phase-plane`, `mp-prestige`, `mp-index`, with 8 reference docs.
- `commands/mp` dispatches orient / attack / close / prestige / index /
  verify / review / status / skills (previously "Not yet wired").
- `tools/review_1000.py` generates the 1000-pass loop as 250 packs
  (4000 phase steps), idempotently.
- `tools/index_project.py` indexes all tracked source files of a git repo,
  excluding generated gates/binaries, hashing in parallel.
- `tools/verify_mindpalace.py` fails on dead doc paths, stale SHAs, or an
  invalid SKILL.md contract.

```bash
bash .hermes/mindpalace/commands/mp verify --strict-paths
bash .hermes/mindpalace/commands/mp review --passes=1000
```
