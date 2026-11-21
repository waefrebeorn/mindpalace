#!/usr/bin/env python3
"""
find_real_gaps.py -- deterministic probe to surface genuine form!=function gaps
in the WuBuOS C tree, filtering the noise that inflates BATTLESHIP.md counts.

NOISE EXCLUDED (NOT gaps):
  - *_test_stub.c / *_test.c files  (intentionally-empty linker shims)
  - 6-arg syscall shims that only (void)-cast unused slots (correct by design)
  - known no-op lifecycle fns (bridge_shutdown, task_preempt_disable/enable, ...)

REPORTS:
  PASS 1: empty `name() {}` bodies in PRODUCT code (stubs excluded).
  PASS 2: functions whose only returns are constants AND which make NO host
          syscall/helper call (candidate real gaps -- needs a manual read).

USAGE:
  python3 find_real_gaps.py [SRC_ROOT] [--dirs runtime/vsl runtime gui kernel bridge styx]
  # default SRC_ROOT = cwd; default = whole tree minus test/stub files
"""
import os, re, sys, argparse

TEST_FILE_RE = re.compile(r"_test(_stub)?\.c$")
# Vendored third-party deps that are NOT WuBuOS product code. Scanning them
# produces thousands of false-positive const-only returns (libsndfile, portaudio,
# flac, reactos-study, wubucontainer submodules). Exclude by path prefix.
VENDOR_DIRS = (
    "reference/", "vendor/", "vendored/", "third_party/", "thirdparty/",
    "extern/", "deps/", "node_modules/", "reactos-study/",
    "wubucontainer/", "venv_viz/", "dist/", "wiki/", "os-studies/",
)
NOISE_FUNCS = {
    "bridge_shutdown", "task_preempt_disable", "task_preempt_enable",
    # extend with other known no-op lifecycle fns as found
}
SYSCALL_CALL_RE = re.compile(
    r"""(?:syscall|ioctl|socket|setsockopt|getsockopt|open|openat|close|read|write|
         fcntl|bind|connect|listen|accept|send|recv|sendto|recvfrom|sendmsg|recvmsg|
         pipe|pipe2|dup|dup2|dup3|mkdir|rmdir|unlink|unlinkat|rename|renameat|
         symlink|readlink|chmod|fchmod|chown|lchown|fchown|chdir|fchdir|getcwd|
         truncate|ftruncate|creat|stat|lstat|fstat|fstatat|getdents64|poll|epoll_create1|
         epoll_ctl|epoll_wait|clock_gettime|gettimeofday|getuid|geteuid|getgid|getegid|
         getresuid|getresgid|setresuid|setresgid|setreuid|setregid|setuid|setgid|
         getgroups|setgroups|umask|uname|sysinfo|getrandom|getrlimit|setrlimit|
         fork|execve|clone|wait4|kill|prlimit64|access|faccessat|mknod|mknodat|
         mount|umount|umount2|setns|unshare|sched_yield|eventfd|timerfd_create|
         inotify_init|inotify_add_watch|inotify_rm_watch|select|pselect6)\s*\("""
)

CTRL_KW = {"if", "for", "while", "switch", "do"}

def strip_comments(src):
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)

def scan_file(path, only_dirs):
    rel = os.path.relpath(path)
    if any(rel.startswith(d) for d in VENDOR_DIRS):
        return [], []
    if only_dirs and not any(rel.startswith(d) for d in only_dirs):
        return [], []
    if TEST_FILE_RE.search(path):
        return [], []
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return [], []
    noc = strip_comments(src)
    empty, const_only = [], []

    # PASS 1: empty bodies
    for m in re.finditer(r"\n([A-Za-z_]\w*)\s*\([^)]*\)\s*\{([ \t]*)\}", noc):
        name = m.group(1)
        if name in NOISE_FUNCS or name in CTRL_KW:
            continue
        empty.append((rel, name))

    # PASS 2: const-only return, no syscall call in body
    for m in re.finditer(r"\n([A-Za-z_]\w*)\s*\([^)]*\)\s*\{(.*?)\n\}", noc, flags=re.S):
        name, body = m.group(1), m.group(2)
        if name in NOISE_FUNCS or name in CTRL_KW:
            continue
        if SYSCALL_CALL_RE.search(body):
            continue
        returns = re.findall(r"return\s+([^;]+);", body)
        if not returns:
            continue
        nonconst = [r for r in returns
                    if not re.fullmatch(r"\s*-?\d+\s*", r)
                    and "errno" not in r and "NULL" not in r
                    and "ENOSYS" not in r and "EPERM" not in r]
        if not nonconst and 0 < len(body.strip()) < 800:
            const_only.append((rel, name, [r.strip() for r in returns]))
    return empty, const_only

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--dirs", nargs="*", default=[])
    args = ap.parse_args()

    empty_all, const_all = [], []
    for dp, _, fns in os.walk(args.root):
        for fn in fns:
            if not fn.endswith(".c"):
                continue
            e, c = scan_file(os.path.join(dp, fn), args.dirs)
            empty_all += e
            const_all += c

    print("=== EMPTY {} bodies (product code, test/stub files excluded) ===")
    for rel, name in sorted(set(empty_all)):
        print(f"  {rel}: {name}()")
    print(f"\n  TOTAL: {len(set(empty_all))}")

    print("\n=== CONST-ONLY return, NO host syscall (candidate real gaps -- manual review) ===")
    seen = set()
    for rel, name, rets in const_all:
        k = (rel, name)
        if k in seen:
            continue
        seen.add(k)
        print(f"  {rel}: {name}() -> {rets}")
    print(f"\n  TOTAL: {len(seen)}")

if __name__ == "__main__":
    main()
