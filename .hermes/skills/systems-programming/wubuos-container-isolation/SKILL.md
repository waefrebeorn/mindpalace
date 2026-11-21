---
name: wubuos-container-isolation
category: systems-programming
description: WuBuOS container isolation using cgroups v2 + seccomp-bpf
---

## WuBuOS Container Isolation (cgroups v2 + seccomp-bpf)

### Overview
Cell 420: Security hardening for container execution using real Linux kernel isolation primitives. Not syscall emulation — real cgroups/seccomp.

### Architecture

#### Files
- `src/runtime/wubu_ct_isolate.h` — API header
- `src/runtime/wubu_ct_isolate.c` — implementation (~600 lines)

#### Integration Points
- `wubu_ct_start()` in `wubu_host_exec.c`:
  - Parent (pre-fork): `wubu_ct_setup_isolation(ct)`
  - Child (post-fork, pre-exec): `wubu_ct_child_isolation()`

### cgroups v2

#### Path
`/sys/fs/cgroup/wubu/<container_name>/`

#### Controllers Enabled
- `memory` — `memory.max` (bytes, from `ct->mem_limit_mb`)
- `cpu` — `cpu.max` (quota/period, from `ct->cpu_limit`)
- `pids` — `pids.max` (default 1024)

#### Setup Sequence
1. Ensure base `/sys/fs/cgroup/wubu` exists
2. Enable controllers: `cgroup.subtree_control = "+memory +cpu +pids"`
3. Create container cgroup directory
4. Enable controllers for container cgroup
5. Write limits
6. Pass path via `WUBU_CGROUP_PATH` env to child
7. Child attaches via `cgroup.procs`

### seccomp-bpf

#### Profiles (allowlist, deny-by-default)

| Runtime | Profile | Key Syscalls |
|---------|---------|--------------|
| native/holyc | basic | 120+ (proc, mem, file, net, signals, futex, sched) |
| steamos | gpu | basic + ioctl/mmap/DRM |
| proton | wine | basic + ptrace/personality/modify_ldt/arch_prctl |

#### Filter Structure
- Load architecture (AUDIT_ARCH_X86_64) → verify x86_64
- Load syscall number
- For each allowed syscall: `JEQ_SYSCALL(nr) → ALLOW`
- Default: `KILL_PROCESS`

#### Installation
```c
prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0);
syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER, 0, &prog);
```

#### Profile Selection
- Parent sets `WUBU_SECCOMP_PROFILE` env (basic/gpu/wine/none)
- Child reads env and builds appropriate filter

#### Namespace Isolation API (2026-06-06-26)

#### New Functions Added
| Function | Purpose |
|----------|---------|
| `wubu_cgroup_write(path, value)` | Generic cgroup file write helper |
| `wubu_seccomp_install(profile)` | Install seccomp filter by profile (BASIC/GPU/WINE/NONE) |
| `wubu_ns_unshare(flags)` | Unshare namespaces (CLONE_NEWNS|NEWPID|NEWNET|NEWUSER|CLONE_NEWUTS|CLONE_NEWIPC) |

#### Usage
- `wubu_cgroup_write()`: Low-level helper called by `wubu_ct_cgroup_set_memory/cpu/pids`
- `wubu_seccomp_install()`: Called from `wubu_ct_child_isolation()` after fork, or standalone for testing
- `wubu_ns_unshare()`: Intended for pre-exec namespace isolation; flags typically `CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWUSER | CLONE_NEWUTS | CLONE_NEWIPC`

### cgroups v2 I/O Controller (2026-06-26 Phase 12)

#### New API
| Function | Purpose |
|----------|---------|
| `wubu_ct_cgroup_set_io_max(path, read_bps, write_bps)` | Set I/O bandwidth limits (bytes/sec). 0 = unlimited. Writes `io.max` with format `8:0 rbps=X wbps=Y` |
| `wubu_ct_cgroup_set_io_weight(path, weight)` | Set I/O weight (1-10000). 0 = default (100). Writes `io.weight` |

#### Integration in `wubu_ct_setup_isolation()`
```c
/* I/O controller limits (procmem/io) */
if (ct->io_read_bps > 0 || ct->io_write_bps > 0)
    wubu_ct_cgroup_set_io_max(cgroup_path, ct->io_read_bps, ct->io_write_bps);
if (ct->io_weight > 0)
    wubu_ct_cgroup_set_io_weight(cgroup_path, ct->io_weight);
```

#### WubuCt struct additions (wubu_host_exec.h)
```c
uint64_t io_read_bps;   /* I/O read bandwidth limit (bytes/sec, 0 = unlimited) */
uint64_t io_write_bps;  /* I/O write bandwidth limit (bytes/sec, 0 = unlimited) */
uint32_t io_weight;     /* I/O weight (1-10000, 0 = default 100) */
```

#### Namespace Flags Constant
```c
#define WUBU_NS_FLAGS (CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWNET | \
                       CLONE_NEWUSER | CLONE_NEWUTS | CLONE_NEWIPC)
```

#### Child Isolation Integration
```c
/* Unshare namespaces for container isolation */
const char *ns_flags_str = getenv("WUBU_NS_FLAGS");
if (ns_flags_str) {
    int flags = atoi(ns_flags_str);
    if (flags != 0) wubu_ns_unshare(flags);
} else {
    wubu_ns_unshare(WUBU_NS_FLAGS);
}
```

---

### Build Notes
- Requires `<sched.h>` for `CLONE_*` constants
- cgroup v2 `io` controller must be enabled in `cgroup.subtree_control` (kernel 5.4+)

### Snapshot Manager — Native Backends (2026-06-28)

**Gap**: `system("zfs snapshot ...")` in `zfs_snapshot_create()` + btrfs/zfs config-only.

**Fixes Applied**:

| Backend | Implementation | Status |
|---------|---------------|--------|
| **btrfs** | `BTRFS_IOC_SNAP_CREATE_V2` ioctl on parent subvolume dir | ✅ Real ioctl |
| **zfs** | `fork()+execvp("zfs", "zfs", "snapshot", dataset, snapshot)` | ✅ fork+exec |
| **LVM** | Skeleton (`-ENOSYS`), falls back to overlayfs | Stub (needs lvm2 tools) |

**Key code changes**:
- `zfs_snapshot_create()`: replaced `system(cmd)` with `fork()+execvp()+waitpid()`
- `snapshot_mount_fs()`: dispatches to btrfs/zfs/LVM backends based on `fs_type` + filesystem detection
- Added `#include <sys/wait.h>` for `waitpid()`
- Fixed btrfs `strncpy` overflow with proper bounded `memcpy`
- Increased overlayfs mount_opts buffer 2048 → 4096 bytes

**Verification**: `make test_snapshot` → 132/132 pass (includes btrfs/zfs/LVM string helpers)

### Per-container 9P server (L9, 2026-11)

`run_container_styx_server` is no longer skipped: `wubu_ct_start` forks it
PARENT-side (process model) right after `setup_styx_socket`; `styx_fd` is
CLOEXEC so the container's execv drops it. `ct_retire` (wait/state-poll) and
`ct_detach` (destroy) SIGTERM + bounded-reap the server (`ct->styx_pid`),
close+unlink the socket. The running-container registry lives in
wubu_host_exec.c (`wubu_ct_registry_count/get/find`); /n/guests renders from
it (wubu_ns_guests.c). The written server loop had DOUBLE framing bugs:
styx_serve expects the 4-byte LE size prefix INSIDE inbuf and its responses
already carry it -- a socket loop must read/write whole frames verbatim,
never strip the prefix inbound or prepend outlen outbound.

### Empty tmp root + unprivileged userns = chroot SUCCEEDS, exec 127

A test container with `root = mkdtemp dir` and argv `/bin/sh`/`/bin/sleep`
exits 127 on boxes with unprivileged user namespaces enabled: the child's
`wubu_ns_unshare(CLONE_NEWUSER|...)` grants CAP_SYS_CHROOT in the new userns,
so `chroot(empty_tmp)` SUCCEEDS (no EPERM fallback to host namespace) and
execv finds no binaries inside. Fix the TEST, not the isolation: seed the
rootfs with a STATIC binary (`cp /usr/bin/busybox root/bin/busybox`, argv
`/bin/busybox sleep 1`) -- a real chrooted container under the basic seccomp
profile, exit 0. Gate reaping with `kill(spid,0)==-1 && errno==ESRCH`: kill 0
SUCCEEDS on a zombie, so ESRCH is the only proof of no-zombie.

### Fork+Exec Zombie Process Debugging (2026-07-03)

#### Symptom
- `wubu_container_test` binary **hangs indefinitely** (60-90s timeout instead of ~3s completion)
- `ps aux` shows 50+ orphaned `wubu_container_test` / `wubu_host_exec_test` processes in `S` state, running for days
- These accumulate from every previous test run — `wubu_ct_wait()` never returns

#### Root Cause
`wubu_ct_start()` calls `fork()` + child `execvp()`. `wubu_ct_wait()` calls `waitpid()`. If the child **never execs** (e.g., chroot rootfs doesn't exist, or execvp fails and child exits unexpectedly), the parent's `waitpid()` can block forever.

Common failure modes:
1. **Child fork succeeds but exec fails** → child calls `_exit(127)` but parent waits on wrong PID or wrong flags
2. **waitpid() returns before child exits** (WCONTINUED/WUNTRACED) and caller doesn't loop
3. **SIGCHLD handler** interferes — if a signal handler calls waitpid() first, the synchronous call gets -1/ECHILD
4. **Grandchild zombie accumulation**: if the child forks its own sub-processes, they become orphan/init children

#### Diagnostic Commands
```bash
# Count orphaned test processes
ps aux | grep -E "wubu_container_test|wubu_host_exec_test" | grep -v grep | wc -l

# Kill ALL zombies at once
pkill -9 -f "wubu_container_test" 2>/dev/null
pkill -9 -f "wubu_host_exec_test" 2>/dev/null

# Check for sleep orphans from test_ct_state_poll (sleep 2) and test_ct_kill (sleep 30)
ps aux | grep -E "sleep [23]0" | grep -v grep

# Run binary directly (bypass make rebuild) to isolate build-vs-runtime hang
timeout 10 ./src/runtime/wubu_container_test 2>&1 | tail -20
```

#### Prevention Patterns
1. **Child death signal**: `prctl(PR_SET_PDEATHSIG, SIGTERM)` in child right after fork — if parent dies, child dies too
2. **Timeout loop in waitpid**: `while (waitpid(pid, &st, WNOHANG) == 0) { sleep(1); if (tries++ > 5) break; }` for bounded wait
3. **Test teardown**: Kill child processes at test teardown, don't rely on `_exit()`
4. **Makefile hardening**: Add `timeout N` in test targets so hanging tests don't cascade through phases
5. **Regular check**: After running fork-heavy tests, always `pkill -9 -f "wubu_container_test"` to clean up

### Build Integration
```makefile
RT_OBJS += $(RT)/wubu_ct_isolate.o
HOSTED_OBJS += $(RT)/wubu_ct_isolate.o

# Test targets include wubu_ct_isolate.c
test_wubu, test_hosted, test_host_exec, test_arch
```

### .wubu Container Format (Phase 3 - Cell 480)

#### Overview
The `.wubu` package format provides a portable container format for Windows/Wine applications managed by Bottles and Lutris. Each `.wubu` file is a tar.zst (or squashfs) archive containing a complete Arch Linux rootfs + Wine prefix + dependency manifests.

#### Structure
```
wubu/
  meta.json          # Package metadata (name, version, runner, deps, DXVK/GameScope configs, mounts, env)
  rootfs/            # Arch Linux rootfs (overlay)
  prefix/            # Wine prefix (drive_c, etc.)
  dependencies/      # Dependency manifests (DXVK, VKD3D, vcrun, dotnet, etc.)
  scripts/           # Pre/post install scripts
  icons/             # App icons
  desktop/           # .desktop files
```

#### meta.json Schema
```json
{
  "name": "MyGame",
  "version": "1.0.0",
  "wubu_version": "2",
  "runner": "wine-ge-9-20",
  "arch": "win64",
  "dependencies": ["dxvk", "vkd3d", "vcrun2019", "dotnet48"],
  "dxvk_config": { "async": true, "hud": "fps" },
  "gamescope": { "mode": "steam_deck", "fsr": true },
  "gpu_passthrough": true,
  "hid_passthrough": true,
  "environment": { "WINEDEBUG": "-all", "DXVK_ASYNC": "1" },
  "mounts": [
    { "host": "/home/user/Games/MyGame", "guest": "/home/wubu/MyGame" }
  ]
}
```

#### API (src/runtime/wubu_bottles.h/c)
- `WubuBottle` struct — Complete bottle descriptor (runner, deps, mounts, env, DXVK/GameScope configs)
- `wubu_bottle_create/load/save/install/uninstall/run()` — Full lifecycle
- `wubu_bottle_add/remove_dep()` — Dependency management (DXVK, VKD3D, vcrun, dotnet, etc.)
- `wubu_bottle_dep_available()` — Runner-specific availability check
- `wubu_bottle_add/remove_mount()` — Bind mount management
- `wubu_bottle_set/get_env()` — Environment variables
- `wubu_bottle_import_bottles()` / `wubu_bottle_export_bottles()` — Bottles format integration
- `wubu_bottle_import_lutris()` / `wubu_bottle_export_lutris()` — Lutris integration
- `wubu_bottle_flatpak_manifest()` — Flatpak export stub

#### Test Coverage
- `test_bottles`: 16/16 passing (creation, deps, mounts, env, configs, Flatpak)

---

### WuBuContainer Integration (2026-07-05)

#### Overview
Integrated `https://github.com/waefrebeorn/WuBuContainer` as git submodule at `src/runtime/container/wubucontainer` and created C interface for the agentic latent AGI layer.

#### Submodule Setup
```bash
cd /home/wubu/wubuos
git submodule add https://github.com/waefrebeorn/WuBuContainer src/runtime/container/wubucontainer
```

#### C Interface Created

##### `src/runtime/container/wubucontainer.h` (240 lines)
Public API with opaque `WubuContainerEngine`:
- `wubu_container_init()` / `wubu_container_shutdown()` — engine lifecycle
- `wubu_container_convert_file()` — convert any file to any format
- `wubu_container_convert_buffer()` — in-memory conversion
- `wubu_container_find_path()` — graph traversal for format conversion paths
- `wubu_container_to_canonical()` / `wubu_container_from_canonical()` — **agentic layer primitives**
- `wubu_container_batch_convert()` — bulk operations
- `wubu_container_detect_format()` — magic byte / extension detection

**Canonical representations for agents:**
- Images → PNG (lossless) / JPEG (perceptual)
- Audio → WAV (raw PCM) / OPUS (compressed)
- Video → WebM/VP9 / MP4/H.264
- Documents → Markdown / JSON
- Archives → TAR
- 3D Models → glTF
- Fonts → TTF/OTF
- Executables → ELF analysis JSON

##### `src/runtime/container/wubucontainer.c` (696 lines)
Implementation using JSON-RPC over Unix socket pair to long-running Bun/Node.js + Electron + WASM subprocess:
- Spawns `bun run src/main.ts --ipc-mode` in container submodule dir
- Communicates via length-prefixed JSON-RPC 2.0 over stdin/stdout
- Spawns engine as child process, manages lifecycle

##### Makefile Integration
```makefile
# Added to RT_OBJS
RT_OBJS = ... $(RT)/container/wubucontainer.o

# Pattern rule
$(RT)/container/%.o: $(RT)/container/%.c
	$(CC) $(CFLAGS) -I$(RT) -I$(RT)/container -I$(COMP) -I$(JIT) -c $< -o $@
```

#### Test Results
```
make clean && make runtime
✅ WuBuOS runtime built

All existing tests still pass:
test_oci: 10/10 ✅
test_wm: 16/16 ✅
test_vsl: 62/62 ✅
test_network: 139/139 ✅
test_snapshot: 132/132 ✅
```

#### Architecture Notes
- **WuBuContainer** is a universal file converter (80+ format handlers: FFmpeg, ImageMagick, Pandoc, WASM runtimes, etc.)
- Runs in Electron/Bun with WASM for heavy lifting
- Graph-based conversion path finding (AVI → PDF via multiple hops)
- C interface enables WuBuOS agents to convert arbitrary formats to canonical representations for reasoning/synthesis
- Submodule tracks upstream independently; `git submodule update --remote` pulls latest converters

#### Agentic Layer Usage Pattern
```c
// Agent receives unknown format input
WubuContainerEngine *engine;
wubu_container_init(&engine, "/path/to/wubucontainer");

// Convert to canonical form for reasoning
wubu_container_to_canonical(engine, "input.xyz", "/tmp/canonical", "image");

// ... agent reasons on canonical PNG ...

// Synthesize output in target format
wubu_container_from_canonical(engine, "/tmp/canonical/canonical.png", "webp", "output.webp");

wubu_container_shutdown(engine);
```

#### Files Created
```
src/runtime/container/
├── wubucontainer.h       (240 lines, public API)
├── wubucontainer.c       (696 lines, JSON-RPC impl)
└── wubucontainer/        (git submodule: WuBuContainer)
    ├── src/
    │   ├── handlers/     (80+ format handlers)
    │   ├── main.ts       (Electron entry point)
    │   ├── FormatHandler.ts
    │   ├── TraversionGraph.ts
    │   └── ...
    ├── package.json      (deps: ffmpeg, imagemagick, pandoc, wasm runtimes)
    └── ...
```

#### Lessons Learned
1. **Submodule + C wrapper pattern** — keeps heavy JS/WASM runtime isolated, C side stays thin
2. **JSON-RPC over socket pair** — robust IPC, language-agnostic, handles large payloads
3. **Canonical forms as agent primitives** — agents don't need format knowledge, just media type
4. **Length-prefixed JSON-RPC** — simple framing, no delimiter parsing issues
5. **Submodule in `src/runtime/container/`** — follows existing `src/runtime/vsl/`, `src/runtime/oci/` patterns

- **`ct->envp` is IGNORED by `execv` — seccomp/namespace/no-ns flags never reach the payload (2026-07-22 fix).** `wubu_ct_start()`'s child did `execv(ct->argv[0], ct->argv)` — `execv` takes NO envp, so the `WUBU_SECCOMP_PROFILE` / `WUBU_NS_FLAGS` / `WUBU_REPO_ROOT` you registered via `wubu_ct_add_env(ct, "NAME=VALUE")` were never applied. Symptom: a payload that needs relaxed isolation (e.g. Wine via `wubu_exec_win_pe`, which sets `WUBU_SECCOMP_PROFILE=wine`/`none` + `WUBU_NS_FLAGS=0` to avoid SIGSYS) dies with **SIGSYS (`wubu_ct_wait` returns `-WTERMSIG(31)` = -31)** because the child fell back to the DEFAULT full-isolation seccomp (and `wubu_ct_child_isolation()` reads the profile from `getenv`, which saw nothing). **Fix:** in the child, BEFORE `wubu_ct_child_isolation()` (which reads those env vars), loop over `ct->envp[]` and `setenv` each entry (`char *eq = strchr(p,'='); *eq='\0'; setenv(p, eq+1, 1); *eq='=';`). Then `execv` inherits them. **Order is critical** — isolation reads env, so env must be applied first. Also: `wubu_ct_child_isolation` `chroot("/")` is a no-op but STILL `chdir`s the child to `/` when `ct->root[0]` is truthy (e.g. the literal `/`); for a host-namespace container set `ct->root` to `""` (or skip chroot when root is `/`) and instead `chdir(parent_cwd)` (capture `getcwd` in the parent before fork) so CWD-relative payload output (marker files) lands where the caller can see it. **Trap: Wine changes its own CWD to the launched `.exe`'s directory**, so a relative marker path written by a Win32 demo lands next to the temp exe (e.g. `/tmp`), not the repo — pass an absolute path via env (`WUBU_REPO_ROOT`) and have the demo `CreateFileA(getenv("WUBU_REPO_ROOT")+"/marker")`. Verified: `test_era_apps` Win32 leg went from SIGSYS to writing its marker after this fix.

### Pitfalls
- cgroups v2 requires root for creating base cgroup (but we delegate to system)
- seccomp requires `PR_SET_NO_NEW_PRIVS` before filter install
- BPF macros conflict with `linux/filter.h` — use `#undef` + custom defs
- `offsetof(struct seccomp_data, ...)` doesn't work in BPF — use hardcoded offsets (0=nr, 4=arch)
- `__NR_waitpid` not a direct syscall on x86_64 → use `__NR_wait4`
- `__NR_fstatat` → `__NR_newfstatat`
- Zombie accumulation from fork+exec tests: always check `ps aux | grep test` after running fork-heavy tests
- Test timeout ≠ test failure: run the binary directly (`timeout 10 ./src/runtime/test_binary`) to rule out build/link latency
- Don't let forked children run for days — `pkill -9 -f "wubu_container_test"` after each test run
- **Env-delivery order bug has a fast confirm probe.** When a payload ignores a `WUBU_*` setting you registered via `wubu_ct_add_env`, see [`references/verify-container-env-reaches-payload.md`](references/verify-container-env-reaches-payload.md) — the `[seccomp-debug]` stderr print that tells `profile=(null)` (env never delivered / applied after isolation) from `profile=none/wine` (delivered, profile too narrow), plus the Wine-CWD-marker subtlety.

### OCI Runtime (wubu_oci.c)

See [`references/oci-runtime-operations.md`](references/oci-runtime-operations.md) for:
- Registry API endpoints and URL formats
- Manifest/config JSON schemas
- Function-level fix notes (sha256_file recursion, get_blob handle leak, etc.)
- **Native HTTP client implementation** (removed curl CLI dependency — 2026-06-28)
- Build/test commands and pitfalls

### Binary-format execution legs (ELF / PE / Mach-O / DOS MZ loaders + rootfs runner)

See [`references/binary-loader-legs.md`](references/binary-loader-legs.md) for the
loader construction pattern (validate → extent pass → zero-arena → copy pass →
entry = base + (entry_field − lo)), the per-format gotchas (PE SizeOfRawData
clamp, Mach-O LC_SEGMENT_64 walk, DOS MZ reloc fixups, ELF ET_EXEC vs ET_DYN),
the rule to verify against a REAL toolchain-produced binary, and the
distro-agnostic rootfs container runner that composes the ELF loader.

### OCI Layer Blob Copy — sendfile() Replaces system("cp") (2026-06-28)

**Gap**: `system("cp '%s' '%s' 2>/dev/null")` in `oci_image_from_manifest()` copying layer blobs.

**Fix**: Native `sendfile()` kernel copy:
```c
int src_fd = open(src_path, O_RDONLY);
struct stat st;
fstat(src_fd, &st);
int dst_fd = open(dst_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
off_t offset = 0;
ssize_t sent = sendfile(dst_fd, src_fd, &offset, st.st_size);
close(src_fd);
close(dst_fd);
if (sent != st.st_size) unlink(dst_path);  // Cleanup partial copy
```

**Verification**: `make test_oci` → 10/10 pass

### Real Zip Archive Mounting in explorer (Option C - 2026-06-28)

**Gap**: `explorer_mount_zip()` was a stub returning `false` with comment "Not implemented".

**Implementation** (`src/gui/explorer.c`):

| Component | Approach |
|-----------|----------|
| **Primary** | Try libzip via `dlopen("libzip.so.4")` — use `zip_open`, `zip_get_num_entries`, `zip_get_name`, `zip_close` |
| **Fallback** | Raw zip central directory parser using zlib structures (no headers needed) |

**Key Structures**:
```c
#pragma pack(push, 1)
typedef struct { uint32_t signature; ... } ZipCentralDirHeader;
typedef struct { uint32_t signature; ... } ZipEndCentralDir;
#pragma pack(pop)

typedef struct {
    char name[256];
    uint64_t uncompressed_size, compressed_size;
    uint32_t crc32;
    uint16_t compression_method;
    time_t modified;
    int central_dir_index;
    bool is_directory;
} ExZipEntry;
```

**Functions Added**:
| Function | Purpose |
|----------|---------|
| `ex_libzip_load()` | `dlopen` libzip.so.4 + resolve symbols |
| `ex_zip_read_central_directory(path)` | Raw parser: finds EOCD, reads CD entries, converts DOS timestamps |
| `ex_zip_populate_entries()` | Converts `ExZipEntry[]` → `ExEntry[]` for explorer UI |
| `explorer_mount_zip(path)` | Tries libzip first, falls back to raw parser |
| `explorer_unmount_zip()` | Clears cache, navigates up |

**ZIP Format Details**:
- Signatures: Local=0x04034b50, Central=0x02014b50, EOCD=0x06054b50
- EOCD search: last 64KB of file
- DOS time conversion: bits for year/month/day/hour/min/2sec
- Directory detection: trailing '/' or zero size

**Test Added** (`explorer_test.c`):
```c
bool ret = explorer_mount_zip("/tmp/test.zip");
TEST_ASSERT(ret, "mount_zip returns true for real zip");
TEST_ASSERT(explorer_is_in_zip(), "in_zip_archive is true after mount");
TEST_ASSERT(ex->entry_count > 0, "entries populated from zip");
explorer_unmount_zip();
TEST_ASSERT(!ex->in_zip_archive, "unmount_zip clears flag");
ret = explorer_mount_zip("/fake/archive.zip");
TEST_ASSERT(!ret, "mount_zip returns false for missing file");
```

**Verification**: `make test_explorer` → 74/74 pass (real zip mount/unmount)

### Option C Feature Complete — All Items Done

| Item | Status | Location |
|------|--------|----------|
| **libzip integration** (zip mount) | ✅ Complete | `explorer.c` |
| **PTY + ANSI parser** (terminal) | ✅ Already complete | `term.c` |
| **.desktop parser** (start menu) | ✅ Already complete | `wubu_mime.c` (scans XDG dirs) |
| **Notification history + actions** | ✅ Already complete | `wubu_notify.c` |

**Verification**: `make test` (and the isolation-specific targets) must pass. Run for the live target/assertion count; do not cite a fixed total.