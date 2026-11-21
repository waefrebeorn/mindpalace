---
name: waefrebeorn-repo-creation
description: Use when creating a new WaefreBeorn GitHub repo.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [github, repo, license, bootstrap, waefrebeorn]
    related_skills: [github, wubuos-github-push, wcode-ide]
---

# Creating a new WaefreBeorn repo

## When to Use

- The user asks for a new project/app/repo, or says an app "has its own repo".
- Bootstrapping a project that is NOT a subdirectory of an existing repo.
- Linking two WaefreBeorn repos, or syncing a consumer after a producer changes.

## Standing rules (apply to every WaefreBeorn repo)

1. **License is always the WaefreBeorn Umbrella License v3.0.** Never MIT,
   Apache, GPL or a GitHub license template. Copy the file from an existing
   repo rather than retyping it:
   ```bash
   cp /home/wubu/wubuos/LICENSE <new-repo>/LICENSE
   ```
2. **Default branch is `main`.**
3. **A new app gets its OWN repo** -- not a subdirectory or submodule of
   WuBuOS. Shared code is reached by linking/vendoring, not by nesting.
4. **OS-family repos are PUBLIC — source is the distro.** WuBuOS and every
   repo its build consumes (kernel, compiler, compositor, submodule
   sources) must be publicly cloneable: users build from source and CI
   fetches submodules anonymously. A private repo in the family is a
   distribution bug, not a safety measure — scan for secrets, then make it
   public (`gh api -X PATCH repos/<owner>/<repo> -f visibility=public`).
   Verify with ANONYMOUS `git ls-remote https://github.com/<owner>/<repo>`
   (no credential helper) — that is exactly what CI and fresh clones do.

## Procedure

### 1. Create the repo (API, not the CLI)

`gh` may not be installed. Git push already works from the token stored in
`~/.git-credentials`, so use that token against the REST API:

```python
import re, subprocess, json
tok = re.match(r'https://([^:]+):([^@]+)@(.+)',
               open('/home/wubu/.git-credentials').read().strip()).group(2)
body = json.dumps({"name": "<Name>", "description": "...",
                   "private": False, "auto_init": False})
# NEVER pass "license_template". auto_init=False alone is enough; a template
# makes GitHub commit a LICENSE on main even with auto_init off.
subprocess.run(['curl','-s','-X','POST',
                '-H', f'Authorization: Bearer {tok}',
                '-H','Accept: application/vnd.github+json',
                '-H','Content-Type: application/json','-d',body,
                'https://api.github.com/user/repos'], ...)
```

Confirm the token's scopes first (`x-oauth-scopes` on a HEAD to
`/user`); `repo` is required. Never print the token.

### 2. Initialise locally and push

```bash
mkdir -p <repo> && cd <repo> && git init
git remote add origin https://github.com/waefrebeorn/<repo>.git
# ... write code, LICENSE, README ...
git add -A && git -c user.name='WaefreBeorn' \
    -c user.email='waefrebeorn@users.noreply.github.com' commit -m "..."
git branch -M main
git push -u origin main
```

## Slerming an existing tool (clean-room reimplementation)

"Slerm" is this user's verb: rewrite someone else's tool from scratch as our
own ground-up reimplementation. A fork, a patch, a vendor, or a copy is NOT
slerming. Trigger: the user drops a URL and says "slerm" (or "sle" -- Siri
truncation of the same word).

1. **Read the original's behaviour, not its code.** Fetch the README, the
   public API docs and the config surface. Reimplement the *behaviour and the
   public interface*; write every algorithm yourself. Clean-room is the point
   and the legal basis.
2. **Own name, own license.** Never keep the original's name and never take
   its license -- the WaefreBeorn Umbrella License v3.0 stands rule 1. Pick a
   name in our family (the trinity pattern: `wubuos` body, `wubunos`
   compiler, `wubuwizard` brain; `wubulens` lens).
3. **Provenance section in the README, always.** Name the inspiration, state
   that the behaviour and public API were the reference, and state plainly
   that no source was copied, linked, or derived. This is what makes the
   clean-room claim auditable.
4. **A fake/demo backend behind the same interface**, so the whole pipeline
   is testable with no hardware and the gate runs on any machine.
5. **Verify against the real thing by running both.** Build a workload, point
   the lens at it, and check the numbers land (a GPU lens must name the
   program and attribute its memory). A green unit test on a fake backend
   proves nothing about the hardware path.

## Linking repos with submodules

WaefreBeorn repos nest: `WWW -> Wua`, `WuBuOS -> WET -> Wua`, `VWS -> WET -> Wua`.
A consumer adds the producer as a submodule and bumps the pointer by commit.

```bash
git submodule add https://github.com/waefrebeorn/<repo>.git <path>
git submodule update --init --recursive
```

### Pitfall: a PRIVATE submodule breaks CI and fresh clones silently

The parent repo can be public while a submodule is private: local builds
work (your credentials fetch it) but anonymous CI checkout dies with
`could not read Username for 'https://github.com'`, and a user's fresh
clone cannot build the gated tests. Check every `.gitmodules` URL with
anonymous `git ls-remote` when wiring CI; make the submodule public
(standing rule 4) rather than injecting tokens into public workflows.

### Pitfall: a fresh submodule is on a DETACHED HEAD

`git submodule add` checks out a COMMIT, not a branch. A commit made there is
left dangling, and `git push origin main` pushes the STALE branch -- it reports
success while the work never reaches the remote. Branch before committing:

```bash
cd <submodule> && git checkout main
... commit ...
git push origin main
```

### Pitfall: `git submodule update` checks out the RECORDED sha, not the latest

After pushing a fix inside a submodule, the parent still points at the old
commit. Plain `git submodule update` checks out that recorded SHA and silently
reverts your checkout. Follow the branch instead, then commit the pointer:

```bash
git submodule update --remote --init <path>
git add <path> && git commit -m "bump <repo>"
```

### Pitfall: `--remote` reads a STALE remote ref

If the submodule has never been fetched, its `origin/main` is old and
`--remote` keeps the old SHA with no warning. Fetch inside the submodule first,
and reset rather than merge when the local branch is just a duplicate of
upstream:

```bash
cd <submodule> && git fetch origin && git checkout main && git reset --hard origin/main
```

### Pitfall: a dirty submodule blocks the fast-forward

Local edits inside a submodule (a header patch that has since landed upstream)
make `git merge --ff-only` abort. If those edits are already upstream, discard
them. Never resolve it by `git add -A` in the parent.

### Pitfall: header edits do not trigger a rebuild

A Makefile that lists `.c` prerequisites does not track headers. Editing a
header and running `make` reuses stale objects, so the change appears to have
no effect (or an old prototype keeps being used). Run `make clean && make`
after any header change.

## Pitfall: GitHub's auto-created LICENSE commit blocks the push

Creating the repo with a `license_template` (or letting GitHub initialise the
branch) makes GitHub commit a template LICENSE on `main`. Your first push then
fails with `error: failed to push some refs` / `refusing to merge unrelated
histories`, because the remote branch has a commit you do not have.

Fix by merging the two roots and keeping YOUR license:

```bash
git fetch origin
git merge origin/main --allow-unrelated-histories -X ours \
  -m "merge GitHub initial commit (replace template LICENSE)"
git push origin main
```

`-X ours` is what keeps the WaefreBeorn Umbrella LICENSE instead of the
template one. Verify afterwards: `head -1 LICENSE` must read
`# WaefreBeorn Umbrella License v3.0`.

## Pitfall: a fresh `gh` install is not authenticated

Installing `gh` gives you an unauthenticated CLI. Either run `gh auth login`
(interactive, needs the user) or set `GH_TOKEN` from the stored credential
and use `gh api` / the REST calls above. Do not report the CLI as broken --
the API path works without it.
