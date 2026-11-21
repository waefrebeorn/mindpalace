# VSL isolation monolith split — gotchas (2026-07-22)

Split `src/runtime/wubu_ct_isolate.c` (638 LOC) into `ct_iso_seccomp.c/.h` +
`ct_iso_cgroup.c/.h` + `ct_iso_ns.c/.h` + a trimmed orchestrator. Two concrete
traps that cost iterations, captured so the next split avoids them.

## Trap 1: Makefile link lines use the `.c` form, not `.o`
WuBuOS test recipes compile+link in one `$(CC) ... $(RT)/wubu_ct_isolate.c ...`
step (NOT `$(RT)/wubu_ct_isolate.o`). So a `replace_all` keyed on
`wubu_ct_isolate.o` updates ONLY prerequisite lines and MISSES every link line
-> `undefined reference to wubu_ct_child_isolation` / `runtime_to_seccomp` at link
time. Fix: do a SECOND `replace_all` on `$(RT)/wubu_ct_isolate.c` -> same token with
the three new `.c` files appended. Prereq lines may end up with harmless duplicate
`.o` entries (make-tolerant) — dedupe `RT_OBJS` by hand if you care about hygiene.

## Trap 2: slicing a `.c` by arbitrary line ranges cuts mid-definition
Naive `sl(580,631)` grabbed `wubu_seccomp_install` (which sat at line 595, *inside*
the "cgroup" range) into the wrong module, and the seccomp file lacked `CtRuntime`
(defined in wubu_host_exec.h). Also `wubu_ct_child_isolation` (521-584) built the
seccomp filter inline (used `filter_init`/`g_seccomp_*_allowlist` defined in the
seccomp slice) — so it belonged in the seccomp file, not the orchestrator.
Correct slice (from `git show HEAD:.../wubu_ct_isolate.c` line numbers):
- seccomp: 38-463 (filter infra + `wubu_ct_apply_seccomp`) + 521-584
  (`wubu_ct_child_isolation`) + 595-633 (`wubu_seccomp_install`).
- cgroup: 585-594 ONLY (`wubu_cgroup_write` helper; the cgroup create/set/attach
  ops live in the pre-existing `wubu_ct_isolate_cgroup.c`).
- ns: 634-638 (`wubu_ns_unshare`); move `WUBU_NS_FLAGS` macro (line 380) into
  `ct_iso_ns.h` so both the ns file and the orchestrator see it.
- orchestrator: header 1-37 + 466-520 (`wubu_ct_setup_isolation`).
Always re-derive function start lines with `grep -nE "^(static )?(int|void) .*\("`
on the git-original before slicing. Promote `static` fns the new module needs
publicly (e.g. `runtime_to_seccomp`) into the new header + drop `static` in the `.c`.

## Verification
After split: compile each new `.c` standalone with
`gcc -O2 -std=c11 -D_GNU_SOURCE -I src/runtime -c src/runtime/<f>.c`. Then run the
real gates: `make test_wubu` (56/56), `test_launch`, `test_host_exec`, `test_dos_proc`,
`test_syscall`. All passed — the split is behavior-preserving.
