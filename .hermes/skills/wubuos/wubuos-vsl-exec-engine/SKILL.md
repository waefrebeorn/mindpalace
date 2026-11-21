---
name: wubuos-vsl-exec-engine
category: wubuos
description: Use when executing loaded ELF in-process via seccomp SIGSYS.
---

# In-process ELF execution via seccomp SIGSYS (VSL L11)

Landed in `src/runtime/vsl/vsl_exec_engine.c` (+ `.h`, `vsl_exec_test.c`,
`exec_guests/*.c`), gate `make test_vsl_exec` in `test_critical_runtime`.
Runs static freestanding ET_EXEC x86-64 ELF in-process: MAP_FIXED segments
at link addresses, getcontext/setcontext entry on a built argc/argv/envp/auxv
stack, seccomp TRAP -> SIGSYS -> vsl_syscall_dispatch (the ONE Linux table),
exit/exit_group via the real vsl_sys_exit handler then siglongjmp.

## Hard-won kernel/libc facts (probe BEFORE building)
- **SIGSYS siginfo has NO `si_args`.** Kernel/glibc expose only si_syscall,
  si_call_addr, si_arch. Read the 6 args from the trapped ucontext gregs:
  REG_RDI/RSI/RDX/R10/R8/R9. A design doc saying "si_args" is wrong.
- **RIP may already be advanced.** On kernel 7.0 SIGSYS arrives with RIP
  pointing PAST the 2-byte syscall; older kernels point at it. Never blindly
  `RIP += 2`: advance only when the bytes at RIP are still `0F 05`.
  Blind +2 skips the next instruction -> guest executes garbage -> SIGSEGV.
- **Trap ALL syscalls is impossible in-process**: the VSL handlers call host
  libc, whose syscalls would re-trap recursively. Scope the BPF filter by
  `seccomp_data.instruction_pointer` (offset 8, u64; test hi32@12 == 0 then
  lo32@8 against the window): TRAP inside the guest window, ALLOW outside.
  seccomp_data layout: nr@0, arch@4, ip@8, args@16.
- **Filters are immutable once installed** -> the trap scope must be a FIXED
  window, not a per-run range. VSL uses [VSL_USER_BASE, +VSL_USER_SIZE)
  (0x2000000..0x80000000); guests must link inside it
  (`-Wl,-Ttext-segment=0x40000000`). Check /proc/self/maps for collisions
  before MAP_FIXED (a non-PIE host at 0x400000 would be destroyed).
- `_GNU_SOURCE` needed for REG_* gregs and ucontext (egojar.h provides it).
  Probe recipe: scratch C file, mmap RWX page in window, hand bytes
  `mov eax,39; syscall; mov rbx,rax; mov eax,60; mov edi,7; syscall`,
  handler spoofs RAX + longjmp on exit; run under gdb if it segfaults.

## Engine patterns
- Output capture: the real vsl_sys_write does host write(fd) -> dup2 a
  memfd onto fds 1/2 for the run, pread it back after. No second write path.
- exit: dispatch through the REAL handler first (records ZOMBIE+exit_code
  on VSL_PROC), then siglongjmp; read proc->exit_code. Never kill the host.
- Guest SIGSEGV/SIGBUS: SA_SIGINFO handler siglongjmps with ERR_FAULT;
  engine cleans up and stays runnable (gate: run again after a fault).
- Reuse single owners: vsl_elf_validate (format), vsl_create_process (proc
  record), vsl_syscall_dispatch (routing), wubu_kernel_select("linux") for
  the bare range (save/restore previous selection). The legacy vsl_elf_load
  RELOCATES (VSL_USER_BASE + vaddr&0xFFFFFF) for inspection — execution needs
  original link addresses, so the engine maps segments itself after the same
  validation; document why instead of "fixing" the inspection loader.
- Freestanding guests: `gcc -O1 -nostdlib -static -ffreestanding -fno-pie
  -no-pie -fno-stack-protector -Wl,-N -Wl,-Ttext-segment=0x40000000`. Inline
  asm syscall wrappers with "rcx","r11","memory" clobbers. -N gives one RWX
  PT_LOAD. Also gate a hand-assembled ELF byte image (no toolchain).
- Assert REAL semantics, not passthrough: getpid must return the VSL pid
  (g_vsl.current_pid), NOT host getpid — that check proves dispatch is real.

## ET_DYN bounded loader (post-dynsym)
Six relocation types are now applied from DT_RELA/DT_REL/DT_JMPREL:
RELATIVE, 64, GLOB_DAT, JUMP_SLOT, COPY (5) and IRELATIVE (37). Symbols come
from DT_HASH/DT_GNU_HASH with caps; undefined names resolve ONLY from the fixed
host table. COPY sources must be host symbols with a declared `copy_sz` byte
limit and an in-image SHN_UNDEF dynsym whose st_size fits it; every relocation
write is bounded to the page-aligned mapped PT_LOAD union. IRELATIVE does NOT
call guest bytes during relocation: the link-time resolver address (RELA addend
or original GOT word) must be in a fixed host IFUNC table, whose function is
called instead; unregistered resolvers fail closed. TLS (DTPMOD64/TPOFF64/
TLSDESC, STT_TLS) is intentionally UNSUPPORTED and verified rejected. Lazy
PLT binding and init/fini remain boundaries. Differential gate lives in
vsl_exec_test.c gate(n)/gate(o)/gate(p); `legacy_rejects_nonrelative()`
models the pre-change RELATIVE-only rule; gate(p)'s
`legacy_rejects_dtneeded()` models the pre-DT_NEEDED rule (verified by
actually linking+running the HEAD loader: rc=-11 ERR_RELOC on the fixture).

## Bounded DT_NEEDED leg (gate p)
`vsl_dyn_set_dep_search_dir(dir)` allow-lists ONE directory; a DT_NEEDED soname
must be a plain basename whose FILE NAME in that dir equals the soname (a .so
linked with `-Wl,-soname,libvsldep.so` but saved as `guest_dep.elf` is
"missing"). Deps are ET_DYN freestanding guests: read from the dir with
realpath(child-of-dir) confinement, mapped at their own in-window bias BEFORE
the main image chooses its bias, relocated with the same bounded resolver,
then their defined dynsyms are merged (first-wins) into a per-run table that
`ex_resolve_symbol` checks before the fixed host table. Missing/malformed/out-
of-tree deps and cap overruns are ERR_RELOC. Gate asserts dep output precedes
main output (load order), the imported magic, dep symbol address in-window,
and ERR_RELOC for a disabled dir or a mutated soname.
Pitfalls: `realpath(path, buf)` with a buffer smaller than PATH_MAX trips glibc
fortify `__realpath_chk` -> use `realpath(path, NULL)` + free. `ld` 2.42 refuses
to link a dynamic .so input into a `-N`/Omagic output ("attempted static link
of dynamic object"): build the DEP with -N but the MAIN importer WITHOUT -N.
Keep the post-run load-order/symbol view intact: release mappings in cleanup,
but only reset the arrays at the START of the next run (or the gate sees NULL).

## Pitfalls
- A fresh `git worktree add` has UNINITIALIZED submodules. `test_vsl_exec` and
  `test_vsl` still build, but `test_docs` fails on `src/apps/wubuoffice/...`
  files until `git submodule update --init --force` is run in the worktree
  (plain `--init --recursive` can leave submodules at newer branch HEADs;
  `--force` restores the recorded gitlink commits and a clean status).
- When a host data symbol's `sizeof(x)-1` is used as a COPY byte limit, COUNT
  the literal first. `"VSLCOPY-DATA-1234"` is 17 chars, not 16, so an
  "oversized = limit+1" negative probe silently passed until the literal was
  shortened to a true 16 bytes.
- Test binary must stay PIE (default) or its own 0x400000 text collides with
  low-linked guests; the maps check turns that into ERR_COLLISION, not death.
- sigsetjmp(jb,1) saves the signal mask; siglongjmp from the handler restores
  it — do not use plain setjmp/longjmp across signal handlers.
- Handler must check an `active` flag: a stray SIGSYS with no guest running
  restores the old disposition and re-raises instead of touching dead state.
- Pre-existing test_vsl_nt failures (NtRevertContainerImpersonation,
  NtSetCachedSigningLevel x2) are unrelated to this leaf — the NT binary
  does not link the engine.
- **libc return != syscall return.** The table wraps host libc, but the
  Linux syscall ABI sometimes returns something different: getcwd libc
  returns the buffer POINTER, the syscall returns strlen+1. Returning the
  pointer passed native-exec tests but made the WEMU bridge gwrite() a
  pointer-sized copy -> segfault. When wrapping a libc call, check the
  syscall's documented return (man 2 syscalls, not man 3 libc) and convert.
- **The WEMU user-mode bridge is a SECOND consumer of vsl_syscall_dispatch**
  (wubuos src/runtime/wubu_wemu_bridge.c). It runs guest bytes in the
  interpreter and bounces every pointer arg guest->host (gread/gwrite/gstr).
  A handler that "works" in native exec can still break the bridge if it
  returns a host pointer or expects a host address. EFAULT from a guest
  applet usually means a missing bridge marshalling case (utimensat,
  getgroups, getcwd were added this way), not a VSL handler bug. Audit the
  syscall NUMBER table against /usr/include/x86_64-linux-gnu/asm/unistd_64.h
  — a wrong number routes to the wrong handler silently (see
  devils-advocate-audit).
