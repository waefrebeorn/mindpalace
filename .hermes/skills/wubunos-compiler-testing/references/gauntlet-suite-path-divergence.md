# Gauntlet suite-path vs --dump-asm divergence — ROOT CAUSE FOUND & FIXED (2026-10-11)

## Symptom (now historical)

`gauntlet_runner --suite <name>` reported `EROR <test> x86-64
(crash/timeout/parse)` for TRIVIAL tests (int_add_assign `{int a=5; a+=3; a}`,
ctrl_while) that pass perfectly via `gauntlet_runner --dump-asm x86-64 "$SRC"`
(same hd_build_mir, same x86_run, in-process). `--core` showed pass=3410
error=48.

## Root cause

The `-march=native -mavx2 -mfma` auto-vectorizer MISCOMPILES the x86-64 JIT
runtime (`wubu_isa_x86_64.c` x86_run + emitter). The miscompiled code faults
with SIGSEGV inside the JIT'd code ONLY when executed in a forked grandchild:
- same bytes run fine in-process (--dump-asm)
- same bytes run fine under gdb
- layout-sensitive: ANY change to the binary's code layout moves the fault
  (adding a sigaction call, changing a comment that shifts code, etc. made it
  vanish and reappear)
- `-O2` without the arch/vector flags: 0 errors
- scrubbing only `-frename-registers -funroll-loops` on the emitter TU: no help

Same miscompile family as the documented `clock_gettime`/`-funroll-loops` bug.

## Fix (commit a60c02d)

`GAUNTLET_CFLAGS = -O2 ...` (no `-march=native -mavx2 -mfma`) used ONLY for the
gauntlet_runner link line; the rest of the build keeps the aggressive flags.
Verified: `--core` = pass=3458 fail=0 error=0 (was 3410/48).

## Two real ABI bugs found while investigating (also fixed in a60c02d)

1. The JIT prologue clobbered rbx (`movabs rbx, &wubu_jit_mem_ptr`) and the
   epilogue never restored it — a SysV ABI violation. x86_run's GCC code can
   keep locals in rbx across the fn() call; `jit_free_exec(exec, size)` then
   munmaps with a corrupted size. Prologue now `push rbx`; both epilogue paths
   `pop rbx`.
2. The struct-return epilogue emitted `ret` WITHOUT `leave`, so ret popped from
   inside the frame (rsp still 0x78 below rbp) and returned to a garbage
   address. Added the missing `leave`.

## The same miscompile also HANGS the fuzz target (not just SIGSEGVs it)

The miscompile does not always fault — in a loop it can spin forever. The
`test_fuzz_diff` target (3000-iteration differential fuzz) links
`wubu_isa_x86_64.c` with the DEFAULT `$(CFLAGS)` (`-march=native …`) and HANGS
indefinitely inside its JIT'd fuzz loop; `make test` dies at that step with a
timeout and `make: *** Deleting file 'test_fuzz_diff' … Terminated`. Verified
pre-existing: the parent commit hangs identically, so it is the same root
cause, not a regression. Fix: point the `test_fuzz_diff` recipe's `$(CC)` line
at `$(GAUNTLET_CFLAGS)` (the same scrub). Any target that RUNS JIT'd code in a
loop is a hang candidate under the aggressive flags — scrub its link line too.

## Debugging techniques that worked

- Instrument the GRANDCHILD path (fork+watchdog loop ~line 303-390 of
  test_gauntlet_runner.c), not `run_test_safe_all` — `--suite` does not use
  that function.
- Report the grandchild's wait status: `WIFSIGNALED`/`WTERMSIG` distinguishes
  SIGSEGV (signal 11) from parse failures. All 48 were SIGSEGV.
- The decisive isolation: rebuild with progressively fewer aggressive flags
  (`-O2`, then drop `-march=native`). The fault disappeared with plain `-O2`.
- gdb and any instrumentation that shifts code layout can MASK the fault —
  never conclude "works under gdb = environmental" for a layout-sensitive
  miscompile.
- `mallopt(M_MMAP_THRESHOLD)` was tested and ruled OUT (threshold=0 kept the
  same 48 errors).
- A target that HANGS (no output, no exit) vs one that SIGSEGVs: same
  miscompile family — check the wait status first, then scrub the link flags.

## Verify a pre-existing red with the PARENT COMMIT, then STOP (don't poll it)

Before blaming your change for a hang/red, reproduce at the parent:
`git checkout <commit>~1 -- <files> && make <target>`. If it hangs/fails
identically, it is pre-existing — fix or report it, and move on. Do NOT
rebuild the baseline and then sit polling it; one run proves the point.

## GPU-less boxes: per-seed popen legs turn a fuzz target into an apparent hang

The `test_fuzz_diff` hang has TWO stacked causes — check both before blaming
the JIT:

1. **The miscompile (above)** — scrub the target's link line to
   `GAUNTLET_CFLAGS`.
2. **Per-seed out-of-process GPU runners.** The fuzzer invokes the PTX and
   Vulkan legs per seed (3000 seeds = 3000 launches). The vulkan leg
   `popen`s `/tmp/vk_run`; on a WSL box with only the dzn ICD (no real GPU)
   every launch costs ~1s, so the vulkan leg alone runs ~50 minutes. Symptom:
   the target "hangs" with zero output while actually grinding through
   launches. `fuzz_native_f32()` runs at the end of main unconditionally and
   is usually the hot path — gate EVERY driver-lookup site (main's loop AND
   the sub-fuzzers), not just the first one you find.
   Fix: gate the GPU legs behind `WUBU_FUZZ_GPU=1` (opt-in); the
   x86-64/8086/interpreter differential is the core oracle and always runs.
   In the driver itself, mirror ptx's early-disable: probe the runner binary
   once (`access(path, X_OK)`), return the failure sentinel immediately when
   absent, and set the unavailable flag on the first hard failure so later
   calls don't pay a popen round-trip.

**Orphaned children compound the illusion.** Every timed-out run leaves
orphan `test_fuzz_diff`/`vk_run` processes (the parent's timeout kills make,
not the detached children). They keep eating CPU and make the NEXT run look
worse. After any timeout: `ps aux | grep -E '[t]est_fuzz_diff|[v]k_run'`,
kill by PID (a `pkill -f <pattern>` whose pattern appears in your own shell
command line kills your own launcher first — see the pkill self-match
gotcha in `wubuos-test-suite`), and confirm the count is 0 before re-running.
When a fuzz mode's summary lines print (`float seeds: N match: N
mismatch: 0`), the run is HEALTHY — a `grep -c mismatch` hit count of
hundreds is those zero-mismatch summary lines, not failures.

## Self-inflicted gate timeouts are NOT test failures

`make test` on this repo takes ~15+ minutes from clean (compile + run). A
foreground `timeout N make test` that returns exit 124 is YOUR timeout, not a
red — read the log tail (`Terminated` mid-target) before diagnosing. Run the
full gate as a PERSISTENT background job (`persist_on_release=true`, a
>gate-duration window) and END THE TURN — the completion notification re-enters
the conversation. Never burn turns in `time.sleep()` wait loops polling a
background job; that pins the UI in "⏳ Working" and the user checks in. One
quick poll is fine; sustained polling is the failure.

When a background job's notification finally arrives for a STALE run (started
before a fix landed), do not re-diagnose from its output — state which commit
it measured and wait for the current run. Stale notifications re-enter the
conversation hours after their run started.

## Rules for future miscompile hunting

1. If a crash is fork-only + layout-sensitive + vanishes under gdb, suspect
   the optimizer, not the logic. Rebuild with scrubbed flags to confirm.
2. When a flag scrub fixes a target, scope it to that target's link line
   (GAUNTLET_CFLAGS pattern), never globally — the aggressive flags help the
   hot paths elsewhere.
3. Keep the ABI fixes even when the flag scrub is the real cure: the rbx
   clobber and missing `leave` are genuine latent bugs.
