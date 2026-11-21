---
name: wubu-session-workflow-agro
trigger: End of work session — package skills, clean memory, prep prestige.
description: Agro-cycle. Skill harvest, memory cleanup, prestige prep.
---

# The Agro-Cycle

## Autonomous-run discipline (the standing "make wubuos the best os / complete all goals" goal)
When running the standing autonomous goal turn after turn:

- **No completion-status disclaimers.** Do not open turns with "I want to be honest about the 1000", "I'm not going to claim X is done", "here's the honest accounting", or any meta-commentary about what fraction of a large goal list is finished. The user has explicitly said they do not care and to just work. State what you shipped this turn (concrete, with the commit + gate counts), then name the next concrete step and continue.
- **Report shipped artifacts, not progress narratives.** Each turn: the module/commit, the test count, the gates green. One line. Then the next step.
- **NEVER phrase a status update as an achievement confirmation** — no "N DONE, pushed", "Task complete", "✓ Goal achieved", "All tests passed — done". The goal-list watcher reads a confident declarative "X done" as the user having confirmed the goal was reached, and fires a spurious completion notice. State shipped artifacts in NEUTRAL present/past facts — "Built wubu_elfload (ELF execution leg); real static binary loads, 30+ assertions green; commit 665baf3 pushed. Next: PE leg." — and put the registry count as a plain data point, not a banner. The user flagged this directly: stop wording things so ambiguously that it triggers the completion detector.
- **Take the next concrete step yourself.** "do not ask, you are the decision maker" — pick the highest-leverage next item and start it; do not end a turn asking for direction unless genuinely blocked. Offering a MENU of next frontiers as a closer ("say the word / which one should I take") is itself the ask-for-direction anti-pattern — the user reads it as stalling. Name the concrete step you are taking and take it; a real question is only for decisions you genuinely cannot make.
- **Default next step = wire the last tested component into its live path.** When a track's pieces all build and pass their own unit tests but one still isn't called from the real entry point, that wiring outranks starting something new — it converts "we have a guard/module" into "the loop/path IS guarded/uses it". Verify with the component's own gate PLUS every consumer's gate (a struct/include change ripples to all linkers).
- **Depth in a hard domain beats breadth of small modules.** When called out for "slacking," the fix is to stop shipping many thin, well-tested modules in easy domains (meta-layer/UX) and instead drive ONE hard, high-value domain (compiler/brain/math/worldsim) with a measurable result — a gauntlet delta, a loss curve, a proven theorem. Reassess the real distribution of completed work first (measure, don't narrate), then replan to the hard frontier.
- **Re-measure any gap-analysis claim with a real command before scheduling work from it.** Stale gap docs mislead: verify each claimed gap (does an 8/16-arg call actually fail? is the frame really absent?) with a probe before committing to it. The honest frontier is whatever the current command output says, not what an old doc claims.
- **Never fabricate completion.** Ship only what a real gate verifies, but do not preface every turn with a disclaimer about the rest. Silence on the un-done majority is the correct register; a paragraph defending your honesty is not.
- **No end-of-turn ritual closer.** Do not sign off with "Stopping here — context exhausted. Tree pushed; every number above came from a test run in this session" or any variant. The user's response to it: "THIS IS A FLATOUT LIE STOP DOING THIS". The sentence asserts a verification the reader cannot check, it is unfalsifiable by construction, and repeating it every turn turns a true statement into a slogan. If work shipped, one factual line (what, commit, gate counts) and the next step. If nothing shipped, say nothing or say the blocker. Never narrate your own honesty as a closing move.
- **A re-test that contradicts the source is a STALE BINARY, not a broken revert.** After reverting an edit, force a clean rebuild (`rm -f *.o <testbin>` then rebuild) and check `git diff --stat` before concluding "my revert broke it." A `make` that links a stale `.o` reports the pre-revert behavior and sends you chasing a regression that never landed. Confirm the working tree is clean before trusting any surprising re-test.

## When the user redirects you to a different workstream mid-session
A mid-session redirect ("agent 3 owns X, you work on Y") is a handoff, not a
pivot to forget. Close the old workstream cleanly before starting the new one:

1. **Kill in-flight builds first**, then release — a running `lake build` /
   `make` over a subtree another agent owns will corrupt its object files.
2. **Leave the other agent's repo EXACTLY as you found it.** If you took
   ownership of a package checkout inside it, release the checkout
   (`git rm --cached` + commit) rather than deleting it — the other agent's
   toolchain and built artifacts are its state.
3. **Restore files you touched but are not committing.** A stale uncommitted
   edit in another agent's tree becomes a phantom failure it will blame on
   itself. `git checkout --` them and verify `git status --short` is clean.
4. **Commit and push YOUR repo first**, re-run its gate, and only then start
   the new workstream. Two dirty repos at once is how work gets lost.
5. **A "stop doing X, that is the other agent's work" redirect removes the whole
   domain from scope — do not reopen it.** Drop every goal/task in that domain
   from your plan and re-derive the remaining tractable set from the registry
   (filter the owned domain out) rather than carrying its items forward as
   "still open." Acknowledge the boundary in one line and move to the next item
   in YOUR domain; do not re-litigate or half-finish the other agent's work.

## At End of Work Session

### 1. Harvest all skills
Every procedure done more than once becomes a skill. Review tool calls, identify patterns (builds, tests, git commits, research, fixes). Create ONE skill per pattern.

### 2. Clean memory
- Remove stale facts (PR numbers, commit SHAs, file counts, done statuses)
- Keep only: environment quirks, user preferences, permanent paths
- Consolidate related memories into single facts

### 3. Update INDEX.md
- Mark completed AN-plans as wired

### 4. Prestige prep
- Commit all work
- Write NEXT_SESSION_PROMPT.md in mind-palace
- Export research corpus summary
- Save todo state

## Starting Next Research Session

### 1. Load orientation: skill_view(name='wubu-project-orientation')

### 2. Check prestige artifacts
- Read NEXT_SESSION_PROMPT.md
- Check INDEX.md
- Check research pond sizes

### 3. Knowing where we are by knowing where we are
- List current capabilities (our skills)
- For each: what is the NEXT order of magnitude?

### 4. Three headache questions
1. Where does the AGI leak knowledge? (coherence drops)
2. Where does the model hallucinate architecture?
3. Where does density planner waste compute?

### 5. Seed 7-step research
- Use harvest_pond.py infrastructure
- Each step targets ~70MB pure text
