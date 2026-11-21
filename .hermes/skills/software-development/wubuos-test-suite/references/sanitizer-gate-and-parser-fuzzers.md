# The sanitizer gate and parser fuzzers

## `make test_sanitize` — a separate gate, not a variant of `make test`

Hostile-input sweeps fork with `alarm(1)` and assert "the process did not die". A
sanitizer asserts something stronger: no out-of-bounds access, no signed overflow, no
undefined behaviour. Different claims; only the first is covered by the normal suite.
`mk/sanitize.mk` builds a fixed set of input-handling surfaces FRESH under
`-fsanitize=address,undefined -fno-sanitize-recover=all` and runs them (the
`.desktop`/MIME parser, revolver env parsing, the guest FS image loader, its mutation
fuzzer, and the NT syscall sweep).

Typical options (already set in the makefile):
`ASAN_OPTIONS=detect_leaks=0:abort_on_error=0:exitcode=97:halt_on_error=1` and
`UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1`.

Run it after touching any parser, loader, dispatch table or wire-format reader — not
only when you suspect a bug. It earned its keep on the first run.

## Implicit declarations are the sanitizer gate's favourite find

A call to a function with no visible prototype is undefined behaviour in C99+. GCC
still compiles it (with a warning), assumes an `int` return, and the caller reads the
real return type from whatever occupies the return slot. The observable effect is a
test whose PASS depends on stack layout and optimisation level: green at `-O0`,
failing under `-O1` + ASan.

- **Diagnostic order:** when a check passes normally and fails ONLY under the
  sanitized build, look for a MISSING PROTOTYPE first. Do not start with uninitialised
  memory or heap overflow — this defect needs no bad index, only a missing `#include`
  of the header that declares the function.
- Put `-Werror=implicit-function-declaration` in the sanitized build's flags. It converts
  the class into a compile error at exactly the moment it matters, and it catches your
  own new code too.
- Common triggers: a helper defined above its `#include`s; an include lost during a
  refactor; a test that includes the public header but calls a function declared in the
  internal one.

## Do not split a target out of the gate for a cost you have not measured

A sweep that forks per item looks expensive and invites someone to carve it into a
optional second command. MEASURE first: the NT slot sweep (512 forks) runs in ~0.7s
under ASan. Splitting it would save nothing and hide the most valuable target behind a
command nobody remembers to run. Record the measurement next to the target.

## Deterministic mutation fuzzers

`make test_fs_persist_fuzz` (plain build) and its sanitized twin inside
`test_sanitize` are the reference implementation.

Shape that worked:
- **Seed from argv** (`splitmix64`, never `rand()`), so a finding is reproducible
  instead of an anecdote.
- `build_valid()` produces one well-formed input with the real wire format; mutations
  are bit flips, truncation, extreme length-field values, mid-record cuts, byte deletes.
- **Assert invariants, not just survival.** For the WUBFS01 loader: the return value is
  always `-1` or a non-negative count bounded by the runtime ceiling (a wild number
  means a caller trusts an unvalidated length field), and a corrupted magic byte MUST
  be refused (if that stops holding, nothing downstream matters). "No crash" is what
  ASan adds; the invariants are what make the fuzzer worth wiring into the gate.
- **Never touch the user's real data.** Point the module's env override at `/tmp` with a
  per-PID filename, `unlink` before and after. This is the same rule the test-isolation
  section states for suite storage paths; a fuzzer writes thousands of files, so the
  leak surface is thousands of times larger.
- A fuzzer is a smoke screen against obvious memory faults, not coverage-guided
  verification. Do not describe it as proving correctness.

## Four fuzzers now ship; two found real defects

`make test_<surface>_fuzz` (plain) and the same binary rebuilt under ASan/UBSan inside
`test_sanitize`: guest FS image (`WUBFS01`), `.desktop`/MIME, `.spell` module container,
and JSON. Two of the four found memory-safety defects on their first run, so treat a
green fuzzer as a reason to add another parser, not as evidence the approach is spent.

**Share the PRNG, never copy it.** `src/tools/fuzz_rng.h` holds splitmix64 +
`fuzz_rng_seed/next/below` as header-only inline functions. A second fuzzer that rolls
its own generator produces a DIFFERENT sequence for the same seed, so "seed 7" stops
meaning the same thing across targets -- and the moment somebody improves one copy the
reproducibility contract is gone. Verify the swap is safe: after switching a fuzzer to
the shared header, the per-seed result counts must be identical (they were: 3454
refused / 546 loaded before and after).

## A cap on NODE/ELEMENT COUNT does not bound per-node BYTE LENGTH

`json_parse_number()` copied its literal into `char buf[64]` with no length check:

```c
char buf[64];
memcpy(buf, start, len);      /* len comes straight off the input */
t->int_value = atoi(buf);
```

`JSON_MAX_TOKENS` limits how many NODES a document may contain, not how many BYTES one
literal may use -- ten thousand digits still cost exactly one token, so the arena cap
protects nothing. The plain build aborts with glibc's `*** buffer overflow detected ***`
(stack protector); the fix clamps the copy, which is not a semantic loss because the
value only ever fed `atoi()`.

Rule: when a parser enforces a token/element cap, audit every fixed-size destination
for a PER-ELEMENT length the cap does not bound. A node cap bounds structure; it says
nothing about payload.

## Validation split between parse-time and lookup-time leaves a hole

`wubu_spellmod_open()` accepted images whose export table pointed outside the code blob.
`wubu_spellmod_export()` already re-validated bounds before handing back an offset -- but
only when `code_len > 0`. An image declaring NO code skipped the check entirely, so an
export could claim any offset/size for a blob that does not exist: the exact case the
header's failure policy calls "jumping into an address that does not exist". 1853 of
4000 mutated images were accepted before the fix; the correct behaviour is to refuse the
image in `open()`, unconditionally, and keep the lookup check as defence in depth.

Rule: if a module's header states an integrity promise ("a module that lies about its
own layout must never be half-accepted"), enforce it in the OPEN/PARSE path. A
CONDITIONAL lookup-time check is worse than none -- it reads as protection while leaving
the hole open for whichever caller skips it.

## A parser returning pointers into a global arena: free before you reset

`json_parse_value()` returns `JsonToken *` pointing INTO `g_json_tokens`. Any test or
fuzzer that keeps two trees alive, or calls the arena reset while a tree exists, holds
freed memory. The symptom is a heap-use-after-free reported inside the CHECKER -- it
reads like a parser bug and sends you debugging the wrong file.

- Free each tree BEFORE the next parse or arena reset.
- To compare two parses, use a parse-and-DISCARD probe (return only a bool verdict)
  instead of holding two live trees. Two live trees from a shared-arena parser are not
  possible by construction.
- Same trap for anything returning a borrowed pointer: document the lifetime in the
  header next to the function, because the borrow is invisible at the call site.

## Wiring a new target into `test_sanitize`: the prerequisite expands at PARSE time

Symptom: after adding a fuzz target, the first gate run dies with
`/bin/sh: <binary>: not found`; building the binary by hand makes the next run pass, so
it reads as a flake and gets "fixed" by retrying.

Root cause: GNU make expands a rule's PREREQUISITE LIST when it READS the rule, not when
it runs it. `FS_PERSIST_FUZZ_SAN = $(HOSTED)/fs_persist_fuzz.san` was defined further
down `sanitize.mk`, so `$(FS_PERSIST_FUZZ_SAN)` in the prerequisite line expanded to the
EMPTY STRING and the prerequisite was silently dropped -- while the recipe body,
expanded later, produced the correct path and executed a binary that had never been
built. Targets named literally (`$(GUI)/mime_contract_test.san`) were unaffected, which
is why it looked intermittent.

- Define any variable used in a rule's prerequisite list ABOVE that rule.
- Inspect what make actually parsed: `make -qp | grep '^test_sanitize:'`. If your
  target is absent from that list, it will never be built as a prerequisite.
- Verify the wiring properly: delete the artifact, run the gate, confirm rc=0 -- not
  "run it twice and hope".

This is the same family as an object named only in a link recipe (see the
`wubuos-build-integrity` skill): a dependency that is present in the file but absent
from the graph, invisible to incremental builds and fatal on a clean one.

## A regression test you have not seen FAIL proves nothing

When a fix lands for a defect a fuzzer or gate found, the accompanying regression test
is evidence only if it FAILS against the unfixed code. Otherwise it may assert a
property the code already satisfied, or something too weak to notice the real bug.

Procedure -- prove it by reverting, not by reasoning:

```bash
cp <file> /tmp/<file>.fixed.c
# re-apply the OLD implementation body (whole function, not a fragment)
timeout 400 make <target> > /tmp/t_old.log 2>&1; echo "OLD rc=$?"
grep -E 'FAIL|error:' /tmp/t_old.log | head
cp /tmp/<file>.fixed.c <file>
timeout 400 make <target> > /tmp/t_new.log 2>&1; echo "FIXED rc=$?"
```

Two traps this procedure exposes:

- **A partial revert does not compile, and its non-zero exit proves nothing.** Replacing
  only the body while leaving a reference to the new variable yields
  `'tmpl' undeclared`, which looks like a failing old build but says nothing about the
  test. Replace the WHOLE function, then confirm the failure line is the ASSERTION you
  intended (`FAIL: <the message>`), not a compiler diagnostic.
- **Weak assertions pass on broken data.** `TEST(w->w > 0)` accepted resolutions read from
  what turned out to be XRandR mode IDS rather than pixel widths. Assert against a
  value an independent oracle reports (`xrandr -q` text, a golden vector), never just
  "non-zero" / "non-NULL" for a quantity whose real range you know.

Same principle when choosing the ORACLE: parse the CLI tool's TEXT output instead of
calling the same library again -- an oracle that shares the module's code path can
agree with it against a shared bug, which reads as a pass.

## Borrowed-pointer APIs: one buffer per handle, and never return a lone static

Two separate traps, both of which produce silently wrong results rather than crashes:

**A shared scratch buffer makes every handle alias the last-built object.** Parsers
that BORROW their input (common deliberately: copying a large image costs more than
living with the caller's lifetime) are safe in production and dangerous in tests. If
eight test modules are built into ONE `static uint8_t buf[512]`, all eight handles
point at whichever image was constructed last -- every assertion then validates the
same object, and the suite goes green because each individual check is self-consistent.
Fix: hand each handle its own slot from a fixed pool, and state the borrow rule in the
module header next to the open function.

**A helper returning a pointer to a single static makes comparisons compare an
argument against ITSELF.** `strcmp(mod_name(a), mod_name(b))` where `mod_name()` fills
one shared buffer evaluates both arguments before `strcmp` runs, so both operands are
the same pointer holding the SECOND value -- every comparison reports equality. In a
registry this silently turns every distinct module into a duplicate of the previous one.
Fix: take a caller-supplied buffer (`int mod_name(const T*, char *out, size_t)`), or
copy into two locals before comparing.

Detection for both: a test that passes while the code under test contradicts itself,
or where reordering construction changes the result. If a fixture's outcome depends on
the ORDER objects were built in, look for a shared buffer before suspecting the logic.
