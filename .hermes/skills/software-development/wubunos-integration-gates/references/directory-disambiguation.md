# Directory Name Disambiguation: wubunos vs wubunos

## Verified this session — 2026-10-07: report honestly, run the real gate
- `wubunos make test` is GREEN 195/195 — the `test_tgemm` -O3 segfault was resolved via a target-local flag scrub in the
  Makefile recipe (`$(eval CFG_TGEMM := $(filter-out -march=native -mavx2 -mfma -frename-registers -funroll-loops -O3,$(CFLAGS)))`,
  recipe `$(CC) $(CFG_TGEMM) ...`). Fixed with gdb-verified root cause (`clock_gettime()` → `main()`), rebuilt, and ran
  directly: `T_GEMM correctness: 576/576 entries match naive C` → interpreter/JIT timing, exit 0.
- `wubuwizard test_amoeba_shrink`: real 3-FAILURE live blocker (`grow inserted a block`, `shrink returns to baseline
  depth`, `shrink of a non-core layer ok`). Verify each link/recipe symbol with `grep -rln <symbol> src/ include/`
  and confirm the module source exists (`src/*.c` + `ls`) before editing link lines — a guessed `.o` (e.g. `wubu_calibration.o`)
  that has no source file aborts `make` before linking. Do not handwave "green" from a handoff.
- **Report numbers, not claims.** A "green" claim without a fresh `make test`/`make <target>` run and real exit code
  (`echo exit=$?`) is not green. The wubujos skill (`wubunos-test-gate-closure`) carries the full -O0/-O3/gdb flag-scrub
  procedure for optimizer-sensitive gates.


When typed in shell/terminal commands, these look identical. A single wrong
character silently targets the wrong repo, causing confusing errors (e.g.,
"No such file or directory" for `mk/` when you meant the compiler repo, or
missing `isa-test/` when you meant the OS repo).

## Technique (verified 2026-08-23)
Use Python auto-detection rather than typing the name:

```python
import os
OS = None; COMP = None
for name in os.listdir("/home/wubu"):
    full = os.path.join("/home/wubu", name)
    if not os.path.isdir(full) or not name.startswith("wubu"):
        continue
    if os.path.isdir(os.path.join(full, "mk")) and os.path.isdir(os.path.join(full, "src")):
        OS = full      # 6-char name: has mk/ + src/
    if os.path.isfile(os.path.join(full, "Makefile")) and os.path.isdir(os.path.join(full, "isa-test")):
        COMP = full    # 7-char name: has Makefile + isa-test/
```

Key property checks:
- Compiler repo: has `Makefile` + `isa-test/` directory
- OS repo: has `mk/` directory + `src/` directory

Always verify with `os.path.realpath()` on symlinks to confirm they point to
the expected target.

## Shell workaround
If you must use shell paths, use tab-completion or glob:
```bash
ls -d /home/wubu/wubu*  # shows both
```
Then copy-paste the exact name from the output.
