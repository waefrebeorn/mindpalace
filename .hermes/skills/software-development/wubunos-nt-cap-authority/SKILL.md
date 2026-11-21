---
name: wubunos-nt-cap-authority
description: Bind WuBuOS NT syscalls to the wubu_cap authority core.
---

# WuBuNOS NT -> wubu_cap authority binding (Axis 1)

Canonical OS repo is `/home/wubu/wubuos/` (wubuos, NOT wubunos). The compiler
repo `/home/wubu/wubunos/` is a separate tree. `mk/tests.mk` +
`src/runtime/wubu_cap/wubu_cap.h` exist only in wubuos. Always resolve the repo
by glob instead of typing the name:

```python
R = next(d for d in sorted(glob.glob('/home/wubu/*' + chr(47)))
         if (Path(d)/'mk'/'tests.mk').is_file()
         and (Path(d)/'src/runtime/wubu_cap/wubu_cap.h').is_file())
```

## Why
The NT bridge had a flat 4096-slot `handle_table` (handles = `0x1000+index`)
and wubu_cap was a standalone, unwired authority core. Two parallel models that
never talked meant no single answer to "what may this agent do?". Binding them
gives revocable, rights-checked, audience-gated authority per NT handle while
the uint32 NT-handle ABI is preserved.

## Architecture
- Each `handle_table[i]` carries `cap_slot`, `cap_token`, `cap_backed`
  (added in `vsl_nt_bridge.h`). The record store is legacy; authority is the cap.
- `vsl_nt_cap_bind(ctx, nt_handle, type, access)` mints a cap object for an
  already-allocated handle and records the binding. Call AFTER the record's
  `data` (e.g. `strdup(dir)`) is set so the cap carries the same payload.
- `vsl_nt_cap_authorize(ctx, nt_handle, access)` is the gate. Returns
  NT_STATUS_INVALID_HANDLE for unknown handles, NT_STATUS_ACCESS_DENIED when
  revoked or rights-short, and NT_STATUS_SUCCESS for unbound (legacy) handles
  so unmigrated paths keep working.
- `vsl_nt_cap_unbind` closes the cap slot; `vsl_nt_cap_alias` gives a second
  handle the SAME object (NtDuplicateObject); `vsl_nt_cap_revoke_nt` revokes.
- Authority survives independently of the record: after revoke the handle
  still `valid == true` but every gate denies. That is the property the tests
  assert.

## Return-value conventions that will bite you
These are the real bugs found while wiring this. All three failed as "silently
always fails" or "never matches a success check":
- `wubu_cap_create` returns the object **slot index (>0) on success**, not
  `WUBU_CAP_OK` (0). Test with `rc <= 0` for failure, then derive the index via
  `wubu_cap_token_idx(out_token)`. Checking `rc != WUBU_CAP_OK` rejects every
  success.
- `wubu_cap_revoke` returns the **count of invalidated objects (>0)** on
  success, not a status. Normalize in the wrapper: `if (rc < 0) return rc;
  return WUBU_CAP_OK;` or a `switch (rc) { case WUBU_CAP_OK: }` never matches.
- `wubu_cap_handle_resolve_by_slot` needs `slot >= 1`; slot 0 is the null
  handle. Guard `nt_handle == 0` before calling.

## Wiring points that worked
- `NtClose` and `NtDeleteKey`: `vsl_nt_cap_unbind` before `vsl_nt_free_handle`
  so no stale token outlives the object.
- `NtCreateKey` / `NtOpenKey`: `vsl_nt_cap_bind(..., WUBU_NT_KEY_DEFAULT_ACCESS)`.
  This transliteration's NtOpenKey signature carries a root handle, not a
  DesiredAccess mask, so bind the standard key set (0x000F0033) explicitly
  rather than misreading an argument as an access mask.
- `NtDuplicateObject` is syscall **72** (not 63). Verify with
  `grep -rn 'vsl_nt_duplicate_object' src/runtime/vsl/*.c` -> `tbl[72-1] = ...`.
- Gates on 7 registry ops: set/query/enumerate/delete for both values and keys.
  Insert right after the handle->data lookup. Two body shapes exist: some use
  local `d` and `const char *dirname`, others use `d0`; enumerate_* use
  `opendir(dirname)` and have no `!dirname` check. Anchor per-shape or the
  search leaks gates into the wrong function (it happened: 3 gates piled into
  delete_key). Audit after inserting:
  `awk '/^int64_t vsl_nt_/ {fn=$2} /vsl_nt_cap_authorize/ {print NR": "fn}'`.

## Header / include discipline
- `vsl_nt_cap.h` includes `wubu_cap/wubu_cap.h` (path-qualified). A bare
  `#include "wubu_cap.h"` does NOT resolve under the VSL_NT `-I` flags.
- `vsl_nt_internal.h` includes `vsl_nt_cap.h`, so all `vsl_nt_*.c` get the API.
  No cycle: `vsl_nt_cap.h` -> `vsl_nt_bridge.h`, which internal.h already had.
- Shared NT key masks (`WUBU_NT_KEY_DEFAULT_ACCESS`, `..._WRITE_GUARD`,
  `..._READ_GUARD`) live in `vsl_nt_cap.h` so tests can reference them.

## Makefile wiring
Both `VSL_NT_OBJS` and `VSL_NT_EXT_OBJS` need `$(RT)/vsl/vsl_nt_cap.o` plus ALL
five cap objects (object, handle, token, revoke, system) and `-lpthread` on the
link line. Omitting any one yields an undefined-reference link error:
- `wubu_cap_validate_audience` lives in `wubu_cap_token.c` (NOT system.c).
- The global registry `g_wubu_cap_ptrs` and `wubu_cap_init` live in
  `wubu_cap_object.c`.
- `$(RT)` expands to `src/runtime`; a doubled `$(RT)/vsl/vsl/` is a build stop.
- A doubled backslash at end of line (`\\`) is a make parse error, not a
  continuation. Audit with `git diff -- mk/tests.mk | cat -A`.
- After editing makefile lists, verify which function each edit landed in with
  `git diff` -- a truncating edit once silently mangled the `test_cap` recipe's
  continuation line. Restore such lines verbatim from `git show HEAD:<file>`.

## Verifying
```
make test_cap test_vsl test_vsl_nt test_vsl_nt_ext
```
Green baseline after this work: 34/34, 87/87, 284/284, 16/16. The NT suite went
251 -> 284 as cap tests landed. `test_vsl_nt` must stay at 0 failures; the
registry gates must not break the pre-existing registry assertions.

## Proof that matters
The end-to-end test asserts the real syscall surface honors the cap: create a
key (cap-backed), write a value (allowed), `NtDuplicateObject` (same cap object,
two handles), revoke via the source handle, then `NtSetValueKey` and
`NtQueryValueKey` both return `NT_STATUS_ACCESS_DENIED` while the handle record
is still valid, and the alias is denied too. That cascade is the whole point.
