# Implicit declarations and include-guard collisions

## The class of bug

Calling a function with no visible prototype is **undefined behaviour** in C99+.
The compiler assumes an `int` return and the real value is recovered from whatever
is in the register/stack slot -- so the program is reading garbage, and *whether it
looks correct depends on stack layout and optimization level*.

Observed shape: a test asserted that an empty input parses as "not valid" and
passed at `-O0`, then failed under ASan/`-O1`. Nothing in the source had changed;
the parsed verdict was coming from an uninitialized return path because the callee's
prototype lived in a header the caller never included.

## Rule

Every call must have a visible prototype. A warning of the form
`-Wimplicit-function-declaration` (or gcc's "incompatible implicit declaration of
built-in function") is a correctness defect, not noise -- fix it by including the
header that declares the function, never by casting or ignoring it.

Common fixes:
- project functions -> the internal/public header that owns them;
- `snprintf`/`strlen`/`memmove` -> `<stdio.h>` / `<string.h>`;
- `strncasecmp` -> `<strings.h>` (NOT `<string.h>`);
- `fanotify_init`/`fanotify_mark` -> `#define _GNU_SOURCE` BEFORE any include,
  plus `<sys/fanotify.h>`.

## Enumerating them

A normal incremental build shows nothing once the tree compiles, because these are
warnings. Run a **clean** build and scan its log:

```bash
make clean && make -k -j24 > /tmp/build.log 2>&1
grep -B1 'implicit declaration of function' /tmp/build.log | grep -E '^src/' | sort -u
```

Pitfall when counting: `grep -c 'implicit-function-declaration' build.log` also
matches the *flag text* inside recipe command lines (e.g.
`-Wno-implicit-function-declaration`), inflating the count ~30x. Grep for the full
warning phrase `implicit declaration of function` instead, and pair it with the
preceding file line.

Prefer a whole-tree sweep to whack-a-mole: after fixing one, rerun the clean build
until the list is empty.

Measure before restructuring the gate around a target. A fork-per-input sweep looks
expensive under ASan and is not -- timing it (~1s) is the difference between one gate
and a second command somebody has to remember to run. Record the measurement next to
the target so nobody re-splits it on a guess.

## Gate it

Add `-Werror=implicit-function-declaration` to sanitizer builds (this repo:
`mk/sanitize.mk`). Sanitizer builds recompile everything fresh, so they see warnings
incremental builds never surface -- that is exactly why the gate caught this while
the ordinary build stayed green for months.

## Include-guard collisions hide APIs

Two headers using the SAME include guard macro silently shadow each other: whichever
is included first wins, and the second contributes nothing at all. Symptoms appear
far away as "implicit declaration" for something that IS declared -- just not in a
header the TU actually saw.

Verify by preprocessing and counting occurrences of the symbol:

```bash
gcc -E <tu.c> <the-include-flags> | grep -c '<symbol>'
```

Declaration + call = 2 occurrences. Only the call surviving means the declaration
was hidden by a guard collision.

**Renaming the guards alone changes the failure, it does not end it.** With unique
guards any TU that reaches both headers fails with `redeclaration of enumerator` /
`conflicting types`. Read that error to tell two very different situations apart:

- **Duplicate API.** Both headers declare the *same* signatures for the *same*
  functions. Consolidating is a design decision over duplicated state and belongs
  in its own pass; document owners, the evidence trail, and what conflicts rather
  than leaving the build broken or hiding the collision again.
- **ABI collision.** The same names carry *different* prototypes
  (`int f(void)` against `int f(struct s *)`). These are two DIFFERENT APIs that were
  handed one name. They cannot be merged by picking a winner -- each needs its own
  namespace -- and until renamed, every call site binds to whichever definition the
  linker chose, passing arguments the callee will misread. A `void` call reaching a
  pointer-taking callee dereferences whatever happened to sit in the argument
  register; that is a memory-safety fault, not a style problem.

**`-Wl,--allow-multiple-definition` hides the second case completely.** With that
flag the link does not error on duplicate global symbols: the first object in link
order wins and every later definition is discarded silently. Whichever object list
the recipe puts first therefore decides behaviour -- a statement about the recipe,
not about intent, and one nobody wrote down. Two implementations linked into one
binary under that flag can be calling across each other's private state with no
diagnostic at all.

Find the collisions without changing behaviour:

```bash
# symbols defined by BOTH object sets
comm -12 <(nm --defined-only -g <setA>/*.o | awk '{print $3}' | sort -u) \
         <(nm --defined-only -g <setB>/*.o | awk '{print $3}' | sort -u)

# any symbol defined more than once anywhere
nm --defined-only -g <objs> | awk '{print $3}' | sort | uniq -d
```

Then compare each hit's prototype in the declaring headers BEFORE touching anything:
identical signatures mean duplicate code, differing signatures mean ABI collision.
The fix for the latter is a namespace split -- rename declaration AND every caller,
then confirm the symbol no longer appears in both object sets. Verifying with tests
alone is not enough when the two bodies differ: the renamed-to side may never have
executed in production before.

Scan for first-party duplicates with a short walk over `src/**/*.h` comparing each
file's leading `#ifndef`/`#define` pair; ignore vendored trees (SDL, Lua), whose
per-copy guards are intentional.

## Related

Same family: a struct whose header does not carry `egojar.h` produces layout
mismatch between TUs (see SKILL.md); a `static` forward-declared-after-use gives
"static declaration follows non-static". All three are "the compiler cannot see the
real shape" defects, and all three pass tests until stack layout or link order
changes.
