# Slate -- current focus

## Active step

- Step 0004: aggregate all mindpalace skills and wire the review tooling —
  CLOSED (see STEPLOG.md). Router `mp` + 5 companion skills + 8 references;
  `commands/mp`, `tools/index_repo.py`, `tools/verify_mindpalace.py`,
  `tools/review_1000.py` all run; 1000-pass / 250-pack review generated.
- Step 0003: repo-view dead-credit audit — CLOSED (see STEPLOG.md).
- Standing: the 1000-step Devil's Advocate loop continues from `STEPLOG.md`;
  no finding is parked as an "honest gap" — CLOSE with gate, IN-FLIGHT with
  owner/worktree/gate, or VERIFIED_NEGATIVE with exact refusal output.

## Standing directive

Continuous review until no reachable work remains or the user says stop.
Never report a rising ported/coverage count as progress; report the gate
output and the running artifact.

## Last verified

- Index: `python tools/index_repo.py --root . --write`.
- Verification: `python tools/verify_mindpalace.py --root .`.
- Review: `python tools/review_1000.py --root . --passes=1000 --write`.
- Skill count: mechanically counted from `SKILL.md` files, never guessed.

## Next

1. Verify the palace on a fresh clone (`bash commands/mp verify`).
2. Run `mp orient` against wubuwizard, wubunos and wubuos.
3. Advance along the phase plane (see `ROADMAP.md`).
