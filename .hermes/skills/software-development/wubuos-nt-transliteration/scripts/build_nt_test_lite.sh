#!/usr/bin/env bash
# build_nt_test_lite.sh — WSL2-safe lite build of the WuBuOS E1 NT transliteration
# regression test (src/runtime/vsl/vsl_syscall_nt_test.c).
#
# WHY: the Makefile target `make test_vsl_nt` links -lvulkan -lcuda and HANGS/OOMs
# under WSL2. This script compiles the SAME VSL translation units WITHOUT the GPU
# link, supplies a 1-line stub for vsl_vulkan_driver_init() (the only symbol the
# runtime pulls from vsl_gpu_vulkan.c), and links with -ldl -lpthread. The result
# exercises the exact same handler code paths as the real test.
#
# After the monolith decomposition (commit fac7a49), vsl_syscall_nt.c is a FACADE
# and the 58 NT handlers live in six modules. ALL seven (.c files: the facade +
# vsl_nt_atoms/io/job/proc/sync/registry.c) MUST be listed below or the link fails
# with undefined references. Keep this list in sync with RT_OBJS in the Makefile.
#
# OUTPUT: /tmp/wubu_vsl_nt_test_lite
# USAGE:
#   ./build_nt_test_lite.sh           # build only
#   ./build_nt_test_lite.sh run       # build + run to /tmp/nt_out.txt (safe)
#
# SAFETY: the NT test forks children (NtCreateProcess / job objects). ALWAYS run it
# with output redirected to a FILE and read the file afterward — piping its live
# stdout to `tail` hangs forever because the forked children inherit the stdout pipe.
# (This script does exactly that when given `run`.)
#
# Run from the REPO ROOT (the dir containing src/runtime/vsl/...).

set -e
ROOT="$(pwd)"
if [ ! -f "$ROOT/src/runtime/vsl/vsl_syscall_nt_test.c" ]; then
  echo "run from repo root (dir containing src/runtime/vsl/)" >&2
  exit 1
fi

# vsl_vulkan_driver_init() is declared `int vsl_vulkan_driver_init(void)` in
# vsl_gpu_vulkan.h — the stub must match (return int, not void).
STUB="$(mktemp /tmp/vulkan_stub.XXXX.c)"
cat > "$STUB" <<'EOF'
/* Lite-build only: NT test exercises no Vulkan. */
int vsl_vulkan_driver_init(void) { return 0; }
EOF

# Facade + the six decomposed handler modules + the supporting VSL TUs + the test TU.
SRCS="$ROOT/src/runtime/vsl/vsl.c \
$ROOT/src/runtime/vsl/vsl_syscall.c \
$ROOT/src/runtime/vsl/vsl_syscall_nt.c \
$ROOT/src/runtime/vsl/vsl_nt_atoms.c \
$ROOT/src/runtime/vsl/vsl_nt_job.c \
$ROOT/src/runtime/vsl/vsl_nt_io.c \
$ROOT/src/runtime/vsl/vsl_nt_process.c \
$ROOT/src/runtime/vsl/vsl_nt_sync.c \
$ROOT/src/runtime/vsl/vsl_nt_vmem.c \
$ROOT/src/runtime/vsl/vsl_nt_thread.c \
$ROOT/src/runtime/vsl/vsl_nt_section.c \
$ROOT/src/runtime/vsl/vsl_nt_timer.c \
$ROOT/src/runtime/vsl/vsl_nt_registry.c \
$ROOT/src/runtime/vsl/vsl_nt_token.c \
$ROOT/src/runtime/vsl/vsl_nt_misc.c \
$ROOT/src/runtime/vsl/vsl_nt_misc_w11.c \
$ROOT/src/runtime/vsl/vsl_nt_alpc.c \
$ROOT/src/runtime/vsl/vsl_nt_enclave.c \
$ROOT/src/runtime/vsl/vsl_nt_ioring.c \
$ROOT/src/runtime/vsl/vsl_nt_ktm.c \
$ROOT/src/runtime/vsl/vsl_nt_partition.c \
$ROOT/src/runtime/vsl/vsl_nt_wnf.c \
$ROOT/src/runtime/vsl/vsl_nt_worker.c \
$ROOT/src/runtime/vsl/vsl_syscall_proc.c \
$ROOT/src/runtime/vsl/vsl_syscall_fileio.c \
$ROOT/src/runtime/vsl/vsl_syscall_memory.c \
$ROOT/src/runtime/vsl/vsl_syscall_net.c \
$ROOT/src/runtime/vsl/vsl_syscall_cpm.c \
$ROOT/src/runtime/vsl/vsl_syscall_macclassic.c \
$ROOT/src/runtime/vsl/vsl_syscall_mac.c \
$ROOT/src/runtime/vsl/vsl_syscall_mac_bsd.c \
$ROOT/src/runtime/vsl/vsl_syscall_mac_mach.c \
$ROOT/src/runtime/vsl/vsl_process.c \
$ROOT/src/runtime/vsl/vsl_macho.c \
$ROOT/src/runtime/vsl/vsl_memory.c \
$ROOT/src/runtime/vsl/vsl_file.c \
$ROOT/src/runtime/vsl/vsl_driver.c \
$ROOT/src/runtime/vsl/vsl_shared.c \
$ROOT/src/runtime/vsl/vsl_elf.c \
$ROOT/src/runtime/wubu_fs_util.c \
$ROOT/src/kernel/wubu_modsym.c \
$ROOT/src/runtime/vsl/vsl_syscall_nt_test.c"

gcc -O0 -g -D_GNU_SOURCE -I "$ROOT/src/runtime" -I "$ROOT/src/runtime/vsl" -I "$ROOT/src/kernel" -pthread \
  $SRCS "$STUB" -o /tmp/wubu_vsl_nt_test_lite -ldl -lpthread
rm -f "$STUB"
echo "built /tmp/wubu_vsl_nt_test_lite"

if [ "${1:-}" = "run" ]; then
  timeout 30 /tmp/wubu_vsl_nt_test_lite > /tmp/nt_out.txt 2>&1
  ec=$?
  echo "exit=$ec  (full output in /tmp/nt_out.txt)"
  tail -4 /tmp/nt_out.txt
else
  echo "run:  timeout 30 /tmp/wubu_vsl_nt_test_lite > /tmp/nt_out.txt 2>&1; tail -4 /tmp/nt_out.txt"
fi
