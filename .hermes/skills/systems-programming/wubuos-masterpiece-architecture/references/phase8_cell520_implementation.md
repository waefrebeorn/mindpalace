# Phase 8 Cell 520: .wubu Universal Handler Implementation

## Completed: 2026-06-18

### Files Modified

| File | Purpose |
|------|---------|
| `src/runtime/wubu_exec.h` | Added `wubu_exec_wasm()`, `wubu_exec_macho()` declarations |
| `src/runtime/wubu_exec.c` | Implemented WASM/Mach-O handlers, handler_id dispatch, raw format exec |
| `src/bridge/wubu_syscall.h` | Added `SYS_WUBU_EXEC = 23`, handler signature, syscall name |
| `src/bridge/wubu_syscall.c` | Implemented `sys_wubu_exec()`, added trampoline, name table entry |
| `src/bridge/wubu_syscall_test.c` | Updated to test 26 syscalls (was 25) |
| `src/runtime/wubu_container_test.c` | Added 9 new tests for handler_id dispatch + raw format exec |

### Implementation Details

#### WASM Handler (`wubu_exec_wasm`)
- Validates WASM magic: `\0asm`
- Tries runtimes in order: `wasmtime` → `wasm3` → `wasmer`
- Returns `WUBU_EXEC_ERR_VSL` if none available
- Writes payload to temp file (`/tmp/wubu-wasm-<pid>.wasm`)

#### Mach-O Handler (`wubu_exec_macho`)
- Validates 32/64-bit magic: `FEEDFACE`, `FEEDFACF`, `CEFAEDFE`, `CFFAEDFE`
- Executes via `darling` (macOS binary compat on Linux)
- Returns `WUBU_EXEC_ERR_FMT` if Darling unavailable

#### handler_id Dispatch (precedence over payload_type)
| handler_id | Handler | Runtime |
|------------|---------|---------|
| 1 | WuBuOS Native | — |
| 2 | HolyC JIT | HolyC compiler |
| 10 | VSL (Linux) | fork+chroot+exec |
| 11 | Proton (Windows) | Wine+DXVK+VKD3D |
| 20 | Python 3 | python3 |
| 21 | Node.js | node |
| 30 | WASM | wasmtime/wasm3/wasmer |
| 0xFF | Custom | by `handler_name` |

#### Syscall Integration
- `SYS_WUBU_EXEC = 23` (syscall number)
- Handler: `sys_wubu_exec(data_ptr, size, filename_ptr)`
- Trampoline: `syscall_trampoline_23` with `syscall` instruction
- Name: `"WubuExec"` in `wubu_syscall_name()`

#### Test Coverage (9 new tests in wubu_container_test.c)
1. `handler_id=2` HolyC JIT dispatch via .wubu container
2. `handler_id=10` VSL routes ELF correctly
3. `handler_id=11` Proton routes PE correctly
4. `handler_id=30` WASM routes correctly
5. Raw HolyC source execution
6. Raw shell script (with shebang) execution
7. Raw Python script (with shebang) execution
8. Raw WASM magic → graceful VSL error
9. Raw Mach-O magic → graceful format error

### Test Results

| Test Suite | Before | After |
|------------|--------|-------|
| `test_wubu` | 38/38 | **47/47** |
| `test_syscall` | 5/5 (25 syscalls) | **5/5 (26 syscalls)** |
| `test_vsl` | 46/46 | 46/46 |
| `test_holyc` | 76/76 | 76/76 |
| `test_bridge` | 25/25 | 25/25 |

### Architecture Notes

- **Inferno emu pattern**: Single hosted binary (`wubu`) runs everywhere
- **Containers = host processes**: No syscall emulation, fork+chroot+exec
- **9P namespace**: Per-container Styx socket for namespace isolation
- **GPU passthrough**: `/dev/dri`, `/dev/nvidia*` bind-mounted into container
- **Arch base**: Rolling + Steam Runtime + Proton-GE for Windows compat