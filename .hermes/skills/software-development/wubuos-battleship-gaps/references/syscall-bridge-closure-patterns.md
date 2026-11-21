# Syscall Bridge Closure Patterns (bridge/wubu_syscall.c)

This document captures the patterns for closing void-cast REAL_GAPs in the syscall bridge implementation within `src/bridge/wubu_syscall.c`.

## Overview

The syscall bridge connects HolyC/TempleOS-compatible syscalls to the Linux kernel. The original code had many void-cast parameters and `system()` calls that are REAL_GAPs.

## Patterns

### 1. File Handlers: fd-based I/O with Internal Mapping

**Before (REAL_GAP):**
```c
int64_t sys_file_open(int64_t path_ptr, int64_t mode, ...) {
    (void)mode; (void)_unused; ...
    FILE *f = fopen(path, (mode & 1) ? "r" : "w");
    return f ? (int64_t)f : -1;
}
```

**After (Real Implementation):**
```c
static int g_file_fd_map[256] = {0};
static int g_file_fd_count = 0;

int64_t sys_file_open(int64_t path_ptr, int64_t mode, ...) {
    const char *path = (const char *)path_ptr;
    if (!path) return -1;

    int flags = 0;
    switch (mode & 0x03) {
        case 0: flags = O_RDONLY; break;
        case 1: flags = O_WRONLY | O_CREAT | O_TRUNC; break;
        case 2: flags = O_RDWR | O_CREAT; break;
        default: flags = O_RDONLY;
    }
    if (mode & 0x08) flags |= O_APPEND;

    int fd = open(path, flags, 0644);
    if (fd < 0) return -1;

    if (g_file_fd_count >= 256) {
        close(fd);
        return -1;
    }
    g_file_fd_map[g_file_fd_count] = fd;
    return (int64_t)g_file_fd_count++;
}

int64_t sys_file_read(int64_t fd_idx, int64_t buf_ptr, int64_t len, ...) {
    if (fd_idx < 0 || fd_idx >= g_file_fd_count) return -1;
    int fd = g_file_fd_map[fd_idx];
    if (fd < 0) return -1;
    if (!buf_ptr || len <= 0) return -1;

    ssize_t r = read(fd, (void *)buf_ptr, (size_t)len);
    return r < 0 ? -1 : (int64_t)r;
}
```

### 2. Styx Handlers: Persistent Offset Tracking

**Before (REAL_GAP):**
```c
int64_t sys_styx_read(int64_t fid, int64_t offset, ...) {
    (void)offset; ...
    lseek(fd, offset, SEEK_SET);  // Every call seeks
}
```

**After (Real Implementation):**
```c
static struct {
    int fd;
    off_t offset;
} g_styx_fds[256] = {{0}};
static int g_styx_fd_count = 0;

int64_t sys_styx_open(int64_t path_ptr, int64_t mode, ...) {
    int fd = open(path, flags, 0644);
    g_styx_fds[g_styx_fd_count].fd = fd;
    g_styx_fds[g_styx_fd_count].offset = 0;
    return (int64_t)g_styx_fd_count++;
}

int64_t sys_styx_read(int64_t fid, int64_t offset, ...) {
    if (offset >= 0) {
        g_styx_fds[fid].offset = lseek(fd, offset, SEEK_SET);
        if (g_styx_fds[fid].offset < 0) return -1;
    }
    ssize_t n = read(fd, buf, count);
    g_styx_fds[fid].offset += n;  // Track position
    return n;
}
```

### 3. Container Handlers: fork+exec Instead of system()

**Before (REAL_GAP - 2 system() calls):**
```c
int64_t sys_container_create(...) {
    char cmd[2048];
    snprintf(cmd, sizeof(cmd), "wubu_ct_bwrap create --name %s", name);
    int rc = system(cmd);  // REAL_GAP
    ...
}

int64_t sys_container_exec(...) {
    char syscmd[1024];
    snprintf(syscmd, ..., "wubu_ct_bwrap exec --id %ld --cmd '%s'", id, cmd);
    int rc = system(syscmd);  // REAL_GAP
    ...
}
```

**After (Real Implementation):**
```c
static struct {
    int id;
    pid_t pid;
    char name[64];
    char args[256];
    char env[256];
} g_containers[32] = {{0}};
static int g_container_count = 0;

int64_t sys_container_create(int64_t name_ptr, int64_t args_ptr, ...) {
    const char *name = (const char *)name_ptr;
    const char *args = (const char *)args_ptr;
    ...
    
    char *bwrap_argv[64];
    int argc = 0;
    bwrap_argv[argc++] = "bwrap";
    bwrap_argv[argc++] = "--ro-bind"; bwrap_argv[argc++] = "/"; bwrap_argv[argc++] = "/";
    bwrap_argv[argc++] = "--proc"; bwrap_argv[argc++] = "/proc";
    bwrap_argv[argc++] = "--dev"; bwrap_argv[argc++] = "/dev";
    bwrap_argv[argc++] = "--tmpfs"; bwrap_argv[argc++] = "/tmp";
    bwrap_argv[argc++] = "--unshare-all";
    bwrap_argv[argc++] = "--die-with-parent";

    if (args && args[0]) {
        bwrap_argv[argc++] = "/bin/sh";
        bwrap_argv[argc++] = "-c";
        bwrap_argv[argc++] = args;
    } else {
        bwrap_argv[argc++] = "/bin/sh";
    }
    bwrap_argv[argc] = NULL;

    pid_t pid = fork();
    if (pid == 0) {
        execvp("bwrap", bwrap_argv);
        _exit(127);
    }

    g_containers[container_id].pid = pid;
    g_container_count++;
    return (int642container_id;
}

int64_t sys_container_destroy(int64_t id, ...) {
    if (id < 0 || id >= g_container_count) return -1;
    pid_t pid = g_containers[id].pid;
    if (pid > 0) {
        kill(pid, SIGTERM);
        int status; waitpid(pid, &status, 0);
    }
    g_containers[id].id = -1;
    g_containers[id].pid = 0;
    return 0;
}
```

### 4. Syscall Trampolines: Proper x86-64 Syscall Convention

**Before (REAL_GAP - ignores arguments):**
```c
static int64_t syscall_trampoline_0(void) {
    __asm__ volatile("syscall" : : "a"(0) : "rcx", "r11", "memory");
    return 0;
}
```

**After (Real Implementation):**
```c
#define SYSCALL_TRAMPOLINE(num) \
    static int64_t syscall_trampoline_##num(void) { \
        register int64_t rdi asm("rdi"); \
        register int64_t rsi asm("rsi"); \
        register int64_t rdx asm("rdx"); \
        register int64_t rcx asm("rcx"); \
        register int64_t r8 asm("r8"); \
        register int64_t r9 asm("r9"); \
        register int64_t rax asm("rax") = num; \
        register int64_t r10 asm("r10") = rcx; \
        __asm__ volatile("syscall" \
            : "+a"(rax), "+D"(rdi), "+S"(rsi), "+d"(rdx), "+r"(r10), "+r"(r8), "+r"(r9) \
            : \
            : "rcx", "r11", "memory"); \
        return rax; \
    }

SYSCALL_TRAMPOLINE(0)
SYSCALL_TRAMPOLINE(1)
...
SYSCALL_TRAMPOLINE(25)

static void *g_trampolines[SYS_MAX_DEFINED] = {
    (void *)syscall_trampoline_0, (void *)syscall_trampoline_1, ...
};

void *wubu_syscall_trampoline(uint32_t num) {
    if (num < SYS_MAX_DEFINED) return g_trampolines[num];
    return NULL;
}
```

**Key points:**
- Arguments passed in RDI, RSI, RDX, R10, R8, R9 (System V AMD64 ABI)
- Syscall number in RAX
- RCX → R10 (syscall clobbers RCX/R11)
- Clobbers: RCX, R11
- Use `register ... asm("reg")` for explicit register allocation
- Return value in RAX

## Key Principles

1. **Replace `system()` with `fork+exec`** - Every `system()` call is a REAL_GAP
2. **Track state internally** - Use internal fd/offset mapping instead of passing raw fds
3. **Track offsets persistently** - Don't `lseek` on every call; track in struct
4. **Proper syscall convention** - Match System V AMD64 ABI for syscall instruction
5. **Register allocation** - Use `register ... asm("reg")` for explicit register control
5. **Clobber list** - Must include "rcx", "r11", "memory"
6. **Container registry** - Track containers with PID for proper cleanup
6. **Error handling** - Check all syscall returns, return `-errno` on failure