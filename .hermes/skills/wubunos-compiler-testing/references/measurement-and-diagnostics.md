# Measuring the compiler honestly, and getting diagnostics out of it

## The gauntlet is noisy — never compare single runs

`gauntlet_v3` runs 6 workers with per-test watchdogs. Two runs of the SAME binary
with only a diagnostic-format change between them produced:

```
run A: pass 1581  fail 155  error 932   (59.3%)
run B: pass 1561  fail 151  error 956   (58.5%)
```

That is a ±20-pass band (~0.75%). Consequences:

- A single-run delta smaller than ~20 passes is not a result. Say "within noise",
  not "parity" or "improved".
- To compare two configurations: run each at least THREE times on an otherwise
  idle machine and compare medians.
- Never run two gauntlets concurrently, and never quote a number produced while
  another build/run was active — concurrent runs also leave stale worker state
  that can report `pass 0` for the whole suite.
- A run that ends with all-zero counters is stale state, not a code result.
  Re-run with nothing else going on.

## Getting a diagnostic out of a rejected test

The harness compiles in grandchild processes and discards compiler stderr, so a
failed build is silent. Three pieces make it visible:

1. `hd_last_diag()` (in `holyd_mir_eval.c`, declared in `wubu_mir.h`) returns the
   last parse/semantic messages. `hd_build_mir` populates it on every failure
   path.
2. `HD_DIAG=1` makes the test binary print the messages, WITH the test name on
   the same line (`diag <name>: line L col C: ...`).
3. `tools/compile_diag.c <file.c>` prints parse-vs-semantic diagnostics for a
   single file with no concurrency at all.

**The name must be on the message line.** Workers write stderr concurrently; a
`TEST <name>` line followed by a later `diag:` line belongs to different tests.
Pairing them produces a plausible-looking classification that is simply false —
verify by checking that the quoted identifier actually appears in that test's
source.

## Attribute rejections before changing rules

When a semantic/type rule appears to regress the suite, classify every rejection
first. Rejections that are not about the language construct you are testing are
not rule bugs:

| class | example | real fix |
|---|---|---|
| preprocessor leftovers | `stdout`, `stderr`, `HUGE_VAL`, `FILE`, `va_list` | the preprocessor strips `#include`, so these never appear as declarations; whitelist them as declared names |
| GNU label addresses | `&&label` inside `goto *p` | labels referenced as values are not free identifiers |
| externs from other TUs | `hit_nonpic_addr` etc. | multi-file link tests; a single-TU compiler cannot resolve them by design |
| macro parameters | `__VA_ARGS__`, named variadics | skip `__`-prefixed names in the checker |

## Diagnostics need source positions in the AST

`HDASTNode` originally carried no line/col, so `parse_error` formatted the
LEXER's current line — which, in a pass that runs after parsing, is the file's
last line. Every semantic message then pointed at the same place and could not be
used to locate the construct.

Rules now in place:

- create nodes with a factory that stamps `p->lex->line` / `p->lex->col`;
- report semantic errors with `parse_error_at(p, node->line, node->col, name, msg)`;
- format as `line L col C: name: message`.

## Verify a rule change against the gate, in order

1. `./test_mir_battery` — 142 probes, expect all PASS (one known deferred case:
   `float add`, which needs true f32).
2. `make test_diag` — three diagnostics cases (recovery, undeclared, arity).
3. `make gauntlet_v3` then run it alone, three times, medians.

A change that gains one battery probe and loses gauntlet passes is a net loss;
revert it rather than defending it.
