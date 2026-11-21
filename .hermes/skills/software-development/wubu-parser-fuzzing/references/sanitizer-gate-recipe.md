# Sanitizer gate recipe (WuBuOS)

`mk/sanitize.mk` builds a set of targets fresh under ASan/UBSan and runs them. Both
gates matter: the plain target proves the parser works, the sanitized one proves it is
not executing undefined behaviour.

## Flags

```make
SAN_CFLAGS := -O1 -g -std=c11 -fno-omit-frame-pointer \
              -fsanitize=address,undefined -fno-sanitize-recover=all \
              -Werror=implicit-function-declaration
```

- `-fno-sanitize-recover=all` turns every detected issue into an abort, so a fault stops
  the run instead of being printed past.
- `-Werror=implicit-function-declaration` is what makes the sanitized build earn its
  keep: a call through a missing prototype reads the real return type from garbage and
  can pass or fail depending on stack layout and optimisation level.

## Environment

```
ASAN_OPTIONS=detect_leaks=0:abort_on_error=0:exitcode=97:halt_on_error=1
UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1
```

`detect_leaks=0` because several modules intentionally borrow buffers and report
ownership elsewhere; leaks are not this gate's subject.

## Structure

Each target gets a `.san` rule that lists its sources explicitly (NOT a shared macro
unless the macro is defined ABOVE the rule that uses it), then one aggregate target:

```make
.PHONY: test_sanitize
test_sanitize: $(GUI)/mime_test.san $(RT)/json_test.san
	@set -e; fail=0; \
	for b in $(GUI)/mime_test.san $(RT)/json_test.san; do \
	   echo "--- sanitized: $$b"; \
	   if ! $$b; then echo "!!! $$b failed"; fail=1; fi; \
	done; \
	if [ $$fail -eq 0 ]; then echo "=== all sanitized targets clean ==="; fi; \
	exit $$fail
```

Plus one prerequisite per mutation fuzzer, invoked AFTER the loop.

## Verification discipline

1. Delete the `.san` artifacts, run the aggregate, confirm they were rebuilt. A gate
   that never built the thing it claims to run is theatre.
2. Count targets: the summary should name every entry. Record the measured number in
   the commit message when it changes.
3. Timing is a trap: a fork-per-input fuzzer under ASan can be fast in the background
   and appear to hang in a foreground terminal. Measure it in the background before
   concluding it is slow, and record the measurement rather than guessing.
