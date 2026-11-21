# Makefile prerequisite and link-line traps (WuBuOS mk/*.mk)

Three failure shapes that only appear when the tree is built CLEAN or from a cold
checkout, so an incremental loop hides them indefinitely. All three were found by doing
something the repo had stopped doing.

## 1. Objects named in the LINK RECIPE but never in the prerequisite list

A recipe can name `$(FOO)/bar.o` in its compile/link command while the target's
prerequisite list does not. Incremental builds succeed because a stale `.o` from an
earlier configuration is still on disk; `make clean && make` fails with
"cannot find ... No such file or directory".

**Rule:** every object that appears in a recipe must also appear in the target's
prerequisite list, even if a pattern rule can build it. Add it explicitly:

```make
HOSTED_LINK_ONLY = $(COMP)/wubu_tgemm_avx512.o $(APPS)/edr_dash.o \
                   $(RT)/wubu_holyd_agi.o $(RT)/wubu_holyd_lifecycle.o
hosted: $(HOSTED)/hosted.c ... $(JIT_SRCS) $(HOSTED_LINK_ONLY)
```

**Detect:** `make clean && make -k -j24`, then confirm exit 0. A "green" tree that has
never been cleaned proves nothing.

## 2. GNU make expands a rule's PREREQUISITE LIST at PARSE TIME

A target named only through a variable is silently DROPPED if the variable is defined
further down the .mk file:

```make
# WRONG -- FS_FUZZ_SAN is empty at parse time, so the prerequisite vanishes
thing: $(FS_FUZZ_SAN)
...
FS_FUZZ_SAN = path/to/x.san     # defined too late
```

The recipe line still expands correctly later (recipes expand at execution time), so the
run executes a path that was never built: `sh: x.san: not found`, then PASSES on retry
after anything else happens to build the artifact. It reads like a flake and is not one.

**Rule:** define any variable used in a prerequisite list ABOVE the rule that lists it,
with a comment saying why.

**Detect:** `make -qp 2>/dev/null | grep '^<target>:'` prints the parsed prerequisite
list. If a target you added is missing from it, the variable expanded to nothing.
This is the one command that turns this class of bug from mysterious to obvious.

## 3. Test recipes referencing a `.o` that nothing builds

A recipe may pass `foo.o` while only `foo.c` exists and no rule produces the `.o`.
Incremental runs survive on the leftover object; a clean build dies with
`cannot find foo.o`. Prefer compiling the source directly in test recipes, matching the
every-other-recipe convention in this repo:

```make
$(CC) ... $(RT)/wubu_guest_root.c $(RT)/wubu_spell_resolve_test.c -o ...
```

**Detect:** same as (1) -- clean build.

## General rule

Run `make clean && make -k -j24` before declaring the tree green after ANY change to
`mk/targets.mk`, `mk/tests.mk`, or a recipe. Incremental success is not evidence; these
three traps all live precisely in the delta between incremental and clean.
