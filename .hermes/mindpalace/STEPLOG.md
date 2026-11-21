# Step log

### Step 0001 -- bootstrap mindpalace
- Claim: a cloneable palace can carry all skills and the four-phase loop.
- Evidence: `python tools/verify_mindpalace.py` run on the generated tree.
- Negative control: a missing SKILL.md or dead doc path fails verification.
- Smallest real increment: index + verifier + `mp` alias skill.
- Gate run: `python tools/verify_mindpalace.py`.
- STATUS: CLOSED
- Next phase-plane coordinate: R1/R0 (single repo, shape+negative control).

### Step 0002 -- repo-view dead-credit audit
- Claim: a rising claim count can rise while the product stays unchanged.
- Evidence: 264 wired objects exported zero symbols (`nm -g --defined-only`);
  398 placeholder bodies; water-cup 3.4%; no runnable binary.
- Negative control: the same detector flags `base_flow`/`api_server_flow` as
  live and new adapter flows as dead.
- Smallest real increment: a dead-credit detector with a tracked baseline,
  a pre-dispatch guard, and in-place re-porting with nm-proven callers.
- Gate run: `make workflow-check` rc=0, 2166/2166 build health, 0 new dead.
- STATUS: CLOSED
- Next phase-plane coordinate: R2/D2 (repo-wide, differential + reachability).

### Step 0003 -- repo-view DA carried into the mp alias
- Claim: the evidence ladder survives a session boundary as a skill.
- Evidence: `skills/mp/references/repo-view-da.md` in the `mp` skill, loaded on `mp`.
- Negative control: dropping the reference removes the dead-credit guard.
- Smallest real increment: reference file + rule 6 in SKILL.md.
- Gate run: skill loaded and rule quoted from artifact.
- STATUS: CLOSED
- Next phase-plane coordinate: R1/D1.

### Step 0004 -- aggregate all mindpalace skills and wire the loop
- Claim: the palace can be more than docs — it can run its own review.
- Evidence: router `mp` + 5 companion skills + 8 references; `commands/mp`
  dispatches orient/attack/close/prestige/index/verify/review/status/skills;
  `tools/index_repo.py`, `tools/verify_mindpalace.py`, `tools/review_1000.py`
  produce real outputs; 1000 passes generated as 250 packs.
- Negative control: verifier fails on a dead doc path, stale SHA, missing
  `## When to Use`, or description >60 chars.
- Smallest real increment: three tools + CLI + skill family + slate.
- Gate run: `bash commands/mp verify` and `bash commands/mp review --passes=1000`.
- STATUS: CLOSED
- Next phase-plane coordinate: R2/D2 (repo-wide, gated + differential).
