# Splitting a Dispatch-Table Module (NT syscall / VSL handler style)

When a monolith registers its handlers into a shared dispatch table via a
`*_register(tbl, size)` function (the WuBuOS E1 NT-bridge pattern:
`vsl_nt_<subsys>_register` writes `tbl[N-1] = vsl_nt_foo;` into a 297-slot
array), splitting it into per-subsystem TUs is HIGH-VALUE but has one trap
that will silently regress tests: **the Nt-number → function mapping must be
preserved EXACTLY.**

## The trap (hit 2026-07-13)
`vsl_nt_proc.c` mixed 5 subsystems (vmem / process / thread / section /
timer). When extracting each subsystem's body into its own file, it is
tempting to rebuild the new `register` block from memory. That scrambles the
slots:

- Wrong: `tbl[26-1]=create_timer; tbl[57-1]=set_timer; tbl[254-1]=cancel_timer;`
- Right: `tbl[26-1]=cancel_timer; tbl[57-1]=create_timer; tbl[254-1]=set_timer;`

A wrong mapping makes `NtCreateTimer(57)` dispatch to `set_timer`, which reads
a handle that doesn't exist yet → returns `INVALID_HANDLE`. The function
BODIES were correct; only the dispatch slots were wrong. Symptom:
`test_vsl_nt` drops from 205/0 to 199/6 (failures cluster on the syscalls
whose slots you mis-mapped).

Also note: two different subsystems can legitimately use the SAME slot number
in the original single-function `register` (the LAST write wins). When you
split, each subsystem's `register` writes its own slot — so the FINAL
effective mapping = order of the `*_register()` calls in the facade. Mirror
the original's last-writer-wins outcome by calling the split registers in the
same relative order, OR (cleaner) keep each slot owned by exactly one
subsystem module so there's no collision.

## Correct procedure (verified, restored 205/0)
1. Extract each subsystem's function bodies verbatim into
   `vsl_nt_<subsys>.c` (opaque structs, minimal includes). The bodies are
   value — copy them exactly.
2. For the new `register` block, **do NOT invent the mapping**. Recover the
   authoritative mapping from the ORIGINAL monolith first:
   `git show HEAD:<path>/<monolith>.c | sed -n '/void <subsys>_register/,/^}/p'`
   and transcribe `tbl[N-1] = fn;` lines 1:1 into each new module's register.
3. Wire the facade: replace the single `vsl_nt_proc_register(...)` call with
   the 5 `vsl_nt_<subsys>_register(...)` calls, in an order that preserves the
   original last-writer-wins result.
4. Update the internal header: drop `vsl_nt_proc_register` decl, add the 5 new
   `*_register` decls.
5. Update `Makefile`: `RT_OBJS` + every test link line that named
   `vsl_nt_proc.o` → the 5 new `.o` files (grep for all 3 occurrences: the
   `RT_OBJS` line, the `runtime`-style link, and `test_vsl_nt`).
6. **Verify against baseline**: stash your changes, run the relevant test on
   HEAD to get the pre-split pass count, then unstash and confirm you match
   it. `git stash && make test_vsl_nt 2>&1 | tail; git stash pop`.

## Programmatic extraction gotcha
If you slice function bodies with a Python script, the regex that detects a
function start (`^(int64_t|void|...)\s+<prefix>_\w+\s*\(`) will NOT match
`void *vsl_nt_thread_tramp(void *p)` (the `void *` return type has a space).
Handle such trampolines with a hardcoded line-range slice, not the scanner.
Also: when building the `funcs` list as `[start, name]` then appending `end`,
unpack carefully — `for s,e,n in funcs` will bind `e=name` if you appended
`end` as the 3rd element (order `[start, name, end]`). Use explicit
`entry[0], entry[1], entry[2]`.
