# Freestanding bare-metal kernel link recovery (`make kernel`)

WuBuOS's `kernel` target links `src/kernel/*.o` with
`-ffreestanding -nostdlib -nostartfiles -fno-pie -mno-red-zone -mcmodel=kernel`.
That combination rejects several things normal hosted builds accept. This is a
DIFFERENT failure class from the hosted/RT link errors (multiple-def, missing
`.o`, OOM). Symptoms and fixes verified 2026-07-14.

## Symptom 1 — `R_X86_64_32` relocation truncated to fit (crt0.S / boot stub)

`ld` errors like:
```
crt0.S:91: relocation truncated to fit: R_X86_64_32 against symbol `_kernel_end'
crt0.S:94: relocation truncated to fit: R_X86_64_32 against `.bss'
```
Root cause: the kernel is linked at a higher-half VA (`0xffffffff80000000 + ...`).
Any `movl $_higher_half_sym, %reg` or `movl sym_in_.bss, %reg` in the 32-bit
`.code32` boot stub emits a 32-bit absolute relocation against an address >4GB,
which `-mcmodel=kernel` forbids.

Fix recipe (what worked):
1. **Split VMA from LMA in `kernel.ld`.** Keep `. = 0xffffffff80000000 + 0x100000`
   for VMA, but give each output section an `AT(physical)` (e.g. `AT(KERNEL_PHYS)`
   with `KERNEL_PHYS = 0x100000`) via `PHDRS { text PT_LOAD FLAGS(5); ... }`.
2. **Define absolute LOW-PHYSICAL symbols** in the linker script for everything
   the 32-bit stub must touch:
   ```
   _kernel_phys_base    = ABSOLUTE(_kernel_start) - _physical_offset;
   _kernel_phys_end     = ABSOLUTE(_kernel_end)   - _physical_offset;
   page_table_base  = 0x90000;   /* absolute low addr, <4GB */
   pdp_base = 0x90008;  pd_base = 0x90010;  pt_base = 0x90018;
   limine_boot_info = 0x90020;  long_mode_jmp = 0x90030;
   ```
   Do NOT reference input-object or `.rodata`/`.text` symbols inside `= expr`
   assignments — `ld` often reports them "undefined symbol ... in expression".
3. **Make crt0.S position-independent for the long-mode jump.** Get the physical
   EIP with `call .get_eip; .get_eip: pop %ebx`, then compute the GDT pointer and
   `.long_mode_start` physical addresses from *assembly-time offsets*
   (`leal (gdt64_ptr - .get_eip)(%ebx), %eax`), never from a higher-half symbol.
4. **Page-table setup** (PML4/PDP/PD/PT) must use 32-bit physical addresses
   (`_kernel_phys_end` etc.) and `rep stosl` (4 bytes x 4096 = 16KB for 4 pages).
   The higher-half `PD[511]` entry maps `_kernel_phys_base` (physical).

## Symptom 1b — CONCRETE INSTANCE: `.section .data` boot-scratch symbol (2026-07-16)

Exact failure after a crash left a half-applied bare-metal boot fix:
```
src/kernel/crt0.o: in function `_start':
crt0.S:115:(.text+0xbe): relocation truncated to fit: R_X86_64_32 against `.data'
crt0.S:620:(.text+0x44f): relocation truncated to fit: R_X86_64_32 against `.data'
```

Root cause: a 4-byte boot-protocol scratch (`boot_magic`, holding the entry EAX
value — 0x2BADB002 for multiboot, a Limine pointer otherwise, used to decide
whether to dereference Limine `.response` fields) was declared INSIDE crt0.S:
```asm
        .section .data
    boot_magic:
        .long 0
        .previous
```
and the 32-bit stub did `movl $boot_magic, %edx`. Under `-mcmodel=kernel` the
`.data` section is linked at a higher-half VA (>4GB), so `$boot_magic` is a 32-bit
absolute relocation against an address that doesn't fit → rejected. THE BUG IS
THE `.data` PLACEMENT, not the `movl` syntax. (A bare-metal boot fix is exactly
the kind of diff a crash leaves half-applied in the working tree — see the
crash-reconciliation note in SKILL.md.)

CORRECT FIX (use this, not `.section .data`): declare the scratch as an
**ABSOLUTE LOW-PHYSICAL** symbol in `kernel.ld`, exactly like the existing
page-table scratch block:
```ld
    boot_magic       = 0x90040;   /* absolute low-phys, <4GB, identity-mapped */
```
Then reference it from crt0.S with `movl $boot_magic, %edx` — `$boot_magic`
assembles to the literal `0x90040` (a valid 32-bit immediate), so there is NO
relocation and NO `R_X86_64_32`. This is the same mechanism that already works
for `page_table_base = 0x90000`, `pdp_base = 0x90008`, etc. The 64-bit phase
reads it via the identity map (0x90040 is <4GB and covered by the early PD).

GENERAL RULE: any variable the 16/32-bit boot stub must touch must be
  (a) a `page_table_base = 0x900xx`-style ABSOLUTE low-physical linker symbol, OR
  (b) reached via position-independent `call .get_eip; pop %ebx; leal (sym - .get_eip)(%ebx), %reg`.
Never a `.section .data` / `.bss` / higher-half symbol referenced with a 32-bit
absolute. If you ever see `R_X86_64_32 against '.data'`, grep crt0.S / boot.S for
a `.section .data` scratch and convert it to an ABSOLUTE linker symbol.

## Symptom 2 — `undefined reference to _setjmp / __longjmp_chk / setjmp`

`tasking.c` has `#if WUBU_BAREMETAL ... task_switch_asm(...) #else ... setjmp/longjmp`.
The kernel build was defining `MYSEED_METAL` (not `WUBU_BAREMETAL`), so it took the
hosted setjmp path — which doesn't exist under `-nostdlib`.

Fix: build kernel objects with `-DWUBU_BAREMETAL=1` (real asm switch in
`tasking_switch.S`). Introduce a `KERNEL_CFLAGS = -DMYSEED_METAL -DWUBU_BAREMETAL=1
-DWUBU_NO_LIBM` var and use it in the `$(KERNEL)/%.o`, `$(KERNEL)/%.S`, and
`$(KERNEL)/libc.o` recipes. (Do NOT also define setjmp/longjmp in libc.c — that
clashes with libc.h's `jmp_buf` typedef.)

## Symptom 3 — missing freestanding libc symbols

`undefined reference to __fprintf_chk, __memcpy_chk, __memset_chk, __printf_chk,
__snprintf_chk, __sysv_signal, stderr, abs, gmtime, time, __ctype_toupper_loc`.

Fix: complete the freestanding libc in `src/kernel/libc.c`:
- `abs`, `labs` (trivial).
- `time()` returns fixed epoch (no RTC wired); `gmtime()` returns static
  `struct tm` (g_tm.tm_year=70). NOTE: `struct tm`/`time_t` are already typedef'd
  at the TOP of libc.c — do NOT redeclare them (redefinition error).
- `sigaction`/`signal`/`__sysv_signal` -> bare-metal no-ops returning 0 / NULL.
- `__ctype_toupper_loc` -> returns `&identity` (a `const unsigned short*`).
- `__memcpy_chk`/`__memset_chk` -> wrappers to `memcpy`/`memset` (ignore `dstlen`).
- `fprintf`/`printf`/`snprintf` + `__fprintf_chk`/`__printf_chk`/`__snprintf_chk`
  -> route through a serial `klog` (see below). Define `FILE *stderr` as a sentinel
  (e.g. `static kfile_t g_kstderr; FILE *stderr = (FILE*)&g_kstderr;`).
- Add `klog.c`/`klog.h` (serial COM1 UART sink) to `KERNEL_OBJS`; route
  `memory.c` diagnostics via `#ifdef MYSEED_METAL ... klog_printf ... #else
  fprintf(stderr,...)`, and call `klog_init()` early in `kernel_main`.

## Verification

```
make kernel          # -> "Bare-metal kernel.elf built", exit 0
make shell           # -> "Shell built"
make test_shell      # -> "shell test: 9 passed, 0 failed"
make all             # exit 0, all targets built
```
Caveat: `kernel.elf` *links*; runtime boot (paging/long-mode handoff) needs QEMU
to validate — not available in this WSL env. Link success is the verified bar.

## Split-module shell pattern (BATTLESHIP 228-231)

The `shell` target was missing entirely. Implemented as 4 self-contained modules
behind `wubu_shell_internal.h` (opaque `ShellState`, no god headers):
`wubu_shell_history.c`, `wubu_shell_complete.c`, `wubu_shell_exec.c`,
`wubu_shell.c`. The pipeline engine's two real bugs (both worth reusing):
- **`execvp` argv is NULL-terminated, NOT argc-counted.** Popping a fd-prefix word
  (`2>` -> src_fd 2) must ALSO null the stale `argv[argc]` slot, or `execvp` reads a
  dangling `"2"`. Symptom: `echo out 2>/dev/null` prints `out 2`.
- **Cross-call fd leak in a fork/exec pipeline:** after the child sets up
  stdin/stdout/redirs, close EVERY fd >= 3 (the shell keeps none open) so a prior
  command's leaked pipe/redir end can't corrupt a later command's wiring. Without
  this, a later `... | head -1 > file` reads EOF and writes nothing.
