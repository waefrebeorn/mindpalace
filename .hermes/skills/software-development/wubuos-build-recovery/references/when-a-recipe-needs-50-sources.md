# When a recipe needs 50+ sources: it is not link rot

`test_hosted` linked 2 files and reported 128 undefined symbols across 45
distinct names. The tempting move is to resolve each symbol to its defining
file and append the list. Doing that is a trap.

## The measurement that decides it

Track (undefined symbol count, cumulative files added) each round. Two
successive rounds at similar counts mean OSCILLATION, not progress:

| round | undefined | files linked | added |
|---|---|---|---|
| start | 128 (45 distinct) | 2 | - |
| hand-resolve every symbol | 0 (links!) | 27 | 25 |
| after that | 110 (58 more) | - | 58 |
| copy test_wm's GUI list | 3 | 61 | 34 |
| add those 3 | 45 | - | 22 more, same 45 symbols |

It hit ZERO undefined references and still did not converge. Copying a
working sibling recipe got 45 -> 3, then the next round was back to 45. That
is a cyclic dependency over the whole application stack.

Stop rule: if the next round needs > ~15 new files, OR the symbol count does
not strictly decrease across two successive rounds, stop and revert.

## When the loop IS converging — finish it
The stop rule above is about OSCILLATION, not about total size. A recipe for a
whole hosted application stack can legitimately need 100+ objects: one
recovery took ~180 objects (kernel drivers, hosted Wayland, bridge, worldsim,
OCI, MIR/JIT passes, edr, applet objects) across ~150 rounds and linked
successfully. What distinguishes it from the oscillation trap is the TREND:

| signal | oscillation (revert) | converging (finish) |
|---|---|---|
| undefined count | plateaus / returns to a prior value | strictly decreases each round |
| new files per round | grows as the same symbols come back | stays small (1-5) late |
| symbol identity | the SAME names reappear | each name is seen once |

Converging-but-large means the target was simply never wired up, not that it is
unbuildable. The efficient procedure is a sed loop over ONE link line, not
symbol resolution by hand — anchor `sed -i "<LINE>s|UNIQUE-LAST-TOKEN|UNIQUE-LAST-TOKEN <new>.o|"`,
always append at the END of the link line, and filter any path matching `_test`,
`_stub`, `_support` before resolving (those define the symbol as a no-op and
make the target pass vacuously). Full recipe + the `$(VAR)` expansion traps:
`wubunos-hosted-capture-bridge`.

After the link succeeds, keep going: a hosted target that LINKS can still crash
at startup for reasons unrelated to the link (physical-address heap in a
userspace process, libgomp init colliding with the in-tree libc). Run it and
read the backtrace before calling the recipe done.

## Two traps before appending anything

1. **Is the candidate a stub?** Many files define the missing symbols as
   no-op doubles: `src/hosted/hosted_test.c`, `src/gui/wm_test_stub.c`,
   `src/apps/cmd/cmd_test_stub.c`, `src/runtime/wubu_hc_eval_stub.c`,
   `src/kernel/test/test_agi_kernel_stub.c`, plus every `*_test_support.c` and
   `*_test_stubs.c`. Linking those makes the test PASS VACUOUSLY, which is
   worse than failing. Filter paths matching `_test`, `_stub`, `_support`
   before resolving.

2. **Find the right sibling, and verify it passes.** Rank targets by how many
   GUI sources their recipe links, then actually run the top candidate --
   `test_ui` 7/7 and `test_wm` 33/33 both pass. Do NOT pick by
   name similarity: `test_styxfs` uses the same `$(HOSTED_TEST_OBJS)`
   variable but links the compiler + JIT + StyxFS and NO GUI at all, so it is
   useless as a template for a desktop target.

## Editing these recipes safely

These lines are 500-1500 chars with backslash continuations. A python string
insert assuming a short line corrupts them:

- Use literal `src/...` paths, NOT guessed `$(VAR)` forms. `$(GUI)`,
  `$(KERNEL)`, `$(RT)`, `$(COMP)`, `$(HOSTED)` exist (mk/vars.mk); `$(SRC)`
  does NOT and silently expands to nothing, leaving `//filename.c` debris.
- Insert as its OWN tab-indented continuation line ending in `\`, never
  append into an existing line -- appending lands on the wrong token and
  yields `wubu_spawn.c/hosted`.
- After ANY edit: `make -n <target> | grep -oE '[^ ]*//[a-z0-9_]+\.c'` must be
  EMPTY, and `grep -c '$(SRC)/' mk/tests.mk` must be 0.
- `git diff` the recipe and confirm exactly the line count you intended.

## Current state

`test_hosted` is reverted and baselined as a known orphan (312 orphans,
wiring gate green). `test_metal` and `test_gauntlet` are the same class.
Reviving any of them is a deliberate decision to assemble the hosted
application stack -- a separate task, not a mechanical fix.