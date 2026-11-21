# NT slot ABI and capability probing

Depth behind the always-on rules in SKILL.md's "SLOT ABI AND PROBING" section.
Read this when you are changing `g_nt_dispatch`, adding a probe/query API, or writing
a gate that reasons about which syscalls are supported.

## Why a probe is necessary at all

A caller deciding whether to use syscall N has two bad options:

1. **Call it.** Real handlers may have side effects (create an object, write a file,
   signal an event) -- a capability check must be inert. And the return value cannot
   distinguish "unsupported" from "not yet implemented": an EMPTY slot and a STUB
   both answer `NOT_IMPLEMENTED`.
2. **Inspect the table directly.** It is file-scope static; exposing it breaks the
   encapsulation that lets registration order change safely.

So the surface needs a third thing: a state query with no side effects.

```c
typedef enum {
    WUBU_NT_SLOT_EMPTY = 0,   /* nothing registered -> NOT_IMPLEMENTED */
    WUBU_NT_SLOT_STUB,        /* placeholder; also NOT_IMPLEMENTED      */
    WUBU_NT_SLOT_REAL,        /* genuine handler                        */
    WUBU_NT_SLOT_CONFLICT     /* two REAL handlers claimed it           */
} wubu_nt_slot_state_t;

int  vsl_nt_probe(uint32_t num, wubu_nt_slot_state_t *state);
void vsl_nt_slot_counts(uint32_t *empty, uint32_t *stub,
                        uint32_t *real, uint32_t *conflict);
```

CONFLICT is reported per-slot (set by `nt_record_collision`) so a contested syscall
is visible through the same query instead of only via a log line.

## The NULL-before-init trap

`g_nt_dispatch[]` is zero-filled statically and populated lazily on the first
dispatch (`nt_dispatch_init()`). Its "empty" sentinel is `vsl_sys_nosys`, but before
init every entry is **NULL**.

Any classifier that tests only `!= vsl_sys_nosys` therefore reports the whole table
as populated on a fresh process. This is not hypothetical -- it made
`vsl_nt_coverage()` report **512** registered slots while the contract sweep reported
**412**, and it made a first-cut probe call all 512 slots REAL.

The rule: treat `NULL || vsl_sys_nosys` as EMPTY in coverage, counts and probe alike.
Make the test assert the pre-init state explicitly (probe before any dispatch and
require zero REAL slots), because that state is invisible to every test that sweeps
first.

## Fail-closed probe semantics

`vsl_nt_probe(num, &st)` writes `WUBU_NT_SLOT_EMPTY` FIRST, then validates `num`. So a
refused probe (out of range, or a NULL state pointer) leaves a safe value rather than
the caller's previous contents. A caller that forgets to check the return code sees
"unsupported" instead of acting on stale stack data. Assert this in the gate -- do
not assert that the output is untouched, because writing EMPTY is the better
contract.

## Conformance gates that follow from the above

- **Partition check:** empty + stub + real + conflict == NT_TBL_SIZE, and the
  per-slot scan agrees with `vsl_nt_slot_counts()`. Catches any classifier drift.
- **Fail-closed dispatch:** out-of-range numbers return `NOT_IMPLEMENTED`. Note
  ordinal 0 is special-cased in the dispatcher and DOES fan out to real handlers, so
  it must be excluded from "fails closed" assertions.
- **No contests:** collision count stays zero; a non-zero value is a defect, never
  expected state.

Measured on the tree this was written against: 100 empty, 17 stub, 395 real,
0 conflict (412 of 512 non-empty).

## Contract rules worth keeping next to the code

- A number's identity is frozen once its slot leaves EMPTY. Additive changes only.
- Retirement = replace the handler with a logging STUB and reserve the number
  forever. Never re-use a retired ordinal for a different syscall.
- A REAL-over-REAL overwrite must stay VISIBLE (counted and probed). Removing that
  visibility is an ABI break even if the dispatch behaviour is unchanged.
- These live in `docs/ABI.md`; the doc and the probe must be updated together.
