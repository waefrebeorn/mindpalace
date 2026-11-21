---
name: wubuos-vsl-test-speedup
category: software-development
description: How WuBuOS VSL/NT test targets and other single-translation-unit Makefile recipes were converted from one giant $(CC) invocation (7+ min recompile every run) to incremental object linking (seconds on unchanged files). Apply to ANY test/main recipe that feeds many .c files to one $(CC).
---

# WuBuOS VSL/NT test — single-TU → incremental object linking

## The problem (symptom)
`make test_vsl_nt` (and `make test_vsl`) took **7+ minutes** every run even
when only ONE `.c` changed. Root cause: the recipe fed ~15 VSL `.c` files plus
the test `.c` to a **single `$(CC) ... file1.c file2.c ... -o bin`** invocation.
GCC compiles all of them into one translation unit every time → no incremental
rebuild benefit. This is the same anti-pattern the `wubuos-monolithic-split`
skill calls out for the hosted/main binary ("the inline recipe is the #1
rebuild-speed killer").

## The fix (pattern)
1. Define an object list variable instead of listing `.c` files in the link line:
   ```makefile
   VSL_NT_OBJS = \
       $(RT)/vsl/vsl.o $(RT)/vsl/vsl_syscall.o ... $(RT)/vsl/vsl_syscall_nt_test.o
   ```
2. Make the test target depend on `$(VSL_NT_OBJS)` (not a bare recipe):
   ```makefile
   test_vsl_nt: $(VSL_NT_OBJS)
       $(CC) ... $(VSL_NT_OBJS) -o $(RT)/wubu_vsl_nt_test -ldl -lvulkan -lcuda
       $(RT)/wubu_vsl_nt_test
   ```
3. The objects build via the EXISTING pattern rules — do NOT add a parallel
   compile line. WuBuOS already has:
   - `$(RT)/vsl/%.o: $(RT)/vsl/%.c`  (line ~328) compiles with
     `-DHAVE_VULKAN -DHAVE_CUDA -I$(RT) -I$(RT)/vsl -I$(COMP) -I$(JIT)`
   - `$(RT)/%.o: $(RT)/%.c` (line ~288/324) for non-vsl RT files like
     `wubu_fs_util.c` / `wubu_vsl_test.c`.
   These pattern rules only recompile a `.o` when its `.c` is newer, so after
   the first cold build, editing one file recompiles only that `.o` + relinks
   (seconds, not minutes).

## CRITICAL gotchas
- **List `.o`, never `.c`, in the dependency line.** A test target recipe that
  compiles sources inline lists `.c` paths; the `OBJS` variables (`RT_OBJS`,
  `APP_RT_OBJS`) use `.o`. Mixing them up (putting `.o` where a DIRECT-COMPILE
  test recipe expects `.c`) produces link failures. Here we CONVERT a direct-
  compile recipe to an object-link recipe, so everything becomes `.o`.
- The VSL pattern rule carries `-DHAVE_VULKAN -DHAVE_CUDA`. If a test needs
  those defines, ensure its sources go through the vsl rule (they do, since
  they live under `$(RT)/vsl/`). Non-vsl RT sources (`wubu_fs_util.c`) inherit
  the defines from the link-line `-D_GNU_SOURCE -DHAVE_VULKAN -DHAVE_CUDA` too,
  but their `.o` is built by the plain `$(RT)/%.o` rule which does NOT add those
  -D flags — that's fine because `wubu_fs_util.c` doesn't need them; the test
  binary still gets them at link/compile of the test .c via the vsl rule.
- Keep the same `-ldl -lvulkan -lcuda` link order: objects FIRST, libraries LAST.

## Verify
- First run: `make test_vsl_nt` still compiles everything (cold) but links via
  objects. Confirm the test prints `Results: <n> passed, 0 failed` (run for the live count).
- Second run (no source change): should say nothing to do / relink instantly.
  `touch src/runtime/vsl/vsl_nt_token.c && time make test_vsl_nt` must be
  dramatically faster than the old single-TU path.

## Companion bugs found while converting (same "test must finish" class)

### Orphan-process "hang" — `wchan == __do_sys_pause`
After converting, the recipe may still appear to "hang" for minutes. Before
assuming a deadlock, inspect the stuck process:
```
cat /proc/<pid>/wchan        # __do_sys_pause ⇒ forked sentinel child, not a lock
ps -o pid,ppid,comm <test>   # ppid==1 (init) ⇒ orphan from a PRIOR crashed run
```
`pause()`-blocked children (NT job/process sentinels) that were never reaped
survive a killed/crashed run, get reparented to init, and look like a hang.
They are NOT a recompile problem. Fix in the production module: track every
forked child pid at fork() time and reap ALL of them unconditionally in the
module's `*_shutdown()` (kill + bounded `waitpid(.,WNOHANG)`). Verify: run the
binary directly and confirm `ps` shows 0 leftover `<test>` processes.

CAUTION: piping the recipe through `tail` + a `/usr/bin/timeout -s KILL` run
MASKS a real hang — it force-kills the binary but orphans already reparented
to init persist. Always check `ps` for orphaned comms after the run.

### Stale-test inversion when a batch promotes STUB → REAL
A regression test may assert the OLD stub behavior (e.g. "NtAccessCheck ->
NOT_IMPLEMENTED"). The moment the handler becomes real, the test fails — but
the code is correct; the test is now wrong. Fix the test to assert the real
behavior and keep a genuine NOT_IMPLEMENTED check pointed at a truly-
unregistered slot. The failing check is a *symptom of success*, not a
regression. (Full detail in wubuos-monolithic-split
`references/split-wiring-pitfalls-2026-07-19.md`.)

## Applied to
- `test_vsl_nt` (commit d166149 follow-up) — VSL_NT_OBJS.
- `test_vsl` (sibling) — VSL_OBJS, identical pattern.
- Orphan-leak fix in `vsl_nt_bridge_shutdown` + `vsl_nt_track_child` (commit
  40f1955).

## Reuse trigger
Any Makefile recipe in this repo (or similar) that does
`$(CC) ... a.c b.c c.c ... -o bin` with >3 sources → convert to
`target: $(OBJS)` + link `$(OBJS)`. Especially test_* targets and the hosted
`main:` recipe (the split-skill's "convert inline recompile recipe to
incremental object linking" variant).
