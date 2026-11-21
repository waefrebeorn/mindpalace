# Hosting a real QEMU guest as a WuBuOS process (wubu_dos_proc pattern)

Verified approach used to make `src/runtime/wubu_dos_proc.c` actually boot a
real FreeDOS guest and capture its VGA frame (test_dos_proc 9/9). This is the
canonical "host delegation" module shape: a self-contained runtime module that
spawns a nested emulator and surfaces it through the Styx/9P namespace.

## Spawn: DIRECT fork()+execvp(), NOT the container API

A nested full emulator (QEMU) must run in the **host namespace**. Do NOT route
it through `wubu_ct_*` (`wubu_ct_native`/`wubu_ct_start` — chroot + cgroups v2 +
seccomp-bpf + bind mounts built for Arch containers). Two concrete failures that
produced when the module used `wubu_ct_*`:

1. **Hang inside launch, no child process.** `wubu_ct_start` runs isolation
   setup in the *parent* before `fork()`, and that machinery blocked — so
   `fork()` never happened, `host_pid` was a false positive (fork() of the
   parent "succeeded" in the sense the variable got set), and the test hung
   with no qemu child visible (`pgrep` shows nothing).
2. **Silent dead guest.** Even when spawn proceeded, `execv("qemu-system-i386", …)`
   with a *bare program name* fails — `execv` does NOT search `PATH` — so the
   child `_exit(127)` and the guest was dead while the module reported RUNNING.

### Correct spawn (the fix)
```c
pid_t pid = fork();
if (pid < 0) { p->state = DOS_PROC_FAILED; return p; }
if (pid == 0) {
    /* Child: no chroot/isolation — the guest VM owns its own address space.
     * execvp (not execv) so a bare "qemu-system-i386" resolves via PATH. */
    execvp(qemu_bin, argv);
    _exit(127);
}
p->host_pid = (int)pid;
p->state    = DOS_PROC_RUNNING;
```
Build `argv[]` with `-fda <freedos.img> -display none -vga std -chardev
socket,path=<qmp>.sock,server=on,wait=off,id=mon -mon chardev=mon,mode=control
-serial none -m 16 -no-reboot`.

## QMP handshake: negotiate ONCE, on connect

QEMU rejects a second `qmp_capabilities`. Move the greeting-read +
capabilities-negotiation into `qmp_connect()` (once, before any command),
instead of lazily inside the first `qmp_exec`. Then `qmp_exec` only sends the
command and reads the single-line JSON reply:
```c
static int qmp_exec(int fd, const char *cmd_json, char *resp, size_t resp_size) {
    if (fd < 0) return -1;
    char buf[1024];
    int n = snprintf(buf, sizeof(buf), "%s\n", cmd_json);
    if (write(fd, buf, n) < 0) return -1;
    return qmp_recv_line(fd, resp ? resp : buf, resp ? resp_size : sizeof(buf), 3000) > 0 ? 0 : -1;
}
```
Frame capture: `screendump` with `{"execute":"screendump","arguments":{"filename":"<x>.ppm"}}`
→ read the PPM file → decode `P6\n<W> <H>\n<max>\n` binary to RGBA. The QMP
protocol itself is healthy (a direct `socket`-client probe gets `{"return":{}}`
for both `qmp_capabilities` and `screendump`, producing a valid PPM), so any
capture failure is in the module's own client flow, not QEMU.

## Styx / 9P namespace mount needs mkdir -p

`wubu_dos_proc_styx_mount(root)` creates `<root>/proc/<pid>/dos/{screen,ctl,status}`.
A bare `mkdir(dir)` fails because `/proc` and `/proc/<pid>` intermediates don't
exist (returns `""`). Add a `mkdir_p()` helper that creates every component:
```c
static int mkdir_p(const char *path) {
    char tmp[1024]; snprintf(tmp, sizeof(tmp), "%s", path);
    for (char *p = tmp + 1; *p; p++) if (*p == '/') {
        *p = '\0';
        if (mkdir(tmp, 0755) != 0 && errno != EEXIST) return -1;
        *p = '/';
    }
    return (mkdir(tmp, 0755) == 0 || errno == EEXIST) ? 0 : -1;
}
```

## Debugging a hung integration test

If a real-QEMU test hangs with no child: (1) `pgrep -af '[q]emu-system-i386'`
(with the `[b]racket` trick so `pkill -f`/`pgrep -f` doesn't self-match and
kill its own shell — see `wubuos-test-suite`); (2) if no child, the spawn path
is the bug, not the test. Reproduce the exact qemu argv manually in a
`terminal(background=true)` and confirm the socket appears + a python QMP probe
(`socket` + `qmp_capabilities` + `screendump`) returns `{"return":{}}`. That
isolates "QEMU works" from "my module's spawn/client is wrong".

## Wire-in regression (Makefile)

When a shared `.c` (e.g. `wubu_exec_dos.c`) starts really calling this module's
API, every recipe linking it needs the module's `.o`. See `wubuos-test-suite`
"SWEEP discipline" — add `$(RT)/wubu_dos_proc.o` to `test_syscall`, `test_wubu`,
`test_styxfs`, etc. (all link `wubu_exec_dos.c`).
