# Build Recovery — Repo Topology Note (2026-08-15)

The WuBuNOS compiler is reached by the OS repo via a symlink at
`wubuos/src/compiler/` → `/home/wubu/wubunos` (NOT a gitlink submodule).

## If src/compiler/ is not a symlink

```bash
cd /home/wubu/wubunos
rm -rf /home/wubu/wubuos/src/compiler      # only if it's a real dir, not a symlink
ln -s /home/wubu/wubunos /home/wubu/wubunos/src/compiler
```
Also remove the now-stale `.gitmodules` entry for `src/compiler` (it is a
symlink, not a submodule — see `wubuwizard/docs/TOPOLOGY.md` §3.1).

## If you're fixing compiler build issues

Authoritative repo map: `wubuwizard/docs/TOPOLOGY.md` (§§1-3). The compiler
source lives in `~/wubunos` (its own repo, branch `main`). Edit there only;
the OS build reaches it via the `wubuos/src/compiler` symlink, so no
submodule-pointer commit is ever needed — git tracks the symlink itself.

## Three-repo layout

| Repo | Local | GitHub |
|------|-------|--------|
| wubuwizard (brain) | `~/wubuwizard` | `waefrebeorn/wubuwizard` |
| WuBuNOS (compiler) | `~/wubunos` | `waefrebeorn/WuBuNOS` |
| WuBuOS (body) | `~/wubuos` | `waefrebeorn/WuBuOS` |

## Hallucination warning

A prior session's memory claimed "wubunos = symlink → wubuos" — this was
WRONG and caused Makefile corruption. These are THREE REAL DIRECTORIES:
`wubunos` is the independent compiler repo; `wubuos/src/compiler` is the
symlink into it. `wubuos/src/brain` is the real submodule → wubuwizard.
