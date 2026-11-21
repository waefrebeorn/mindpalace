# Objects named only in a link recipe are never built

## Symptom

`make clean && make` fails:

```
/usr/bin/ld: cannot find src/compiler/wubu_tgemm_avx512.o: No such file or directory
/usr/bin/ld: cannot find src/apps/edr_dash.o: No such file or directory
/usr/bin/ld: cannot find src/runtime/wubu_holyd_agi.o: No such file or directory
/usr/bin/ld: cannot find src/runtime/wubu_holyd_lifecycle.o: No such file or directory
make: *** [mk/targets.mk:144: hosted] Error 1
```

## Mechanism

Make only builds a target that appears in a prerequisite list. An object spelled out
inside a *recipe* (the link command) is not a prerequisite -- it is just an argument
to the compiler invocation. If it is also absent from the target's prerequisite
line, nothing ever creates it.

This stays invisible indefinitely because **incremental builds work**: stale `.o`
files from an earlier configuration satisfy the linker, so `make` never tries to
build them and the missing rule is never exercised.

## Rule

An object referenced anywhere in a target's recipe must ALSO be named in that
target's prerequisite list. When auditing a link line, treat every token ending in
`.o` as something make ought to be able to build, and grep the prerequisite line for
it.

Fix shape (this repo):

```make
HOSTED_LINK_ONLY = $(COMP)/wubu_tgemm_avx512.o $(APPS)/edr_dash.o \
                   $(RT)/wubu_holyd_agi.o $(RT)/wubu_holyd_lifecycle.o
hosted: ... $(COMP_OBJS) $(JIT_SRCS) $(HOSTED_LINK_ONLY)
```

## Verify with a CLEAN build, not an incremental one

Any time a Makefile dependency is touched, or a link fails with "cannot find
<object>", run:

```bash
make clean && make -k -j24     # exit 0 expected; a few minutes on this box
```

If you only ever build incrementally you cannot tell whether the tree builds.
Incremental success after a Makefile change proves nothing about prerequisites.

## Related trap, opposite direction

Adding an object to prerequisites but forgetting it in the recipe leaves make
rebuilding it pointlessly while the link still misses it. Check both directions
after editing a link line.
