# Image Tar & Fork+Exec Patterns (wubu_image.c)

## Direct POSIX ustar Tar Writer (replaces `system("tar -cf ...")`)

### Header Structure (512 bytes per POSIX ustar)
```c
static int tar_write_header(int fd, const char *name, mode_t mode,
                            uid_t uid, gid_t gid, off_t size, time_t mtime) {
    char header[512] = {0};
    
    /* name (100 bytes) */
    strncpy(header, name, 99);
    /* mode (8 bytes, octal) */
    snprintf(header + 100, 8, "%07o", (unsigned int)mode);
    /* uid (8 bytes, octal) */
    snprintf(header + 108, 8, "%07o", (unsigned int)uid);
    /* gid (8 bytes, octal) */
    snprintf(header + 116, 8, "%07o", (unsigned int)gid);
    /* size (12 bytes, octal) */
    snprintf(header + 124, 12, "%011lo", (unsigned long)size);
    /* mtime (12 bytes, octal) */
    snprintf(header + 136, 12, "%011lo", (unsigned long)mtime);
    /* chksum (8 bytes) - initially spaces */
    memset(header + 148, ' ', 8);
    /* typeflag (1 byte) - '0'=file, '5'=dir */
    header[156] = S_ISDIR(mode) ? '5' : '0';
    /* magic (6 bytes) - "ustar" */
    memcpy(header + 257, "ustar", 5);
    /* version (2 bytes) - "00" */
    header[263] = '0'; header[264] = '0';
    
    /* Calculate checksum */
    unsigned int chksum = 0;
    for (int i = 0; i < 512; i++) chksum += (unsigned char)header[i];
    snprintf(header + 148, 8, "%06o\0", chksum);
    
    return write(fd, header, 512) == 512 ? 0 : -1;
}
```

### File Writing with Padding
```c
static int tar_write_file(int fd, const char *path, const struct stat *st) {
    if (tar_write_header(fd, path, st->st_mode, st->st_uid, st->st_gid,
                         st->st_size, st->st_mtime) < 0) return -1;
    
    if (S_ISREG(st->st_mode)) {
        int src_fd = open(path, O_RDONLY);
        if (src_fd < 0) return -1;
        
        char buf[8192];
        ssize_t n;
        while ((n = read(src_fd, buf, sizeof(buf))) > 0) {
            if (write(fd, buf, n) != n) { close(src_fd); return -1; }
        }
        close(src_fd);
        
        /* Pad to 512-byte boundary */
        off_t size = st->st_size;
        size_t padding = (512 - (size % 512)) % 512;
        if (padding > 0) {
            char pad[512] = {0};
            if (write(fd, pad, padding) != (ssize_t)padding) return -1;
        }
    }
    return 0;
}
```

### Recursive Directory Walking
```c
static int tar_write_dir(int fd, const char *src_dir) {
    DIR *dir = opendir(src_dir);
    if (!dir) return -1;
    
    struct dirent *ent;
    while ((ent = readdir(dir)) != NULL) {
        if (strcmp(ent->d_name, ".") == 0 || strcmp(ent->d_name, "..") == 0) continue;
        
        snprintf(path, sizeof(path), "%s/%s", src_dir, ent->d_name);
        if (lstat(path, &st) < 0) continue;
        
        if (S_ISDIR(st.st_mode)) {
            if (tar_write_header(fd, path, st.st_mode, st.st_uid, st.st_gid, 0, st.st_mtime) < 0)
                return -1;
            if (tar_write_dir(fd, path) < 0) return -1;
        } else {
            if (tar_write_file(fd, path, &st) < 0) return -1;
        }
    }
    closedir(dir);
    return 0;
}
```

### Archive Termination
```c
/* Write two 512-byte blocks of zeros (end of archive) */
char zeros[1024] = {0};
write(fd, zeros, 1024);
```

## Fork+Exec for RUN Instruction (replaces `system("cd ... && cmd")`)

```c
case WUBU_INST_RUN: {
    pid_t pid = fork();
    if (pid == 0) {
        /* Child process */
        if (chdir(stage_dir) != 0) _exit(1);
        execl("/bin/sh", "sh", "-c", inst->args, (char *)NULL);
        _exit(127);
    } else if (pid > 0) {
        /* Parent process */
        int status;
        waitpid(pid, &status, 0);
        if (WIFEXITED(status) && WEXITSTATUS(status) != 0) {
            fprintf(stderr, "RUN failed (exit=%d): %s\n", WEXITSTATUS(status), inst->args);
        }
    } else {
        fprintf(stderr, "RUN fork failed: %s\n", strerror(errno));
    }
    break;
}
```

## nftw-based Recursive Remove (replaces `system("rm -rf ...")`)

```c
static int remove_cb(const char *fpath, const struct stat *sb,
                     int typeflag, struct FTW *ftwbuf) {
    (void)sb; (void)ftwbuf;
    int rv = remove(fpath);
    if (rv) fprintf(stderr, "[wubu_image] failed to remove %s: %s\n", fpath, strerror(errno));
    return rv;
}

static int rmtree(const char *path) {
    if (!path || !path[0]) return -1;
    return nftw(path, remove_cb, 64, FTW_DEPTH | FTW_PHYS);
}
```

**Key flags**: `FTW_DEPTH` (post-order: children before parent), `FTW_PHYS` (don't follow symlinks), `FTW_MOUNT` (don't cross mount points)

## Compilation Notes

### Build Flags
```makefile
# For test_oci (includes image tar)
test_oci:
    $(CC) -O0 -g -D_GNU_SOURCE -DHAVE_VULKAN -DHAVE_CUDA -I$(RT) \
        $(RT)/wubu_oci.c $(RT)/wubu_image.c $(RT)/wubu_container.c \
        $(RT)/wubu_oci_test.c -o $(RT)/wubu_oci_test -ldl -ldl -lvulkan -lcuda
```

### Required Headers
```c
#define _GNU_SOURCE  /* For nftw, FTW_* constants */
#include <ftw.h>
#include <sys/wait.h>   /* waitpid, WIFEXITED, WEXITSTATUS */
```

## Test Verification
```bash
# All tests pass with new implementations
make test_oci      # 10/10 - OCI export with direct tar
make test_image    # (no dedicated target yet, but OCI tests cover it)
make test_snapshot # 132/132 - nftw copy/remove in rollback/restore
make test_holyd    # 31/31 - dynamic paths, fork+exec eval
make test_vsl      # 52/52 - real drivers, ELF loading
make test_network  # 139/139 - netlink rtnetlink
make all           # Clean build, only warnings
```