# Orphaned recipe lines in mk/tests.mk

## Symptom
A target "works when the command is run by hand and fails under make". `make -p <target>`
shows the target with **no recipe** and `Implicit rule search has not been done`,
so make falls back to an implicit rule and executes something else entirely
(e.g. `test_ns_session` ran the 9P test's binary and `-ljson-c`).

## Cause
A tab-indented line in `mk/tests.mk` with **no target above it** attaches to the
previous target as recipe text. Long hand-maintained link commands make this easy:
a continuation line loses its leading tabs (or gains literal tabs inside the
argument list), make parses it as a *new rule*, and the remainder of the original
command silently stops being part of the recipe.

## Detect
- `make -p -n <target> | grep -A2 '^<target>:'` — no recipe = caught.
- Compare `make -n <target>` against the block you wrote; if the tail belongs to a
different test, the block is contaminated.
- Heuristic scan: for every line starting with a tab, walk back to the previous
  non-blank line; if it is neither a target (`ends with :`), a continuation
  (`ends with \`), nor another recipe line, it is a candidate. The heuristic
  over-counts multi-line recipes — treat it as a list to inspect.

## Repair
1. Delete the orphan run (the tab lines after the last legitimate command), not just
   the target line.
2. Restore exactly one leading `\t` (recipe) or `\t\t` (continuation) and ensure the
   line ends with ` \` if more arguments follow.
3. Prefer replacing a fragile multi-line link command with a wrapper script
   (`tools/test_ns_session.sh`) that contains the verified compile+link+run sequence.
   A script cannot be re-broken by a stray tab.
4. Verify with the real target, not `make -n`.

## Beware
- `git checkout -- mk/tests.mk` discards hand repairs; re-apply deliberately.
- Appending files to a contaminated recipe produces new errors at a different symbol
  each round. Stop and check whether the recipe is even being executed.
