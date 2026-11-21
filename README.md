# Mind Palace

`mindpalace` is the durable skill-and-review layer for the ~WuBu~ AGI family:

- **wubuwizard = brain**
- **wubunos = compiler**
- **wubuos = body**
- **mindpalace = the written structure a fresh agent can verify and continue**

It is a repo another agent can clone to inherit the mind palace **without inheriting one
session's memory**. Memory evaporates between sessions; the palace does not. Every state
claim in it is a hypothesis until it is gated.

The core idea is deliberately simple: a **human-readable, per-project-adaptable markdown
folder** that uses human-psychology-style examples (prestige, loci, stage walks, vivid
slates) so that both a person and an agent can navigate it. It is not a global config file,
not a memory dump, and not a rigid template stamped onto every project.

## Origin

From the author's own post (21 Nov 2026):

> mindpalace
>
> its a human readable memory organization i tried to pitch as a default skill
>
> teknium never understood why a organized human readable markdown folder skill that uses
> human psychology style examples was useful
>
> bruh its a human readable per project adaptable
>
> screw it i am making it a repo now and will aggregate all of the agents learning into it
> as i go

Source: [x.com/waefrebeorn/status/2124173043035467830](https://x.com/waefrebeorn/status/2124173043035467830)

History: the workflow was first submitted upstream as `NousResearch/hermes-agent` PR #25240,
then withdrawn as a personal workflow skill that belongs in `~/.hermes/skills/`. It later
became this repo. The intended destination is slermes ("mind palace is built into slermes");
when a palace outgrows flat markdown, the planned graduation is DuckDB + wiki over the same
structure, not a second competing system.

## What is in this repo

| Path | What it is |
|------|-----------|
| `.hermes/mindpalace/` | **Canonical, verifiable palace** — slate, index, attack protocol, roadmap, prestige, steplog, tools, skills, commands |
| `.hermes/mind-palace/` | Seed walkway: `slate.md`, `INDEX.md`, `DEVILS_ADVOCATE.md`, `ROADMAP.md`, `PRESTIGE.md`, `STEPLOG.md` |
| `.hermes/skills/` | Aggregated Hermes skill family for the WuBu projects, including the `mp` router and five companion skills |
| `tools/` | Root-level index/verify/review scripts mirrored from the canonical palace |
| `LICENSE` | WaefreBeorn Umbrella License v3.0 |

### Canonical palace files

| File | Purpose |
|------|---------|
| `slate.md` | What is being worked on **right now** |
| `INDEX.md` | Every file in the repo with SHA-256 provenance |
| `DEVILS_ADVOCATE.md` | The four-phase attack loop and finding template |
| `ROADMAP.md` | Extension phase plane and 1000-step cadence |
| `PRESTIGE.md` | Controlled handoff, not a reset |
| `STEPLOG.md` | One finding per step, with gate and STATUS |

Supporting directories: `docs/` (canon, devil-advocate, phase-plane, review-1000, slate,
stage-system), `index/` (decision log, project index), `sessions/review-1000/` (generated
review packs), `slates/active.yaml` (live slate), `skills/` (mp family), `tools/` (working
scripts), `commands/mp` (the CLI).

## Core properties

From the palace canon (`docs/mind-palace.md`):

- **Prestige** — only high-signal payloads are promoted.
- **Multi-stage** — work is divided into ordered stages based on project needs.
- **Deterministic** — given the same seed, the same path is taken.
- **Loopable** — loops can terminate early, be truncated, or be resumed.
- **Ephemeral** — the 1000-step list is regenerated if it diverges from reality.

Operating rules:

1. **Branch-first load.** All implementations branch from an existing branch; no branch is
   created without a parent.
2. **Four permitted moves:** Load a branch into context, Index the project-wide file index,
   Scaffold a stage or phase skeleton, Review a target with the four-phase loop.
3. **Question authority.** Nothing is authoritative unless it is inside the palace folder.
   On conflict, the more populated branch wins.
4. **A handoff is a claim, not evidence.** Verify paths, SHAs, gates, and skill state against
   the artifact before repeating them.

## The four-phase Devil's Advocate loop

Never condensed, never reordered. A pass that skips a phase is an opinion, not a pass.

1. **Locate** — subject, scope, success criteria; write a falsifiable claim.
2. **Argue AGAINST** — the strongest negative case; attack the metric itself.
3. **Argue FOR** — the strongest positive case, with evidence.
4. **Decide** — synthesize, choose, record rationale and the next coordinate.

The CLI also exposes the mnemonic `ORIENT / ATTACK / CLOSE / PRESTIGE`, which maps onto the
same loop. Findings are recorded in `STEPLOG.md` with a STATUS and a gate, never a vague
"honest gap". The smallest real increment ships with a negative control and a differential
gate.

## The 1000-step review

From the original lilypad prompt: *create it as a looping 1000 step devils advocate review
process, then roadmap the extension phase plane.*

The operator contract (`docs/review-1000.md`):

- A **review** is a series of **passes**; a **pass** is one four-phase loop over a subject.
- **1000 passes** is the full 1000-review cycle.
- Passes are **eager** (run in order), **observing** (recorded from live activity), or
  **batch** (consolidated in `sessions/review-1000/`).
- Bookkeeping uses **packs**: `pack-001` through `pack-250`, four passes per pack, four
  phases per pass = **4000 phase steps** counted at pass granularity as **1000 passes**.
- Generation is **idempotent** — `tools/review_1000.py` rebuilds the same packs.
- Status codes: `pending`, `running`, `done`, `skipped`, `failed` (retains partial state).

Note on interpretation: the upstream `mind-palace` skill implements the same idea as a
**convergence loop** — repeat the four-phase pass until no new high-risk item appears —
rather than a literal counter. Both forms express the same discipline: do not exit on
"looks done".

## Slate markdown

Walkway files use a compact slate format: purpose (one sentence), key decision, then
structured data and bullets. Slates are the active working set; the `INDEX.md` is the file
inventory with hashes; the `STEPLOG.md` is the audit trail. Keep bullets over prose.

## Quick start

```bash
git clone https://github.com/waefrebeorn/mindpalace.git
cd mindpalace

# Rebuild the SHA-256 index and verify the palace is internally consistent
bash .hermes/mindpalace/commands/mp orient
bash .hermes/mindpalace/commands/mp verify --strict-paths

# Generate the full 1000-pass review (idempotent)
bash .hermes/mindpalace/commands/mp review --passes=1000
```

Then ask an agent to load the `mp` skill and give it a step number or a target:

| Command | Effect |
|---------|--------|
| `mp orient [repo]` | Rebuild `INDEX.md`, verify every named path, list state claims as hypotheses |
| `mp attack <claim>` | Run the four Devil's Advocate phases against a claim |
| `mp close <finding>` | Implement the smallest real increment with a negative control and gate |
| `mp prestige` | Update slate, step log, and handoff; verify SHAs and gates |
| `mp index [--write]` | SHA-256 index of every file with provenance |
| `index_project.py` | Git-aware index of all tracked source files, excluding generated gates/binaries |
| `mp verify` | Hard gate: required files, dead doc paths, skill contract |
| `mp review --passes=N` | Generate idempotent review packs, four passes per pack |
| `mp status` | Show the active slate and review progress |
| `mp skills ls\|view` | Inspect the skill family |

Review operators: `mp begin review`, `mp status`, `mp run --passes=N`, `mp report`,
`mp reset --hard` (drops review state — use with caution).

## Skill family

`.hermes/skills/` carries the aggregated skill tree for the WuBu projects. The palace's own
six-skill family lives in `.hermes/mindpalace/skills/`:

- `mp` — router / alias. Load this first.
- `mp-devils-advocate` — four-phase loop and evidence ladder.
- `mp-review-1000` — the 1000-pass review engine.
- `mp-phase-plane` — extension phase plane.
- `mp-prestige` — handoff discipline.
- `mp-index` — index plus dead-path gate.

The router's `references/` holds the detailed procedures. In the installed Hermes skill
tree the same system is available as `mind-palace` with alias `mp`; that copy also carries
aggregated third-party references (see below).

## Tools

| Script | Job |
|--------|-----|
| `tools/index_repo.py` | SHA-256 index of every file with provenance |
| `tools/index_project.py` | Git-aware index of all tracked source files in a repo; excludes generated gates/binaries |
| `tools/verify_mindpalace.py` | Hard gate — fails on dead doc paths, stale SHAs, invalid SKILL.md contract |
| `tools/review_1000.py` | Idempotent 1000-pass / 250-pack review generator |

## Provenance and third-party references

The core palace and its skill family are authored by waefrebeorn. Third-party mindpalace
skills are **linked as clickthrough references, not vendored here**:

- [frankxai/mind-palace-agent-skills](https://github.com/frankxai/mind-palace-agent-skills) —
  Memory Palace and Blessing Protocol suites (13 skills).
- [aashutosh396/mindpalace-skill](https://github.com/aashutosh396/mindpalace-skill) —
  portable resource-first knowledge vault.

The installed `mind-palace` skill keeps verbatim copies with source clickthroughs in its
`third-party/` folder, subordinate to this repo's doctrine.

No API keys, tokens, passwords, credentials, or connection strings are stored in this repo;
skills reference secret files by path only.

## Direction of travel

- Per-project adaptation over a single global template.
- Human-readable markdown first; DuckDB + wiki graduation when a palace gets large.
- slermes as the eventual built-in home.
- Accumulate agents' learnings in this repo over time rather than in transient chat.

## License

WaefreBeorn Umbrella License v3.0. See `LICENSE`.
