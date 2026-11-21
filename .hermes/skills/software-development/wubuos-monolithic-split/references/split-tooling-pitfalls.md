# Split-Time Tooling Pitfalls (WuBuOS monolith busting)

Concrete traps hit while splitting `vsl_nt_proc.c`, `wubu_bottles.c`, `wubu_metal.c`.
Each is a *tooling/workflow* failure, not a code failure — so encode it here.

## 1. hermes `read_file`/`write_file` silently TRUNCATE large files

**Symptom:** After `write_file` of the WuBuOS `Makefile` (897 lines), the file came
back as **500 lines** with a literal `...` injected mid-line ~char 2105 and the entire
tail (targets `test_oci`, `test_spawn`, `test_network`, ~400 lines) **gone**. `make test`
then failed with `No rule to make target 'test_oci'`.

**Root cause:** `hermes_tools.read_file` caps output (~100K chars / paginated) and
`write_file` persists whatever it received — if the read was truncated, the write
truncates too. Large Makefiles exceed the safe threshold.

**Fix (ALWAYS for large files):** read + write with `open()` inside `execute_code`,
never the `hermes_tools` read/write wrappers:

```python
p = "/home/wubu/.hermes/profiles/mind-palace/home/myseed/Makefile"
with open(p) as f:
    lines = f.readlines()          # raw, no truncation
# ... do edits ...
with open(p, "w") as f:
    f.writelines(lines)
```

After any Makefile edit, VERIFY before building:
```python
with open(p) as f:
    L = f.readlines()
print(len(L), "lines")                       # expect 896/897, NOT 500
print("literal ...:", "..." in "".join(L))   # must be False (a real '...' in a target is corruption)
print("test_oci defined:", any(l.startswith("test_oci:") for l in L))
```

If you ever see the file dropped to ~500 lines, `git checkout -- Makefile` and
re-apply edits via the `open()` Python path (NOT read_file/write_file).

## 2. Dispatch-slot scramble when splitting a register-table file

Files like `vsl_nt_proc.c` end with one `vsl_nt_proc_register(tbl, size)` that maps
Nt syscall NUMBERS to handler fns (`tbl[277-1] = vsl_nt_write_virtual_memory;`).
When you slice functions into per-subsystem modules, it is easy to mis-assign the
number->fn pairs (e.g. put `57->set_timer` instead of `57->create_timer`).

**This is SILENT** — it compiles fine, links fine, but dispatches the WRONG handler,
so `NtCreateTimer` calls `set_timer` and fails. `test_vsl_nt` went 205/0 -> 199/6.

**Fix:** After carving the modules, extract the ORIGINAL register block verbatim and
reproduce the exact mapping in every new module's `register()` fn:

```bash
git show HEAD:src/runtime/vsl/vsl_nt_proc.c | sed -n '/void vsl_nt_proc_register/,/^}/p'
```

Then diff your new `vsl_nt_*_register()` tables against it slot-by-slot. Verify with the
TARGETED test and compare to the pre-split baseline:
```bash
git stash && make test_vsl_nt 2>&1 | grep -E "passed|failed"; git stash pop
# your split must match the baseline (205 passed, 0 failed)
```

Rule: **split functions freely, but treat the dispatch table as sacred — copy it exactly.**

## 3. Circular-dependency detection — DO NOT split these

Before splitting, build a call graph (regex over `wubu_\w+\(` inside each fn body) and
check cross-concern calls. If concern A calls concern B AND B calls A, a split forces a
god header exporting everything -> violates "no god headers / self-contained". Examples
correctly LEFT as monoliths this session:

- `wubucontainer.c` — `wubu_container_convert` calls `wubu_ctr_send_request` (engine) and
  `wubu_ctr_cleanup_engine` calls `wubu_container_init`; fully cyclic.
- `wubu_editor.c` — all 40 fns call `wubu_ed_current_tab` (CORE); undo records buffer ops;
  buffer fns call undo fns. Circular. Splitting -> god header.

**Decision rule:** if the residual core is one concern, OR splitting needs a god header,
it is NOT a monolith per the rule — leave it. The codebase's genuine multi-concern
monoliths were `vsl_nt_proc.c`, `wubu_bottles.c`, `wubu_metal.c` (all busted). Survey
the top-18 files by function-prefix; most large files are already split into siblings
(`explorer_*`, `wubu_editor_*`, `fat32_*`, `interrupt_*`).

## 4. Verifying a split is real (not form-without-function)

Grep new modules for stub markers; the user's recurring bug is placeholder windows:
```bash
grep -nE "TODO|FIXME|not implemented|unimplemented|stub|XXX" src/.../new_module.c
```
A comment noting *future* work inside a function that does real work is OK (e.g.
`wubu_bottle_install_deps` validates WINEPREFIX and marks deps — not a stub). Only a
function whose body is empty / single `return 0;` with no logic is a form-without-function
gap and must be wired to the real engine.

## 5. `.o`-as-list vs `.c`-as-source DUAL reference (the `styx.c` trap)
When you delete a monolith `X.c` and replace it with modules `X_a.c X_b.c …`,
a single `replace_all` on `$(RT)/X.o` is NOT enough. The same logical
unit is referenced in the Makefile in **TWO distinct syntactic roles**, and the
`.o` form only covers one:

- **(a) Object-list token** — `$(RT)/X.o` inside the big backslash-continued
  variables `RT_OBJS`, `HOSTED_OBJS`, `APP_RT_OBJS`. One `replace_all` of
  `$(RT)/X.o` → `$(RT)/X_a.o $(RT)/X_b.o …` fixes ALL of these.
- **(b) Compile SOURCE** — `$(RT)/X.c` (not `.o`) appears as a literal
  source file in ~15 *test recipe* bodies, e.g.
  `… $(RT)/X.c $(RT)/styx_fid.c $(RT)/X_test.c -o $(RT)/X_test`.
  These are **`$(RT)/X.c`, not `$(RT)/X.o`**, so the `.o` replace_all
  leaves every one of them pointing at the now-DELETED `X.c` →
  `gcc: error: X.c: No such file or directory` on the first test.

**Fix (do BOTH passes, in order):**
```bash
# pass 1: object-list tokens (RT_OBJS / HOSTED_OBJS / APP_RT_OBJS)
#   replace_all:  $(RT)/X.o  ->  $(RT)/X_a.o $(RT)/X_b.o $(RT)/X_c.o $(RT)/X_d.o
# pass 2: compile-source sites (test recipes)  -- SEPARATE replace_all
#   replace_all:  $(RT)/X.c  ->  $(RT)/X_a.c $(RT)/X_b.c $(RT)/X_c.c $(RT)/X_d.c
```
Use `replace_all=true` on each form independently. After both, assert zero
residual references with the right guard:
```bash
grep -nE '\bX\.o\b'  Makefile && echo "STILL HAS .o" || echo "no .o refs"   # should be empty
grep -nE '[^a-z_]X\.c\b' Makefile && echo "STILL HAS .c" || echo "no .c refs"  # should be empty
# but CONFIRM the new module names ARE present:
grep -cE 'X_(a|b|c|d)\.(o|c)' Makefile   # expect ~23+
```
**Real example (2026-07-15):** dissolved `src/runtime/styx.c` (657 lines) into
`styx_names.c styx_enc.c styx_serve.c styx_parse.c` + `styx_internal.h`.
The `.o` replace_all repaired RT_OBJS/HOSTED_OBJS/APP_RT_OBJS + 6 test-recipe
*object* lists, but 13 test recipes still compiled `$(RT)/styx.c` as a source →
first `make test` recipe blew up with `styx.c: No such file`. The second
`replace_all` on `$(RT)/styx.c` fixed it. Final gate: `make runtime`
+ `make hosted` + `make kernel` + `make test` all green, `test_styx` 29/29.
Lesson: a deleted monolith's Makefile footprint is **two passes**, never one.
