---
name: wubu-github-ecosystem
category: devops
version: 1.0.0
author: WaefreBeorn
license: Waefrebeorn Umbrella License v3.0
description: "GitHub org ops: README sweeps, push verify, provenance."
metadata:
  hermes:
    tags: [wubu, github, ecosystem, readme, provenance, multipush]
    related_skills: [github, wubuos-doc-gates, wubu-project-orientation]
---

# ~WuBu~ GitHub ecosystem operations

## When to Use

Use when working across the waefrebeorn GitHub org rather than one repo: a
README/ecosystem sweep, classifying repos into a registry, checking commit
authorship, adding the ~WuBu~ family identity line, or any multi-repo push.
Also load before marking any WuBu repo broken/discardable -- it may be an
ethos seed. For a single-repo PR/issue lifecycle use the `github` skill.

Manage the waefrebeorn GitHub org as a coherent ~WuBu~ family: enumerate every
repo, read the READMEs, fix them so they cohere, produce the registry, verify
every push, and audit commit authorship before any attribution work. A future
session cloning this job should get each repo straight on the first try.

## The user's rules that govern this whole class

- **Own work is C11, from-scratch, zero third-party — a SLERM.** A fork/patch
  is never presented as own-repo. Third-party imports are marked in the README
  or the registry, never passed off.
- **A repo can be an ETHOS SEED, not junk.** The WuBuContainer GitHub repo held
  an unrelated web file-converter; before marking a WuBu repo BROKEN or
  discardable, recognise it may be the inspiration to SLERM into the real
  module (universal containers). Ask the user what the repo is FOR before
  labelling it.
- **Provenance is guarded ground.** The working agent is the user's own C11
  reimplementation (`slermes`); the user drives it. Claude/Cursor never worked
  in a harness or contributed — any doc (or future agent) claiming otherwise is
  a hallucination from free-promo-router hosted models trained on Claude, an
  ERROR to correct, not a fact. Record this policy in
  `Waefrebeorn/WuBuFederation/PROVENANCE.md`.
- **Every own-repo README carries the family identity line** tying it to the
  ~WuBu~ AGI (its role + the three pillars), unless it is a third-party fork
  (which gets an honest "third-party fork, kept for reference, NOT a ~WuBu~
  project" marker instead).

## Procedure

1. **Get the token (never print it).** `grep github.com ~/.git-credentials
   | head -1 | sed 's|^https://||; s|@github.com.*||' | sed 's|^[^:]*:||'`.
   `gh` is usually not authenticated; the git credential store is.
2. **Enumerate.** `GET /user/repos?sort=updated&per_page=100` from the API,
   paginated; affiliation=owner,collaborator,organization_member. Note
   `default_branch` per repo (it varies).
3. **Read each README** via `GET /repos/{owner}/{repo}/readme` (base64) to learn
   what each repo actually is before deciding purpose.
4. **Classify every repo into a layer** (pillars, hosted-in-WuBuOS, extracted,
   slermed apps, the ~WuBu~ space, tools, third-party import batch, misc).
   Publish a registry as `Waefrebeorn/WuBuFederation/REPOS.md` (that repo's
   stated purpose is "the registry").
5. **Edit READMEs en masse:** clone into an isolated workdir (`xargs -P` for
   parallel clones; `--depth 1` for huge repos like slermes), insert the
   identity line before the first `##` heading (fallback: after the title
   block), commit, push, verify (see reference).
6. **Audit authorship BEFORE removing attribution.** `git log --all
   --author='...'` and a message scan. Foreign commits often rode in with an
   imported base and PRE-DATE the repo by a year. See the history pitfall.
7. **Update the registry + PROVENANCE** after any repo create/rename/archive.

## Pitfalls

- **Stage only your OWN hunk when the tree is dirty.** Repos in this family
  routinely carry someone else's uncommitted work (a half-finished dims
  migration, a codec experiment). `git add -A` sweeps all of it into your
  commit under your name, and `git commit -a` does the same. Stage the files
  you touched by name, and for a file you SHARE with those changes (a
  Makefile, a `mk/*.mk`), stage only your hunk: `git diff <file> > /tmp/p`,
  hand-write the hunk with the CURRENT line numbers, then
  `git apply --cached --recount /tmp/p`. Verify with
  `git diff --cached --stat <file>` -- it must show exactly your lines.
- **`git pull --rebase` refuses while anything is unstaged**, and you cannot
  stash someone else's work to get around it. Merge instead:
  `git pull --no-rebase origin main`. A merge commit on a family repo is
  honest; silently discarding or stashing a colleague's changes is not.
- **`.gitignore` may list files that ARE tracked.** A repo can ignore
  `tools/test_*` and still carry 445 of them, added before the ignore or with
  `-f`. `git add` then fails with "paths are ignored" on a file every other
  test target has. Check `git ls-files <path>` first; if it is tracked
  elsewhere in the same directory, use `git add -f` and say why in the commit.
- **A push you don't verify is a lie.** After ANY push, `ls-remote` the pushed
  branch and confirm its SHA equals your local HEAD. Printing "pushed" without
  the check is exactly how a silent failure passes.
- **The default branch is not always `main`.** WuBuNOS is `wubu-integration`,
  WuBuFX `root`, several are `master`. `git push origin HEAD` pushes the LOCAL
  branch name, so verify against the local-branch ref — or read
  `default_branch` from the API.
- **`git commit` goes to the branch you are CHECKED OUT on, not the one you
  name at push time.** `git add -A && git commit -m ... && git push origin
  master` from a checkout of `old` commits to `old` and then pushes an
  unchanged `master` — every step reports success and the work is on the wrong
  branch. Seen on a repo where the earlier branch restructure had left the
  working copy on the archive branch; the follow-up submodule checkout then
  failed to find the commit anywhere.
  Check before committing: `git status -sb | head -1` (it names the branch), and
  `git branch --show-current`. After pushing, verify the SHA is on the intended
  branch: `git ls-remote --heads origin | grep <sha>` — a commit that is not on
  any remote head was pushed nowhere.
- **A repo's DEFAULT branch can be the empty one; the code can live on another.**
  Before building, committing, or "fixing the README" on any repo you did not
  create this session, check what each branch actually holds:
  `git ls-remote --heads origin`, then `git ls-tree -r --name-only origin/<branch>
  | wc -l` and a `| head`. A repo can carry an emptied stub (one README saying
  "reserved for repurposing") on `main` while `master` holds the real project
  with thousands of files. Building on the stub branch produces confident work
  attached to nothing, and the correction is "that branch was the trash". Read
  the tree before you write a line.
- **You cannot delete the current default branch.** `git push origin --delete
  <branch>` is refused with `remote rejected ... refusing to delete the current
  branch`. Change the default FIRST via the API, then delete:
  `curl -X PATCH -H "Authorization: token $TOKEN" -H "Accept:
  application/vnd.github+json" https://api.github.com/repos/{owner}/{repo} -d
  '{"default_branch":"<other>"}'`, then re-push the delete, then
  `git remote set-head origin -a` so the local remote-tracking HEAD follows.
  Verify with `git ls-remote --symref origin HEAD`.
- **Do NOT rewrite git history on a foreign-author request without explicit
  confirmation.** Re-authoring/dropping commits (filter-repo + force-push)
  rewrites every SHA and breaks forks/clones. Verify who actually authored what
  first (often there is nothing by the tool the user named, only an imported
  base's history), present options, recommend leaving history, and offer to
  pilot on one repo before branching to others.
- **Apostrophes inside single-quoted `-m` strings break the shell** — use
  multiple `git commit -m` flags with clean ASCII (no `'`).
- **Shell `&` backgrounding is rejected by the terminal tool** — parallelize
  clones with `xargs -P`, not `&`.
- **Replacing a count in prose with an anchored-free regex is silent
  corruption** — it hit every count line in a doc. After any bulk sed/regex
  edit, grep before/after and confirm exactly the intended lines changed.
- **git submodule update can pull the wrong code** if a submodule points at a
  repo that changed or was repurposed; verify what the submodule checkout
  actually contains before trusting it (the real container was in-tree, the
  submodule empty).
- **NEVER `git submodule add` with a token-embedded URL.** `git submodule add
  https://x-access-token:$TOKEN@github.com/...` writes that exact URL into
  `.gitmodules`, and `.gitmodules` is committed -- so the token is now in the
  repo's history. GitHub push protection rejects it (`GH013: Repository rule
  violations ... Push cannot contain secrets`), which is the good case: you
  find out at push time. The bad case is a repo without protection.
  - Add with the CLEAN url (`https://github.com/owner/repo.git`) and let the
    git credential helper / `.git-credentials` authenticate. The helper
    rewrites the URL at push time; nothing secret is stored.
  - If you already did it: `git submodule add` is not the only writer --
    scrub BOTH `.gitmodules` and `.git/config` (`git config -f .git/config
    submodule.<path>.url`), then `git commit --amend`. Verify against the
    REMOTE, not the local file:
    `GET /repos/{owner}/{repo}/contents/.gitmodules?ref=main` and grep for the
    token prefix. Local cleanliness proves nothing once it has been pushed.
- **A committed prebuilt binary in the index is a lie about provenance.**
  `git ls-files --stage <path>` shows mode `100755` and a blob for a file that
  should be built, not stored. The shipped artifact then has no relationship
  to any source, and no reader can tell which revision produced it. Replace it
  with a submodule or a `build/` output rule; check `git ls-files --stage` for
  other `100755` blobs before declaring the tree clean.

## References

- `references/verify-push.md` — the one-liner that proves a push landed.
