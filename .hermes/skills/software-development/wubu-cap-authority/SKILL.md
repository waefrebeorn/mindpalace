---
name: wubu-cap-authority
description: Cap-backed NT Object Manager authority via wubu_cap.
version: 1.0.0
author: Hermes Agent
license: CC-BY-4.0
hermes:
  tags: [capabilities, nt-object-manager, authority, revocation, audit]
  related_skills: [wubu-project-orientation, wubunos-runtime-integrity, wubu-kvfs-namespace]
---

# wubu_cap-backed authority layers

## When to Use
Use when binding an authority surface onto the wubu_cap core: the NT Object
Manager handle/token/revoke bridge in `src/runtime/vsl/vsl_nt_*`, or any
future capability layer that must back authority handles with audience gating,
rights checks, and cascading revocation.

Load whenever you bind an authority surface onto the wubu_cap core — most notably the NT Object Manager (handles, tokens, revocation cascades) in the VSL NT bridge. This is the seL4-style capability layer that replaces ad-hoc handle tables with one revocable, audience-gated, rights-checked primitive. Repo/path disambiguation lives in `wubu-project-orientation`; this skill owns the cap API contract.

## The pattern (cap-backing an authority surface)

1. One cap object per authority object: `wubu_cap_create(kind, rights, audience, flags, kind_data, owner_pid, parent_idx, &token)`. `kind_data` is the object body; the token is the authority handle.
2. NT handles ARE cap handle slots: `htok = wubu_cap_handle_insert(cap_ht, object_idx, 0)`; the NT handle value is `token_idx(htok)`; slot 0 == NULL handle. The uint32 NT-handle ABI is unchanged.
3. Translate NT `DesiredAccess` to a `uint64_t rights` mask (`vsl_nt_desired_access_to_cap`) before every op; `resolve_handle` enforces it.
4. Per-op gate, per-process table: each `vsl_nt_bridge_ctx_t` owns a `cap_ht` (`handle_table_create` in init, `handle_table_free` in shutdown). Every syscall runs `resolve_handle` first; deny (ACCESS_DENIED) on NULL.
5. Revocation cascades: `revoke_handle` authorizes DELETE then `handle_revoke_by_slot` bumps the object generation so EVERY alias (any pid) fails resolve — the single agent-lost-authority operation.

## Critical pitfalls (verify, do not assume)

- `wubu_cap_create` returns the object SLOT INDEX (>0), NOT `WUBU_CAP_OK(0)`, and writes the token via the `out` param. Checking `rc != WUBU_CAP_OK` makes every acquire fail. Check `rc <= 0 || token_is_null(out)`.
- `wubu_cap_revoke` returns a COUNT of invalidated objects (>0) on success, not `WUBU_CAP_OK`. Normalize `rc < 0 ? rc : WUBU_CAP_OK` before a status switch.
- `object_idx != handle slot`. `object_idx = token_idx(obj_token)` is passed to `handle_insert`; the NT handle is `token_idx(htok)`. Confusing them mints handles against the sentinel at index 0.
- Audience gating is caller_pid: `handle_resolve_by_slot` returns NULL for a foreign pid even when rights suffice — use this to prove/deny cross-process access.
- `wubu_cap_init` is idempotent but process-global: call once per process (the NT bridge does it in `vsl_nt_bridge_init`); cap objects persist in the global registry until revoked/destroyed, so tests must release handles.
- TWO handle conventions coexist and share one set of entry points. `vsl_nt_allocate_handle` mints a legacy record handle `0x1000+idx` and binds it via `vsl_nt_cap_bind`; `vsl_nt_cap_acquire`/`vsl_nt_cap_make_handle` mint a BARE cap slot with no record. `resolve_handle`/`release`/`revoke_handle` must accept both: look up the legacy table first (exact, and its values >= 0x1000 cannot collide with cap slots), then fall back to treating the value as a live cap slot (`wubu_cap_handle_slot_live`). Routing only one convention silently disables every revoke/release on the other.
- Never translate a handle twice. `vsl_nt_cap_revoke_nt` used to pass `handle_table[idx].cap_slot` into `vsl_nt_cap_revoke_handle`, whose parameter is an NT handle and which re-ran `slot_of` internally — the cap slot was re-looked-up as a handle and every revoke failed. Pass the handle once and let one layer own the translation.
- Probe liveness through the cap SLOT, never `handle_table[i].cap_token`. Only the slot is revalidated on rebind (bind/alias/duplicate); `cap_token` keeps the `(object_idx, gen)` pair from mint time. A later `wubu_cap_create` reuses that object idx for a different object, so the token goes stale and liveness reports a LIVE handle as dead — `vsl_nt_cap_granted_mask` returns 0 and every SRM check on that handle fails.
- GrantedAccess belongs to the HANDLE, not the object. `NtDuplicateObject` aliases one object but narrows the new handle, so object rights alone let a reduced duplicate still report its source's authority. `resolve_handle` needs a second gate: expand the request and require `handle_table[idx].cap_rights` to cover it. The same ceiling already lives in `vsl_nt_cap_authorize` gate (b).

## Always-on

- Link `wubu_cap_object.o wubu_cap_handle.o wubu_cap_token.o wubu_cap_revoke.o wubu_cap_system.o -lpthread` into ANY test binary that pulls `vsl_syscall_nt.c` (it now calls `wubu_cap_init` and the handle-table API).
- Never pass a read-only string literal as an NtQueryValueKey / registry read OUTPUT buffer. The handler `fread`s into `args[3]`; a `const char *val = "..."` lives in `.rodata` and the write faults as a SIGSEGV that looks like random heap corruption far from the real call site. Use a writable `char qbuf[N]` and pass `sizeof(qbuf)` as the cap.
- When the NT suite dies with a SIGSEGV whose top frames are libc (`__memcpy_avx512_unaligned_erms`, `__GI_fread`, `__GI_kill`) rather than your code, the fault is real but the frame is where it landed, not the cause. gdb ALSO stops on the suite's own intentional `kill(getpid(), SIGCONT)` — add `handle SIGCONT nostop noprint pass` or you will backtrace a non-crash. The build is `-O0 -g`, so trust the backtrace you get after that.
