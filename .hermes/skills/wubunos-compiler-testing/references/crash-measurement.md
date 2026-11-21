# Crash-measurement harness pattern (WuBuNOS gauntlet)

When you need to know *which* gauntlet/test-suite entries crash the frontend
(rather than merely fail to parse), you must isolate each entry in its own
process and detect a real signal termination. The naive pipe approach has a
subtle trap that produces FALSE crash flags — documented here so the next
session doesn't repeat it.

## The pipe-read race (TRAP — causes false "crash" flags)

```c
/* WRONG: parent reads the child's 1-byte result over a pipe */
int pfd[2]; pipe(pfd);
pid_t pid = fork();
if (pid == 0) {
    close(pfd[0]);
    uint8_t r = (hd_build_mir(src,&prog)==0) ? 0 : 1;
    write(pfd[1], &r, 1);   /* may be lost if child _exit()s immediately */
    close(pfd[1]); _exit(r);
}
/* parent */
uint8_t res = 2; size_t g = 0;
while (g < 1) { ssize_t n = read(pfd[0], &res+g, 1-g); if (n<=0) break; g+=n; }
if (g != 1) crash++;        /* <-- FALSE POSITIVE: pipe read got 0 bytes
                                because the write raced the process death */
```

A pipe `read()` can return 0 bytes when the child `_exit()`s before/as the
`write()` flushes. The parent then mis-flags a **clean parse-reject** (rc=1) as
a **CRASH** (`g != 1` → REALCRASH). This produced 6 false crash flags in the
2026-08-19 session that ASAN/UBSAN loops (10–20 runs each) proved were clean.

## Reliable method 1 — file-based result reporting (preferred)

```c
/* child writes a status file, parent reads it AFTER reaping */
FILE *g = fopen("/tmp/cr.bin", "wb");
if (g) { fputc(r ? 2 : 1, g); fclose(g); }
return r;
/* parent after waitpid: */
int b = 0; FILE *f = fopen("/tmp/cr.bin", "rb");
if (f) { b = fgetc(f); fclose(f); }
/* b==1 => built OK, b==2 => parse-reject, file missing => real crash/hang */
```

The filesystem write is durable across the child's death; no byte is lost.

## Reliable method 2 — retry the write + WIFSIGNALED only

If you must use a pipe, retry the write to drain it, and treat **only**
`WIFSIGNALED(status)` as a real crash — never the `g != 1` heuristic:

```c
uint8_t res = 2; size_t w = 0;
while (w < 1) { ssize_t n = write(pfd[1], &r+w, 1-w); if (n<=0) break; w+=n; }
...
int status; waitpid(pid, &status, 0);
if (WIFSIGNALED(status)) crash++;   /* real crash: SIGSEGV/SIGFPE/SIGABRT/... */
```

## Recommended harness shape (used in session 2)

- Fork a grandchild per entry (so a crash can't take down the classifying
  parent). Arm `signal(SIGSEGV/SIGFPE/SIGABRT/SIGBUS/SIGILL, SIG_DFL)` in the
  child so it dies on its own fault instead of being caught.
- 8s per-entry `alarm()`/watchdog: if it doesn't finish, `kill(SIGKILL)` and
  count as crash/hang.
- Classify into three buckets: `built` (hd_build_mir==0), `parsefail`
  (build!=0, clean exit), `crash` (WIFSIGNALED or file missing).
- For the HolyD full-C gauntlet (18,259 external tests), the result was
  ~17,158 parsefail + **0 reproducible crashes** (after the SIGFPE clamp fix
  in `holyd_parse.c`). The parse-fails are frontend scope (expression-only
  frontend), NOT missing tests.

## Verifying a crash is real (ASAN/UBSAN loop)

A single "crash" flag is not proof. Build the probe with
`-fsanitize=address,undefined` and run the suspect entry 10–20×; if it
returns cleanly (rc=1, 0 sanitizer hits) every time, the original flag was a
classifier artifact, not a compiler bug.
