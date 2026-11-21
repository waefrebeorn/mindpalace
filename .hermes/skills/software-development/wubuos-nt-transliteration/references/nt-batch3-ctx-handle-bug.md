# NT Batch-3: ctx / handle-table NULL bug

## Symptom (batch 3, file + event syscalls)
After adding `NtOpenFile/NtReadFile/NtWriteFile/NtClose/NtCreateEvent/NtSetEvent/
NtResetEvent/NtQueryInformationFile/NtOpenEvent/NtDelayExecution`, the standalone
`wubu_vsl_nt_test` ran fine (no hang) but reported **10 false failures**:
- `NtSetEvent signals the event` FAIL
- `NtResetEvent clears the event` FAIL
- `NtClose frees the event handle` FAIL
- `NtWriteFile writes 8 bytes` FAIL
- `NtReadFile reads 8 bytes` / `returns the written bytes` FAIL
- `NtQueryInformationFile succeeds` / `reports size 8` FAIL
- `NtClose closes the file handle` FAIL
- `NtClose frees the opened event` FAIL

Meanwhile `NtDelayExecution`, `NtCreateEvent` (handle mint), `NtOpenFile` (handle mint),
`NtOpenEvent` (handle mint) PASSED — because minting a handle only calls
`vsl_nt_allocate_handle`, while every *use* of the handle calls
`vsl_nt_handle_to_vsl_fd`, which is what failed.

## Root cause
`vsl_nt_syscall_dispatch` calls each handler as `fn(a,b,c,d,e,f)` — the handler
signature is `(uint64_t, ...)` and does **NOT** receive the `vsl_nt_bridge_ctx_t*`.
The handle-table helpers (`vsl_nt_allocate_handle` / `vsl_nt_handle_to_vsl_fd` /
`vsl_nt_free_handle`) take a `vsl_nt_bridge_ctx_t*`. The batch-3 handlers passed
**`NULL`** for that ctx (copy-paste habit from batch 1/2 helpers that didn't touch the
handle table).

`vsl_nt_handle_to_vsl_fd(NULL, ...)` early-returns `-1`, so the fd lookup fails, the
handler returns `NT_STATUS_INVALID_HANDLE`, and the test sees a failure — even though
the underlying `eventfd`/`open`/`pread`/`pwrite` was never even attempted.

## Fix
1. In `vsl_syscall_nt.c`, add a file-scope pointer set during init:
   ```c
   static vsl_nt_bridge_ctx_t *g_nt_ctx = NULL;
   int vsl_nt_bridge_init(vsl_nt_bridge_ctx_t *ctx) {
       ...
       g_nt_ctx = ctx;   /* so handlers (which get no ctx) can reach the handle table */
       return 0;
   }
   ```
2. In every batch-3 handler, pass `g_nt_ctx` (NOT `NULL`) to the handle helpers:
   `vsl_nt_allocate_handle(g_nt_ctx, fd, 0, NT_OBJECT_TYPE_FILE)`,
   `vsl_nt_handle_to_vsl_fd(g_nt_ctx, h, &fd)`, `vsl_nt_free_handle(g_nt_ctx, h)`.

A repo-wide `s.replace("vsl_nt_allocate_handle(NULL,", "vsl_nt_allocate_handle(g_nt_ctx,")`
(plus `_to_vsl_fd` and `_free_handle`) catches all sites at once.

## Lesson
When a transliterated NT syscall mints a handle successfully but every handle *use*
fails, suspect a `NULL` ctx passed to the handle-table helpers — not the syscall
logic itself. The mint-only checks pass, masking the bug until a use-site is tested.
Always wire `g_nt_ctx` in `vsl_nt_bridge_init` and use it in handlers.

## Verification (fast, no vulkan/cuda link)
```bash
cat > /tmp/nt_shim.c <<'EOF'
#include <stdint.h>
int64_t vsl_sys_nosys(uint64_t a,uint64_t b,uint64_t c,uint64_t d,uint64_t e,uint64_t f){
  (void)a;(void)b;(void)c;(void)d;(void)e;(void)f; return -1; }
EOF
gcc -std=c11 -O0 -g -D_GNU_SOURCE -I src/runtime/vsl -I src/runtime -I src/kernel \
  src/runtime/vsl/vsl_syscall_nt.c src/runtime/vsl/vsl_syscall_nt_test.c /tmp/nt_shim.c \
  -o /tmp/wubu_vsl_nt_test
timeout 30 stdbuf -oL /tmp/wubu_vsl_nt_test | tail -20
# expect: "=== Results: 53 passed, 0 failed ==="  (batch 1+2 = 49, batch 3 = +4 tests/~10 checks)
```
