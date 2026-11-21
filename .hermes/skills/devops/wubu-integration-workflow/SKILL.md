---
name: wubu-integration-workflow
description: WuBu unified-branch commit protocol. Use before any push.
---

# WuBu Unified-Branch Workflow

The three repos share ONE remote branch name: **`main`** — the
ONLY branch on GitHub for each. It is also the LOCAL branch name in every
repo (verify with `git branch --show-current`). All branches were consolidated
(see `docs/BRANCH-AUDIT-2026-08-09.md`). `master`, `wubu-integration`,
`work-fork`, `lfm25-adapter`, etc. are retired. Never create a new REMOTE
branch — the one sanctioned exception is LOCAL leg branches in git worktrees
for parallel agents (below), which are merged into main and never pushed.
A submodule repo leg is different: its commit must be pushed so the parent
gitlink is fetchable by CI.

> **NEVER force-push — hard rule (user-standing).** `--force`, `--force-with-lease`,
> and any history rewrite are forbidden on these shared branches. If a push is
> rejected as non-fast-forward, the remote moved: `git stash` uncommitted work,
> `git pull --rebase`, resolve, then push fast-forward only. Never merge to
> paper over it and never force.

## Three repos, one protocol (all on `main` local + remote)

| Repo | Path | Remote |
|------|------|--------|
| The Brain | `/home/wubu/wubuwizard` | `origin/main` |
| The Body/OS | `/home/wubu/wubuos` | `origin/main` |
| The Compiler | `/home/wubu/wubunos` | `origin/main` |

When you commit in more than one repo, push EACH with its own
stash→rebase→push→pop cycle. Their branches are independent.

## Two Engines (critical, not interchangeable)

| Engine | Files | Loads | Used by |
|---|---|---|---|
| WuBu-35M (mustard seed) | `src/wubu.c`, `include/wubu.h` | `.safetensors` (NOT GGUF) | `wubu_live_learn`, `wubu_train_gpu` — TRAINING target |
| WuBu1 (big model) | `src/wubu_model.c`, `include/wubu_model.h` | `.gguf` | `gen_text`, `gen_text_cpu` — INFERENCE |

- `gen_text` does NOT load `.st`/`.safetensors` files.
- `wubu_live_learn` does NOT load `.gguf` files.

## Per-Session Workflow

```bash
git fetch origin
git branch --show-current                 # expect main in all 3 repos
# ... make changes ...
# <verify the relevant build/test gate for THIS repo goes green>
git stash push -m "pre-push: uncommitted work"   # trees often hold build artifacts
                                                      # + a parallel agent's edits;
                                                      # rebase is blocked otherwise
git pull --rebase origin main  # fast-forward only
git push origin main           # NEVER --force; MUST fast-forward
git stash pop                             # restore the stashed work
git log --oneline -1 origin/main  # confirm your hash is the remote tip
```

**Git identity is per-repo, never global**: this host has no `user.name`/
`user.email` in global config, and each repo's history uses a different author
(e.g. wubuos `WaefreBeorn <wubu@waefrebeorn.ai>` vs wubuwizard
`<waefrebeorn@github.com>`). `git commit` in a fresh repo dies with "Author
identity unknown". Before the first commit in a repo, read its convention
(`git log -1 --format='%an <%ae>'`) and set a matching repo-local identity
(`git config user.name/email`) — never rely on global. `git rebase --continue`
also creates a commit and dies the same way: set the identity in the leg
worktree BEFORE resuming a conflicted rebase, not after the failure.

Stage paths EXPLICITLY (never `git add -A`) — see the artifact rules in the
`wubuos-github-push` skill (nested `metal2vulkan/.git`, gitignored binaries).
Commit ONLY your own source; when a shared file (e.g. the Makefile) already
carries a parallel agent's in-progress edits, do NOT stage the whole file —
commit only the paths you changed and leave the other hunks for their owner.

When a doc/plan says "finish THE existing <module|test>", read that file fully
and PROVE it builds and passes BEFORE writing new code — it may already be
is complete and committed, and the correct deliverable is a verification run, not
a fresh implementation. Fighting a commit on an already-shipped artifact is the
generic trap. In wubuos the same trap wears a second face: `.gitignore` ignores
test sources (`src/*/test_*`, `src/**/*_test`), so a NEW test is silently skipped
by `git add`. The repo's convention is an explicit allowlist -- add
`!src/<area>/test_<name>.c` beside the other `!src/gui/test_*.c` exceptions, then
stage. Diagnose with `git check-ignore -v <path>` rather than retrying `git add`.

### The pre-push stash swallows YOUR commit (recurring)

The stash step exists to clear build artifacts + a parallel agent's edits so the
rebase is not blocked — but `git stash push` also sweeps up YOUR tracked source
edits. The failure mode is silent: after `git stash`, `git status` is clean,
`git add <file>` reports "nothing added", and `git commit` exits non-zero with
"no changes added to commit" while you believe the file is committed.

Sequence that always works:
1. Stash, rebase, push, pop FIRST — then check `git status --short <file>`.
2. If your edits are inside the stash (stash list shows your message; the file
   is clean on disk), recover with `git checkout stash@{0} -- <file>`, then
   `git add <file>` and commit normally.
3. VERIFY the commit landed before moving on: `git log --oneline -1` shows your
   hash and `git log --oneline -1 origin/<branch>` matches it. A commit that
   never happened is the cheapest bug to catch and the most embarrassing to
   discover later.

When a repo has dozens of dirty artifact binaries (wubunos does), prefer
`git stash push -- <specific files>` or `git checkout stash@{0} -- <file>` over
popping the whole stash — a blanket pop re-dirties binaries and can conflict.
After restoring your file, `git checkout --` the binary artifacts to leave the
tree clean.

### SAME symptom, DIFFERENT cause: the file is ALREADY committed at HEAD

"no changes added to commit" while `git add`/`git status` go quiet can ALSO mean
the exact file is already in HEAD byte-identical — a prior session shipped it
and the tree matches, so there is genuinely nothing to stage. `git add -f`
stages a blob equal to HEAD and commit still reports nothing. Diagnose before
fighting the commit for a loop:
- `git cat-file -e HEAD:<path>`  (exists in HEAD?)
- `git ls-tree HEAD <path>`      (committed, shows blob)
- `git rev-parse HEAD:<path>` == `git hash-object <path>`  (byte-identical)
- `git log --oneline --all -- <path>`   (which commit already shipped it)

If HEAD holds the identical blob, the artifact is done and the real deliverable
is VERIFICATION (build it, run it, record pass/fail) — not more commits. Note an
associated `.gitignore` line does not explain silence either: a tracked file is
immune to ignore rules, so an ignore entry next to a committed path is stale,
not the blocker. The three plausible causes of "nothing staged" are
(1) stash swallowed the edits (above), (2) already committed identical, (3)
actually gitignored-and-untracked — disambiguate with `git ls-files -v <path>`
and `git check-ignore -v <path>` before retrying.

## Parallel-agent worktree legs (multi-agent work lands on main)

The compact order-of-operations checklist lives in
`references/leg-integration-checklist.md`; the detailed rules below are
authoritative when they differ.

When several agents implement independent legs at once, isolate them in
worktrees, not in the shared tree (concurrent `make -j` in one tree races
on .o files):

```bash
git worktree add /home/wubu/wubuos-<leg> -b leg/<leg> main
# agent works ONLY there; inits needed submodules; commits locally; NEVER pushes
```

Give each agent a self-contained brief: the audited evidence for its leg,
the exact gate it must run and paste real output from, the build commands,
and the commit-no-push rule. Tell leg agents to run ONLY their narrow gates:
a fresh worktree's full suite fails on missing submodules, stale inventories
and config-dependent artifacts, while the integrator's canonical run is the
evidence. Merge protocol (integrator):
1. **Re-run every claimed gate yourself in the agent's worktree before
   merging** — agent summaries are self-reports; a claimed PASS is a
   hypothesis until your own run prints it.
   - **Treat a late background result batch as stale unless its commit is
     missing from HEAD.** Compare the reported SHA with `git rev-parse
     HEAD` and the gap-map/handoff record; if the commit is already an
     ancestor, report "no new actionable item" and do not re-merge,
     rebase, or repeat the integration chain. Why: delayed batches are
     confirmations of work already landed, and reprocessing them invites
     duplicate merges and conflicts on shared `mk` files.
2. Merge legs SEQUENTIALLY into main; after EACH merge re-run that leg's
   gates on the merged tree (later merges touch shared mk files).
3. Object-list conflicts (GUI_OBJS/RT_OBJS/APP_OBJS in mk/objects.mk) are
   the usual collision: one side dedups an object, the other adds a new
   leaf. Resolve by KEEPING BOTH INTENTS — grep where the deduped object
   is really linked before accepting its removal, and re-add the new
   leaf. A wrong resolution surfaces as undefined references or duplicate
   definitions at the next link (the hosted link no longer tolerates dups).
4. After the last merge run the integrated suite (boot gate + persistence
   gate + kernel-strict + the leg gates + hosted smoke) before pushing main.
   For wubuos also run `make test_linux_product`: it rebuilds the hosted
   binary, boots a headless frame and asserts five distinct GUI frames.
   That gate MUST isolate the host display (`env -u DISPLAY -u
   WAYLAND_DISPLAY` for the boot and capture): never drive `:0`, weston, or
   a compositor from an audit gate, because monitor churn can crash the
   user's shell. Verify the shell is still active after the product gate.
   When the user asks whether the product works on Linux, pause child-leg
   integration and run that product gate first; report the gate result,
   not just a green unit suite.
   A gate that invokes `make` internally must stay OPT-IN, never a
   prerequisite of `make -k -j24 test`: the nested make races with sibling
   prerequisites on the same `.o` files in a parallel full gate. Keep the
   full gate for unit/integration targets and run nested gates separately.
   When a leg adds a new `test_*` target, wire it into the default tier in
   the SAME merge (or state the explicit SKIP contract). A child that leaves
   its gate opt-in has proven the mechanism, not shipped the gate; re-run
   the full gate after wiring.
   After both gates are green, record one round per merged leg in the
   central gap map (evidence, differential, negative control, scope
   boundary, final gate log names), commit/push, and update the handoff
   HEAD before starting the next batch.
5. `git worktree remove` spent worktrees; parent leg branches stay local.
6. **Rebase before merge.** A child branch based on an older main must be
   rebased onto the CURRENT main tip, its narrow gates re-run after the
   rebase, then merged with `--ff-only`. In a noninteractive terminal finish
   a conflicted rebase with `GIT_EDITOR=true git rebase --continue`
   (`--continue -q/-m` are not accepted); unstage rebuild artifacts and
   restore tracked test binaries before continuing. Child summaries are
   self-reports;
   the post-rebase run is the evidence. Conflicts in shared headers are
   resolved by keeping BOTH intents (e.g. revocation cache plus txn backup
   fields), not by choosing one side.
   When editing conflict markers with the patch tool, re-read the exact
   conflicted span and review the returned diff: `context_aware` matching
   can land on a similar earlier line and silently corrupt an unrelated
   section. Before `git add` / `rebase --continue`, grep every touched file
   for `^<<<<<<<`, `^=======`, and `^>>>>>>>` and require zero matches.
7. **Submodule legs need a pushed commit.** A leg that changes a submodule
   repo must push that repo's leg branch and bump the parent gitlink;
   otherwise CI cannot fetch the commit. Verify `git remote -v` in the leg
   worktree first: a worktree cloned from a local mirror pushes to that
   mirror, not to the canonical remote, so a successful push there still
   leaves CI unable to fetch. Publish from the parent's submodule checkout
   (`git -C src/<sub> fetch /path/to/mirror leg/<name> && git -C src/<sub> push origin FETCH_HEAD:refs/heads/leg/<name>`)
   and confirm `git ls-remote origin leg/<name>` matches the local SHA
   BEFORE bumping the gitlink. A leg worktree often pushes to a local mirror
(`origin` can be `/home/wubu/wemu`, not GitHub), so its "remote=..." line is
NOT proof CI can fetch. From the PARENT submodule checkout run
`git ls-remote origin leg/<name>` and compare with the local SHA; if the
branch is absent, publish through the canonical checkout/mirror before the
bump. Fetching a bare SHA can fail with "not our ref" until the branch is
published — fetch the branch by name first. If the submodule must not be
   dirtied in the parent tree, apply a narrow overlay patch to the
   out-of-tree build copy instead of editing the submodule checkout.
   **Never rebase a submodule leg onto a SHA fetched from the parent repo.**
   A parent docs-only commit is not in the submodule's history; fetching it
   into the submodule worktree replays unrelated commits (wrong project
   README, foreign gates) and produces meaningless conflicts. Verify the
   candidate belongs to the SUBMODULE (`git -C <leg> cat-file -e <sha>^{commit}`
   plus a subject check) before any rebase. When only the parent docs moved,
   do not rebase at all: publish the leg commit from the original base.
   Publish a leg whose `origin` is a local mirror explicitly through the
   canonical remote, by SHA into the named branch:
   `git -C <leg> push -q https://github.com/<owner>/<repo>.git <sha>:refs/heads/leg/<name>`,
   then confirm `git ls-remote <canonical> leg/<name>` matches before bumping.
   After every submodule bump, verify the parent's SUBMODULE WORKING TREE
   actually moved: `git -C src/<sub> rev-parse --short HEAD` must equal the
   newly staged gitlink. A merge updates the index, not the checkout, so a
   stale checkout silently builds old sources and fails with missing files.
   Fetch/checkout the new SHA explicitly before rebuilding. Delete the
   out-of-tree build copy and rebuild from scratch before trusting gates
   that use it: a stale copy keeps the old sources and hides link failures. When an overlay patch
   fails, read its `.rej` against the CURRENT header — signatures drift —
   and fix both the context and the `@@ -a,b +c,d @@` line counts; a hunk
   that applies "with offset" is not proof the target still compiles. If the
   overlay has drifted more than once, stop hand-editing hunks: regenerate
   the entire patch as unified diffs from the pinned sources with unique
   string replacements (Python `difflib`), then apply it to a clean copy
   and run the gates. Never accept a fuzzy hunk that landed on a different
   function than the one it was written for.
   When two submodule legs start from the SAME parent, rebase one onto the
   other and resolve conflicts by keeping both intents (dispatch enums,
   result fields, gate calls). Once combined, regenerate the overlay patch
   against the COMBINED commit: `git archive <sha> | tar -x` into a clean
   tree, apply only the hook-only hunks, then `diff -ruN clean patched` with
   `a/`/`b/` labels. Verify the regenerated patch applies to a fresh copy
   before pinning it. If a newly combined fixture (e.g. a guest ELF) is
   absent from the parent gate, add its compile step to the parent test
   target rather than treating the missing file as a regression.
8. **Regenerate generated inventories after source additions.** Files such
   as `docs/owned-surface.md` are checked artifacts, not prose; run their
   `scripts/<name>.py --write` before the full suite when new owned source
   files were added, or the full gate fails on a stale manifest even when
   the code is correct. Regenerate in the CANONICAL tree, not in a fresh
   leg worktree whose submodules may be populated differently: a worktree
   manifest can encode environment-derived path churn that is unrelated to
   the leg. Inspect the diff and keep only the expected module additions.
   Gate-regenerated evidence artifacts are the inverse case: a timing or
   CT-evidence gate rewrites its timestamp in the canonical tree and then
   blocks a `--ff-only` child merge on that file. Diff it first — a
   timestamp-only change can be discarded with `git checkout -- <path>`;
   keep the child's version when it carries new measurements.
   A statistical gate that passes standalone can still go VACUOUS inside
   `make -k -j24 test`: CPU contention inflated the sample ranges and the
   deliberately variable control's Welch t fell below the fixed 10.0
   non-vacuity threshold. Fix by increasing ONLY the sample count (e.g.
   `WUBU_TIMING_NSAMP` 64 -> 512, clamped), keeping fixed thresholds, one
   pass and no retries; add margin after a near miss (t=10.6 was too thin
   under load). Re-run the FULL parallel gate to verify — a standalone
   timing run is not evidence for the parallel tier.
9. **Point crypto gates at an existing devroot in fresh worktrees.** When a
   leg worktree lacks its own mbedTLS headers, set `WUBU_MBEDTLS_ROOT` to
   the already-built repo-local devroot before re-running those gates; a
   skip or "root missing" there is environment setup, not a code defect.
   Never fetch a new root just to satisfy a gate. Likewise, `make test_docs`
   can report two missing `wubuoffice` files in a fresh worktree that are
   present in the canonical tree; verify against `/home/wubu/wubuos`
   before calling it a regression. Any object whose CFLAGS depend on a
   detected config (e.g. `oci_http_client.o` with `WUBU_HAVE_MBEDTLS`)
   must have that config as an explicit, content-checked make prerequisite
   (`build/hosted_tls.state`): otherwise a TLS-enabled object survives a
   later root-less build and the link fails with undefined `mbedtls_*`
   symbols.   Test both config transitions with `make hosted` before merging.

   **Compile pointer types under CI's warning policy, not the local relaxed
   one.** A local gate that adds `-w` can hide an incompatible anonymous
   struct pointer assignment that CI rejects with
   `-Wincompatible-pointer-types`; define a named type in the owning header
   and use it at every assignment, then verify with
   `gcc -fsyntax-only -std=c11 -Werror=incompatible-pointer-types <file>`.
   Layout-compatible anonymous structs are still distinct types across
   translation units.

   `boot-verify.yml` only auto-runs on changes under `src/kernel/**`,
   `src/firmware/**`, `mk/**`, `Makefile`, `tools/ci_boot_assert.py`, or the
   workflow file. A docs-only or `src/gui/**` fix will NOT get a CI run:
   dispatch one explicitly with `gh workflow run boot-verify.yml --repo
   waefrebeorn/wubuos --ref main`, then verify the run's conclusion. A local
   green plus a pushed commit is not proof CI is green. Also, CI uses a
   shallow checkout: a gate that `git show`s a historical SHA fails there
   even though it passes locally; replace such negative controls with a
   synthetic pre-change variant built from current source or an in-run
   state switch, never a hard-coded object ID.

   **A feature proven by a gate is not yet in the product.** Check the
   product's object list and CFLAGS, not just the gate's compile command: a
   gate that passes its own `-D<FEATURE>` can ship an object built with the
   legacy backend. When two backends are auto-detected, make the selected
   path win explicitly in the shared `#if` chain; an `#elif` fallback can
   silently re-enter the product even though the single-backend gate was
   green. Verify the built object with `nm` (the legacy backend's symbols
   must be absent) before calling it closed. Make CFLAGS changes actually
   rebuild: `make` does not invalidate objects on flag changes, so delete
   the affected objects or add a content-checked config prerequisite.
   Why: a green gate with a different compile command proves the gate,
   not the shipped binary.

## Before you push: leave no process strays

The gates fork short-lived test binaries and X/GLX children. Anything that hangs
or is SIGKILLed mid-run keeps its X connection open, which pins an unmapped window
in the WM -- the user sees "lots of zombie processes open" days later. Check and
clean BEFORE pushing:

```bash
ps -eo pid=,stat=,etime=,args= | grep -E 'Z|defunct'      # true zombies
DISPLAY=:0 xwininfo -root -tree | grep -cE '340x250|320x200'   # orphan demo windows
```

WuBuOS ships a reaper for exactly this: `tools/dev/reap_stale_tests.sh`
(`--dry-run` first; kills test binaries older than `WUBU_REAP_AGE_MIN`, default
10 min, and closes those orphan windows).

**Never `pkill -f <pattern>` when the pattern appears in your OWN command line.**
The shell running the cleanup matches its own argv, so pkill SIGTERMs the agent's
shell mid-command (observed twice in one session). Harvest PIDs instead and kill
by number:

```bash
ps -eo pid=,args= | awk '$2 ~ /vsl_nt_contract_test/ {print $1}' > /tmp/pids
xargs -r kill -9 < /tmp/pids
```

## Commit Format

```
<type>(<scope>): <subject under 72 chars>
<blank>
<body, wrap at 72>
Co-authored-by: <handle>
```

## Build Targets to Verify

1. **Inference**: `make gen_text_cpu` (always works, no GPU needed)
2. **Training**: `make wubu_train_gpu wubu_live_learn`
3. **SSM/backward**: `make test_ssm test_ssm_backward_standalone`

Fix any failure BEFORE committing.

## Environment Gotchas

- WSL2, RTX 4050 (sm_120). CUDA device NOT exposed (`/dev/dxg` absent) — GPU inference/training does NOT work in this WSL env. CPU-only works.
- NVCC at `/usr/local/cuda-13.1/bin/nvcc` (compile `.cu` objects fine).
- `gen_text` (GPU) link is BROKEN here: `__cudaRegisterLinkedBinary` errors. Use `gen_text_cpu` (works).
- Git LFS: `git lfs install && git lfs pull` for tokenizer.json + model weights.

## Known-Fixed Bugs (do NOT regress)

1. **SSM outer-product** (`src/wubu_ssm.c`): `h[i][j] += k[i]*diff[j]` NOT `k[j]*diff[i]` (transposed). Fixed in unified.
2. **Layer-count probe** (`src/wubu.c`): probes active layers via binary search, sets `m->n_layers`. `src/wubu_save.c` saves only `m->n_layers` (not WUBU_LAYERS).
3. **CFLAGS**: `-fno-fast-math` (numerical correctness; was `-ffast-math`).

## Model Facts

- `models/wubu/model-mixed.gguf`: 12 layers, GQA 3:7 heads, d_model=448, vocab=16384, output TIED. Loads via WuBu1/gen_text_cpu.
- Tokenizer: `models/wubu/tokenizer.json` (1.1MB BPE, recovered from LFS object store).

## Coordination with LFM Agent

- The LFM/Distiller agent works on the SAME trunk (`origin/main`)
  — one branch, all agents together. **Never force-push to clobber it.**
- Before pushing, stash uncommitted work, then `git pull --rebase`
  (fast-forward only), push, and `git stash pop`.
- Both agents use the same commit protocol. Share this skill's content
  with the other agent if they need it.
