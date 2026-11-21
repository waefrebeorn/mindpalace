# Stale background-process notifications

A background process launched BEFORE a fix completes and reports pre-fix
output. Nothing in the notification says so. `exit_code=0, reason=exited`
is always reported, because the harness reports the wrapper's exit, not the
build's.

## The one-line triage

Compare the LOG FILE's mtime against the commit/file that would have fixed
it. If the log predates the fix, the notification is stale -- re-run the
target and move on.

```bash
ls --time-style=+%m-%d_%H:%M <log> <the-file-that-was-fixed>
```

## Concrete example (this happened 3x in one session)

`test_drivers` link failures kept arriving:
```
undefined reference to `wubu_isa_wasm'
undefined reference to `wubu_tensor_dispatch'
undefined reference to `tgemm_avx512'
undefined reference to `powf'
```
These were fixed in `10bf8e9`/`15215a4`. Re-running gave
`DRIVER SPACE PASSED (6 drivers, 33/33)` every time. The logs were written
before those commits.

Tells that a notification is stale rather than real:
- the message names a defect already committed as fixed
- the same text arrives more than once with different exit codes
- a fresh run of the same target passes

## Also check for wrong target names

`make: *** No rule to make target 'test_mir_driver'` arrived alongside real
failures. There is no such target -- it is `test_drivers`. A notification
citing a non-existent target is stale by definition; do not go looking for
that bug.

## Never do this

Do NOT re-litigate a fix because a stale notification disputes it, and do
not spend a turn "investigating" a defect whose commit is already in the
log. Re-run the target once to confirm, state that it is stale, and absorb
the rest silently.

## Reused /tmp names are the underlying cause

`/tmp/agi.log`, `/tmp/full4.log`, `/tmp/full6.log`, `/tmp/batt2.log`,
`/tmp/full8.log` have all mixed runs hours apart. Use a UNIQUE name per
launch, and include the timestamp in the name so ordering is checkable.

Note that a log's own `MAKE_EXIT=` line is authoritative for THAT run -- but
only if you know which run wrote it. Two logs claiming different results is
a naming collision, not a regression: compare mtimes before believing
either.