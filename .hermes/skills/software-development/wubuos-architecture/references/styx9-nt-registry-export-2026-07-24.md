# STREAM D — NT Registry as Styx9 Namespace (STYX SOUL)

## Overview

The NT registry (file-backed: key=dir, value=`[type:4][len:4][data]` file) is
now exposed as a 9P filesystem at `/n/nt/registry`. This implements the "Styx
soul" vision: everything is a 9P file, including the NT personality's registry.

## Implementation

**File**: `src/runtime/styxfs_server.c`

**Function**: `nt_registry_styx_export(styx_server_t *srv)`

```c
int nt_registry_styx_export(styx_server_t *srv) {
    if (nt_registry_ensure_root() != 0) return -1;
    
    /* Set NT registry callbacks */
    srv->walk = nt_registry_walk;
    srv->open = nt_registry_open;
    srv->read = nt_registry_read;
    srv->write = nt_registry_write;
    srv->create = nt_registry_create_key;
    srv->remove = nt_registry_remove;
    srv->stat = nt_registry_stat;
    srv->clunk = styxfs_clunk;
    
    return 0;
}
```

## Backing Store

The registry uses the same `g_nt_reg_root` (e.g. `/tmp/wubu_nt_reg_<pid>`) that
the NT syscall handlers use:
- `vsl_nt_create_key` / `vsl_nt_open_key` → mint handle with `data` = key dir path
- `vsl_nt_set_value_key` → writes `[type:4][len:4][data]` file under key dir
- `vsl_nt_query_value_key` → reads the file, returns type + data
- `vsl_nt_enumerate_key` / `vsl_nt_enumerate_value_key` → readdir on key dir
- `vsl_nt_delete_key` / `vsl_nt_delete_value_key` → rmdir / unlink

The Styx9 export operates on this **exact same directory tree**. No separate
daemon, no copy — the 9P server and NT personality share the backing store.

## 9P Operations Mapped

| 9P Op | Registry Action |
|-------|-----------------|
| `walk` | Traverse keys (dirs) and values (files) |
| `open` | Open value file for read/write |
| `read` | Read value data (skips 8-byte type+len header) |
| `write` | Write value data (preserves type, updates len) |
| `create` | Create new key (mkdir) |
| `remove` | Delete key (rmdir) or value (unlink) |
| `stat` | Return key/value metadata |
| `clunk` | Close fd |

## Verification

```bash
cd /home/wubu/wubuos
make clean && make test
# ✅ All tests pass
```

The shared `g_nt_reg_root` means:
- NT syscalls create a key → visible via `9p ls /n/nt/registry/...`
- 9P `create` makes a key → `NtOpenKey` finds it
- 9P `write` updates a value → `NtQueryValueKey` returns new data
- Cross-access survives test teardown/teardown cycles

## Pattern for New Styx9 Exports

To expose another subsystem as 9P:

1. Add `*_styx_export(styx_server_t *srv)` to `styxfs_server.c`
2. Implement the 9 callbacks (walk, open, read, write, create, remove, stat, clunk)
3. Call the export function from your subsystem's init, passing the server instance
4. Mount the server at your namespace path

The NT registry export is the canonical example — ~180 lines including helpers,
sharing the backing store with the primary personality.