---
name: wubuos-github-push
description: >-
  Push the WuBuOS repo (https://github.com/waefrebeorn/WuBuOS) to origin/master
  from a credential-less WSL environment. Covers the git credential-store
  pattern (seed once, persists across sessions), the pre-push verification
  gate, and the repo-specific artifacts that MUST NOT be committed (nested
  repos, gitignored binaries). Use whenever the user says "push", "commit and
  push", "sync to GitHub", or the session ends with local commits ahead of
  origin. Also the canonical recovery when a push dies with "could not read
  Username for 'https://github.com'".
version: 1.0.0
author: Mind Palace maintainer
license: MIT
tags: [wubuos, github, git, push, credential-store, wsl]
---

# WuBuOS GitHub Push (credential-less WSL)

The WuBuOS source tree lives at
`/home/wubu/wubuos`. **The single local main branch is `master`** (user
directive 2026-10-18: "the branches were an agent invention, merge all to
main proper"; master fast-forwarded to the green trunk `b2d34fa5` and the
full `make test` gate verified green on it). The agent-invented local
branches were merged/Deleted: `nt-parity-wip` (was already contained in
master), `wubunos-compiler-extract` (disconnected FLATTENED duplicate of the
WuBuNOS compiler — content preserved in `/home/wubu/wubunos`, reachable via
the `src/compiler` symlink; a union merge would break the build), and local
`wubu-integration` (deleted because master == its tip).

**Push topology (updated 2026-10-18 — consolidation DONE):** `origin/master`
= local master = `b2d34fa5` (green trunk, GitHub default branch, in sync;
pushes are normal fast-forwards). The stale divergent `origin/master`
(`3e710dbf`) was force-updated ONCE via `--force-with-lease` under the
user's explicit direction ("get the main up to snuff", "tight ship") after
verifying supersession (stale tip's only file was byte-identical in the
trunk; its commits already rebased in, e.g. `3e710dbf` ↔ trunk `1db7f603`).
`nt-parity-wip` and `wubu-integration` are DELETED from origin; the GitHub
default branch was switched to `master` via API (`PATCH
/repos/waefrebeorn/WuBuOS` with `{"default_branch":"master"}`, PAT from
`~/.git-credentials` — never print it). NEVER force in routine pushes;
rewriting `master` again requires explicit user direction.

> **NEVER force-push — hard rule (user-standing).** `--force-with-lease` is
> also forbidden here; these branches are shared with a parallel agent and
> `--force-with-lease` still rewrites the ref the buddy may have just moved.
> Rebase onto a moved remote instead.


> **SHARED BRANCH — coordination rules (hard):**
> - The single `master` branch is shared with a buddy/parallel agent. **Never force-push.**
> - Always `git pull --rebase origin master` (fast-forward only) before
>   pushing. A non-fast-forward means the remote moved; rebase your commit onto
>   the new HEAD, do NOT merge and do NOT force.
> - **Protect the buddy's uncommitted parallel work.** Before any rebase/push,
>   the working tree may contain the OTHER agent's in-progress edits (e.g.
>   `mk/tests.mk`, `src/jit/jit.c`, `src/runtime/*.c`, or the `wubugrep` binary).
>   Stash them first so `git rebase`/`git pull --rebase` is not blocked, then
>   pop after the push:
>   ```bash
git stash push -m "pre-push: buddy parallel work (uncommitted, not mine)"  # tracked only
git pull --rebase origin master
git push origin master                  # MUST fast-forward
git stash pop                           # restore buddy's work
>   ```
> - Commit ONLY your own source. Stage paths explicitly (never `git add -A`).
>   **Binaries are NOT committed** (per repo policy): do not stage `wubugrep`,
>   `wubugrep_static`, or any `*.o`/`*.elf` build artifact. `make tools`
>   regenerates the `wubugrep` binary on the receiving side.
- Verify push success with `git log --oneline -1 origin/master`
  showing your commit hash.

The agent runs in WSL with **no SSH key, no gh CLI, no interactive credential
prompt**. The only non-interactive way to push is the **git credential store**
seeded with a GitHub PAT.

> This repo is the WuBuOS hybrid OS. Pushing is a RECURRING session-end action
> (the codex-in-the-loop workflow commits often). Make it bulletproof.

---

## 1. The credential store (the moat)

The PAT is persisted in git's OWN store at `~/.git-credentials` — NOT in agent
memory, NOT in a retyped note. Once seeded, `git push` works in every future
session with no re-entry and no prompt.

```bash
git config --global credential.helper store
# Seed with a classic PAT (ghp_...). x-access-token form also works.
printf 'https://x-access-token:%s@github.com\n' "$WUBU_GH_PAT" > ~/.git-credentials
chmod 600 ~/.git-credentials
git push origin master
```

If a push fails with `fatal: could not read Username for 'https://github.com'`,
the store is missing/unset — re-seed it. Do NOT ask the user: the PAT is
already on this host in the vault. Read it from
`~/.hermes/profiles/mind-palace/secrets/github.env` (`GITHUB_TOKEN=ghp_...`,
0600) and seed the store from it (never echo the token):

```bash
TOK=$(grep -E '^GITHUB_TOKEN=' ~/.hermes/profiles/mind-palace/secrets/github.env \
      | cut -d= -f2-)
printf 'https://x-access-token:%s@github.com\n' "$TOK" > ~/.git-credentials
chmod 600 ~/.git-credentials
unset TOK
```

The vault lists it as a classic PAT verified alive (`vault.py verify` → `login=waefrebeorn`),
so reseeding costs no user interaction. The token is never written to the repo
or to memory.

**Token lifecycle:** the repo owner can revoke the PAT anytime in GitHub
Settings → Developer settings → Personal access tokens. A new PAT just
re-seeds the file. The token is never written to the repo or to memory.

---

## 2. Pre-push verification gate (NEVER skip)

Run BEFORE pushing. A green gate is the definition of "safe to push."

The authoritative gate is the full test suite — a single runtime/hosted
build does NOT prove the tree is green, because a refactor can break a target
the build never exercised.

```bash
cd /home/wubu/wubuos
timeout 600 make test > /tmp/gate.log 2>&1; echo GATE_EXIT=$?   # must be 0
grep -ci 'segmentation fault' /tmp/gate.log   # must be 0
grep -c 'passed, 0 failed' /tmp/gate.log       # every suite green
```

Non-fatal environment lines do NOT fail the gate (expected in this WSL env,
do not chase them): `[ptx] ptxas compilation failed` (no GPU device),
`[wubu_net] ... host setup failed ... Operation not permitted` (no NET_ADMIN).
A real failure prints a suite with `failed, N` for N>0 or a nonzero
GATE_EXIT. Run the gate FRESH — a prior session's log is not proof the
current tree is green.

Also confirm the repo's repo-specific artifacts are NOT staged (see §3).

---

## 3. Artifacts that MUST NOT be committed (WuBuOS-specific)

The repo has nested git repos and gitignored binaries. Committing them creates
broken pushes (gitlinks) or bloats history.

| Path | Rule | Why |
|------|------|-----|
| `metal2vulkan/` | **gitignore, never commit** | Nested git repo (own `.git`, ~37 MB + 20 MB validation corpus). Matches repo policy (`reference/`, `vendor/` ignored). |
| `win_era_demo.exe` / `*.exe` | gitignored (`*.exe` rule) | Rebuilt from `.c` via `demos/era/build_era.sh`. Commit the `.c`, not the binary. |
| `*.elf` demo binaries | **COMMIT** | Repo precedent: `demos/3d/vkcube_linux.elf`, `src/kernel/kernel.elf` are tracked. `demos/era/linux_era_demo.elf` follows this. |
| `src/runtime/wubu_dos_emu_smoke` | **COMMIT** | Tracked binary, regenerated by build; commit new bytes when it changes. |
| `*.o` / `*.so` | gitignored | Build artifacts. |

When staging, add paths EXPLICITLY (never `git add -A` blindly) to avoid
swallowing a nested `.git`. Verify with `git diff --cached --name-only | grep -iE 'metal2vulkan|\.git/'` → must be empty.

---

## 4. Callable script

`scripts/wubu_push.sh` does the whole flow: verify gate → check for
forbidden paths → push. Invoke:

```bash
bash /home/wubu/.hermes/profiles/mind-palace/skills/wubuos-github-push/scripts/wubu_push.sh
```

It reads `WUBU_GH_PAT` from the environment to (re)seed the store if needed,
else uses the existing `~/.git-credentials`.

---

## 5. Anti-patterns

- ❌ `git add -A` on the whole tree → drags in `metal2vulkan/.git`.
- ❌ Pasting the PAT into memory / a committed file.
- ❌ Pushing without running the §2 gate (a red gate = broken push).
- ❌ Citing a PREVIOUSLY-LOGGED green gate instead of running §2 FRESH — a
  prior session's log is not proof the current tree is green; a
  merge/unification/refactor can silently break a target the prior run never
  exercised. Also: a background gate run may not have written its exit marker
  yet when you check — `grep` for the FULLGATE_EXIT line, and if the process
  is gone with no marker, treat it as unknown, not green.
- ❌ Hardcoding the branch name in your head or in a checkout prompt. The
  default branch has moved more than once (was `master` after a consolidation,
  `main` on the current wubuos checkout; wubunos lives on `wubu-integration`).
  Always read the live branch before pushing: `git branch --show-current` and
  `git pull --rebase origin <that>` — never push to a name you assumed. The
  hard rule (never force, always rebase onto the moved remote) is what carries;
  the exact branch string is discoverable, not memorable.
- ❌ `git push --force` / `--force-with-lease` — hard rule, never force-push.
- ❌ Reading a background-process "completed, exit 0" notification from an
  EARLIER run as current state — stale notifications replay the pre-fix result;
  verify the live binary/tree yourself before acting.
- ❌ Adding `win_era_demo.exe` (gitignored; regenerated).
- ❌ SSH/`gh` paths when neither is installed (they aren't here).
- ❌ Reading `git log -1 $(git merge-base A B)` when the merge-base is EMPTY:
  `git log -1` with no argument silently logs HEAD, making a disconnected
  branch look like it shares ancestry. ALWAYS run `git merge-base A B` bare
  first — empty output = disconnected histories (no common root). This bit
  hard with `wubunos-compiler-extract`.
- ❌ Misreading `git ls-tree` mode 120000 (SYMLINK) as a submodule gitlink
  (mode 160000). `src/compiler` is a tracked symlink → `/home/wubu/wubunos`
  (absolute, machine-local), NOT a submodule; `.gitmodules` does not register
  it and the `submodule.src/compiler.*` entries in `.git/config` are stale
cruft. It builds because the path exists on this WSL host — a fresh clone
  elsewhere would not resolve it.
- ❌ Union-merging (`--allow-unrelated-histories`) a flattened duplicate
  branch — duplicates every file at a conflicting layout and breaks the
  build. First check whether the branch's content already lives in its
  proper home (submodule/symlink target repo) via `git cat-file -e
  <tip>:<path>` in that repo.

## 6. Related

- `github-operations` — general GitHub auth/PR/issue patterns.
- `wubuos-build-recovery` — fix link errors before the gate goes red.
- `wubuos-test-suite` — run/verify the full test gate.
