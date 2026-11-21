# Prestige — controlled handoff, not reset

A fresh session inherits only what is written and verified here.

1. Commit and push both the palace and the project it reviews.
2. Record local and remote SHAs; they must match.
3. Update `slate.md` with the current step, not a vague "needs focus".
4. Rebuild `INDEX.md`; a path named in a doc that does not exist is a defect.
5. Re-run `tools/verify_mindpalace.py` and paste the real output.
6. Never claim a gate you did not run. Mark UNVERIFIED if trusted.

A handoff phrased as "remaining honest gaps" is avoided work. Every gap is
CLOSED with a gate, IN-FLIGHT with owner/worktree/gate, or VERIFIED_NEGATIVE
with exact refusal output. Write the next step before stopping — writing the
handoff is not completion.
