---
name: wubuos-vsl-cpm
description: "How to add an ABANDONED/toast OS syscall personality to WuBuOS's VSL (the inter-device-agnostic syscall layer). Covers the CP/M BDOS and Classic Mac OS (68K A-line) personalities — BOTH LANDED with passing tests — AND the repeatable pattern for the next toast OS personalities: BeOS libbe, RISC OS SWI, AmigaOS Exec. The CRITICAL WIRING RULE section prevents the link-break that occurs when a new personality is added but not wired into every vsl_syscall.c compile site. Use when the user says 'find older abandoned software to get those syscalls into VSL' or 'add another OS personality'."
---

# WuBuOS VSL — adding an abandoned OS personality

## Why
WuBuOS is the inter-device-agnostic OS: it runs ALL container calls, so VSL must understand
every execution personality. The mission is to harvest "even older toast abandoned software"
syscall tables and wire them into VSL as first-class personalities (real host effects, no stubs).

## Architecture (table-driven, proven)
`vsl_syscall_dispatch()` in `src/runtime/vsl/vsl_syscall.c` routes by **high-order class bits**:
- `0xC0xxxxxx` → CP/M BDOS (`vsl_cpm_syscall_dispatch`)
- `0xFF000000` mask → macOS/XNU (`vsl_mac_syscall_dispatch`)
- else → native Linux/pOSIX `vsl_syscall()` table

Each personality = ONE module file + ONE internal header + a dispatch entry point + a test.
Reuse the existing Linux/VSL host calls (open/read/write/close/mmap/stat) — never reimplement
the OS; just translate the old ABI onto VSL's backing syscalls.

## CP/M BDOS (LANDED, passing)
Files: `src/runtime/vsl/vsl_syscall_cpm.c`, `vsl_syscall_cpm_internal.h`, `vsl_syscall_cpm_test.c`.
Makefile target `test_vsl_cpm`. Coverage: functions 0-44 (console I/O, select disk, set DMA,
open/close/create/delete/read-seq/write-seq/search-first/next/rename/random-read/write/size,
user number). Dispatched via `num = 0xC0000000 | (fn<<8)`; guest `de`/param in `regs[0]`.
FCB 8.3 names map to host files under `WUBU_CPM_ROOT/<DRIVE>/`. Real host I/O round-trip verified.

## Repeatable procedure for the NEXT "toast" OS
1. **Pick + cite.** Choose an abandoned OS with a citable syscall/trap table:
   - Classic Mac OS (1984): 68K **A-line trap words** `$Axxx` (OS traps + Toolbox traps,
     Trap Manager, 256 OS entries + 1024 Toolbox). Complements the XNU macOS personality.
   - BeOS (1991/1998): `libbe` R5 syscalls (kernelkit). Distinctive, abandoned 2001.
   - RISC OS (1987): **SWI** numbers (OS_*, FileCore, etc.).
   - AmigaOS (1985): **Exec** library vectors / `Exec`/`DOS` packet functions.
2. **Encode a class bit** distinct from `0xC0`/`0xFF`. Add the prototype to
   `vsl_syscall_internal.h` and a `case`/`if` in `vsl_syscall_dispatch()`.
3. **Write the internal header** (function-number #defines + handler typedef + table extern +
   `vsl_<os>_syscall_dispatch` prototype). Mirror `vsl_syscall_cpm_internal.h`.
4. **Write the module**: a `const <os>_syscall_fn <os>_table[N]` with real handlers backed by
   host syscalls. Unimplemented fns return the OS's error convention (not a fake success).
5. **Write the test** driving `vsl_syscall_dispatch()` with the encoded numbers; assert REAL
   effects (file round-trip, etc.), not just non-crash.
6. **Wire the Makefile** `test_vsl_<os>` target: list the core VSL objects
   (`vsl.c vsl_syscall.c vsl_syscall_*.c vsl_memory.o vsl_file.o vsl_driver.o vsl_shared.o
   vsl_elf.o vsl_gpu_vulkan.o vsl_macho.c vsl_syscall_mac*.c vsl_syscall_cpm.c <os>.c <os>_test.c`)
   + `-lpthread -lvulkan`.
7. **Run** `make test_vsl_<os>`; confirm ALL PASSED. Then `make -j4` + `make test` for regressions.

## Landed personalities (update as you add)
- **CP/M BDOS** (`0xC0`) — `vsl_syscall_cpm.c` + test. GREEN.
- **Classic Mac OS (68K A-line)** (`0xB0`) — `vsl_syscall_macclassic.c` + test. GREEN.
  Encodes as `num = 0xB0000000 | (trap & 0xFFF)`. Handles NewPtr/DisposePtr/GetPtrSize,
  NewHandle/DisposeHandle, Open/Close/Read/Write/Create/Delete/GetFPos/SetFPos (host fd as
  refNum), TickCount (CLOCK_MONOTONIC @60Hz), DrawChar/WriteChar/WriteLn (stdout). Unimplemented
  trap -> paramErr (-1). NOTE: needs `<malloc.h>` for `malloc_usable_size` (glibc).

## CRITICAL WIRING RULE (learned from a crashed-session link break)
`vsl_syscall_dispatch()` in `vsl_syscall.c` calls THREE personality entry points UNCONDITIONALLY:
`vsl_cpm_syscall_dispatch` (0xC0), `vsl_macclassic_syscall_dispatch` (0xB0),
`vsl_mac_syscall_dispatch` (XNU, 0xFF000000). So **every** Makefile link line that compiles
`vsl_syscall.c` (or lists `vsl_syscall.o`) MUST include the object files for ALL THREE:
`vsl_syscall_cpm.o`, `vsl_syscall_macclassic.o`, `vsl_syscall_mac.o`,
`vsl_syscall_mac_bsd.o`, `vsl_syscall_mac_mach.o` — PLUS `vsl_macho.o` (pulled in by
`vsl_process.c` via `vsl_macho_validate/load/is_macho`, unconditional). If you add a new
personality, grep Makefile for every `vsl_syscall.c` / `vsl_syscall.o` site and add the new
`.o` there too, or the whole VSL suite (test_vsl, test_vsl_nt, test_syscall, APP_RT_OBJS,
even test_vsl_cpm) fails to LINK with undefined reference. The dedicated `test_vsl_<os>` target
is not enough — it only fixes that one test, not the shared link sites.

## Pitfalls
- **Handler signature MUST be 7 params** (`fn, a, b, c, d, e, f`) in BOTH the .c definition and
  the header prototype — the router passes all 6 registers. A 6-param definition vs 7-param
  prototype fails the build with "too few arguments".
- **Link needs `-lvulkan`** whenever `vsl_gpu_vulkan.o` is in the link line (it references
  vk* symbols). Forgetting it → undefined reference to `vkGetDeviceQueue` etc.
- **Don't re-implement file I/O** — CP/M/BeOS/RISC-OS file semantics all reduce to
  open/read/write/close/mmap on the host; keep handlers thin.
- **DOS is ALREADY covered** by `wubu_dos_emu.c` (INT 21h). Don't add a DOS personality to VSL;
  it's a separate emulator. The "older toast" targets are PRE-DOS (CP/M) and non-x86 (Mac/Be/RISC/Amiga).
- **Class-bit collisions**: macOS uses `0xFF000000`. Pick a top byte not `0xFF` for new ones
  (CP/M uses `0xC0`). Keep a registry in `vsl_syscall_internal.h`.
- Keep each module C11, opaque, self-contained, minimal includes (per project rules).
