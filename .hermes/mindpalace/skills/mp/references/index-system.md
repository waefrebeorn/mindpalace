# Index system — provenance and dead-path gate

`tools/index_repo.py` walks the tree, skips `.git`/`.testbin`/`.locks` and
computes a SHA-256 (first 12 hex) for each file, emitting `INDEX.md`:

```
# Mind Palace Index
Files: N
- `path/to/file` [debb0e9fd633]
```

`tools/verify_mindpalace.py` is the hard gate:

- every required file exists;
- every path-like token in every doc exists (dead path = failure);
- every INDEX SHA matches the current file (stale SHA = defect under --strict);
- every `SKILL.md` has a description <=60 chars and a `## When to Use` section.

`tools/index_project.py` is the repo-scale companion: it reads `git ls-files`,
excludes generated gates, build objects and binaries, and hashes the rest in
parallel into `PROJECT_INDEX.md` — the index of all project files. DA findings
are linked from it into `DEVILS_ADVOCATE.md` and `STEPLOG.md`.

Rule: rebuild the index after every change; a stale index is a defect, not a
stylistic nit. The index is the "index system of all project files and
Devil's Advocate details" — DA findings live in `STEPLOG.md` and are linked
from `DEVILS_ADVOCATE.md`.


## Pitfalls (learned on Windows/MSYS)

- Native Python cannot consume an MSYS `/c/...` path — it becomes `C:\c\...`.
  Convert with `cygpath -m` before passing paths to a Python tool.
- `git` on this box's PATH is an MSYS shim that native Python cannot spawn
  (`PermissionError: WinError 5`). Use a native `git.exe` via `--git`.
- Never verify the SHA of `INDEX.md` against itself — it is self-referential
  and always stale. Skip that entry in the verifier.
- Doc paths come in three flavours: relative to the doc, relative to the palace
  root, and `.hermes/mindpalace/...` project-prefixed. Resolve all three.
