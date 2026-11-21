# cgroups v2 I/O Controller Reference (wubu_ct_isolate.c)

## Overview
Extension to WuBuOS container isolation adding cgroups v2 `io` controller support for bandwidth limiting and weight-based I/O scheduling.

## New API

### `wubu_ct_cgroup_set_io_max()`
```c
int wubu_ct_cgroup_set_io_max(const char* cgroup_path,
                              uint64_t read_bps, uint64_t write_bps);
```
- Sets `io.max` in container cgroup
- Format: `8:0 rbps=X wbps=Y` (8:0 = major:minor for block device, typically sda)
- `read_bps`/`write_bps` = 0 → writes `"max"` (unlimited)
- Returns 0 on success, -1 on failure

### `wubu_ct_cgroup_set_io_weight()`
```c
int wubu_ct_cgroup_set_io_weight(const char* cgroup_path, uint32_t weight);
```
- Sets `io.weight` in container cgroup
- Range: 1-10000, default 100
- 0 → uses default (100)
- Returns 0 on success, -1 on failure

## WubuCt Struct Extensions (wubu_host_exec.h)
```c
typedef struct {
    // ... existing fields ...
    uint64_t io_read_bps;   // I/O read bandwidth limit (bytes/sec, 0 = unlimited)
    uint64_t io_write_bps;  // I/O write bandwidth limit (bytes/sec, 0 = unlimited)
    uint32_t io_weight;     // I/O weight (1-10000, 0 = default 100)
} WubuCt;
```

## Integration in `wubu_ct_setup_isolation()`
```c
/* I/O controller limits (procmem/io) */
if (ct->io_read_bps > 0 || ct->io_write_bps > 0) {
    wubu_ct_cgroup_set_io_max(cgroup_path, ct->io_read_bps, ct->io_write_bps);
}
if (ct->io_weight > 0) {
    wubu_ct_cgroup_set_io_weight(cgroup_path, ct->io_weight);
}
```

## Namespace Isolation Constant
```c
#define WUBU_NS_FLAGS (CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWNET | \
                       CLONE_NEWUSER | CLONE_NEWUTS | CLONE_NEWIPC)
```

## Child Isolation Integration
```c
/* Unshare namespaces for container isolation */
const char* ns_flags_str = getenv("WUBU_NS_FLAGS");
if (ns_flags_str) {
    int flags = atoi(ns_flags_str);
    if (flags != 0) wubu_ns_unshare(flags);
} else {
    wubu_ns_unshare(WUBU_NS_FLAGS);  // Default: full isolation
}
```

## cgroup v2 io Controller Requirements
- Kernel 5.4+ (io controller introduced in 5.4)
- `io` controller must be enabled in parent's `cgroup.subtree_control`:
  ```bash
  echo "+io" > /sys/fs/cgroup/wubu/cgroup.subtree_control
  ```
- Block device major:minor (8:0 for sda) — may need dynamic detection for other devices

## Example Usage
```c
// Create container with 100MB/s read, 50MB/s write limit, weight 200
WubuCt* ct = wubu_ct_create("my-container", "/var/wubu/roots/arch", CT_NATIVE);
ct->mem_limit_mb = 2048;
ct->cpu_limit = 4;
ct->io_read_bps = 100 * 1024 * 1024;   // 100 MB/s
ct->io_write_bps = 50 * 1024 * 1024;   // 50 MB/s
ct->io_weight = 200;
wubu_ct_setup_isolation(ct);
wubu_ct_start(ct);
```

## cgroup Files Created
```
/sys/fs/cgroup/wubu/my-container/
├── cgroup.procs
├── cgroup.subtree_control
├── memory.max
├── cpu.max
├── pids.max
├── io.max          # "8:0 rbps=104857600 wbps=52428800"
├── io.weight       # "200"
├── io.stat         # I/O statistics (read-only)
└── io.pressure     # I/O pressure stall info (read-only)
```

## Testing
```bash
# Verify cgroup limits applied
cat /sys/fs/cgroup/wubu/my-container/io.max
cat /sys/fs/cgroup/wubu/my-container/io.weight

# Run I/O benchmark inside container
# Should observe bandwidth throttling
```

## Notes
- Non-fatal if cgroups unavailable (returns 0, continues without limits)
- Requires `<sched.h>` for `CLONE_*` constants in `wubu_ct_isolate.c`
- `io.max` uses device major:minor — currently hardcoded to 8:0 (first SCSI/SATA disk)
- For production, consider detecting actual block device from container rootfs