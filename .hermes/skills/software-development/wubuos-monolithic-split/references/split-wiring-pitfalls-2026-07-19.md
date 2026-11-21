# Split-wiring pitfalls — 2026-07-19 session (E1 NT Batch 12 + canvas codec)

Captured while splitting live monoliths AND recovering a crashed session's
half-finished WIP. These are wiring/verification traps that the base workflow
(Step 0–8) assumes but does not call out explicitly.

## 1. Globals must move WITH the functions that use them

When you brace-count-extract a function that reads a file-scope `static`
array/flag, the NEW module references an undeclared symbol. The extraction
script only copies the function body, not the globals it closes over.

Symptom:
```
wubu_image_codec.c:17: if (crc32_table_init) return;
wubu_image_codec.c:23: crc32_table[i] = c;
error: 'crc32_table' undeclared (first use in this function)
```
the global `static uint32_t crc32_table[256];` is still sitting in the old
host file (now dead there).

Fix: move the globals into the new module as its private `static`s, and delete
them from the host. Verify with `grep -rn <name> src/...` across BOTH files
before compiling — every reference site must be accounted for.

## 2. Stale-test inversion when a batch promotes STUB → REAL

A pre-existing regression test may assert the OLD stub behavior:
```c
CHECK(r == NT_STATUS_NOT_IMPLEMENTED, "stubbed NtAccessCheck -> NOT_IMPLEMENTED");
```
The moment a batch makes that handler REAL, the test FAILS — but the code is
correct and the test is now wrong. This is a *symptom of success*, not a
regression.

Fix:
- Replace the stale assertion with one that proves the new real behavior
  (e.g. a default token with an empty privilege set now returns SUCCESS, not
  NOT_IMPLEMENTED).
- Keep a genuine "stub still returns NOT_IMPLEMENTED" check, but point it at a
  TRULY-unregistered dispatch slot (e.g. syscall 0, never registered) so it
  keeps guarding the stub path.
- Add assertions that exercise the real handler's edge cases (grant/remove a
  privilege → access decision flips). That converts the test from
  "doesn't crash" into "real work verified".

## 3. Orphan-process leak from forked `pause()` sentinels

NT-object modules that model a process/job as a forked child that blocks in
`for(;;) pause();` (job sentinel, NtCreateProcess placeholder) MUST reap those
children on teardown. If the test (or a test block) exits without reaping, the
children are reparented to init and live forever as sleeping zombies — and
they look exactly like a "test hang" because the main process sometimes waits
on them.

Diagnosis trick (this is how the "hang" was un-mystified): `cat /proc/<pid>/wchan`
on the stuck process. If it says `__do_sys_pause`, it's a forked sentinel
child, NOT a real deadlock. And `ps -o pid,ppid,comm` shows ppid==1 (init) for
the orphans — they survived a previous crashed/killed run.

Robust fix (don't patch per-test symptoms): track every forked child pid in a
global array at fork() time (`vsl_nt_track_child(pid)` in the parent branch),
and reap ALL of them unconditionally in the module's `..._shutdown()` — even
if the owning handle was closed mid-session. Kill + bounded `waitpid(.,WNOHANG)`
loop (don't block forever). Verify by running the binary directly and checking
`ps` shows 0 leftover `<test>_test` processes afterward.

If a test recipe pipes through `tail`, a force-kill via `/usr/bin/timeout -s KILL`
will MASK a real hang (it kills the binary but orphans may already be reparented
and persist). Always inspect `ps` for orphaned `<binary>` comms after the run.

## 4. Test-recipe `.c` vs `OBJS` `.o` trap (reiterated from base workflow)

When a split module is consumed by BOTH the incremental build and direct-
compile test recipes, you must add it in two forms:
- `APP_OBJS` / `RT_OBJS` / hosted-link line  → `$(APPS)/wubu_image_codec.o` (`.o`)
- each `test_*` recipe that compiles sources inline → `$(APPS)/wubu_image_codec.c` (`.c`)

`grep -n 'old_file\.c' Makefile` finds BOTH forms; update every hit. A missing
`.c` in a test recipe surfaces only on `make clean && make <that-test>`.
Beware substring collisions: `wubu_canvas_io.o` is a prefix of
`wubu_canvas_io_ppm.o` — match `wubu_canvas_io.o ` (trailing space) so the
replace doesn't corrupt the `_ppm` entry.

## 5. `static` follows non-static declaration (base Step 7 gotcha, confirmed)

After promoting extracted functions to non-static in the internal header, the
definitions in the new `.c` MUST also drop `static`. The compiler error is
explicit: "static declaration of 'fn' follows non-static declaration". Fix
both the header declaration and every definition. Do it with a scripted
replace (`s/static <sig>/<sig>/`) across the extracted set, not by hand.

## 6. Missing system headers in the extracted leaf

The new standalone module often needs headers the old host got transitively:
`<stdlib.h>` (free/malloc), `<stdbool.h>` (bool/true/false), `<signal.h>`/
`<sys/wait.h>`/`<unistd.h>` (kill/waitpid/usleep/pause). Add them explicitly
to the leaf's includes — never rely on transitive inclusion once it's a
separate compilation unit.
