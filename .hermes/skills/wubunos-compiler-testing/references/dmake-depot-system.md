# DMake — Gauntlet Depot Build System

DMake (`scripts/dmake.py`) manages the acquisition, generation, and integration of compiler test suites from upstream sources.

## Why DMake exists

The gauntlet depot needs to:
1. Pull tests from multiple upstream sources (Fujitsu, c-testsuite, etc.)
2. Convert them into gauntlet-compatible C files
3. Track which tests are return-value vs output-comparison
4. Never destroy test semantics by concatenating multi-file programs

## Architecture

```
Upstream repos (git clones) → DMake generate → Gauntlet C suites → Compiler JIT → Results
```

### Depot folders (gitignored)
Each source has a `depot/<name>/upstream/` symlink to the cloned repo.

### Generated suites (git-tracked)
Each source produces:
- `gauntlet_<name>.c` — test array with source + expected return value
- `gauntlet_<name>_outputs.c` — expected stdout (for output-comparison tests)

## Test acquisition rules

1. **Single-source only for return-value tests** — extract individual `.c` files
2. **Multi-file programs stay as-is** — reference outputs capture full program behavior
3. **Never concatenate** — each translation unit preserves its linkage semantics
4. **Expected values via host gcc** — compile + run with gcc to get ground truth for new tests
5. **Reference outputs from upstream** — use `.reference_output` files directly when available

## Adding a new source

1. Add entry to `UPSTREAM_SOURCES` dict in `dmake.py`
2. Add `generate_<source>()` function
3. Call it from `generate()`
4. Add header declarations to `wubu_test_gauntlet.h`
5. Add to gauntlet_v2/v3 suite arrays

## Session outcomes (2026-09-06)

- 758 tests acquired from 5 sources
- VLA implementation: parser + codegen for runtime-sized arrays
- gauntlet_v3 fork fix: no free in forked children
- gauntlet_v3 worker 0 fix: waitpid BEFORE reading result file (not after)
- Baseline: 2,827 PASS / 403 FAIL / 1,862 ERROR = 5,092 (55.5% pass rate)

### gauntlet_v3 worker 0 bug (FIXED)

**Symptom:** Worker 0 (first worker) produces 0 results while other workers complete normally.

**Root cause:** The main loop opened and read the result file BEFORE calling waitpid(). Since the worker hadn't finished writing yet, the file was empty. The parent then unlinked the file, then waited for the worker — but the data was already lost.

**Fix:** Call `waitpid(worker_pids[w], &status, 0)` BEFORE opening/reading the result file. This ensures the worker has finished writing all results before the parent reads them.

**Lesson:** In fork+file IPC, always synchronize (waitpid) before reading shared resources. The file is the synchronization point — its contents are only valid after the writer exits.
