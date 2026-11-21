---
name: wubu-tree-standardization
description: Bring old WuBuOS code up to standard, measured.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wubuos, standards, audit, ratchet, cleanup]
    related_skills: [wubuos-monolithic-split, wubuos-build-integrity, wubuos-hosted-product]
---

# Standardizing the WuBuOS tree

## When to use

- Asked to "fix all old code", "standardize", "clean up the tree" or "make it
  conform to the standards".
- Before starting a split/refactor of a first-party module.
- When adding a module that must obey the layout-scale, include or one-owner
  rules.

Full statement of every rule and its owner file:
`docs/STANDARDS_AND_WORKFLOW.md`. This skill is the operating procedure.

## The measurement comes first

A standard nobody can check is an opinion. `tools/std_audit.py` turns three
rules into numbers:

```bash
python3 tools/std_audit.py      # report; exit 1 on a HARD violation
make test_standards             # the gated form, using the ratchet
```

Rules measured: `.c` files over 600 lines; files with more than 40 includes;
layout literals in the eight surfaces the token scale governs. Plus WARN-level
counts of TODO/FIXME/placeholder markers.

### The ratchet is the point

Reporting 120+ offenders at once is not a plan, it is a reason to give up. So
the audit takes a baseline and fails only when violations GROW:

```bash
python3 tools/std_audit.py --baseline tools/std_audit_baseline.json   # gate form
python3 tools/std_audit.py --write-baseline tools/std_audit_baseline.json  # after improving
```

Regenerate the baseline ONLY when the number went DOWN. Lowering it after making
things worse is how a ratchet gets abused. Put the numbers in the commit body so
the next reader can watch them drop.

**Ratchet IDENTITY must survive ordinary edits.** Key long-file/fat-header
entries by FILE PATH, never `file:linecount` — every edit shifts line counts,
so a shrinking monolith reads as a "new" violation and the gate fails on
improvement. Key literal hits by `file:value`, never `file:line` — a hit moving
lines is not growth. Line-anchored keys make the ratchet cry wolf until people
regenerate the baseline blindly, which destroys the ratchet.

## Org-wide constant census (duplicate owners across repos)

`std_audit.py` governs the GUI surfaces; `tools/hardcode_census.py` measures the
WHOLE tree and any sibling repo: duplicate `#define`s (CONFLICT = different
values, mirror = same value in 2+ files), path literals, `getenv` knobs, literal
allocations, literal sleeps. First-party only; submodule mounts and vendored
trees are excluded — they are measured in their OWN checkout.

```bash
python3 tools/hardcode_census.py --json                 # full report
python3 tools/hardcode_census.py --root /path/to/repo   # sibling repo
python3 tools/hardcode_census.py --write-baseline tools/hardcode_census_baseline.json
python3 tools/hardcode_census.py --baseline tools/hardcode_census_baseline.json
```

Work order: CONFLICTS first (one side is usually a real bug), then mirrors
(merge into the owner), then env-knob registry + revolver clamping, then path
owners. The owner decision tree (revolver / settings / tokens / theme / shared
format header / register header / module-local) is `docs/CONSTANTS.md`; the
triage table for what NOT to "fix" is `references/constant-ownership.md`.

Per-repo protocol: run the census with `--root`, edit ONLY in that repo's own
checkout, gate with THAT repo's tests, commit/push per its branch protocol,
record the numbers in `docs/compendium/04-roadmap/hardcoding-census.md`. Never
edit submodule content from the body; never carry a gate claim across a repo
boundary. Compare define VALUES comment-free and numeric-spelling-normalized
(`0x30 == 0x0030`, `1u == 1`, `3.14f == 3.14`) or mirrors read as conflicts.

## Compiler-target hygiene campaigns (gcc14 class)

When the goal is "clean under the NEWER compiler" (CI runners carry gcc14
while the dev box has gcc13), implicit declarations, int/pointer
conditionals and return mismatches are ERRORS there and warnings locally.
Do not play whack-a-mole one CI push at a time:

1. **Measure the FULL frontier locally first.** The old compiler accepts
   the same strict flags — force a rebuild and collect every error in one
   pass: `make -B kernel KERNEL_CFLAGS="<normal flags> -Werror=incompatible-pointer-types -Werror=int-conversion -Werror=implicit-function-declaration"`.
   (Drop flags the old compiler lacks, e.g. -Wreturn-mismatch is gcc14-only.)
2. **Run waves.** `tools/kernel_strict_wave.py <error-log>` parses implicit
   declarations, maps each symbol to its owning header (name-prefix
   scoring + a libc→header map), inserts the include, rebuilds strict and
   reports the remainder. Implicit declarations are mechanical; type
   mismatches and symbols with NO declaring header are listed for manual
   fixing. A file that calls 200 subsystem functions legitimately includes
   200 owners — that is minimal-includes done right, not a god header.
3. **Ratchet it.** `make kernel-strict` is the gate; CI runs it as a
   permanent step so the class cannot regress. Record the measured count
   (e.g. 214 -> 0) in the ledger, not just "fixed warnings".

Manual-fix classes the waves surface:

- **Prototype-scope struct tags.** A struct tag FIRST named inside a
  function-pointer prototype's parameter list is scoped to that prototype
  — a DIFFERENT type from the file-scope definition that follows. Newer
  gcc errors at the call site with a note showing both types looking
  identical (`expected 'struct X *' but argument is 'X_t *' {aka 'struct X *'}`).
  Forward-declare the tag at file scope before the typedef that uses it.
- **Linker symbols are arrays.** `extern char _bss_start[];` zeroed via a
  word pointer needs decay + explicit cast — `(uint64_t *)_bss_start`,
  not `&_bss_start` (that is `char (*)[]`).
- **A .c cannot include a header that re-defines what the .c owns.** When
  a header duplicates the .c's structs/inlines, including it "just for the
  declaration" detonates redefinitions. Forward-declare the one symbol
  whose definition order is wrong, and record the duplicate-owner merge
  as its own batch.
- **Include-guard collisions.** Two different headers sharing one guard
  macro: whichever is included second is SILENTLY SKIPPED. A metric macro
  sharing a guard name is the same trap. Guard names are layer-qualified
  (WUBU_KERNEL_*, WUBU_APP_*, *_IMPL_H); the census's dup-define CONFLICT
  list surfaces these — rename both sides, never just one.

## Auditing protection code that nothing runs (dead guards)

A guard written and never called is worse than no guard: it reads as protection.
This class is real -- a heap canary checker existed with no caller on any
allocator path, so an overflow was silently absorbed by `free()`.

Grep cannot find it. The checker DOES have a caller (`mem_check_redzones`) which
itself has no caller. So build the real call graph:

```bash
python3 tools/dead_guard_scan.py            # whole src tree, probe-named hits
python3 tools/dead_guard_scan.py --all-names  # every uncalled function
```

It walks `src/**.c`, EXCLUDES each function's own signature from its call count,
and reports functions whose name suggests a check that nothing reaches.

**Exclude definition spans or the scan counts every function as its own caller**
-- the first version of this tool returned an impossible "zero dead guards"
because a definition line contains its own name followed by `(`. Verify the tool
against a function you KNOW is uncalled before trusting any result.

### Four mechanisms make live code look dead -- check before deleting
1. **Dispatch tables.** `tbl[5-1] = handler;` has no textual `name(` call site.
2. **Parity `#define`s.** An alias maps a TempleOS name onto ours, so the real
   name is never written at the call site.
3. **Cross-repo API.** Another repo links these objects.
4. **Callbacks passed as arguments**, registered rather than invoked by name.

The deliverable is TRIAGE, not deletion: read each hit, classify it, and write
down the verdict (real defect / live-through-a-table / optional utility with no
caller). Leave the optional utilities DOCUMENTED with why they are not defects --
leaving them unexplained invites someone to "fix" them blindly. A repo-wide
report belongs in `docs/`, and new guard code should state in its commit body
which of the two wiring routes it took.

## Workflow, one module at a time

Never attempt the whole baseline in one pass.

1. **Measure.** Run the audit; read the specific offender it names first.
2. **Pick ONE offender** and decide which rule it breaks.
3. **Refactor/split** along the concern boundary -- a `_name.c` leaf plus a
   public `.h`, never a bigger file.
4. **Add or extend a gate** that would have caught the defect. If a bug was
   found by hand, the gate is the other half of the fix.
5. **Re-run the audit**; regenerate the baseline only if the count dropped.
6. **Commit and push**, with the measurement in the message.

## Rules in one line each

Owners are named in `docs/STANDARDS_AND_WORKFLOW.md` -- change the rule there,
not in five places.

- **C11, opaque structs, minimal includes.** No function bodies in headers.
- **One concern per file, ~500 lines.** Measured budget 600.
- **No god headers.** More than 40 includes means no boundaries.
- **Fail closed.** Every refusal returns -1/false/NULL and leaves the caller's
  buffer untouched; a partial write is worse than none.
- **One owner per concern.** Search before writing something that smells like a
  copy. Existing reuse points: `apps/guest_file.h`, `gui/wubu_runline.c`,
  `wubu_mime_desktop.c::parse_desktop_file`, `gui/wubu_tokens.h`,
  `kernel/wubu_thermal_read.c`. For CONSTANTS specifically, the front door is
  `docs/CONSTANTS.md` (decision tree + per-layer owner map); shared format facts
  (magics, register offsets, PCI IDs) live in `include/wubu_*_fmt.h`-style
  headers included by every layer, never re-defined per consumer.
- **Geometry comes from `src/gui/wubu_tokens.h`** and nowhere else, in the
  desktop-drawing surfaces.
- **Comments explain WHY.** Never narrate WHAT.
- **Behaviour gates, not assert-nothing tests.**
- **Weak glue for optional modules** so headless tests link without the world.

## Pitfalls

- **Accepting data and then discarding it while returning SUCCESS is a recurring
  shape -- grep for it deliberately.** Three instances in one tree: a parser
  incremented no counter so every `[Desktop Action ...]` overwrote slot 0 and the
  field writer computed index -1 and wrote nothing; a file-add copied
  `min(len, capacity)` bytes and returned success, so a large save came back "ok"
  holding a shortened file; a section's `Name=` overwrote its id and the id was
  never checked for survival. Each one is invisible to a happy-path test because
  the error path IS the bug. Add a hostile-input gate per parser: oversized
  fields, missing terminators, more entries than the cap, embedded NULs, orphan
  headers -- each case forked under `alarm(1)` so a hang fails instead of
  stalling the suite.
- **A setting written to one store and applied through another is two sources of
  truth.** Persist through the settings object AND apply the setter in the same
  step; a signature/sentinel written before the change is real becomes a claim
  that is false.
- **A tree-wide "no numeric literal" rule produces thousands of false hits**
  -- enum values, colour channels, generated Wayland protocol constants. That
  noise teaches people to ignore the tool. Scope the rule to the surfaces where
  it actually applies, and filter on coordinate-ish neighbours. Narrow beats
  comprehensive for a standing gate.
- **Write the baseline AFTER finalising the rules, not before.** A baseline
  taken first records the wrong frontier and the ratchet then rejects the
  improvement it was meant to measure.
- **An anchor string that appears in several test recipes double-inserts when
  replaced globally** -- including into the recipe you already patched, giving
  `multiple definition` at link. After patching, `grep -c <inserted token>
  mk/tests.mk` and expect exactly the number of targets that needed it. Dedupe
  before building.
- **Enumerate every recipe that lists the SOURCE FILE before editing anything.**
  `grep -n '<module>\.c' mk/tests.mk` IS the complete affected-target list. Fix
  them all in one pass: discovering them one failed build at a time leaves a
  DIFFERENT gate red on each successive commit, and "I added the stub" is not
  evidence that the stub reaches the recipes that actually need it.
- **Anchor on the whole target line, and never append after a line ending in
  `\`.** A prefix match (`startswith("test_apps:")`) also hits the longer target
  sharing that prefix (`test_apps_weak:`); a replace aimed at a recipe line
  ending in `\` lands on the CONTINUATION, which is another variable or the next
  recipe's command -- it builds clean and changes nothing. Prefer the `patch`
  tool with an exact unique string over a scripted replace, and print the recipe
  body (awk from the target line to the first line not beginning with TAB)
  before trusting the edit.
- **A product build is NOT a gate.** `make hosted` succeeding while
  `mk/tests.mk` recipes fail to link is the normal outcome of adding a symbol to
  a module the WM links: those recipes are separate and must be fixed in the
  same commit. Run the affected gate before pushing, not after.
- **Every target that links an application must link its new dependencies.**
  Giving an app a real dependency breaks each test recipe that compiles the app
  directly, even though the product builds clean.
- **New test files under `src/` are gitignored** (`src/*/test_*`). `git add -f`
  them and say so in the commit body.
- **A `*/` sequence inside a comment closes it early.** Writing
  `/sys/class/thermal/thermal_zone*/type` inside a block comment terminates the
  comment at `zone*`, and the compiler reports the damage dozens of lines later
  as stray tokens. Write `thermal_zoneN/type`. Check any comment containing a
  glob or a path with a wildcard.
- **A module compiling under one flag set is not evidence its includes are
  correct.** Several VSL files used `statvfs`/`timerfd` via transitive includes
  and broke only when another target's feature-test flags applied. Include what
  the TU uses.
- **Exclude GENERATED code before measuring — trees AND files.** CMake writes
  probe sources under `build*/CMakeFiles/**/CompilerIdC/*.c`, and those dominated
  the line budget (881 lines each) until `build*` directories were pruned from the
  walk. Within the tree, wayland-scanner bindings (`protocols/*-protocol.c`) carry
  `Generated by wayland-scanner` / `DO NOT EDIT` in their first lines — skip files
  whose head marks them generated, or their private ladders read as conflicts.
  A metric that counts artifacts alongside source measures the build, not the
  code.
- **Inner double quotes inside a shell-heredoc C string get escaped on the way
  in.** Writing a test message like `"/" maps exactly"` through
  `python3 - <<'PY'` produced `"\""` in the file: the compiler sees an unescaped
  string boundary, reports `invalid operands to binary /`, and points at a line
  that looks correct. When a patch script must emit C string literals, either
  word the message with no embedded quotes (`guest slash maps exactly onto the
  root`) or patch the offending lines by INDEX rather than by matching the quoted
  text. If a build fails on a line you just wrote via heredoc, read the file back
  before editing the logic.
- **A ratchet compared against a LIVE external value must BRACKET, not match once.**
  Read the oracle twice around the call under test and require the result to sit
  inside the two samples (+/- slack). One-sample-vs-one-sample is a race: a CPU
  moves several degrees between reads, so the identical test fails
  intermittently and the tempting fix -- loosening the tolerance -- turns a real
  gate into noise. Bracketing still catches a wrong sensor or a mis-scaled unit.
- **Removing the CAUSE of a rendering bug obliges removing the WORKAROUND drawn to hide it.** A hand-drawn vector underlay existed beneath a bitmap sprite whose white fur was encoded transparent; its own comment said so. Once alpha was baked correctly the underlay became a DOUBLE DRAW -- limbs at hardcoded coordinates sticking out from under a complete sprite, identically for every pose. Read the comments around any "solid body under X" helper before trusting it; fixing the encoder is only half the job.
- **Dead code hides in pairs: a static function plus the struct field that feeds it.** `draw_eye_open()` had no caller, and the four-stage blink computation filling `BonziAnim.eye_open` had no reader either -- both ran every frame. Use `tools/dead_guard_scan.py --all-names` for uncalled statics AND grep each anim/state struct field for a reader; a field written but never read means its whole producer chain is dead.
