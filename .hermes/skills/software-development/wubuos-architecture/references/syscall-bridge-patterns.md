# Syscall Bridge Patterns — WuBuOS

## Overview
Patterns for implementing syscall handlers in `src/bridge/wubu_syscall.c` that bridge HolyC/TempleOS syscall conventions to host Linux syscalls.

## File Handlers (fd-based I/O)
Replace `FILE*` stdio with raw fd operations and internal mapping:

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
    if (g_file_fd_count >= 256) { close(fd); return -1; }
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

## Styx Handlers (with Offset Tracking)
Track per-fd offset instead of lseek on every call:

```c
static struct { int fd; off_t offset; } g_styx_fds[256] = {{0}};
static int g_styx_fd_count = 0;

int64_t sys_styx_read(int64_t fid, int64_t offset, int64_t count, ...) {
    if (fid < 0 || fid >= g_styx_fd_count) return -1;
    int fd = g_styx_fds[fid].fd;
    if (fd < 0) return -1;
    
    if (offset >= 0) {
        g_styx_fds[fid].offset = lseek(fd, (off_t)offset, SEEK_SET);
        if (g_styx_fds[fid].offset < 0) return -1;
    }
    ssize_t n = read(fd, (void *)buf_ptr, (size_t)count);
    if (n < 0) return -1;
    g_styx_fds[fid].offset += n;
    return (int64_t)n;
}
```

## Container Handlers (fork+exec bwrap)
Replace `system("wubu_ct_bwrap...")` with direct fork+exec:

```c
static struct { int id; pid_t pid; char name[64]; } g_containers[32];

int64_t sys_container_create(int64_t name_ptr, int64_t args_ptr, ...) {
    const char *name = (const char *)name_ptr;
    if (!name || name[0] == '\0') return -1;
    if (g_container_count >= 32) return -1;

    int container_id = g_container_count++;
    g_containers[container_id] = {.id = container_id, .pid = 0};
    strncpy(g_containers[container_id].name, name, 63);
    // ... copy args/env ...

    char *bwrap_argv[64];
    int argc = 0;
    bwrap_argv[argc++] = "bwrap";
    bwrap_argv[argc++] = "--ro-bind"; bwrap_argv[argc++] = "/"; bwrap_argv[argc++] = "/";
    bwrap_argv[argc++] = "--proc";  bwrap_argv[argc++] = "/proc";
    bwrap_argv[argc++] = "--dev";   bwrap_argv[argc++] = "/dev";
    bwrap_argv[argc++] = "--tmpfs"; bwrap_argv[argc++] = "/tmp";
    bwrap_argv[argc++] = "--unshare-all"; bwrap_argv[argc++] = "--die-with-parent";

    if (args && args[0]) {
        bwrap_argv[argc++] = "/bin/sh"; bwrap_argv[argc++] = "-c"; bwrap_argv[argc++] = args;
    } else { bwrap_argv[argc++] = "/bin/sh"; }
    bwrap_argv[argc] = NULL;

    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) { execvp("bwrap", bwrap_argv); _exit(127); }

    g_containers[container_id].pid = pid;
    return (int64_t)container_id;
}

int64_t sys_container_destroy(int64_t id, ...) {
    if (id < 0 || id >= g_container_count) return -1;
    pid_t pid = g_containers[id].pid;
    if (pid > 0) { kill(pid, SIGTERM); waitpid(pid, &status, 0); }
    g_containers[id].id = -1; g_containers[id].pid = 0;
    return 0;
}
```

## Syscall Trampolines (x86-64)
Proper System V AMD64 ABI: RAX=num, RDI/RSI/RDX/R10/R8/R9=args

```c
/* Simple trampoline pattern */
static int64_t syscall_trampoline_0(void)  { __asm__ volatile("syscall" : : "a"(0) : "rcx", "r11", "memory"); return 0; }
static int64_t syscall_trampoline_1(void)  { __asm__ volatile("syscall" : : "a"(1) : "rcx", "r11", "memory"); return 0; }
/* ... 0-25 */

static void *g_trampolines[SYS_MAX_DEFINED] = {
    syscall_trampoline_0, syscall_trampoline_1, /* ... */
};

void *wubu_syscall_trampoline(uint32_t num) {
    return (num < SYS_MAX_DEFINED) ? g_trampolines[num] : NULL;
}

/* Advanced: Full register passing for HolyC extern calls */
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
            : : "rcx", "r11", "memory"); \
        return rax; \
    }
```

## HolyC Registration
```c
extern int hc_gen_add_extern(void *hc_compiler, const char *name, void *func_ptr);

int wubu_holyc_register_syscalls(void *hc_compiler) {
    if (!hc_compiler) return -1;
    int count = 0;
    for (int i = 0; i < SYS_MAX_DEFINED; i++) {
        const char *name = wubu_syscall_name(i);
        void *trampoline = wubu_syscall_trampoline(i);
        if (trampoline && hc_gen_add_extern(hc_compiler, name, trampoline) == 0) count++;
    }
    return count;
}
```