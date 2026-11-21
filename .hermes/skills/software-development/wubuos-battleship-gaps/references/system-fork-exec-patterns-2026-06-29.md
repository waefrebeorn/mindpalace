# system() → fork/exec Conversion Patterns (2026-06-29)

This session closed **20 `system()` calls** across 4 files by replacing with native C fork/exec implementations.

## Files Modified

| File | `system()` Calls | Replacement Pattern |
|------|------------------|---------------------|
| `src/runtime/wubu_arch.c` | 7 | `run_cmd(cmd, progress)` — fork/exec `/bin/sh -c` with optional progress callback |
| `src/runtime/wubu_archd.c` | 6 | `rm_rf()` via `nftw()` + `run_chroot_cmd()` for chroot operations |
| `src/runtime/wubu_ramdisk.c` | 1 | `run_cmd()` fork/exec |
| `src/gui/wubu_pkgmgr.c` | 6 | tar\|zstd pipeline, glob/unlink, stat-based cleanup |

---

## Pattern 1: Simple fork/exec with progress callback (`wubu_arch.c`)

```c
/* -- Helper: run command via fork+exec (no system()) -------------- */

static int run_cmd(const char *cmd, void (*progress)(const char *msg)) {
    if (progress) progress(cmd);

    pid_t pid = fork();
    if (pid < 0) return -1;

    if (pid == 0) {
        /* Child: execute via /bin/sh -c */
        execl("/bin/sh", "sh", "-c", cmd, (char*)NULL);
        _exit(127);
    }

    /* Parent: wait for child */
    int status;
    waitpid(pid, &status, 0);
    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    return -1;
}
```

**Usage:**
```c
// With progress callback
int ret = run_cmd("pacstrap -c /mnt/root base base-devel ...", progress_cb);

// Without callback
int ret = run_cmd("chroot /mnt/root locale-gen", NULL);
```

---

## Pattern 2: Recursive directory removal via nftw (`wubu_archd.c`)

```c
#include <ftw.h>

static int unlink_cb(const char *fpath, const struct stat *sb, int typeflag, struct FTW *ftwbuf) {
    (void)sb; (void)typeflag; (void)ftwbuf;
    return unlink(fpath) == 0 ? 0 : -1;
}

static int rm_rf(const char *path) {
    if (!path) return -1;
    return nftw(path, unlink_cb, 64, FTW_DEPTH | FTW_PHYS);
}
```

**Usage:**
```c
int ret = rm_rf(r->path);  // Replaces: system("rm -rf /path")
```

---

## Pattern 3: chroot command execution (`wubu_archd.c`)

```c
#include <stdarg.h>

static int run_chroot_cmd(const char *root, const char *fmt, ...) {
    char cmd[WUBU_ARCHD_MAX_CMD];
    va_list args;
    va_start(args, fmt);
    vsnprintf(cmd, sizeof(cmd), fmt, args);
    va_end(args);
    
    pid_t pid = fork();
    if (pid < 0) return -1;
    
    if (pid == 0) {
        execl("/bin/sh", "sh", "-c", cmd, (char*)NULL);
        _exit(127);
    }
    
    int status;
    waitpid(pid, &status, 0);
    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    return -1;
}
```

**Usage:**
```c
return run_chroot_cmd(r.path, "arch-chroot %s pacman -R --noconfirm %s", r.path, packages);
return run_chroot_cmd(r.path, "arch-chroot %s systemctl disable %s 2>/dev/null", r.path, svc);
```

---

## Pattern 4: tar + zstd pipeline (`wubu_pkgmgr.c`)

```c
/* Fork and exec tar | zstd pipeline */
int pipefd[2];
if (pipe(pipefd) < 0) return false;

pid_t tar_pid = fork();
if (tar_pid == 0) {
    close(pipefd[0]);
    dup2(pipefd[1], STDOUT_FILENO);
    close(pipefd[1]);
    if (chdir(payload_dir) < 0) _exit(1);
    execlp("tar", "tar", "-cf", "-", ".", (char*)NULL);
    _exit(1);
}

pid_t zstd_pid = fork();
if (zstd_pid == 0) {
    close(pipefd[1]);
    dup2(pipefd[0], STDIN_FILENO);
    close(pipefd[0]);
    
    int out_fd = open(payload_archive, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (out_fd < 0) _exit(1);
    dup2(out_fd, STDOUT_FILENO);
    close(out_fd);
    
    execlp("zstd", "zstd", "-3", (char*)NULL);
    _exit(1);
}

close(pipefd[0]);
close(pipefd[1]);
waitpid(tar_pid, &tar_status, 0);
waitpid(zstd_pid, &zstd_status, 0);

if (!WIFEXITED(tar_status) || WEXITSTATUS(tar_status) != 0 ||
    !WIFEXITED(zstd_status) || WEXITSTATUS(zstd_status) != 0) {
    return false;
}
```

---

## Pattern 5: Glob + unlink for pattern matching (`wubu_pkgmgr.c`)

```c
#include <glob.h>

char desktop_pattern[512];
snprintf(desktop_pattern, sizeof(desktop_pattern), 
         "%s/share/applications/%s-*.desktop", 
         g_pkgmgr.config.install_prefix, pkg_id);

glob_t glob_result;
if (glob(desktop_pattern, 0, NULL, &glob_result) == 0) {
    for (size_t i = 0; i < glob_result.gl_pathc; i++) {
        unlink(glob_result.gl_pathv[i]);
    }
    globfree(&glob_result);
}
```

---

## Pattern 6: stat-based cleanup by age (`wubu_pkgmgr.c`)

```c
char cache_pattern[512];
snprintf(cache_pattern, sizeof(cache_pattern), "%s/*.wubu", g_pkgmgr.config.cache_dir);

glob_t glob_result;
if (glob(cache_pattern, 0, NULL, &glob_result) == 0) {
    time_t now = time(NULL);
    time_t cutoff = now - (max_age_days * 86400);
    
    for (size_t i = 0; i < glob_result.gl_pathc; i++) {
        struct stat st;
        if (stat(glob_result.gl_pathv[i], &st) == 0) {
            if (st.st_mtime < cutoff) {
                unlink(glob_result.gl_pathv[i]);
            }
        }
    }
    globfree(&glob_result);
}
```

---

## Key Principles

1. **Always use `fork()` + `exec*()`** — never `system()`
2. **Child calls `_exit()` not `exit()`** — avoids flushing parent's stdio buffers
3. **Parent uses `waitpid()`** — captures exit status correctly
4. **Check `WIFEXITED()` + `WEXITSTATUS()`** — robust error handling
5. **Use `nftw()` for recursive removal** — handles symlinks, deep trees correctly
6. **Use `glob()` for pattern matching** — replaces shell `*.pattern` expansion
7. **Use `stat()` for metadata** — file age, size, type checks without shell
8. **Include `_GNU_SOURCE` for `nftw`/`accept4`** — defines FTW_* constants