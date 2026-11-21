---
name: wubuos-nt-test-lite
description: How to build + run the WuBuOS E1 NT-bridge regression test (test_vsl_nt) on WSL2 when the skill's build_nt_test_lite.sh script and find_real_gaps.py are ABSENT from the checkout. Manual lite-binary recipe, run-in-background rule, and gdb segfault triage.
---

# WuBuOS E1 NT-test: manual WSL2 lite build

The `wubuos-nt-transliteration` skill says to use
`scripts/build_nt_test_lite.sh`, but **that script is NOT in this checkout**
(verified 2026-07-13). `find_real_gaps.py` (referenced by the gap-closer loop) is
also missing. The Makefile `make test_vsl_nt` links `-lvulkan -lcuda` and
**hangs / OOMs under WSL2**. Build the lite binary manually instead.

## Compile + link (skip GPU objects, stub vsl_vulkan_driver_init)

```bash
cd ~/profiles/mind-palace/home/myseed
rm -f /tmp/nt_objs/*.o; mkdir -p /tmp/nt_objs
SRCS="vsl.c vsl_syscall.c vsl_syscall_nt.c vsl_nt_atoms.c vsl_nt_job.c vsl_nt_io.c \
      vsl_nt_proc.c vsl_nt_sync.c vsl_nt_registry.c vsl_syscall_proc.c \
      vsl_syscall_fileio.c vsl_syscall_memory.c vsl_syscall_net.c vsl_process.c \
      vsl_memory.c vsl_file.c vsl_driver.c vsl_shared.c vsl_elf.c vsl_syscall_nt_test.c"
for s in $SRCS; do
  gcc -O0 -g -D_GNU_SOURCE -c -I src/runtime -I src/runtime/vsl \
      src/runtime/vsl/$s -o /tmp/nt_objs/${s%.c}.o || { echo "FAILED $s"; break; }
done
echo 'int vsl_vulkan_driver_init(void){return 0;}' > /tmp/nt_objs/vsl_vulkan_stub.c
gcc -O0 -g -c -I src/runtime -I src/runtime/vsl /tmp/nt_objs/vsl_vulkan_stub.c \
    -o /tmp/nt_objs/vsl_vulkan_stub.o
gcc -O0 -g /tmp/nt_objs/*.o -o /tmp/wubu_vsl_nt_test_lite -ldl -lpthread
```

Keep `SRCS` in sync with the `test_vsl_nt` Makefile recipe — add any new
`vsl_nt_*.c` module or you get undefined-reference link errors.

## RUN (this is where false-hangs come from)

`NtCreateProcess` / job handlers `fork()` children that inherit the stdout pipe.
A foreground `timeout ... | tail` **hangs forever** (children never close the
pipe). A `pkill -9 -f wubu_vsl_nt_test` in the SAME command **SIGKILLs the shell**
(exit -9). Always run in background, redirect to a file, then read it:

- Hermes: `terminal(background=true)` with the binary + `> /tmp/nt_out.txt 2>&1`,
  then `process(action=wait)`; read `/tmp/nt_out.txt`.
- Expected after Batch 7: `Results: 133 passed, 0 failed` (grows per batch).

## Segfault triage

```bash
gdb -batch -ex 'set debuginfod enabled off' -ex run -ex bt \
    --args /tmp/wubu_vsl_nt_test_lite
```

Common causes seen in practice:
- `NtQueryValueKey` writing a `ResultLength` to `e_len` treated as a **pointer**
  (the arg is an input *length value*, not an out-pointer).
- A raw `futex` wake on a `uaddr` that is not a live, aligned `uint32_t`.
- `mkdir` on a multi-level path without `mkdir -p` semantics (fails ENOENT).
- **gdb shows `__GI_kill` as the crash frame — that is a RED HERRING.** Several
  handlers (e.g. `NtAlertResumeThread`, `NtSuspendThread`) call `kill(pid, SIGCONT)` /
  `tgkill(...)` on themselves, which makes gdb catch a `SIGCONT` and stop at `kill()`.
  The REAL segfault is in a LATER frame along the same run (e.g. `NtResetVirtualMemory`
  dereferencing `c_size` as a pointer when the test passed it by value). **Fix:** re-run
  with `handle SIGCONT nostop noprint pass` before `run`, so gdb continues past the
  self-signal and reports the genuine faulting frame:
  `gdb -batch -ex 'set debuginfod enabled off' -ex 'handle SIGCONT nostop noprint pass' -ex run -ex bt --args /tmp/wubu_vsl_nt_test_lite`
- **Handler return-contract mismatch in the TEST (not a crash, but false failures).**
  `NtWriteFile`/`NtReadFile` return the BYTE COUNT (CHECK `r == (int64_t)len`), and
  `NtCreateEvent`/`NtOpenMutant`/`NtOpenSemaphore`/`NtOpenSection` return the HANDLE as
  the result (CHECK `r != 0`; read the handle from `r`, not from an out-param). Asserting
  `r == NT_STATUS_SUCCESS` on those fails incorrectly.
- **Missing `NT_STATUS_*` code.** `vsl_nt_bridge.h` defines only a small set; referencing
  `NT_STATUS_TIMEOUT` / `NT_STATUS_WAIT_0` / `NT_STATUS_ALERTED` / `NT_STATUS_NO_MORE_FILES` /
  `NT_STATUS_BUFFER_OVERFLOW` (all needed by wait/blitz handlers) fails the build with
  "undeclared" — ADD the standard codes to the header's NT_STATUS block.
