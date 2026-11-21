# Monolith-Split Pitfalls: Dispatch Scramble + Stop-Splitting Survey

Hard-won lessons from the 2026-07-13 session that split `vsl_nt_proc.c`
(5 NT subsystems) and `wubu_bottles.c` (4 concerns) into self-contained
modules. These are the failure modes NOT covered by the generic split recipe.

## 1. Dispatch-slot SCRAMBLE (the silent regressor)

When the monolith uses a **dispatch-table register function** that maps
syscall/op numbers -> handler fns (e.g. `tbl[277-1] = vsl_nt_write_virtual_memory`),
a mechanical slice of function bodies + a hand-rewritten register block is
prone to **swapping the numbers**. The function bodies are copied verbatim
(correct), but the `tbl[N-1] = fn` mapping gets mis-transcribed.

Concrete bugs hit this session:
- vmem: `195` (write) and `277` (unlock) swapped; `264` (suspend_thread) was
  wrongly assigned to `unlock_virtual_memory`.
- timer: `26/57/254` -> `cancel/create/set` were assigned to
  `create/set/cancel` (all three rotated).

Symptom: compiles clean, links clean, but `test_vsl_nt` regressed from
205/0 to **199/6** -- specific syscalls now dispatch to the wrong handler.
The gate's `make test` (all tiers) stayed green because the affected tests
live in a specific `test_vsl_nt` target, not the default gate. **Always run
the subsystem's own targeted test after a split.**

### Fix / prevention
After generating the new modules, extract the ORIGINAL authoritative mapping
and diff your new register blocks against it:

```bash
git show HEAD:src/runtime/vsl/vsl_nt_proc.c | sed -n '/void vsl_nt_proc_register/,/^}/p'
```

Then for each new module, grep its `tbl[NN-1] = vsl_nt_*` lines and confirm
the (number, function) pairs match the original register block EXACTLY.
Bonus: a number used in two entries (e.g. `264` = both suspend_thread and
unlock in the original) means the LAST writer wins -- preserve that ordering
across your split register calls (the module registered last owns the slot).

### Mechanization
Prefer generating the register block programmatically from a verified
`regmap` list, then assert no number appears twice, rather than hand-typing
the `tbl[...]` lines.

## 2. STOP-SPLITTING: the circular-coupling / god-header trap

The user's rule "no monolithic files" does NOT mean "split everything."
A survey of the top ~18 largest files showed the genuine multi-concern
monoliths were the 3 already busted (`vsl_nt_proc.c`, `wubu_bottles.c`,
`wubu_metal.c`). The rest fell into two safe-to-leave classes:

- **Single-concern cores** (large by repetition or breadth, not by mixed
  concerns): `interrupt.c` (71 ISR stubs + APIC glue), `fat32.c`,
  `vsl_syscall_net.c`, `vsl_nt_io.c`, `bear_cudnn.c`, `holyc_codegen_expr.c`.
- **Already-split residuals** whose siblings exist: `explorer.c` (10
  `_explorer_*` siblings), `wm.c` (8), `wubu_editor.c` (3),
  `wubu_canvas.c` (4), `wubucontainer.c` (already has `wubucontainer_registry.c`).

Forcing a split on the residuals causes **circular module dependencies** and
requires a **god header** exporting nearly every symbol -- directly violating
"no god headers / keep modules self-contained" and the "simplify before
extending" directive. Concrete example: `wubu_editor.c` has 40 fns where
everything calls `wubu_ed_current_tab` [CORE] and buffer fns call undo fns;
a 6-way split would need a header exposing all of it.

### Procedure: survey BEFORE splitting
1. `find src -name '*.c' | xargs wc -l | sort -rn | head -18`.
2. For each candidate, group functions by prefix + map the **cross-concern
   call graph** (does concern A call concern B AND vice-versa?).
3. Only split if concerns are **acyclic** (leaves call down into a core, core
   never calls leaves). If cyclic -> leave it; splitting buys fragility, not clarity.
4. Report honestly when the frontier is exhausted -- do NOT fabricate
   artificial splits (that is a form-without-function of the refactoring urge).

## 3. Testability of a split whose real API shells out (DI ops table)

Some modules' real implementations `fork()`/`popen()` external binaries that
cannot run in CI (e.g. `wubu_archd_svc_*` shells `arch-chroot`/`systemctl`;
`wubu_bottle_run` execs `wine`). You still must verify the **dispatch routing**
(a ctl write -> correct handler) without executing the binary.

Pattern: define an **injectable ops struct** in the module header; production
wires the real fns, the test injects mocks that record which op was called.

```c
typedef struct wubu_ns_svc_ops {
    int (*svc_start)(WubuArchd*, const char*, const char*);
    /* ... stop/restart/enable/disable/status ... */
} wubu_ns_svc_ops_t;
extern const wubu_ns_svc_ops_t wubu_ns_svc_ops_real;  /* wired to real archd */
```

The pure dispatcher `wubu_ns_svc_ctl(d, root, svc, cmd, ops)` routes the verb
to the right op -- test asserts the mock recorded the expected op, and that
unknown verbs return -1. Production passes `&wubu_ns_svc_ops_real` (or NULL ->
defaults to it). No stubs, fully verified.

Caveat discovered the hard way: a test that calls the REAL exec path can
**hang** the CI runner (wine with no prefix/display blocks on `waitpid`).
For exec paths, either (a) use a bogus prefix so the launcher-existence guard
fails fast (returns -1 before `fork`), or (b) only assert routing, never
invoke the real binary in the test.
