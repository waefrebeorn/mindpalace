# Compiler Makefile testing gates (wubunos)

Three self-contained, verifiable gates that add CFLAGS/Makefile discipline without
touching codegen. Each is proven by its own `make test_*` target printing
`ALL PASSED`, with file:line evidence recorded in
`docs/PORTFOLIO-REALITY-CHECK.md`. All three are safe to add because the flags are
additive (warnings, not errors) and the gate is a separate target — verify an
existing target still builds after each change.

## 1. Header-dependency tracking
- Add `-MMD -MP` to CFLAGS (additive; emits `.d` files, never changes codegen).
- Add `-include $(wildcard *.d tools/*.d)` before the source groups so a touched
  header recompiles its dependents.
- Gate: compile a witness `tools/test_<x>.c` that `#include`s a sibling header,
  assert the emitted `<x>.d` lists that header, then run the binary.

## 2. Zero-warning gate with a locked baseline
- Append `-Wall -Wextra` to CFLAGS. The build still succeeds (warnings ≠ errors)
  but emits real debt; lock it instead of fixing hundreds of sites.
- Generate baseline: `make -B test_isa_driver 2>log; grep 'warning:' log | sort >
  tools/warning_baseline.txt`.
- Gate: rebuild with `2>now`, `grep 'warning:' | sort`, `diff` against the
  committed baseline; print `ALL PASSED` iff identical, `exit 1` on drift.
- The baseline is the honest current debt; the gate prevents NEW warnings and
  does not claim a clean compile.

## 3. Compile-flag parity gate
- `tools/check_compile_flags.py` enumerates every `$(CC)` recipe, extracts the
  flag source, and classifies SAME (uses `$(CFLAGS)`) vs DEVIATES
  (`$(GAUNTLET_CFLAGS)` or an explicit codegen token not in CFLAGS: `-O`,
  `-std=`, `-march=`, `-mavx*`, `-mfma`, `-Wall`, …).
- Only genuine codegen tokens count as overrides. Skip `-I`, `-D`, `.c`/`.o`,
  `$^`/`$@`, `$(VAR)` — otherwise source filenames and stray parens leak into the
  deviation list and the gate is meaningless.
- Emit a sorted manifest (`tools/compile_flag_parity.txt`); the gate regenerates
  and diffs it; `ALL PASSED` iff no drift.

## Pitfalls
- `$(CC)`/`$(CFLAGS)` inside a `python3 -c "..."` argument get shell-expanded —
  always author these scripts as files and run them with `python3 path.py`.
- `make -n <target>` prints the RUN line (`./$@`) when the binary already exists;
  only after `rm -f <target>` does it print the compile line. Do not mistake the
  run line for the compile command when measuring flags/warnings.
- A regenerate-and-diff gate passes vacuously on an empty baseline — print the
  row count and the deviation set before trusting the green.
