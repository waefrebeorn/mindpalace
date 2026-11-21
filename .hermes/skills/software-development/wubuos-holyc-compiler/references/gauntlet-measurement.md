# Gauntlet measurement, corpus defects, and build plumbing

Rules for reading and repairing the gauntlet before blaming the parser. The
parent SKILL.md is at its size budget; this file is the depth.

## A test that never ran is not a pass

`make test_x` on an already-built binary prints "up to date" and skips the
recipe's `./$@` line entirely, so a green-looking run can mean the test never
executed. Grep the Makefile for `^test_[a-z0-9_]+:` and emit one `.PHONY:` line
covering every one of them.

Symptom that exposed it: a Harness^2 probe scored 0/1 because its check grepped a
log the target never wrote.

## The corpus can itself be wrong

Captured sources have contained `extern void return 1;` where an `abort`
declaration belonged, and fixture entries that are expected-output text
(`OK\nexit 0`, `Test 1: 1`) rather than C. `HD_DIAG=2` writes each failing source
so it can be opened: if the text cannot compile under ANY compiler, repair the
suite rather than adding parser rules. Repairing 27 mangled declarations recovered
17 passes; a corpus of 458 output fixtures is a different (already skipped) class.

Non-C fixture test: the source contains none of `; { # (`. Those belong in skip,
not in `valid_total` as compiler failures.

## Fixed-size parameter tables truncate silently

`HD_MAX_PARAMS 16` made any function with more parameters fail with `expected ')'`
at the 17th; the fujitsu suite defines functions with 32. Count the parameters and
compare against the cap before debugging such a report. Raising it is cheap — the
arrays it sizes are small — and moved the gauntlet by +6.

## Measure the noise band before believing a delta

While sources could time out, repeated runs of one binary spread over ~60 passes
(two runs of the same build gave 1581 and 1561). After the parser became
hang-free, three consecutive runs returned byte-identical numbers
(2031/210/427) and the band went to 0.

So: fix hangs first, then trust single-run deltas. `tools/gauntlet_noise.sh N`
runs N times and prints min/median/max plus the band; re-run it whenever a change
could reintroduce nondeterminism.

## Diagnose by class, not by test

Capture with `HD_DIAG=2` (writes `/tmp/failcases/<name>.c`) and bucket failures by
first diagnostic into classes (~550 tests -> ~70 classes). Per-test rows are a work
queue; classes are a backlog. A 35-message class can be 6 tests, so count tests
before predicting a gain.

Extracting a test by name from a suite file has repeatedly produced text that did
not match what executed. Always capture the source the harness actually ran, or
replay one file (`./gauntlet_v3 <file>`) before reducing.
