# Link-line defects that incremental builds hide

Two failure shapes with the same symptom (a build that only breaks from clean) and
the same reason they survive: stale artifacts from an earlier configuration.

## 1. An object named only in a recipe is never built

A make rule is `target: prerequisites` followed by TAB-prefixed recipe lines. Only
things on the prerequisite line enter the dependency graph; make knows how to build
a target only if it appears there or matches a pattern rule reachable FROM there. An
object that appears solely inside the link command on a recipe line is therefore never
compiled.

- Symptom: `make clean && make` dies with `cannot find src/.../foo.o: No such file or
  directory` / `ld returned 1 exit status`, while a plain `make` succeeds.
- Cause of the illusion: leftover `.o` files from an earlier build (or an earlier
  version of the recipe) sit on disk and satisfy the link line. Every normal
  incremental workflow stays green.
- Fix: add the object to the target's prerequisite list beside the other object-set
  variables. Then verify with `make clean && make -k -j24` — never with `make`.
- Audit trigger: a target whose recipe lists objects its prerequisite line does not.
  If a link succeeds only because of files older than the source that defines them,
  this is the defect.

## 2. Duplicate global symbols resolved silently by link order

`-Wl,--allow-multiple-definition` makes duplicate definitions link without an error:
the linker keeps whichever object comes first and discards the rest. Nothing warns.

Find the collisions between two sets of objects:

```bash
comm -12 <(nm --defined-only -g A/*.o | awk '{print $3}' | sort -u) \
         <(nm --defined-only -g B/*.o | awk '{print $3}' | sort -u)
```

Check the LINK ORDER in the recipe (e.g. `$(RT_OBJS) $(GUI_OBJS)`): the earlier set
wins. That is the definition every call site reaches.

**If the colliding functions have different prototypes, this is an ABI hazard, not
just duplication.** A caller compiled against the other header passes arguments the
winner does not expect — a `void f(void)` call reaching `int f(struct x *)` hands the
callee a garbage pointer that it dereferences. Before treating a collision as harmless
copy-paste, print both declarations side by side and compare every parameter type.

Fix shape when the two are genuinely DIFFERENT APIs given the same names: give one
side its own namespace (rename declaration + definitions + every caller on that side,
leaving the other untouched). Do NOT merge them by picking a winner — the bodies may
carry incompatible state machines.

Renaming can expose further conflicts: translation units that reach both internal
headers now fail to compile. If the entanglement is wide, revert the rename, keep the
build green, and record the collision with evidence (declarations, callers, the link
order that decides the winner) so consolidation becomes a deliberate pass rather than
a half-applied one.

Removing `--allow-multiple-definition` outright is NOT the fix: it papers over
unknown legitimate cases, and flipping it blind breaks whatever they are. Measure the
blast radius first with the `comm` command over the whole link set.

## 3. Two headers sharing one include guard hide each other

If two headers use the same `#ifndef`/`#define` pair, whichever is included first
defines the guard and the second body vanishes entirely — every declaration in it
becomes invisible, which surfaces downstream as implicit declarations.

Prove it by preprocessing and counting occurrences of the missing symbol:

```bash
gcc -E <tu.c> | grep -c '<symbol>'   # 1 = only the call survived; the declaration is hidden
```

Give each header a guard derived from its path (`<DIR>_<FILE>_H`) so collisions cannot
recur. Distinct guards alone do NOT fix an ABI collision — they only make it visible
(see section 2).
