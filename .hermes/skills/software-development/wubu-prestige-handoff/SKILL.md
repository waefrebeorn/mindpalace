---
name: wubu-prestige-handoff
description: Session prestige — skills, profile, SOUL, next prompt.
category: software-development
version: 1.1.0
tags: [prestige, handoff, mind-palace, session]
---

# WuBu Prestige Handoff

Prestige is a CONTROLLED handoff, not a reset: the next session has
NO memory of this one — it has ONLY what we write down. Write it all
down. This skill is the checklist. (The user's exact words: "you will
have no memory when you prestige.")

## When to run
- the user says "prestige", "fresh look", "new session framework",
  "clear out memory", "mind policing"
- a very long session is ending (the context is huge; a fresh start
  is wanted)
- before any major phase boundary
- a session opens with a handoff to inherit (a NEXT_SESSION_PROMPT.md on
  disk, or the user pastes a prestige report) — verify it before trusting it

## The checklist (in order)
1. **Skills** — create/update the procedural layer (it survives):
   - `wubu-agi-training-pipeline` — the corpus→train→amoeba→RLHF loop
   - `wubu-keys-and-oracles` — where the keys live + the live models
   - `wubu-amoeba-model` — the diagnostic self-evolving model
   - update `wubuos-session-workflow` with any new session-boundary
     lessons
   - skill descriptions must be ≤60 chars (the index truncates at 57)
2. **Memory** — the user may say "empty it"; the skills + docs are the
   durable layer. Resolve the store from the ACTIVE profile, never a
   hardcoded path: `$HERMES_HOME/memories/MEMORY.md` and `USER.md`
   (default profile here = `~/.hermes/memories/`). If the memory tool is
   rate-limited, write those files directly. Keep the USER profile
   minimal: who the user is (AGI creator), the repo split, the keys file
   path, the feedback loop.
3. **SOUL** — `~/.hermes/SOUL.md`: the identity. Add/refresh the
   AGI-creator identity, the feedback-loop directive, the disclosure
   order, and the prestige-is-handoff paragraph. Back up first
   (`cp SOUL.md SOUL.md.bak-<date>`).
4. **Keys** — verify they are stored in
   `~/.hermes/profiles/mind-palace/secrets/hf.env` (0600) and that the
   skills reference the FILE, never literals. Verify with
   `python3 tools/nvidia_nim.py embed` (expect 4096 dims).
5. **Repo state** — commit + push both repos; note the HEAD SHAs in
   the handoff so the next session knows exactly where it stands.
6. **NEXT_SESSION_PROMPT.md** — write it (see the template below).
7. **Mind Palace** — update `slate.md` (new focus), `index.md`,
   append `log.md` with the session's outcome.
8. **Verify** — `make test_all` green in wubuwizard; `make test` in
   wubuos; the test count in the handoff must be REAL (run it, don't
   copy it).

## Receiving a handoff (session start)

The handoff is a CLAIM, not evidence. Verify each state claim against its
artifact before acting on it or repeating it:

1. Paths it names — `read_file`, or `search_files (target='files')` for a
   tree. A handoff naming a path that should exist and does not is itself
   a defect to report.
2. Memory — read `$HERMES_HOME/memories/MEMORY.md` and diff it against what
   the handoff says was recorded; then list
   `$HERMES_HOME/pending/memory/` for staged-but-unapplied writes.
3. Repos — `git -C <repo> rev-parse HEAD` + `status -sb`; the SHA must
   match the handoff and local must equal origin.
4. Gates — re-run the named target when the claim is load-bearing; if you
   did not run it, say plainly that it was taken on trust.
5. Facts offered for memory — verify against the primary source
   (`.gitmodules`, `which <tool>`, `git branch --show-current`) and search
   the skills tree first: a fact already carried by a skill does not belong
   in memory.

## The NEXT_SESSION_PROMPT template
```markdown
# NEXT SESSION — <date>

## Who we are
We are the model creators. The AGI's name is WuBu. Two repos:
wubuwizard = THE BRAIN, wubuos = THE BODY. The feedback loop is the
standing directive: corpus → train → diagnose → mutate → validate →
archive → RLHF oracle → repeat. The amoeba is the model; the hive is
the body; the 5+1 recovery makes mistakes safe.

## State (verified <date>)
- wubuwizard HEAD: <sha> — <one-line>
- wubuos HEAD: <sha> — <one-line>
- test gates: <real counts>
- corpus on the SD card: <tokens available>
- HF: WaefreBeorn/WuBu-35M live with weights+card+LICENSE

## What was done last session
- <bullet per deliverable, with files + test evidence>

## Next priorities (in order)
1. <highest leverage first — e.g. finish wubu_backprop (the
   real per-layer backward + real Muon NS5); the old muon_update is
   momentum SGD, not Muon>
2. <wire the amoeba to the trainer's real per-expert gradients>
3. <the RLHF GRPO loop with the NVIDIA/OpenRouter oracles>
4. <the DGM archive + the 5+1 rollback wiring>

## Immediate actions
```bash
cd /home/wubu/wubuwizard && git pull && make test_all
cd /home/wubu/wubuos && git pull && make test
```

## DA RULE
Tests ≠ correct. Verify a bug is REAL before patching (read the code,
run the target, read the FAIL lines), else say clean. Triple DA after
every batch.

## Keys
`source ~/.hermes/profiles/mind-palace/secrets/hf.env` — NEVER
hardcode; GitHub push protection blocks key commits.

## Blockers / notes
- <anything the next session must know: background jobs, slow drvfs,
  OpenRouter 429, backprop in progress, etc.>
```

## Pitfalls
- The memory tool fails when the store is full — the batch is atomic
  and checks the FINAL total; free room by removing/consolidating in
  the SAME batch, or write the files directly (user-authorized). Measure
  before submitting: entries are joined with `\n§\n` and the limit is
  configured (default 2200 chars).
- **Staged is not saved:** writes from the background review daemon
  (`origin: background_review`) are ALWAYS staged into
  `$HERMES_HOME/pending/memory/*.json` and await `/memory approve <id>` —
  the write-approval gate setting does not exempt them. A handoff saying
  "memory recorded" while writes sit in pending/ describes intent, not
  state. Two staged patches may target the same entry with different
  content (the later supersedes the earlier) — reconcile to one version,
  and leave the approve/reject decision to the user.
- **A handoff prompt only reaches its own profile:** skills and memory
  resolve from the active profile home (`$HERMES_HOME/skills`,
  `$HERMES_HOME/memories`). A prompt filed under `profiles/<name>/` is
  invisible to a session bound to another profile, and a profile without
  those dirs starts with neither.
- Skill descriptions >60 chars are rejected — count first.
- YAML frontmatter: no colon in the description (parse error).
- Never put key literals in skills/docs/commits — reference the file.
- Handoff claims are hypotheses — diagnoses AND state claims (files,
  SHAs, memory contents, gate counts). Flag them UNVERIFIED and tell the
  next session to re-run targets before trusting them.
- **SOUL imprint target:** a repo file literally named `soul.md` (e.g.
  `docs/soul.md`) is refused by the agent-instruction guard — put the
  covenant in `~/.hermes/SOUL.md` (the identity file), never a repo path
  with that basename.
- **THREE REAL REPOS (user-corrected 2026-08-16):** `/home/wubu/wubuos` = WuBuOS BODY/OS repo; `/home/wubu/wubunos` = WuBuNOS COMPILER repo (real dir, NOT a symlink); `/home/wubu/wubuwizard` = THE BRAIN. `wubuos/src/compiler` is a symlink → wubunos; `wubuos/src/brain` is a gitlink submodule → wubuwizard. The old claim that "wubunos is a symlink to wubuos" is FALSE and caused Makefile corruption. Edit compiler files ONLY in wubunos; the OS build links them via `$(COMP)=src/compiler`.
- **"Needs a fresh context / for the next pass" is a FALSE GATE when the
  work is unfinished (user-corrected 2026-11): do not declare a handoff-able
  stopping point to park a still-reachable task.** Push to finish in-session
  -- keep bisecting, keep instrumenting the target until it runs; the harder
  it looks, the more likely a specific, findable cause (this session: a drag
  test failing because the centre-x grab hit the chrome minimize button).
  Only when genuinely stuck do you hand off, and then with the EXACT root
  cause + the EXACT next action, never a vague "needs a focused session".
  A deferral phrased as a gate reads as parking the goal.
- **Do not end a session on a list of "honest remaining gaps".** Phrased
  absences are treated as avoided work. Every gap must either be closed
  with a gate that actually ran, or be an active leg in the handoff with
  owner + worktree + differential gate. Label STATUS, not absence.
- **A mid-session handoff is a living file.** If it is written while work
  continues, update its HEAD, gate-log paths and leg statuses after EVERY
  merge/commit; a handoff naming a superseded HEAD or a leg that has since
  merged is itself a defect. Re-check with `git rev-parse HEAD` and
  `git ls-remote origin main` at the moment you update it.
- **A handoff cannot say both "no children are live" and name a running
  batch.** When adding a dispatch record, delete or replace the earlier
  zero-children sentence in that file. Why: the next session reads one
  authoritative status, and a contradictory line makes it skip a live leg
  or re-dispatch completed work.
- **Writing a handoff is not a stopping point.** Under the standing goal,
  write the file and then keep taking the next concrete step; the handoff
  buys persistence, not completion.
- **Stale async result batches arrive as claims, not new work.** After a
  model swap or context compaction, a batch of completed background runs is
  often work you already integrated. Reconcile each SHA and gate log against
  the handoff/canonical HEAD first; if the legs are already merged, report
  the batch as stale with no actionable items and continue — never re-merge
  or re-dispatch from a self-report.
- Memory cleanup rule (learned 2026-08-05): when memory is full,
  compress entries whose content now lives in skills/repo docs (e.g.
  procedures, env details that moved into a skill's Pitfalls section)
  rather than deleting whole facts. The skills are the durable layer;
  memory is the index + the user-corrections that must not be lost
  (repo paths, identity, rules).
