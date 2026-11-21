# wubu_cap API contracts (verified signatures)

Source of truth: `wubu_cap.h` + `wubu_cap_internal.h` in `<WUBOS>/src/runtime/wubu_cap/`
(OS repo = the WuBuOS body tree; see `wubu-project-orientation`).

## Lifecycle
- `void wubu_cap_init(void)` — idempotent, process-global. Call once before any create (NT bridge calls it in `vsl_nt_bridge_init`).
- `wubu_cap_handle_table_t *wubu_cap_handle_table_create(void)` / `void wubu_cap_handle_table_free(t)` — per-process/per-ctx table.

## Object create / revoke
- `int wubu_cap_create(uint16_t kind, uint64_t rights, const int32_t *audience, uint8_t flags, uintptr_t kind_data, int32_t owner_pid, uint32_t parent_idx, wubu_cap_token_t *out)` — returns object SLOT INDEX (>0) on success, `WUBU_CAP_*` (<0) on error; token via `out`.
- `int wubu_cap_revoke(wubu_cap_token_t tok)` — returns COUNT of invalidated objects (>0) on success, `WUBU_CAP_*` (<0) on error. Normalize `rc < 0 ? rc : WUBU_CAP_OK`.
- `void wubu_cap_destroy(uint32_t idx)`.

## Handle table (NT handle == handle-table slot index; slot 0 == NULL)
- `wubu_cap_token_t wubu_cap_handle_insert(t, uint32_t object_idx, uint8_t token_flags)` — `object_idx = token_idx(obj_token)`, NOT `create`'s return. NT handle = `token_idx(htok)`.
- `wubu_cap_object_t *wubu_cap_handle_resolve(t, int32_t caller_pid, wubu_cap_token_t tok, uint64_t required_rights)` — obj*|NULL (audience + rights + gen checked).
- `wubu_cap_object_t *wubu_cap_handle_resolve_by_slot(t, int32_t caller_pid, uint32_t slot, uint64_t required_rights)` — slot-based (NT handles). Returns NULL for a foreign pid even when rights suffice.
- `int wubu_cap_handle_revoke_by_slot(t, uint32_t slot)` — revokes the backing object (cascades to all aliases); returns `WUBU_CAP_OK` on success.
- `int wubu_cap_handle_close_slot(t, uint32_t slot)` — frees the slot; `WUBU_CAP_OK` / `WUBU_CAP_EINVAL`.

## Token helpers (inline in cap.h)
`wubu_cap_token_pack(gen, idx, flags)`; `token_idx(t)` = idx; `token_gen`/`token_flags`; `token_is_null(t)` = (idx==0). HANDLE token idx = handle-table slot; OBJECT token idx = registry/object idx. Never mix.

## Rights lattice
`WUBU_RIGHT_READ=1, WRITE=2, EXEC=4, DERIVE=8, REVOKE=0x10, INSPECT=0x20, GRANT=0x40, SEND=0x80, RECV=0x100, RESTORE=0x200, DELETE=0x400, COMMIT, ABORT, TERMINATE, INVOKE, ATTACH`. `WUBU_RIGHTS_ALL=0xFFFFFFFFFFFFFFFF`.

## NT access mask -> rights (vsl_nt_desired_access_to_cap)
GENERIC_READ(0x80000000)->READ|INSPECT|RECV; GENERIC_WRITE(0x40000000)->WRITE|SEND; GENERIC_EXEC(0x20000000)->EXEC|INVOKE; GENERIC_ALL(0x10000000)->RIGHTS_ALL; DELETE(0x10000)->DELETE; READ_CONTROL(0x20000)->READ|INSPECT; WRITE_DAC(0x40000)->WRITE|GRANT; WRITE_OWNER(0x80000)->WRITE|GRANT; SYNCHRONIZE(0x100000)->RECV; KEY_QUERY_VALUE(1)->READ; KEY_SET_VALUE(2)->WRITE; KEY_CREATE_SUB_KEY(4)->WRITE|DERIVE; FILE_READ/WRITE_DATA, FILE_APPEND_DATA, FILE_READ/WRITE_ATTRIBUTES map to READ/WRITE/INSPECT.

## Test link line
build any binary that links `vsl_syscall_nt.c` with:
`wubu_cap_object.o wubu_cap_handle.o wubu_cap_token.o wubu_cap_revoke.o wubu_cap_system.o -lpthread`.
