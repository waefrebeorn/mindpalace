---
name: wemu-emulator
description: Use when extending WEMU, the WuBu x86-64 emulator.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wemu, emulator, x86, slerm, wubuos]
---

# WEMU — the WuBu Emulator

## When to Use
- Adding instructions/devices to WEMU, or wiring it into WuBuOS as the
  bare-metal guest-execution layer.
- Debugging x86 decode/exec semantics in the emulator.

Repo: github.com/waefrebeorn/wemu (PUBLIC, main), local /home/wubu/wemu.
Clean-room C11 slerm of QEMU's ROLE (not its code): the sovereign
guest-execution layer for WuBuOS bare metal. Umbrella v3. Founded
2026-11-19 by the CI incident: Ubuntu 26.04 gcc14 defaults to
x86-64-v3, vectorized kernel memset with vmovd/vpbroadcastb (AVX2);
qemu64 TCG #UD -> triple fault. Kernel fixed with -march=x86-64;
WEMU makes the needed instruction sets ours.

## Architecture (one concern per leaf)
- include/wemu.h — opaque public API (WemuCpu/WemuMachine)
- src/wemu_internal.h — shared state + WemuInsn; full opcode =
  in.op | ((in.vex[0]>>4)<<8) (op is uint8_t; map lives in vex[0] high
  nibble for BOTH legacy 0F and VEX)
- wemu_decode.c — prefixes/REX/VEX/ModRM/SIB/disp/imm. VEX 3-byte:
  R/X/B ALL from p1 bits 7:5 (inverted): rex = 0x40|((~p1>>5)&7)|(W?8:0);
  vvvv from p2 bits 6:3 (2-byte: p1). imm_len_for must know every
  imm-carrying opcode (B8+r = opsize not rex-only; C0/C1, E4-E7, A0-A3
  moffs=addrsize, 0F 70-73 pshufd/psrl imm8).
- wemu_exec.c — integer core + flags; odd cc (jcc/setcc/cmov) INVERTS
  the base condition; the primary arith block AND the B0-BF/70-7F
  default branches must guard full<0x100 (else 0F 01 xgetbv / 0F 31
  rdtsc / 0F 0B ud2 get eaten as ADD/XOR); CLC/STC/CMC/CLI/STI exist;
  shld/shrd (0F A4/A5/AC/AD, imm8+CL, all widths) live here; count>=width
  is SDM-undefined (follow QEMU semantics, gate only the defined range);
  unimplemented = honest #UD.
- wemu_sse.c — SSE2/AVX seed; VEX.128 zeroes ymm_hi; legacy leaves it;
  vzeroupper/emms (0x177) carry NO ModRM. CPUID outputs map EAX->r0
  EBX->r3 ECX->r1 EDX->r2 (swapping EBX/ECX is a silent wrong-answer
  bug); claim ONLY implemented features + xgetbv XCR0=7, else guests
  never emit the vector code you implemented. Logical ops (pxor/pand/
  pandn/por) MUST be byte-wise: the element-accumulator loop shifts
  8*k into uint64_t — es=16 shifts >=64 are UB (x86 masks to 63) and
  fold upper-lane bytes into lower (glibc strcmp_avx2 vpandn zero-mask
  clear broke exactly this way). 66 0F 73 shift group per SDM: /2
  psrlw, /3 psrldq, /4 psraw, /6 psllw, /7 pslldq (BYTE shift!) — VEX
  vpslldq is /7 too; /7 is NOT psllq (that is 66 0F F3). Also owns the
  scalar SSE2 family (F2=sd/F3=ss; VEX pp=2/3): add/mul/sub/div/min/max,
  cvtsi2sd/ss, cvt(t)sd2si, cvtss2sd/cvtsd2ss, and comisd/ucomisd +
  comiss/ucomiss (scalar compare -> ZF/PF/CF, OF/SF/AF cleared). See
  references/x87-sse-encoding.md for operand-order + class tables.
- wemu_string.c — movs/stos/scas/cmps/lods + rep/repe/repne + cld/std;
  real memset/memcpy compile to rep stos/movs — without these you run
  picked ops, not programs. repe scasb: RCX counts the mismatching
  compare too; RDI ends PAST the mismatch.
- wemu_mem.c — RAM + 4-level walk (PG = cr0 bit31 ONLY, not bit0);
  2MiB leaves mask PA to alignment (SDM); wemu_eff_addr is the ONE
  addressing owner (SIB mod0 base5: disp is the base, added ONCE).
- wemu_cpu.c — state/flags/syscall hook/step-run; cr0 init 0x11 (PG off).
- wemu_elf.c — user-mode: static ET_EXEC loader, PT_LOAD map, SysV
  stack (argc/argv/envp/auxv), wemu_cpu_load_elf(cpu,path,NULL,0,argv).
  arch_prctl(SET_FS/SET_GS) must be handled by the syscall hook
  (wemu_cpu_set_fs_base) — glibc static startup needs TLS before main.
- wemu_x87.c — x87 FPU, PRIMARY-map escapes D8-DF (NO 0F prefix — hook
  them in the primary dispatch, not the two-byte chain). Decoder MUST
  list D8-DF in need_modrm and consume 9B (fwait) as a no-op prefix.
  Internal precision IEEE double (m80 via host long double). fxam uses
  the SDM class table (normal=010, NOT 110) — glibc __printf_fp
  classifies with fxam; a wrong class prints every value as 0.
- wemu_machine.c — COM1 (0x3F8 data, 0x3FD LSR=0x60); port I/O owner.

## Gates (`make test` — every TESTS entry must stay green)
Run the Makefile's full `TESTS` list, not a remembered subset. In addition
to the baseline gates below, the current suite includes differential gates
for LOCK atomics, exception delivery, CMPXCHG8B/16B + fences, IDT gates and
#PF error bits, privilege/IF/IST, and #GP/#SS/#NP/#DF delivery. Each new ISA
feature must add its own gate and keep the whole list green.

Baseline gates:
test_isa (sequences + 800 differential: 8 ops x 4 widths x carry-in,
CF/OF/ZF/SF vs independent C model), test_avx (founding vmovd/
vpbroadcastb 128/256 + gcc14 memset vector body vs native memset),
test_paging (4KiB/2MiB/#PF+CR2/identity), test_machine (port-I/O +
syscall serial), test_string (rep stos/movs/scas vs native, DF both
ways), test_cpuid (claims == executes, xgetbv, vzeroupper), test_sse2
(100 random rounds x 128/256 vs byte-wise C oracle + named strcmp-pandn
and shiftgrp regressions + movq/cvt operand-order + comisd cases),
test_usermode (static ELF + SysV stack + real busybox parses to first
syscall), test_shld (6000 rounds vs HOST CPU inline-asm oracle, result
+ CF, defined range only), test_x87 (bit-exact round-trips, IEEE arith,
fxam/fcom cc tables, all four rounding modes, native fninit/fnstcw).
WuBuOS-side acceptance: make test_wemu_busybox — ~26 real static busybox
applets (echo/uname/cat/ls/true/false/head/tail/grep/sort/sed/seq/expr/
wc/cut/awk/md5sum/sha256sum/base64/touch/cp/mv/rm/pwd/id/sleep/test/
date/hostname) exact output + exit codes through the VSL bridge; the
checksum/base64 applets compare against HOST coreutils (independent
oracle). Every new applet failure is a discovered ISA/syscall gap.

## Devil's-advocate rule
A differential gate that only covers what you remembered to implement
is survivorship bias — expand widths/ops/flags until it catches real
bugs (it caught CLC/STC immediately). Industry smoke standard for
user-mode emulation: static busybox applets + LTP (QEMU project's own
testing guidance) — that is the acceptance bar for the user-mode leg.

ORACLE INDEPENDENCE (two bugs paid for this): an oracle that shares
an abstraction with the implementation can be wrong TOGETHER with it
— the es=16 fold bug passed 100 random rounds because the C oracle
used the same element-accumulator shape; the pslldq bug passed because
the test encoded /6 (written from the implementation, not the SDM).
Write oracles from the SDM/spec, byte-wise where the spec is byte-wise,
and add a NAMED regression for every real-program failure.

WHICH VARIANT RUNS: glibc IFUNC resolvers pick by CPUID — honest CPUID
(no SSSE3/SSE4.2 claimed) makes glibc use __strcmp_sse2, not the avx2
variant you disassembled. Find the ACTUAL resolved target with the
bridge's WEMU_BRIDGE_TRACE=2 (dumps a 400k-rip ring to /tmp/wemu_rips.txt
at exit; =1 traces faults with bytes). Debug chain that worked:
differential probe (native vs emulated strcmp signs over a packed
string blob) -> rip ring -> variant disassembly -> whitebox insn probe.

## Pitfalls (paid for in blood)
- **Native-usermode `rt_sigaction(act == NULL)` is a QUERY, not a SIG_DFL
  registration**: building a zeroed `ksa` from a NULL act silently unregisters
  the handler and breaks a byte-exact oldact differential. Dispositions must
  be PER-THREAD: a CLONE_THREAD child inherits a COPY of its parent's table
  and a synchronous fault is delivered from the FAULTING thread's slot. With
  one process-wide table, one thread's `rt_sigaction` clobbers another's and a
  fault runs the wrong handler; keep the shared table only as a negative
  control. `sigaction` shapes outside the bounded set (unmodeled signal,
  sigsetsize != 8, handler outside the image) must fail closed with an exact
  refuse reason, never dispatch a host handler.
- Hex/decimal in tests: 0x42 != 42; print %llx and compare accordingly.
- Page-table test writes must disable paging first (they target raw GPA);
  large-page PA must be alignment-valid; GPA read-back needs paging off.
- Test call/ret layouts: count bytes from 0x1000; ret consumes the
  return address — callee must not pop it.
- -Werror sign-compare: mixed ?: branches need explicit uint64_t casts.
- Whitebox probes: HLT latches — clear c->halted (or fresh cpu) between
  runs; RAM must cover the load address (0x400000 needs >4MB); get blob
  addresses from nm, never assume .org math; ModRM digit errors make
  you probe a DIFFERENT instruction than you think (FA=/7, F2=/6).
- glibc static guests need arch_prctl TLS + real mmap/brk in the hook
  or startup exits before main (one write + exit_group = that failure).
- **execveat's dirfd is an `int`; normalise it from the low 32 bits** in a
  SIGSYS handler. A guest calling `syscall(322, AT_FDCWD, ...)` through
  glibc's vararg wrapper leaves RDI = `0x00000000ffffff9c` (zero-extended),
  so `(long)rdi == -100` is FALSE and AT_FDCWD is misclassified as a huge
  positive fd (fail-closed turned into a bogus -EBADF). Use
  `(long)(int32_t)rdi`; keep `flags` unmasked so unsupported high bits still
  fail closed. fd-relative execveat must validate the fd against a bounded
  admitted table filled only from successful guest openat/dup3 — a guest
  must not execute a file described by a supervisor fd it never opened.
- **FP printf prints all zeros? Check the silent-zero triad** (no #UD,
  just wrong values): (1) fxam class table wrong -> __printf_fp takes
  the zero branch; (2) movq xmm->r64 (66 REX.W 0F 7E) moving only 32
  bits -> integer-valued doubles lose their upper half (low half==0);
  (3) cvttsd2si reading the wrong xmm (see operand order below). Loop
  counts stay right while every value is 0 = this class, not a fault.
- **cvt operand order is the REVERSE of arithmetic**: cvttsd2si/cvtsd2si
  (0F 2C/2D) ModRM.reg = GPR dest (REX.R extends it), ModRM.rm = XMM
  SOURCE (REX.B). cvtsi2sd (0F 2A) is opposite (reg=xmm dest, rm=GPR
  src). cvtss2sd/cvtsd2ss (0F 5A): reg=dest xmm, rm=src xmm — distinct
  registers, a same-reg round-trip test HIDES the bug. Reading xmm[dst]
  for 2C/2D reads the wrong (zero) register -> every awk $N became $0.
- **VEX test-encoding traps**: C5 already implies the 0F map — do NOT
  emit another 0F after it. Scalar width is the pp field: C5 F8 = pp=0
  (SINGLE), C5 F9 = pp=1 (double) — vcomisd needs F9. modrm 05 (mod=00,
  rm=101) is RIP-relative in 64-bit; absolute [addr] needs SIB (modrm
  04, SIB 25, disp32). A wrong encoding probes a different instruction.
- **Relink scratch probe runners after rebuilding libwemu.a** — a stale
  runner linked against the old library reports "still broken" after a
  real fix and sends you chasing a ghost. Rebuild the runner, not just
  the library, before re-testing.
- Whitebox probe sequence: when a result vanishes but decode fields are
  perfect, dump the decoded WemuInsn (op/rep/rex/opsize/modrm/len) then
  instrument the handler — operand-order bugs hide behind correct decode.

## Roadmap
User-mode leg, VSL bridge, x87, scalar SSE2, shld/shrd, LOCK atomics,
exception delivery with IDT/error-code/privilege/fault handling, and
CMPXCHG8B/16B + fences have LANDED. JIT via WuBuNOS x86-64 encoder remains
open (interpreter stays the oracle; needs SMC invalidation) -> VT-x/EPT VMM
leg -> virtio devices -> guest manager boots Linux on metal. Untrusted
guests belong in the interpreter (true sandbox), not native-exec engines. Bridge: wubuos
src/runtime/wubu_wemu_bridge.c, submodule src/wemu, mk/wemu_user.mk
(out-of-tree build, pristine sub). The bridge FAILS CLOSED: the default case passes only a scalar-arg whitelist plus set_tid_address/set_robust_list (store-not-dereference the guest pointer); every other unlisted syscall is -ENOSYS, because passing guest pointers to host handlers unmarshalled is silent host-memory corruption. Syscall numbers live in TWO places (VSL header AND bridge case labels) — audit both against asm/unistd_64.h; libc-wrapper handlers must translate return semantics (getcwd returns length not pointer; mmap failure is -ENOMEM not 0). It owns the guest<->host ABI
boundary: every pointer-arg syscall needs a bounce buffer (gread/gwrite/
gstr helpers); adding an applet that fails with EFAULT usually means a
missing marshalling case (utimensat/getgroups were added this way), not
an ISA gap. See references/x87-sse-encoding.md for lookup tables. Native user-mode fd, thread, signal and pidfd authority (and the combined-rebase rules for two legs started from the same WEMU base) live in `references/native-usermode-authority.md`.
