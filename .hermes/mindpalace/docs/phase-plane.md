# Phase Plane — Extension Roadmap

## Mission

Sustain and extend the Mind Palace beyond its initial scaffold across
four axes:

- Depth — extend the 1000-step review from review only to planning.
- Breadth — attach new document types besides the slate.
- Automation — make `.hermes/mindpalace` queryable and scriptable.
- Velocity — improve throughput without reducing coverage.

## Phase 0 — Boot

- [x] Scaffold `.hermes/mindpalace`
- [x] Add canon docs: `mind-palace.md`, `stage-system.md`, `devil-advocate.md`
- [x] Add `slate.md`
- [x] Add skeleton project index
- [ ~ ] Add 1000-step review generator
- [ ~ ] Add bash alias `mp`

## Phase 1 — Index & Provenance

- [ ] Automatic branch detection and branching rule enforcement.
- [ ] Provenance stamping on all generated artifacts.
- [ ] Integration with Hermes memory system (write/read only).
- [ ] Per-branch index diff output in `index/`.

## Phase 2 — Observer Mode

- [ ] Lightweight observer process using `cronjob`.
- [ ] Watch for dirty `slate_id` fields.
- [ ] Watch for orphan `stages_run` entries.
- [ ] Snapshots of state on each loop boundary.

## Phase 3 — Generator

- [ ] Scripted generation of `docs/review-1000.md` from a template.
- [ ] JSON and Markdown outputs for programmatic tooling.
- [ ] CI integration for validating `.hermes/mindpalace/` schema.
- [ ] Regeneration if drift exceeds a configurable threshold.

## Phase 4 — Interface

- [ ] Hermes compatible skill interface for `mp`.
- [ ] Shortcuts to the most common MP operations.
- [ ] Interactive prompts for missing schema fields.
- [ ] Query language for `index/project-index.md`.

## Extension principles

- Every script must write real outputs; nothing is synthetic.
- Every new axis must map to an existing phase or a new documented phase.
- Naming must follow the existing canon casing and vocabulary.
