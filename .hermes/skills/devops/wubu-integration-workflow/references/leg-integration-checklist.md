# Child-leg integration checklist

Run in this order for every batch of parallel worktree legs.

1. Verify each reported commit exists in the leg worktree and re-run that
   leg's narrow gates yourself. Treat late background batches as stale when
   the SHA is already an ancestor of HEAD.
2. Merge sequentially; after each merge re-run the leg gates on the merged
   tree because later legs touch shared makefiles and headers.
3. Rebase legs based on older main onto the CURRENT tip; re-run narrow gates
   after the rebase; merge with `--ff-only`. For submodule legs, rebase only
   onto commits from that submodule's own history.
4. For two legs from the same base, rebase one onto the other, keep both
   intents in conflicts, remove superseded code, re-run the combined narrow
   suite, then publish the combined SHA and bump the parent gitlink.
5. Regenerate checked inventories (`scripts/owned_surface.py --write`) in
   the canonical tree after new owned sources land. Revert timestamp-only
   evidence churn when it blocks a fast-forward.
6. Wire every new `test_*` target into the default tier in the same merge,
   or state an explicit SKIP/VERIFIED_NEGATIVE contract and keep it opt-in.
   Full-gate green on a quiet tree is not enough for statistical gates: run
   the full parallel gate and require margin over fixed thresholds.
7. After all merges: full gate, Linux product gate, Cinnamon active check,
   gap-map round per leg, commit/push, handoff HEAD update, then the next
   batch.
