# NtTerminateJobObject waitpid(pgid,0) Hang under WSL2

## Symptom
`vsl_syscall_nt_test` (E1 NT transliteration test) HUNG on every run after the
batch-2 commit (a4ae8a9). It printed 38/49 checks then froze indefinitely.
`make test` was GREEN because `test_vsl_nt` is NOT in the gate aggregate — the
hang was invisible. A "49 checks green" milestone was reported without ever
running the test.

## Root cause
`NtTerminateJobObject` (266) did:
```c
kill(-pgid, SIGKILL);
waitpid(pgid, &status, 0);   /* <-- blocks forever under WSL2 */
```
`pgid` is the sentinel child's pid (it `setpgid(0,0)` + `pause()`s forever).
`kill` succeeds, the sentinel dies, but the blocking `waitpid(pgid,0)` never
returns. A **minimal isolated repro** of the exact
`fork sentinel + setpgid(0,0) + pause() / kill(-pgid) + waitpid(pgid,0)` pattern
works fine and reaps immediately — so the hang is scheduler-specific (observed
on WSL2), not a logic error in the pattern itself.

## How it was diagnosed (no strace / no root available)
1. Build the test binary directly (the Makefile links `-lvulkan -lcuda`, heavy):
   ```bash
   gcc -O0 -g -D_GNU_SOURCE -DHAVE_VULKAN -DHAVE_CUDA -I src/runtime -I src/runtime/vsl \
     src/runtime/vsl/vsl.c src/runtime/vsl/vsl_syscall.c src/runtime/vsl/vsl_syscall_nt.c \
     src/runtime/vsl/vsl_syscall_proc.c src/runtime/vsl/vsl_syscall_fileio.c \
     src/runtime/vsl/vsl_syscall_memory.c src/runtime/vsl/vsl_syscall_net.c \
     src/runtime/vsl/vsl_process.c src/runtime/vsl/vsl_memory.c src/runtime/vsl/vsl_file.c \
     src/runtime/vsl/vsl_driver.c src/runtime/vsl/vsl_shared.c src/runtime/vsl/vsl_elf.c \
     src/runtime/vsl/vsl_gpu_vulkan.c src/runtime/vsl/vsl_syscall_nt_test.c \
     -o src/runtime/wubu_vsl_nt_test -ldl -lvulkan -lcuda
   ```
2. Run under a hard timeout with line-buffered stderr and temporary `[DBG]` markers
   around the kill/waitpid:
   `timeout 20 stdbuf -oL ./src/runtime/wubu_vsl_nt_test 2>/tmp/dbg.out`
3. Last marker printed was `kill done, waitpid(pgid)...` -> the freeze is
   exactly at the blocking `waitpid`.
4. Swapped in a `WNOHANG` poll loop with the SAME `kill`; it reaped the dead
   sentinel on **try 1** and the program exited 0 -> proves the child IS dead and
   reapable, the blocking call was just not delivering the zombie promptly.

## Fix (bounded WNOHANG reap)
```c
kill(-pgid, SIGKILL);
int status = 0;
for (int tries = 0; tries < 50; tries++) {
    pid_t wr = waitpid(pgid, &status, WNOHANG);
    if (wr > 0 || wr < 0) break;   /* reaped, or no such child */
    usleep(20000);
}
```
This reaps the sentinel on the first poll and never blocks the caller.

## Verification
- 3 consecutive runs: `49 passed, 0 failed`, exit 0, no timeout.
- Full `make test` green; `find_real_gaps.py src` -> 0 empty / 0 const-only.
- Committed as `d69b5b4` (HEAD after this fix).

## Lesson
`make test` does NOT exercise `test_vsl_nt`. After any change to
`src/runtime/vsl/vsl_syscall_nt.c`, run `make test_vsl_nt` (or the binary
directly) and confirm exit 0 + no hang before reporting green. Never trust a
handoff's "49 checks green" without a fresh run.
