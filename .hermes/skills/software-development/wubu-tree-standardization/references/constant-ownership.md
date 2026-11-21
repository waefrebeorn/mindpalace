# Constant-ownership triage table

Companion to the org-wide census section in SKILL.md. A duplicate-define hit
is not automatically a bug — classify BEFORE editing. The classes below are
ordered by how much damage they do when left alone.

## Fix classes (real defects)

| class | mechanism | fix |
|---|---|---|
| Include-guard collision | two different headers share one guard macro; whichever is included second is SILENTLY SKIPPED | rename guards layer-qualified (`WUBU_KERNEL_*`, `WUBU_RUNTIME_*`, `WUBU_APP_*`, `WUBU_*_IMPL_H`); grep the guard tree-wide first — a metric or flag may ALSO own that name |
| Guard/metric overload | a guard macro name reused as a value define (e.g. a 32px height) | rename the value (`*_HEIGHT`); bind the audit allowlist too |
| Encoder/interpreter drift | an ISA encoder and its interpreter keep private opcode tables | one shared opcode header; the EXECUTOR's numbering is the contract; add the comparison battery that was missing (see wubunos-compiler-testing references/opcode-contract.md) |
| Format facts per consumer | magics / register offsets / PCI IDs re-defined in each layer | one `include/wubu_<thing>.h` shared header; every layer includes it |
| Overloaded ID name | one vendor/class name means two different IDs in two drivers | distinct names per ID (AMD vs AMD_ATI; BROADCOM vs LSI); comment the corporate history if it explains the confusion |
| Wrong value, right name | one table's constant is simply incorrect (a magic that rejects valid files) | fix the loser, keep the winner as owner, add the must-reject/must-accept regression gate |
| Same name, different array | a protocol cap re-defined larger for a host-side table of a different type | rename the second (`*_HOST_MAX_*`); both named, no overload |
| Private math table | a .c re-defines constants its own .h already owns | .c includes the .h and uses the owner's names; keep only impl-local constants (NAN/INF/hex-float) in the .c |

## Accepted classes (document, do not "fix")

- **Feature-test macro ladders** (`_GNU_SOURCE`, `_POSIX_C_SOURCE`,
  `_XOPEN_SOURCE`): per-TU by design, values differ on purpose.
- **Guarded post-system fallbacks** (`#ifndef M_PI ... #endif` after the
  system header): the fill-in pattern; only active when the system lacks it.
  A fallback defined BEFORE the system header is the bug variant — it shadows
  the real values with a private numbering.
- **File-local test caps/paths** (MAX_ENVS, MAX_STEPS, H/W, NSROOT, OUT_DIR):
  legitimate unless two tests share a harness; merge only then.
- **Layer-local spec constants** (UEFI TRUE/FALSE vs kernel parity): both
  correct in their own layer; a conflict only if co-included.
- **`#ifdef` capability ladders** (HAVE_CUDA defined 1 then 0): conditional
  compilation, not two owners.

## Classifier hygiene

Compare values comment-free AND numeric-spelling-normalized: strip trailing
`u/U/l/L/f/F`, parse int base 0 else float, compare canonically. Otherwise
`0x30` vs `0x0030` and `3.14f` vs `3.14` read as conflicts and the frontier
number lies. Function-like macros are not constants — skip them. Idiomatic
`calloc(1, sizeof T)` is not a literal allocation bound — skip it in the
alloc category (the `1` is the count, the size is type-derived).

## Gate discipline for ownership fixes

Every merged owner needs the gate that would have caught the drift: a
must-reject case for a wrong magic, a callback-fires case for a dead hit-test,
a value-equality case for a cap. "It compiles" is not the gate; the behaviour
that depended on the constant is.
