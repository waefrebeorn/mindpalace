# The NT argument contract: every syscall must survive garbage

Unit tests exercise handlers with VALID inputs. That leaves one class of bug
untested: a handler that dereferences its pointer arguments without looking at
them passes its unit test and takes the OS down when real software passes
something unexpected. Windows code passes NULL freely -- optional out-params,
absent attributes, zero lengths -- so this is not an edge case.

## The gate

`vsl_nt_contract_sweep(out, cap)` lives in `vsl_syscall_nt.c`, because the facade
owns `g_nt_dispatch[]` and no other TU can see the table. For every registered
slot it probes once with all-zero arguments:

```c
int fds[2];
pipe(fds);
pid_t pid = fork();
if (pid == 0) {
    close(fds[0]);
    alarm(1);                              /* a handler may never hang the gate */
    int64_t st = g_nt_dispatch[i](0,0,0,0,0,0);
    write(fds[1], &st, sizeof(st));
    _exit(0);
}
```

Three properties make it usable as a standing gate rather than a one-off:

- **Forked per slot.** A crashing handler costs one child. Without forking, the
  first bad handler ends the run and you learn nothing about the rest.
- **`alarm(1)`.** A handler that blocks forever would otherwise hang the build,
  and a hung gate reports nothing at all -- indistinguishable from success if
  you only look at exit codes. Bounded and recorded instead.
- **Status through a pipe.** Otherwise you cannot tell "returned an error" from
  "returned garbage", and the report names a slot without saying what happened.

The test asserts: every registered slot was probed, none died, and results were
actually produced. Record the probed count in the commit body; it should rise
monotonically as handlers land.

## What it caught immediately

First run over 412 slots found three crashes:

| slot | syscall | cause |
|---|---|---|
| 179 | `NtQuerySystemEnvironmentValue` | `getenv((void*)0)` -- the argument is not allowed to be NULL and glibc dereferences it |
| 180 | `NtQuerySystemEnvironmentValueEx` | delegates to 179 |
| 189 | `NtRaiseException` | `raise(SIGTRAP)` unconditionally |

Two distinct lessons worth generalising beyond these functions:

**`getenv` (and any function whose parameter is documented as non-NULL) needs
an explicit guard.** It compiles cleanly with `(void*)(uintptr_t)a` where `a` is
a raw uint64_t dispatch arg, so nothing warns. Validate pointer-shaped arguments
BEFORE the cast-and-call; a raw dispatch argument is untrusted by construction.

**Never raise a host signal on behalf of a guest API call.** `raise(SIGTRAP)` does
not deliver an exception to the caller's handler -- it terminates the calling
process, which here is WuBuOS. Any capability that genuinely cannot be delivered
returns a status (`NT_STATUS_NOT_IMPLEMENTED`) and says why in the commit message;
it must not take the desktop down with it. Exception DELIVERY needs SEH, which is
a separate work item.

## Also fixed while building the gate

Four VSL modules used POSIX symbols without declaring their headers
(`statvfs`/`fstatvfs`, `TFD_*`). They compiled only because another TU pulled the
header in transitively, and the breakage surfaced only when the layer was built
under a different target's feature-test flags. The rule that matters: **include
what the TU uses**. Building under one flag set is not evidence that the includes
are correct.
