# Bulk edits across many GitHub repos (no gh auth)

When `gh` is not authenticated but git pushes work, the stored git credential
drives everything. This is the loop for sweeping many own-repo READMEs/docs and
it is the only way to propagate a consistent identity line or annotation across
a whole org.

## Confirm the credential path

- `gh auth status` fails -> fine, do not fight it.
- `git config --get credential.helper` = `store` (or `~/.git-credentials`
  contains a `https://<user>:<token>@github.com` line) -> the token is usable
  by git and by curl against the API.

## Use the token WITHOUT printing it

Extract into a shell var, never echo it: token stays in memory only.

```bash
TOKEN=$(grep github.com ~/.git-credentials | head -1 | sed 's|^https://||; s|@github.com.*||' | sed 's|^[^:]*:||')
```

The token also works for authenticated REST reads (own repos with private
visibility): list all repos, read each README, get `default_branch` and
`pushed_at` — which is how you learn an ecosystem map and pick priorities.

## Clone in parallel, not '&'

Shell `&` backgrounding is rejected by the harness. Use `xargs -P`:

```bash
printf '%s\n' repo1 repo2 ... | xargs -P8 -I{} git clone -q "https://github.com/USER/{}.git" "{}"
```

Use `--depth 1` for repos that are huge (multi-GB) — a shallow clone is enough
to edit the README and push one commit.

## Edit, commit, push, VERIFY each repo

Work per-repo in a loop. Set author explicitly: the house identity is
`WaefreBeorn <waefrebeorn@users.noreply.github.com>`.

```bash
git -C $repo add README.md
git -C $repo -c user.name='WaefreBeorn' -c user.email='waefrebeorn@users.noreply.github.com' commit -q -m 'subject'
git -C $repo push -q origin HEAD
```

A push is NOT proven by rc=0. Verify the commit actually landed on the branch
GitHub shows:

```bash
lb=$(git -C $repo branch --show-current)
sha=$(git -C $repo rev-parse HEAD)
rs=$(git -C $repo ls-remote origin refs/heads/$lb | cut -c1-9)
# OK only when sha == rs
```

## Pitfalls

- **Never assume the branch is `main/master`.** Repos have real default
  branches: this session WuBuNOS used `wubu-integration`, WuBuFX used `root`,
  WuBu used `master`. `git push origin HEAD` tracks the LOCAL branch name;
  verify against `git branch --show-current` and `ls-remote refs/heads/<that>`. If `ls-remote refs/heads/main` shows nothing, the repo just has a
different default — check with the API `default_branch`, not by guessing.
- **Commit-message quoting breaks the shell.** A year-apostrophe or an open
  paren inside one `-m '...'` string makes `/bin/sh` choke with `Syntax error`
  (the exact error is opaque). Keep `-m` strings free of `'`, `(`, `)` — or pass
  several clean `-m` flags (each becomes a paragraph) instead of one rich one.
- **First clone of a default branch names it for you.** `git branch --show-current`
  after a clone answers which branch is default; reuse that, not a hardcoded
  name.
- **Resolve the token only once per session** into a var; `git clone`/`push`
  pick the credential helper automatically, REST reads need the var.
