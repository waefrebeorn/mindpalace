# NT Ordinal Source-of-Truth & Dispatch-Collision Root Cause (2026-07-23)

This session fractured the repo by merging a broken NT-6.1/W11 extension branch
(`nt-parity-wip`) into the canonical tree. The breakage was NOT a simple ordinal
typo — it was **60 colliding dispatch slots** + invented ordinals for extension
syscalls. Captured here so the next session does not repeat it.

## The three ReactOS ordinal sources (KNOW THE DIFFERENCE)

| File | What it is | Line number = ? | Usable for mapping? |
|------|-----------|-----------------|---------------------|
| `reactos-study/reactos/ntoskrnl/sysfuncs.lst` | base 296 syscalls, `NtName  <argc>` | **1-based NT ordinal** (NtClose=28, NtAddAtom=9, NtCreateProcess=50) | YES — base 296 |
| `reactos-study/reactos/ntoskrnl/include/sysfuncs64.h` | `SVC_(Name, N)` table, **prefix-less** (AddAtom, not NtAddAtom) | line = 64-bit ordinal BUT order DIFFERS from lst (NtClose=13 here vs 28 in lst) | NO — arg-counts, wrong base order |
| `vsl_syscall_list.h` (in WuBuOS tree) | `VSL_SYSCALL(name, argc) // NtXxx` | line = WuBuOS-internal ordinal (also diverges) | NO — internal only |

**Rule:** for the base 296, `sysfuncs.lst` line number IS the ordinal. `sysfuncs64.h`
and `vsl_syscall_list.h` are NOT authoritative for ordinal numbering (they're
arg-count lists / internal tables with different ordering). The `nt-parity-wip`
branch used `vsl_syscall_list.h` ordinals (NtAddAtom@71, NtCreateProcessEx@77),
the test used a THIRD scheme, and `sysfuncs.lst` a fourth — three+ divergent maps,
none agreeing. That is the fracture made literal.

## Extension syscalls (ALPC / WNF / Enclave / IoRing / Partition / WorkerFactory / KTM)

`sysfuncs.lst` has **ZERO** entries for these. They are NOT in the base 296. The
extension branch INVENTED ordinals 121–486 for them, which **collided** with real
base syscalls (e.g. `NtAlpcCreatePort` was placed at slot 125 = `NtOpenJobObject`).
So `dispatch(125)` ran `alpc_create_port`, which wrote to a bad out-pointer → SIGSEGV.

Correct placement: assign extension blocks to **297+ contiguously** (RecyclerView:
ALPC at 297+, WNF, Enclave, Partition, IoRing, WorkerFactory, KTM, etc.), and
verify NO two handlers share a slot. The real ReactOS ordinal ranges for ALPC/W11
are higher than 296 but the EXACT numbers must be verified against a complete
ReactOS syscall table (the 64-bit `KeServiceDescriptorTable` ordering) before use —
do not guess from `sysfuncs64.h` line numbers (they disagree with `sysfuncs.lst`).

## The collision bug (why it segfaults, not just fails)

`nt_dispatch_init()` loops over modules calling `vsl_nt_<subsys>_register(tbl,size)`,
each doing `tbl[N-1] = handler;`. When two handlers register the same N, the LAST
one wins — silently. So `NtAddAtom` (registered at 71 by atoms module) gets
overwritten by `NtCreateProcessEx` (also at 71 by process module) → a test calling
`dispatch(71, &atom_out, ...)` runs `create_process_ex`, which does
`*(uint32_t*)a_proc_out = h;` where `a_proc_out` was the atom *name string*
→ WRITE to a bad pointer → SIGSEGV. ASAN pinpoints it:
`gdb`-free approach: build a `-fsanitize=address,undefined` binary and run under
`timeout -k 5 60` (plain runs can HANG nondeterministically on a bad read).

## Quarantine decision (do not re-merge blindly)

The `nt-parity-wip` branch stays on origin as a SEPARATE research line. It was NOT
merged to master because, beyond collisions, its `vsl_syscall_nt_test.c` dispatch
numbers were corrupted to a third ordinal scheme and the test itself segfaulted.
To revive it properly:
1. Run `scripts/nt_dispatch_collision_check.py` — must report CLEAN (0 collisions).
   On nt-parity-wip it reported **60 colliding slots** — that is the gate.
2. Re-derive every base handler ordinal from `sysfuncs.lst` (line = ordinal).
3. Reassign all extension handlers to 297+ contiguous, collision-free.
4. Rewrite the test's `dispatch(N, ...)` calls to the ReactOS ordinal of the syscall
   named in each call's nearest `CHECK(...)` message (the CHECK string is the
   authoritative per-call signal; section headers lie because they list ordinal
   TUPLES, not per-call mappings).
5. Build with `scripts/build_nt_test_lite.sh run` and confirm `Results: NNN passed`.

## Single-canonical-repo note (couples to wubuos-architecture skill)

After this session there is ONE WuBuOS checkout: `/home/wubu/wubuos` = `origin/master`.
The old `.hermes/.../home/myseed` duplicate was DELETED. Never create a checkout
under the Hermes profile path. The collision check + ordinal discipline below apply
only to work done on `origin/master` (or a properly-fixed `nt-parity-wip`).
