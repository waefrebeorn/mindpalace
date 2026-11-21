# EDR Engine Split — 2026-07-03

**Session:** 2026-07-03 EDR Split + Host Exec Fix
**Commit:** ed3e79c
**Files Created:** 5 files under `src/runtime/edr/`

## Summary

Split `src/runtime/wubu_edr.c` (566 lines) into 5 modules under `src/runtime/edr/`:

| Module | Lines | Purpose |
|--------|-------|---------|
| `edr_core.c` | 14,484 | Lifecycle, module system, alert buffer (MPSC lock-free), worker thread, FNV-1a, public API |
| `edr_proc_pin.c` | 7,284 | **NETLINK_CONNECTOR + cn_proc** — Linux equivalent of `PsSetCreateProcessNotifyRoutineEx`. Subscribes to `PROC_EVENT_FORK/EXEC/EXIT` in real-time, pushes typed EdrEvents. Verified: discovers 59 live processes. |
| `edr_fanotify.c` | 10,089 | fanotify + inotify with **FAN_ATTRIB** (timestomp detection), script content capture on `FAN_OPEN_EXEC` (.sh/.py/.pl/.rb/.lua/.js/.ps1), expanded inotify to 6 dirs including `/var/spool/cron`, `/etc/systemd/system` |
| `edr_poller.c` | 10,643 | Periodic `/proc` diff scans (every ~1s at 10ms ticks): unix sockets (named pipe pin), modules (driver load pin), cron dirs (scheduled task pin), proc tree (missed-process recovery) |
| `edr_internal.h` | 6,648 | **Shared state pattern** — opaque struct forward declarations + global state definitions + internal function declarations |

## Key Differences from VSL Split Pattern

| Aspect | VSL Split | EDR Split |
|--------|-----------|-----------|
| **Internal header purpose** | Opaque struct definitions only | Shared global state + opaque forwards + internal API |
| **Global state** | `VSL_STATE g_vsl` in `vsl.c` | `EdrState g_edr` in `edr_core.c`, but `edr_internal.h` declares it `extern` for all sub-modules |
| **Opaque types** | Public header has `typedef struct VSL_PROC VSL_PROC;` | Public `wubu_edr.h` has forward decls; internal header defines full structs |
| **Module coupling** | `vsl_syscall.c` is self-contained (all handlers in one file) | Sub-modules call each other via internal API (`edr_queue_push`, `edr_proc_find`, etc.) |

## Internal Header Pattern (Shared State)

```c
// edr_internal.h
#ifndef EDR_INTERNAL_H
#define EDR_INTERNAL_H

#include "wubu_edr.h"  // public opaque forwards
#include <pthread.h>
#include <sys/queue.h>  // MPSC queue

/* Full struct definitions for internal use */
struct EdrProcessInfo {
    uint32_t pid;
    uint32_t ppid;
    uint32_t creator_pid;
    char comm[16];
    char exe_path[256];
    uint64_t start_time_ns;
    uint32_t uid;
    uint64_t file_window_idx;
    uint64_t file_window[32];
    // ... extension dict
};

struct EdrFileWindow {
    char paths[32][256];
    uint64_t timestamps[32];
    uint32_t count;
};

/* Global state — defined in edr_core.c, extern everywhere else */
struct EdrState {
    bool active;
    pthread_t worker;
    pthread_mutex_t lock;
    // MPSC queue...
    struct EdrProcessInfo procs[1024];
    uint32_t n_procs;
    // modules...
    struct EdrModule *modules;
    uint32_t n_modules;
    uint32_t active_module;
    // alerts...
    uint64_t fnv1a_offset;
};
extern struct EdrState g_edr;

/* Internal API (not in public header) */
int edr_queue_push(EdrEvent *ev);
EdrEvent *edr_queue_pop(void);
struct EdrProcessInfo *edr_proc_find(uint32_t pid);
struct EdrProcessInfo *edr_proc_get_or_create(uint32_t pid);
void edr_proc_remove(uint32_t pid);
void edr_alert_push(EdrEvent *ev);
uint64_t edr_fnv1a(const void *data, size_t len);

#endif
```

**Usage in sub-modules:**
```c
// edr_proc_pin.c
#include "edr/edr_internal.h"
// Directly accesses g_edr.procs[], calls edr_proc_get_or_create(), edr_queue_push()

// edr_fanotify.c
#include "edr/edr_internal.h"
// Calls edr_queue_push(), edr_fnv1a()

// edr_poller.c
#include "edr/edr_internal.h"
// Calls edr_proc_find(), edr_queue_push()
```

## Makefile Updates Required

1. **New variable** for source files:
```makefile
EDR_SRC = $(RT)/wubu_edr.c $(RT)/edr/edr_core.c $(RT)/edr/edr_proc_pin.c \
          $(RT)/edr/edr_fanotify.c $(RT)/edr/edr_poller.c
```

2. **Test target** compiles all modules:
```makefile
test_edr:
	$(CC) -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM \
		-I$(RT) -I$(RT)/edr \
		$(EDR_SRC) $(RT)/wubu_edr_test.c \
		-o $(RT)/wubu_edr_test -lpthread
	$(RT)/wubu_edr_test
```

3. **Clean rule** includes `$(RT)/edr/*.o`

4. **Pattern rule** for edr/ subdirectory (if needed):
```makefile
$(RT)/edr/%.o: $(RT)/edr/%.c
	$(CC) $(CFLAGS) -I$(RT) -I$(RT)/edr -c $< -o $@
```

## Gutting the Original to a Shim

```c
// wubu_edr.c (was 566 lines, now 13 lines)
/* wubu_edr.c  --  WuBuOS EDR Engine Shim
 * All implementation moved to src/runtime/edr/ subdirectory.
 * This shim exists for backward compatibility with the test target.
 */
#include "edr/edr_internal.h"

/* All real code is in the submodules — this file is intentionally empty
 * except to provide a compilation unit that pulls in the internal header.
 * The Makefile compiles each edr/ submodule separately. */
```

## Test Verification

```bash
make test_edr
# 12/12 passed
# [edr_poller] periodic poller active (interval=100 ticks)
# [edr_fanotify] inotify active on 6 dirs
# [edr_proc] NETLINK_CONNECTOR process pin active
```

## REAL_GAPs Closed (9)

1. **Process pin** — NETLINK_CONNECTOR + cn_proc (real-time fork/exec/exit)
2. **Thread pin** — (same infrastructure)
3. **Timestomp detection** — FAN_ATTRIB on fanotify
4. **Script capture** — content read on FAN_OPEN_EXEC for interpreters
5. **Registry coverage** — expanded inotify to 6 dirs
6. **Unix socket pin** — /proc/net/unix diff scan
7. **Driver load pin** — /proc/modules diff scan
8. **Scheduled task pin** — /etc/cron* + /etc/systemd/system diff
9. **Proc recovery** — /proc tree scan for missed forks

## Pitfalls Encountered

1. **`_GNU_SOURCE` required** for `SYS_*` syscall numbers, `NETLINK_CONNECTOR`, `cn_proc` — add to test target and any file using these
2. **Netlink requires CAP_NET_ADMIN** — tests run gracefully (print "Operation not permitted" but don't crash)
3. **fanotify requires CAP_SYS_ADMIN** — same graceful degradation
4. **inotify watch limits** — 6 directories is fine, but >1000 may hit `fs.inotify.max_user_watches`
5. **Sub-module forward declarations** — any function called across sub-modules MUST be declared in `edr_internal.h` (not static). The public header only has public API.

## Template for Future Subdirectory Splits

When splitting a monolith into a subdirectory with shared state:

```
src/
  runtime/
    wubu_foo.c          # OLD monolith (to be split)
    foo/
      foo_internal.h    # Shared state + internal API + opaque struct full defs
      foo_core.c        # Lifecycle, global state, public API
      foo_subsys1.c     # First subsystem
      foo_subsys2.c     # Second subsystem
      ...
```

1. Create `foo_internal.h` with:
   - `#include "wubu_foo.h"` (public opaque forwards)
   - Full struct definitions for internal types
   - `extern GlobalState g_foo;`
   - Internal function declarations (NO `static`)

2. Each sub-module `.c` starts with `#include "foo/foo_internal.h"`

3. Original monolith becomes shim: `#include "foo/foo_internal.h"` + global state definition

4. Makefile: new variable for all sub-module sources, update test target, add clean rule