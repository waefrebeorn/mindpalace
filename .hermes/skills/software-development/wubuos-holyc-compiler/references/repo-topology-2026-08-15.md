# WuBuNOS Compiler — Repo Topology (2026-08-15, corrected 2026-08-16)

The WuBuNOS compiler is reached by the OS repo via a **symlink** at
`wubuos/src/compiler/` → `/home/wubu/wubunos` (NOT a gitlink submodule).

## Authoritative source

All placement + linkage rules live in `wubuwizard/docs/TOPOLOGY.md` (§3).
This file only records the corrected facts that the build-recovery notes
rely on.

## Three-Repo Layout

| Repo | Local path | GitHub | Branch |
|------|-----------|--------|--------|
| **wubuwizard** (brain) | `/home/wubu/wubuwizard` | `waefrebeorn/wubuwizard` | `wubu-integration` |
| **WuBuNOS** (compiler) | `/home/wubu/wubunos` | `waefrebeorn/WuBuNOS` | `main` |
| **WuBuOS** (body) | `/home/wubu/wubuos` | `waefrebeorn/WuBuOS` | `wubu-integration` |

## WuBuOS linkage (two different mechanisms)

- `wubuos/src/compiler/` → **symlink** to `wubunos` (NOT a submodule).
  No `git submodule` operations needed; the OS `Makefile` uses
  `$(COMP) = src/compiler` and compiles straight into wubunos.
- `wubuos/src/brain/` is a **real gitlink submodule** → wubuwizard.
- `wubuos/src/runtime/container/wubucontainer/` is a real submodule
  → WuBuContainer.

## CRITICAL

- `wubunos` is its OWN repo (branch `main`). Edit compiler sources there only.
- `wubuos/src/compiler/` is a symlink mirror — never re-add a submodule or
  re-copy compiler files into `wubuos/tools/` (the 2026-08-16 re-org moved
  `holyc.c`, `test_gauntlet_runner.c`, `isa-test/`, `peephole_superopt/`,
  `dev/` into wubunos and repointed `mk/tests.mk` through `$(COMP)/…`).
- The `.gitmodules` entry for `src/compiler` is stale and removed.
