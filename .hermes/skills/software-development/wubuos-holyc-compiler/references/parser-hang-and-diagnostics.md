# Parser hangs, recursion crashes, and diagnostic classification

Measured on the wubunos (HolyD) front end, October 2026.

## The loop that ate 541 files

`hd_parse_decl`'s K&R parameter list:

```c
while (peek(p) != HD_TOK_LBRACE && peek(p) != HD_TOK_EOF) {
    HDType *dt = parse_type(p);   /* consumes NOTHING on '}' */
```

`parse_type` returns a default I64 without advancing on a brace, so the loop ran
forever, allocating one `HDType` per pass. That is why it looked slow rather than
hot: the time went into `calloc`.

Fixes that matter, in order of generality:

1. Progress guard on every `parse_type` loop (struct members, K&R lists, unit
   loop): record `pos`, call, and if `pos` is unchanged report and `advance`.
2. Stop loops at `HD_TOK_RBRACE` as well as `LBRACE`/`EOF`.
3. `advance()` forces `HD_TOK_EOF` when the lexer position does not move, so no
   loop that advances can spin.

## Getting a backtrace when attach is blocked

`gdb -p` fails with "Inappropriate ioctl for device" under `ptrace_scope=1`. Run
under gdb and interrupt from a timer thread:

```python
# timer.py
import threading, time, gdb
def stopper():
    time.sleep(3)
    gdb.post_event(lambda: gdb.execute("interrupt"))
threading.Thread(target=stopper, daemon=True).start()
```

```
gdb -batch -x timer.py -ex run -ex 'bt 12' --args ./cdiag repro.c
```

For a suspect loop add a liveness probe in `peek()`: count calls, and after a
threshold print `p->lex->pos`, `tok.type`, `tok.text` and
`__builtin_return_address(0)`, then `exit(9)`. Build with `-O0 -g -no-pie` and
resolve the caller with `addr2line -f -e ./cdiag 0x...`.

## SEGV that is really recursion

`parse_type` had no `HD_KW_I0` (`void`) case, so the switch fell through with the
default I64 and the new multi-word fold called `parse_type` again on the same
keyword — forever, until the stack died. Guards:

- handle the missing case (`void` -> HD_TYPE_VOID, size 0);
- only fold when the switch consumed something: capture `entry_pos` at function
  entry and require `p->lex->pos != entry_pos` before recursing.

A 256 KB stack makes recursion crash immediately, which distinguishes it from a
loop in one experiment (`ulimit -s 256`).

## Diagnostic classification that actually helps

- Always include the offending token text. `expected token 85, got 80` says
  nothing; `expected token 85, got 80 ('{')` names the bug.
- Classify the **first** diagnostic per file: later ones are fallout.
- Preprocess before parsing in any diagnostic tool. Raw text makes every
  `#include` a phantom error.
- `HD_DIAG=1` on the gauntlet prints `diag <test>: <messages>` per build failure,
  but writes a ~2 GB log. Send it to scratch and delete it after counting.
- Fix, then **reclassify**: several samples from an earlier snapshot parsed with 0
  errors after the guard fixes, so a stale census sends you after already-fixed
  bugs.
- **A queued/background result is only evidence if its binary postdates the last
  fix.** Compare the binary mtime with `git log -1 --format=%cd` before acting on
  any captured count; long autonomous runs keep delivering results built before
  the fix that invalidated them, and acting on one costs a full debugging cycle.

## Reduction discipline: bisect the FILE, not the line

When a failing line parses clean in isolation, the defect is context, not the
line. Every reduction "passing" is the signal to change axis:

1. Capture the exact source the harness ran (`HD_DIAG=2` → `/tmp/failcases/<name>.c`).
   Extracting a test by name from a suite array repeatedly produced text that did
   not match what executed, and an hour goes into a construct the harness never saw.
2. Get the text the builder really parses (`HD_DUMP_BUILD=<path>`), never the raw
   file — diagnostic line numbers are preprocessed line numbers.
3. Delete earlier top-level items one at a time and re-parse. `head -n N` on the
   preprocessed text works only while the cut lands on a complete construct: a cut
   mid-statement yields errors that look like findings.
4. Only then reduce the construct.

Two real defects were found this way after the line itself had parsed clean in
five variants: K&R parameter detection firing on a typedef name, and designators
that were paths (`.f.a`) but were consumed as one component.

## Reading a failure signature before reading code

| message | usual mechanism |
|---|---|
| `expected ')' got <ident>` at a parameter name | old-style (K&R) parameter detection accepted an identifier that is a typedef |
| `expected expression` at the base type of a cast | cast detector is a separate keyword list from `parse_type` and is missing a token (`const`/`volatile`/`void`) |
| `expected ';' got '{'` after a completed function | the source was parsed as a block of statements instead of a translation unit |
| `expected ';'` after `.`/`+` in an initializer | designator path consumed only its first component |
| `expected expression` on a `va_list` family identifier | macro layer, not the parser: `__attribute`/builtins reintroduced after stripping |

## Harness capture loop (in order)

```
HD_DIAG=2 ./gauntlet_v3           # writes /tmp/failcases/<name>.c per build failure
./gauntlet_v3 /tmp/failcases/X.c  # single-file mode: same path as the suite
HD_DUMP_BUILD=/tmp/x.c ./gauntlet_v3 /tmp/failcases/X.c   # builder's real input
```

Bucket the failures into diagnostic classes and fix one class; the class count is
the metric, not the number of individual tests.

## Two failure classes that are NOT the parser

**The test source itself can be corrupt.** Before diagnosing a class, open the
captured source and check it is C. A suite generator had replaced `abort()`
declarations with `extern void return 1;` in 27 entries; every one failed with
`expected identifier`, and repairing the data (`extern void abort (void);`) moved
the gauntlet +17 passes with no compiler change. Grep the corpus for the exact
malformed string, fix the data, then re-measure — a dataset defect looks exactly
like a parser bug in a class histogram.

**A hard-coded cap truncates instead of erroring.** `HD_MAX_PARAMS` was 16 while
a suite defined a 32-parameter function; the parser accepted 16, then reported
`expected ')'` at the 17th. Symptom: the message points at a *parameter name*
in a signature that looks fine. Grep for the array bounds (`HD_MAX_PARAMS`,
`HD_MAX_IDENT_LEN`, fixed dims) whenever a failure count lands exactly on a
round number, and raise the cap rather than reworking the parser.

**Raising a cap is not free — measure it before accepting.** Caps embedded as
array dimensions grow EVERY node, not one table: `HDASTNode` carries
`param_names[HD_MAX_PARAMS][HD_MAX_IDENT_LEN]`, so 16 → 64 took the struct to
**9,592 bytes** and multiplied the per-declaration allocation. Check the bill
with `printf("%zu", sizeof(Node))` and peak RSS (`/usr/bin/time -f %M`) on the
largest input; accept only when both stay reasonable, and record the numbers next
to the constant so the next reader knows the trade.

## Corpus caveat

4,921 extracted sources: 541 hangs before the guards, **0 hangs / 0 crashes**
after. Excellent as a safety metric. As a correctness metric it is misleading:
files that begin with `{` are statement fragments, not translation units, and
rejecting them is correct.
