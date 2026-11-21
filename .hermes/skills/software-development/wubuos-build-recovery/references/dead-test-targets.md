# Dead test targets: a green log can be lying

A target that FAILS TO LINK produces no test results -- and if you only read
the score someone quoted, or only look at the tail of a reused log, you can
report a number that was never produced by the current source.

## Confirm the binary is real before quoting any score

```bash
# 1. Does the target actually BUILD (not just link-fail and stop)?
make <target> > /tmp/t.log 2>&1; echo "EXIT=$?" > /tmp/t.exit

# 2. Prove the binary was produced by THIS build, not a stale one:
ls -l <output-binary>          # mtime must be newer than your edit
make -n <target> | head -3     # the link line make will actually run

# 3. Only then read the results:
grep -ac 'Results:' /tmp/t.log
```

`Source file is more recent than executable` (gdb) or a binary mtime older
than your source means you are reading a STALE build's output. This silently
cost several rounds: the ternary "fix" appeared to fail when the probe binary
had simply not been rebuilt.

## Reused log files mix runs

`> /tmp/foo.log` truncates, but a job that appends (`>>`), or a log written by
two different invocations, can contain an OLD failure AND a newer success. The
same file showed both a link error and `32/32 passed`. Always check `stat -c
'%y' log` against `date` before concluding anything, and prefer a fresh
`rm -f log && make ... > log` for anything you intend to quote.

A background-job completion notification is NOT evidence of current state --
it reports whatever the job printed, whenever it was launched. Re-verify with
a fresh run before reacting.

## Background notifications can be hours stale

`notify_on_complete` fires when the job exits, but the job may have started
before your fix landed. Compare the log mtime to now, and to the mtime of the
binary, before treating a failure as a regression.

## A target nothing invokes rots silently — check reachability

`make test` is a TIER AGGREGATE (`test: check_opcode_coverage test_critical_*
test_high_* test_medium_other test_vsl_* ...`). A test target that is not
named on that line is never built, so its link line rots and its failures
stay invisible. This is the most productive thing to check after any test
or build work:

```bash
grep -n '^test:' mk/tests.mk                     # what the gate actually runs
grep -c  'test_drivers' mk/tests.mk              # 1 = defined only, never invoked
grep -oE '^[a-z_0-9]+:' mk/tests.mk | sort -u    # all rules, to diff against
```

If a rule appears once as its own rule and nowhere in the aggregate, it is
DEAD: assume its build has rotted and verify by running it directly.

`test_gauntlet` and `test_drivers` were both dead this way. `test_drivers`
had not built in months and had four undefined references (`wubu_isa_wasm`,
`wubu_tensor_dispatch`, `tgemm_avx512`, and `powf`/`cosf`/`sinf`/`roundf`
— missing sources, a missing object, and no `-lm`). Fixing it immediately
surfaced a REAL 6502 backend bug: three subtraction expressions returned 0.
Neither the link rot nor the 6502 bug was visible while the target was dead.

Corollary: a target can LINK a backend without EXERCISING it. Linking
`wubu_isa_vulkan.c` proves nothing if no test calls its `compile`/`run`. For
a backend that needs hardware, add a COMPILE-ONLY smoke — it needs no GPU
and still catches an emitter that stops producing a module. Check which
backends a test actually drives:

```bash
grep -nE 'wubu_isa_find|const char \*names' isa-test/mir_driver_test.c
```

## Naming/variable traps in link lines

- `$(JIT)=src/jit` but some JIT sources live in the COMPILER's own `jit/`
  dir (`src/compiler` is a symlink to the wubunos checkout). If a path 404s,
  `find . -name <file>` before assuming it does not exist.
- Prefer `suites/*.c` over naming each suite; a hand-listed subset silently
  omits suites the runner references, and the undefined symbols that follow
  look like missing implementations rather than a missing link entry.
- Generated sources must be fixed at the GENERATOR. A dmake.py emitting `}};`
  to close one `{` breaks every file it writes, so patching the generated
  files alone guarantees the bug returns on the next regen.

## AVX-512 / ISA-flag sources

A `.c` that needs `-mavx512f -mavx512dq -mavx512vl -mavx512bf16` CANNOT be
compiled inside a single-file recipe -- it dies with `always_inline
target specific option mismatch`. Use the prebuilt `.o` from
`mk/pattern-rules.mk` and add it as a prerequisite instead.