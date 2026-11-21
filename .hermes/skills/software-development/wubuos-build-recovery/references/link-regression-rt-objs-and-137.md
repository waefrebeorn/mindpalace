# Link-Regression: RT_OBJS-missing-object + SIGKILL(137) debugging

Two regression classes hit during the 2026-07-20 HolyC-eval / holyd-daemon fix
session. Both look like "build is broken" but are specific, diagnosable states.

## 1. Object on a recipe link line but ABSENT from RT_OBJS

**Symptom:** `make hosted` fails with either
`ld: cannot find src/runtime/wubu_holyd_input.o` (object deleted/stale, never rebuilt)
or `undefined reference to wubu_holyd_set_pointer_handler` even though
`src/runtime/wubu_holyd_input.c` clearly defines it (a STALE `.o` from before the edit
was linked).

**Root cause:** the `hosted:` recipe listed `$(RT)/wubu_holyd_input.o` (and several
other `wubu_holyd_*.o`) on its link line, but those objects were never added to
`RT_OBJS`. So `make runtime` (which builds `RT_OBJS`) never produced them; the link
used whatever stale `.o` existed or failed to find one.

**Diagnose:**
```sh
# Is the object even in the expanded RT_OBJS? (empty = missing from the var)
make -s --eval='p:; @echo $(RT_OBJS)' p 2>/dev/null | tr ' ' '\n' | grep holyd_input
# Does the built .o actually define the new symbol? (empty = stale .o)
nm src/runtime/wubu_holyd_input.o 2>/dev/null | grep set_pointer
```

**Fix:** add the missing objects to `RT_OBJS` (so `make runtime` builds them) and keep
them on the recipe link line:
```make
RT_OBJS   = ... $(RT)/wubu_holyd.o $(RT)/wubu_holyd_session.o \
            $(RT)/wubu_holyd_exec.o $(RT)/wubu_holyd_repl.o \
            $(RT)/wubu_holyd_input.o $(RT)/wubu_holyd_window.o \
            $(RT)/wubu_holyd_9p.o $(RT)/wubu_holyd_event.o $(RT)/wubu_holyd_save.o ...
```
Then `make clean && make runtime && make hosted`. Verify with `nm` that the new
symbol is present in the rebuilt `.o`.

**Edits that cause this:** adding a module to a `hosted:` / `test_*` link line (the
prior session added `wubu_holyd_*.o` to `hosted`) but forgetting the object-list var.
After ANY such edit, run the `make -s --eval` membership check above for every new
object.

## 2. SIGKILL (137) during a test run = OOM-masked infinite loop

**Symptom:** `./src/runtime/wubu_holyc_agi_test` (or any eval/parse test) dies with
exit 137 and prints nothing past `[DBG] main entered`. Looks like an OOM segfault.

**Root cause (this session):** `wubu_holyd_eval` wrapped source in `{ %s }` and called
`hc_parse_block`. On garbage input (`"this is not holyc @@@"`), `parse_stmt` returned a
node WITHOUT advancing the lexer, so `parse_block`'s `while` loop never terminated →
it allocated AST nodes forever until the cgroup SIGKILLed the process →
`hc_ast_new()` returned NULL → `n->child = expr` deref'd NULL.

**Why it looked like OOM:** running under `ulimit -v 400000` (a memory cap) the same
crash reports 137 and hides the NULL-deref. The fix is to debug WITHOUT the cap.

**Debug recipe (gets the real backtrace):**
```sh
# NO ulimit cap — let it allocate so gdb sees the actual fault
gdb -batch -ex run -ex bt --args /tmp/repro_g
# -> Program received signal SIGSEGV, Segmentation fault.
#    parse_stmt (p=...) at holyc_parse.c:572
#    572         n->child = expr;        <-- expr is NULL (hc_ast_new failed)
# #0  parse_stmt
# #1  parse_block
# #2  hc_parse_block
# #3  wubu_holyd_eval
```
The backtrace shows the loop guard is missing, NOT a memory error.

**Fix applied:** add a per-statement progress guard in `parse_block`:
```c
while (peek(p) != HC_TOK_RBRACE && peek(p) != HC_TOK_EOF) {
    int start_pos = p->lex->pos;
    hc_ast_add_stmt(block, parse_stmt(p));
    if (!p->has_error && p->lex->pos == start_pos) {
        parse_error(p, "unexpected token in block");
        break;
    }
    if (p->has_error) break;
}
```
and ensure the eval keeps the persistent `gen.data` section across runs (don't free it
after each eval — that lost module-level globals like `I64 acc = 10;`).

**Rule of thumb:** a test that dies with 137 *inside* the binary (not at `cc`/`ld` link
time) is a runtime logic bug (infinite loop / runaway allocation), not the link-time
OOM class. Drop the `ulimit` cap and run under `gdb` to see the truth.
