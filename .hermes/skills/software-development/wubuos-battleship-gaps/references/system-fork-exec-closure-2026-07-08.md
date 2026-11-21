# system()→fork+exec closure — techniques & pitfalls (2026-07-08)

Captured while closing the last 10 live `system()` calls in WuBuOS (commits
a74dd7b). Form≠function rule: every `system("cmd")` / `popen("cmd")` in `src/`
is a REAL_GAP; close it by routing through a shared shell-free launcher.

## 1. The shared dependency-free helper pattern

Do NOT inline a fork+exec in every call site, and do NOT route through
`wubu_exec.c` (it pulls container/compiler/HolyC deps and will cascade a link
explosion). Create a TINY standalone file:

`src/runtime/wubu_spawn.c` (+ `wubu_spawn.h`):
```c
int wubu_run_program(const char *file, char *const argv[], bool silent) {
    if (!file || !argv) return -1;
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        if (silent) { int fd = open("/dev/null", O_WRONLY); dup2(fd,1); dup2(fd,2); }
        execvp(file, argv);
        _exit(127);                 // exec failed -> conventional code
    }
    int st; while (waitpid(pid, &st, 0) < 0 && errno == EINTR) {}
    return WIFEXITED(st) ? WEXITSTATUS(st) : -1;
}
```
Callers pass an explicit `argv[]` (no `/bin/sh`):
```c
char *argv[] = {"curl", "-fsSL", "-o", dst, src, NULL};
rc = wubu_run_program("curl", argv, true);
```
Exit-code semantics: a missing program returns **127** (exec failed), not -1;
propagate `WEXITSTATUS` so `false`→1, real programs→their code. The regression
test must assert 127 for a missing binary, not -1.

## 2. PITFALL — tokenizer must TERMINATE the token at a closing quote

When replacing `system("cmd with 'single quoted arg'")` with a fork+exec, you
must split tokens yourself. A naive single-quote toggle leaves the `'` INSIDE
the token:
```c
// WRONG: at the closing ', toggle in_q and continue, but never null-terminate.
// Result: argv[1] = "/tmp/wubu spawn q_X'" (stray quote) -> touch can't find it.
if (*p == '\'') { in_q = !in_q; p++; continue; }
```
FIX — on a closing quote, terminate the token here:
```c
if (*p == '\'') {
    if (in_q) { *p = '\0'; argv[argc++] = tok; tok = NULL; }  // end token AT quote
    in_q = !in_q;
    p++;
    continue;
}
```
Test must prove quoting works WITHOUT a shell: `net_cmd("touch 'a b c'")` must
create exactly one file named `a b c` (no word-splitting, no glob, no `>`
redirect interpretation). A `>` inside the arg stays a literal arg — do NOT
assert a redirect happened.

## 3. PITFALL — Makefile link cascade when extracting a shared helper

This bit hard. After moving `wubu_run_program` into `wubu_spawn.c`, every
direct-link test target that compiles a file using it must add
`$(RT)/wubu_spawn.c` to ITS link line, or you get
`undefined reference to wubu_run_program`. Targets affected this session:
`test_oci`, `test_network`, `test_jit`, `test_apps2`,
`test_container_registry`, plus ALL `$(JIT_SRCS)`-based targets
(`test_wubu`, `test_high_gui`, `test_holyd`, `paint`, `doom`, hosted, …).

Workflow that avoids the whack-a-mole:
1. `grep -nE '\$\(JIT_SRCS\)' Makefile` → every one of those lines needs
   `$(RT)/wubu_spawn.c` inserted (use `replace_all` on the common
   `\$(JIT_SRCS) \` / `\$(JIT_SRCS) $(COMP)/holyc_lexer.c ...` substrings).
2. Self-contained targets (`wubu_image_ops.c`, `wubu_netlink.c`, `wubu_codec.c`)
   previously needed NO extra object; now add `$(RT)/wubu_spawn.c`.
3. Put the helper in `RT_OBJS` so `make runtime`/`make hosted` pick it up.
4. After edits: `make clean && make runtime && make hosted && make test`.
   The colorized tail of `make test` hides errors — grep explicitly:
   `make test 2>&1 | grep -iE 'error|undefined reference'`.

Keep the helper DEPENDENCY-FREE (only POSIX fork/exec/wait + open). If you
instead put the definition in `wubu_exec.c`, every target pulling it inherits
the container/compiler/HolyC object graph → far worse cascade.

## 4. PITFALL — qsort over an array of pointers needs a double-deref comparator

`compare_games(const void *a, const void*b)` was written
`ga = (GameLibraryEntry*)a;` — but the array element is a
`GameLibraryEntry*`, so `a` is `GameLibraryEntry**`. The comparator then read
the pointer's BYTES as a struct, corrupting the sort and returning garbage
pointers. FIX:
```c
const GameLibraryEntry *ga = *(const GameLibraryEntry *const *)a;
const GameLibraryEntry *gb = *(const GameLibraryEntry *const *)b;
```
General rule: if you `qsort` an array of `T*`, the comparator must dereference
one level deeper than for an array of `T`. A single-element array (n==1) makes
qsort a no-op and MASKS this bug — it only surfaces at n>=2, so test with >1
entry.

## 5. PITFALL — static filtered[] buffers vs. the live instance

`wubu_gamelib_list_games()` returns a `static GameLibraryEntry *filtered[]`.
When another function reads `g_gamelib.games[]` through that static buffer, it
can resolve to a different `g_gamelib` instance than the caller's (cross-TU
static global), yielding pointers whose fields are empty/garbage even though
`state->games[0]` is correctly populated. If you see "list returns a pointer
whose fields are empty but the stored object is fine," prefer iterating the
live array directly in the caller:
```c
for (int i = 0; i < g_gamelib.game_count; i++) {
    GameLibraryEntry *g = &g_gamelib.games[i];
    ...
}
```
This is self-contained and immune to the static-buffer lifetime / instance
split. (The existing `list_games` callers in the test still pass.)

## Regression-test shape for a closure (required by project rules)

Every closed gap needs a test asserting FIXED BEHAVIOR, not just non-crash:
- `test_spawn` (`wubu_spawn_test.c`): real op happened (file created), exit
  codes propagate, shell metacharacters NOT interpreted (no `/bin/sh`).
- `test_container_registry` (`wubucontainer_test.c`): register succeeds, count
  increments, duplicate rejected, NULL/empty rejected.
- `wubu_gamelib_test.c`: build registers N entries, clear drops exactly N.
