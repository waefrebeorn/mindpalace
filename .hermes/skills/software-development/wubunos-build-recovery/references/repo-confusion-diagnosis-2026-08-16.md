# Diagnosing Repo Confusion — "lost" or "duplicated" files (2026-08-16)

A recurring build-recovery class: the agent believes a file was *lost* or
*dupicated* across repos, yet `git status` is clean and the file is
"missing" from the wrong place. The real cause is always a **wrong mental
map of the repo linkage**, not a missing file. Diagnosis recipe below is
the fast path back to ground truth.

## The three-repo truth (read first, every time)

| Repo | Path | Remote | Linkage into wubuos |
|------|------|--------|---------------------|
| wubuwizard (BRAIN) | `/home/wubu/wubuwizard` | `waefrebeorn/wubuwizard` | `wubuos/src/brain` = **real gitlink submodule** |
| wubunos (COMPILER) | `/home/wubu/wubunos` | `waefrebeorn/WuBuNOS` | `wubuos/src/compiler` = **symlink** → `wubunos` |
| wubuos (BODY) | `/home/wubu/wubuos` | `waefrebeorn/WuBuOS` | self |

- `wubunos` is **NOT** a symlink to `wubuos`. It is its own repo.
- `wubuos/src/compiler` is **NOT** a submodule. There is no `.gitmodules`
  entry for it (if there is, it is stale and must be removed).
- Authoritative, always-current map: `wubuwizard/docs/TOPOLOGY.md` §3.

## The 5-command diagnosis

When a file "appears lost / duplicated", run this before assuming anything:

```bash
# 1. Is the symlink intact? (compiler files appear here via the link)
ls -ld /home/wubu/wubuos/src/compiler && readlink /home/wubu/wubuos/src/compiler

# 2. Real file existence across both views (same inode = one checkout)
stat -c '%i %n' /home/wubu/wubunos/holyc.c
stat -c '%i %n' /home/wubu/wubuos/src/compiler/holyc.c     # same inode => single source

# 3. Is it tracked where you think? (gitlink=160000, symlink=120000, file=100644)
git -C /home/wubu/wubuos ls-files -s src/compiler          # expect 120000 (symlink)
git -C /home/wubu/wubuos ls-files -s src/brain             # expect 160000 (gitlink)

# 4. Does .gitmodules lie about src/compiler?
grep -c 'src/compiler' /home/wubu/wubuos/.gitmodules        # expect 0

# 5. Find the file everywhere it actually exists, not where you assumed
find /home/wubu/wubunos /home/wubu/wubuos -name '<file>' 2>/dev/null | grep -v '/.git/'
```

## The "lost holyc_mir_eval.c" pattern (this session's root cause)

Symptom: agent ran `git show HEAD:holyc_mir_eval.c` inside `wubuos` and got
"pathspec did not match" → concluded the file was "lost" when a symlink was
deleted.

Reality: the file was **never tracked by the OS repo** — `wubuos/src/compiler`
is a symlink to `wubunos`, and only gitlinks/symlinks are tracked, not their
contents. The file always lived in `wubunos` (and still does, committed at
`9e80af6`).

Moral: run `git ls-files -s src/compiler` first. A `120000` mode means
symlink → inspect `wubunos/`. A `160000` means gitlink submodule →
`git -C .git/modules/src/compiler ls-tree HEAD`.

## The "git mv skipped the file" trap

`git mv` operates only on **tracked** paths. If a file was copied (not yet
`git add`-ed), `git mv` silently no-ops with "not under version control".
Recovery: plain `mv`, then `git add`. Verify with `git status --short`
afterward — expect an `RM` or `A` line, not silence.

## Tool-flakiness workaround: read_file vs bash cat on skill refs

`read_file` intermittently returns "File not found" for files under
`skills/software-development/.../references/` even though `find` lists them
and `bash cat` reads them. When `read_file` fails on a reference doc:
fall back to `bash cat <path>` or use `write_file` to rewrite it
(write_file has its own verification and does not hit the same glitch).
This is an agent-local tooling quirk, not a repo problem.
