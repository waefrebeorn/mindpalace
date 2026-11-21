# Build Recovery — Repo Topology Note (2026-08-15)

The WuBuNOS compiler is now reached by the OS repo as a symlink at
`wubuos/src/compiler/` → `/home/wubu/wubunos` (NOT a gitlink submodule).

## If src/compiler/ is not a symlink
```bash
cd /home/wubu/wubunos
rm -rf /home/wubu/wubuos/src/compiler        # only if it's a real dir, not a symlink
ln -s /home/wubu/wubunos /home/wubu/wubunos/src/compiler
# Also remove the now-stale .gitmodules entry for src/compiler (it is a symlink, not a submodule)
```

## If you're fixing compiler build issues

The compiler source lives in `~/wubunos` (its own repo, branch `main`). 
Edit there, push to `waefrebeorn/WuBuNOS` main. The wubuos submodule pointer
will need to be updated + committed after.

## Three-repo layout

| Repo | Local | GitHub |
|------|-------|--------|
| wubuwizard (brain) | `~/wubuwizard` | `waefrebeorn/wubuwizard` |
| WuBuNOS (compiler) | `~/wubunos` | `waefrebeorn/WuBuNOS` |
| WuBuOS (body) | `~/wubuos` | `waefrebeorn/WuBuOS` |

## Hallucination warning

A prior session's memory claimed "wubunos = symlink → wubuos" — this was 
WRONG and caused Makefile corruption. These are THREE REAL DIRECTORIES.
