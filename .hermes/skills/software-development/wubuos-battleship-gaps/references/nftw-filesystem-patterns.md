# nftw() Filesystem Patterns (wubu_snapshot.c, wubu_holyd.c)

## Overview
Replace `system("cp -a")` and `system("rm -rf")` with proper `nftw()`-based recursive operations.

---

## nftw-Based Recursive Copy

### Context Struct
```c
typedef struct {
    const char *src_root;
    const char *dst_root;
    uint64_t bytes_copied;
    int files_copied;
    int errors;
} CopyContext;
```

### nftw Callback (Standard C compatible)
```c
// Static context workaround (nftw doesn't support user_data in standard C)
static CopyContext *g_copy_ctx = NULL;

static int copy_ftw_callback(const char *fpath, const struct stat *sb,
                             int typeflag, struct FTW *ftwbuf) {
    CopyContext *ctx = g_copy_ctx;
    if (!ctx) return -1;
    
    // Compute relative destination path
    const char *rel = fpath + strlen(ctx->src_root);
    while (*rel == '/') rel++;
    char dst_path[WUBU_MAX_PATH];
    snprintf(dst_path, sizeof(dst_path), "%s/%s", ctx->dst_root, rel);
    
    switch (typeflag) {
    case FTW_D:     // directory (pre-order)
    case FTW_DP:    // directory (post-order)
    case FTW_DNR:   // directory not readable
        if (mkdir(dst_path, sb->st_mode & 0777) < 0 && errno != EEXIST) {
            fprintf(stderr, "[copy] mkdir %s failed: %s\n", dst_path, strerror(errno));
            ctx->errors++; return -1;
        }
        // Preserve timestamps
        struct timespec times[2] = { {sb->st_atime, 0}, {sb->st_mtime, 0} };
        utimensat(AT_FDCWD, dst_path, times, AT_SYMLINK_NOFOLLOW);
        break;
        
    case FTW_F:     // regular file
    case FTW_SL:    // symlink
    case FTW_SLN:   // dangling symlink
        if (typeflag == FTW_SL || typeflag == FTW_SLN) {
            char link_target[WUBU_MAX_PATH];
            ssize_t len = readlink(fpath, link_target, sizeof(link_target) - 1);
            if (len > 0) {
                link_target[len] = '\0';
                if (symlink(link_target, dst_path) < 0 && errno != EEXIST) {
                    fprintf(stderr, "[copy] symlink %s -> %s failed: %s\n", 
                            dst_path, link_target, strerror(errno));
                    ctx->errors++; return -1;
                }
            }
        } else {
            // Regular file: copy with sendfile
            int src_fd = open(fpath, O_RDONLY);
            if (src_fd < 0) { ctx->errors++; return -1; }
            int dst_fd = open(dst_path, O_WRONLY | O_CREAT | O_TRUNC, sb->st_mode & 0777);
            if (dst_fd < 0) { close(src_fd); ctx->errors++; return -1; }
            
            off_t offset = 0;
            ssize_t sent = sendfile(dst_fd, src_fd, &offset, sb->st_size);
            close(src_fd); close(dst_fd);
            
            if (sent != sb->st_size) { ctx->errors++; return -1; }
            ctx->bytes_copied += sent;
            ctx->files_copied++;
            
            // Preserve timestamps
            struct timespec times[2] = { {sb->st_atime, 0}, {sb->st_mtime, 0} };
            utimensat(AT_FDCWD, dst_path, times, AT_SYMLINK_NOFOLLOW);
        }
        break;
    }
    return 0;
}
```

### Wrapper Function
```c
static int copy_tree_nftw(const char *src, const char *dst, 
                          uint64_t *out_bytes, int *out_files) {
    if (!src || !dst) return -1;
    
    if (mkdir(dst, 0755) < 0 && errno != EEXIST) return -1;
    
    CopyContext ctx = { .src_root = src, .dst_root = dst,
                       .bytes_copied = 0, .files_copied = 0, .errors = 0 };
    g_copy_ctx = &ctx;
    
    int flags = FTW_PHYS | FTW_DEPTH | FTW_MOUNT;
    int rc = nftw(src, copy_ftw_callback, 64, flags);
    g_copy_ctx = NULL;
    
    if (out_bytes) *out_bytes = ctx.bytes_copied;
    if (out_files) *out_files = ctx.files_copied;
    return (rc == 0 && ctx.errors == 0) ? 0 : -1;
}
```

### Key nftw Flags
- `FTW_PHYS` — Don't follow symlinks (use lstat, not stat)
- `FTW_DEPTH` — Post-order traversal (children before parent)
- `FTW_MOUNT` — Don't cross filesystem boundaries
- `FTW_D`, `FTW_DP`, `FTW_DNR` — Directory types
- `FTW_F`, `FTW_SL`, `FTW_SLN`, `FTW_NS` — File/symlink types

---

## Dynamic Path Allocation Pattern (wubu_holyd.c)

### Path Join Helper
```c
static char *holyd_path_join(const char *base, const char *name) {
    if (!base || !name) return NULL;
    size_t base_len = strlen(base), name_len = strlen(name_len = strlen(name);
    char *result = malloc(base_len + 1 + name_len + 1);
    if (!result) return NULL;
    memcpy(result, base, base_len);
    result[base_len] = '/';
    memcpy(result + base_len + 1, name, name_len);
    result[base_len + 1 + name_len] = '\0';
    return result;
}
```

### Safe snprintf with Reallocation
```c
static int holyd_snprintf_alloc(char **out, size_t *out_size, const char *fmt, ...) {
    va_list ap, ap2; va_start(ap, fmt); va_copy(ap2, ap);
    int needed = vsnprintf(NULL, 0, fmt, ap); va_end(ap);
    if (needed < 0) return -1;
    if ((size_t)needed + 1 > *out_size) {
        *out_size = needed + 1;
        *out = realloc(*out, *out_size);
        if (!*out) return -1;
    }
    int written = vsnprintf(*out, *out_size, fmt, ap2);
    va_end(ap2);
    return written;
}
```

### Usage Examples
```c
// Session directory creation (replaces snprintf + fixed buffer)
s->save_path = holyd_path_join(d->config.sessions_path, name);
if (!s->save_path) return -1;
mkdir(s->save_path, 0755);

// Mount point (replaces strncpy + fixed buffer)
if (s->mount_point) free(s->mount_point);
s->mount_point = strdup(path);
if (!s->mount_point) return -1;

// Save file path
char *save_file = holyd_path_join(s->save_path, "session.sav");
FILE *f = fopen(save_file, "w"); free(save_file);

// Event path
char *event_path = holyd_path_join(d->config.sessions_path, "events");
FILE *f = fopen(event_path, "a"); free(event_path);
```

### Session Struct Changes
```c
typedef struct {
    // ... other fields ...
    char *save_path;            // Was: char save_path[WUBU_HOLYD_MAX_PATH];
    char *mount_point;          // Was: char mount_point[WUBU_HOLYD_MAX_PATH];
    // ... other fields ...
} WubuHolySession;
```

### Cleanup in Destroy
```c
if (s->save_path) { free(s->save_path); s->save_path = NULL; }
if (s->mount_point) { free(s->mount_point); s->mount_point = NULL; }
```

---

## Filesystem Detection (wubu_snapshot.c)

### btrfs Detection
```c
static bool is_btrfs(const char *path) {
    struct statfs fs;
    if (statfs(path, &fs) < 0) return false;
    return fs.f_type == BTRFS_SUPER_MAGIC;
}
```

### zfs Detection
```c
static bool is_zfs(const char *path) {
    struct statfs fs;
    if (statfs(path, &fs) < 0) return false;
    return fs.f_type == 0x2fc12fc1;  // ZFS_SUPER_MAGIC
}
```

### btrfs Native Snapshot (IOCTL)
```c
static int btrfs_snapshot_create(const char *src, const char *dst) {
    int fd = open(dst, O_RDONLY | O_DIRECTORY);
    if (fd < 0) return -1;
    
    struct btrfs_ioctl_vol_args_v2 args = {0};
    strncpy(args.name, basename((char *)src), BTRFS_PATH_NAME_MAX - 1);
    args.flags = 0;  // read-only snapshot
    
    int rc = ioctl(fd, BTRFS_IOC_SNAP_CREATE_V2, &args);
    close(fd);
    return rc;
}
```

### Mount Dispatch by Filesystem
```c
static int snapshot_mount_fs(WubuSnapshot *s, WubuSnapshotManager *mgr) {
    if (!s || !s->lower_dir[0] || !s->upper_dir[0] || !s->work_dir[0] || !s->merged_dir[0])
        return -EINVAL;
    
    // Ensure mount point exists
    if (mkdir(s->merged_dir, 0755) < 0 && errno != EEXIST) return -errno;
    
    if (mgr->fs_type == WUBU_FS_BTRFS && is_btrfs(s->lower_dir))
        return btrfs_snapshot_create(s->lower_dir, s->upper_dir);
    else if (mgr->fs_type == WUBU_FS_ZFS && is_zfs(s->lower_dir))
        return zfs_snapshot_create(s->lower_dir, s->upper_dir);
    else {
        // overlayfs fallback
        char mount_opts[2048];
        snprintf(mount_opts, sizeof(mount_opts),
                 "lowerdir=%s,upperdir=%s,workdir=%s",
                 s->lower_dir, s->upper_dir, s->work_dir);
        int rc = mount("overlay", s->merged_dir, "overlay", 0, mount_opts);
        
        if (rc != 0 && (errno == ENOSYS || errno == ENODEV || errno == EOPNOTSUPP)) {
            // Bind mount fallback
            rc = mount(s->lower_dir, s->merged_dir, NULL, MS_BIND | MS_REC, NULL);
            if (rc == 0) rc = mount(s->upper_dir, s->merged_dir, NULL, MS_BIND | MS_REC, NULL);
        }
        return rc ? -errno : 0;
    }
}
```

---

## Required Headers
```c
#define _GNU_SOURCE
#define _XOPEN_SOURCE 700
#include <ftw.h>
#include <sys/sendfile.h>
#include <sys/vfs.h>       // statfs
#include <linux/fs.h>      // BTRFS_SUPER_MAGIC
#include <linux/btrfs.h>   // btrfs_ioctl_vol_args_v2, BTRFS_IOC_SNAP_CREATE_V2
#include <sys/mount.h>     // mount, MS_BIND, MS_REC
```