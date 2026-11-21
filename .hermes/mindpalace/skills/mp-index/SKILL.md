---
name: mp-index
description: SHA-256 file index and dead-path verification for palaces.
version: 1.0.0
author: WaefreBeorn
metadata:
  hermes:
    tags: [mind-palace, index, provenance, verification]
    related_skills: [mp, mp-prestige]
---

# mp-index — index system and provenance gate

## When to Use

Use to build or refresh the "index system of all project files and Devil's
Advocate details", to check for dead documentation paths, or to prove that a
handoff's file claims match the artifact.

## Build the index

```
mp index --write         # or: python tools/index_repo.py --root <dir> --write
```

Walks the tree, skips `.git`, `.testbin`, `.locks`, `__pycache__`, and emits
`INDEX.md` with `Files: N`, `Bytes: N`, and one `- \`path\` [sha256-12]` line
per file. Provenance is the SHA, not a hand-typed count.

## Index a whole git project

```
python tools/index_project.py --root <repo> --out PROJECT_INDEX.md
```

Reads `git ls-files`, skips generated gates/objects/binaries, hashes the rest
in parallel. Pass `--git <native git.exe>` when calling from Python on Windows
(the MSYS `git` on PATH cannot be spawned by native Python).

## Verify

```
mp verify                # or: python tools/verify_mindpalace.py --root <dir>
```

The gate fails on: missing required files; any doc path-like token that does
not exist; INDEX SHA drift (`--strict-paths`); SKILL.md with description >60
chars or no `## When to Use`.

## Rules

- Rebuild the index after every change; stale SHA is a defect.
- A path named in a doc that does not exist is a build failure.
- DA details live in `STEPLOG.md`, linked from `DEVILS_ADVOCATE.md`; the index
  covers both so a fresh agent can find every file and every finding.
- Count files mechanically; never guess a count.
