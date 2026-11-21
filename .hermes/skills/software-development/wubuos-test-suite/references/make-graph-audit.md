# Auditing a Makefile test graph

Three defect classes make a test suite look greener than it is. Each is
mechanical to detect and cheap to fix **at the source**, not per target.

## 1. Unreachable targets

Declared rules and reachable rules are different sets. Compute the closure from
the aggregate target (`test`) through its prerequisites, and diff it against
every declared `test_*` rule.

`scripts/check_make_coverage.py` does this and exits non-zero on any orphan.

Fix shape (generated file, one line per target):

```make
ALL_TESTS = test_a test_b ... test_z
.PHONY: test_all
 test_all: $(ALL_TESTS)
```

Generate it from the rules so it cannot drift; include it after the file that
defines the rules. A hand-maintained tier list is exactly how 315 of 446 targets
ended up unreachable.

## 2. Header-less duplicated blocks

Symptom: a target runs `gcc -c` with **no input file**, or exits 127 running a
binary it never built, or a rule with no prerequisites suddenly gets extra
commands.

Cause: a tab-indented recipe block whose target line and variable assignments
were lost/duplicated. Make attaches those tab lines to the *previous* target, so
the failure is reported against a rule that looks unrelated.

Detect:

```sh
grep -n '^\t' Makefile | head
python3 - <<'PY'
lines=open('Makefile').read().split('\n')
for i,l in enumerate(lines):
    if l.startswith('\t') and (i == 0 or (lines[i-1] and not lines[i-1].startswith('\t')
                                 and not lines[i-1].endswith('\\') and ':' not in lines[i-1])):
        print('orphan recipe line', i+1, l[:60])
PY
```

A line only counts as an orphan when the preceding non-continuation line is not
a target. Delete the orphan block, keep the complete copy, then `make -n <target>`.

## 3. Shared source-list variables

When many recipes link `$(HOLYD_SRC)` / `$(VSL_NT_OBJS)` / `$(FRONT)`, a single
missing file breaks every target at once and looks like ten separate link bugs.

Procedure when several targets fail with the same undefined symbol:

1. `grep -n '<symbol>' src -r` — find the defining `.c`.
2. `grep -rn '<that file>' mk/*.mk Makefile` — if it appears once, in a variable,
   the variable is the bug; if it appears in no recipe, add it to the variable.
3. Fix the **definition**, not each recipe; then re-run every target that uses
   the variable.
4. Same rule for duplicate definitions: a symbol defined in two TUs that both
   reach a link line needs one of them removed from the list, not `--allow-multiple-definition`.

## 4. Targets that never execute

If the target name equals the file the recipe produces in the same directory,
make considers it up to date forever and skips the `./$@` step. Either declare
`.PHONY` for all test targets, or emit the binary elsewhere (`$(KERNEL)/test_x`)
so the target name can never exist as a file. The second shape is self-protecting
and needs no phony list.

## Reporting

Count three things separately and never conflate them: declared targets,
reachable targets, and targets that pass. A run that reports "all pass" without
stating reachability is reporting on an unknown subset.
