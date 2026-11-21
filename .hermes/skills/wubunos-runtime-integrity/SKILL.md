---
name: wubunos-runtime-integrity
description: Strict-C11 runtime build hardening and shim-header bugs.
license: MIT
author: WaefreBeorn
version: 1.0.0
metadata:
  hermes:
    tags: [c11, build-hardening, nt-bridge, ftw, shim-headers]
    related_skills: [wubunos-compiler-testing, wubuos-masterpiece-architecture, wubu-project-orientation]
---

# WuBuOS Runtime Integrity (strict-C11 host runtime)

Governs the C11 host/runtime build layer of `wubuos`: `src/runtime/`, the `wubu_gnu_compat.h` / `wubu_ftw.h` shim headers, `wubu_fs_util.c`, and the NT transliteration runtime (`src/runtime/vsl/vsl_nt_*.c`). Not the compiler gauntlet (that is `wubunos-compiler-testing`); this is the *hosted-binary* side that compiles with `-std=c11 -D_POSIX_C_SOURCE=200809L` and must stay self-contained per the "no _GNU_SOURCE" directive.

## When to use this skill

Apply whenever the strict-C11 host/runtime build of `wubuos` shows a runtime failure in `src/runtime/` (shim headers, `wubu_fs_util.c`, the NT bridge `vsl_nt_*.c`) that does not reproduce under `_GNU_SOURCE`, any "implicit declaration" warning from runtime objects, or flaky/failing `make test_vsl_nt` / `test_cap` / `test_snapshot` / `test_vsl_nt_ext`.

## Always-on rules
- Builds target **strict C11 + `_POSIX_C_SOURCE=200809L` (no `_GNU_SOURCE`)**. Add runtime-needed symbols to the `wubu_gnu_compat.h` shim, never by flipping `_GNU_SOURCE`.
- **POSIX/Linux include flags live in ONE header — `src/egojar.h` — never in a module.** It is a trojan-horse suit: the feature-test macros plus every POSIX/Linux/libc-extension header the tree uses, and NOTHING else (no declarations, no code, no `static inline`). Standard C (`<stdio.h>`, `<string.h>`, `<stdint.h>`) stays in the module. A file that needs POSIX includes the jar **first**, because feature-test macros only take effect before the first system header. See `references/egojar-posix-seam.md`.
- Every shim constant is a contract with a libc ABI value. Validate against the host header with `search_files` (`path='/usr/include'`, `files='ftw.h'`) or by reading `/usr/include/ftw.h` directly — never transcribe constant values from memory.
- Runtime test binaries are the truth: `test_vsl_nt`, `test_cap`, `test_vsl_nt_ext`, `test_snapshot`. Re-run the full gate after any change to `wubu_fs_util.c`/`wubu_ftw.h`.

## Procedure — harden a strict-C11 runtime build
1. **Reproduce with the real flags.** Standalone probe WITHOUT `_GNU_SOURCE` using the Makefile recipe: `gcc -std=c11 -D_POSIX_C_SOURCE=200809L -include wubu_gnu_compat.h -I$(RT)`.
2. **Instrument, don't infer.** Traced callback printing `unlink`/`rmdir` + `errno`/`strerror` per path.
3. **Compare token values to the host enum.** `gcc -E` the system header; if a shim define disagrees with the libc enum it shadows the real value.
4. Patch the shim, `rm -f` dependent `.o` (incremental Makefile hides header fixes), then `make test_*` and assert green + no leftover state.

## Feature-macro decision rule (which macro exposes which symbol)
When a runtime TU needs a libc symbol that `-std=c11 -D_POSIX_C_SOURCE=200809L`
hides, pick the macro by what the symbol actually needs — do NOT reflex-reach for
`_GNU_SOURCE`, and do NOT assume a project macro is a feature macro:
- `_DEFAULT_SOURCE 1` (preferred, narrowest) exposes the BSD/SVID/glibc-default
  set: `madvise`, `setgroups`, `usleep`, `strcasecmp` (on glibc). Put it at the
  TOP of the TU, before ANY `#include`, so glibc's `<features.h>` sees it.
- `_GNU_SOURCE 1` (per-file, only when `_DEFAULT_SOURCE` is not enough) is
  required for the genuinely glibc-only wrappers: `unshare`, `setns`,
  `memfd_create`, `pipe2`, `clone` with the `CLONE_*` flags. Use it file-local,
  never as a global build flag, so the rest of the tree keeps the strict contract.
- `WUBU_HOSTED` is NOT a feature macro. It only toggles WuBu's own hosted
  shims. A `#define WUBU_HOSTED` added to "expose" a syscall does nothing and
  collides with the `-DWUBU_HOSTED` command-line flag → `"WUBU_HOSTED"
  redefined` warning. Guard any bare `#define WUBU_HOSTED` with `#ifndef`.
- Standard POSIX symbols (`getpid`, `unlink`) usually just need the RIGHT
  header — add `#include <unistd.h>` / `<grp.h>` before reaching for any
  feature macro.
- **Gate the defines on `__STRICT_ANSI__` when the TU must also build under
  the default `gnu17`.** Unconditionally defining `_POSIX_C_SOURCE` narrows the
  default build and can hide GNU-only declarations the rest of the file uses.
  The portable block, at the very top before ANY include:
  ```c
  #if defined(__STRICT_ANSI__)
  #define _POSIX_C_SOURCE 200809L
  #define _DEFAULT_SOURCE 1
  #endif
  ```
  This fixed `CLOCK_MONOTONIC` (POSIX 199309), `M_PI` and
  `MADV_WILLNEED`/`MADV_HUGEPAGE` (`_DEFAULT_SOURCE`) in eight CORE_OBJ
  translation units that only compiled because the normal build is `gnu17`.
  The error appears ONLY under `-std=c11`, so a green aggregate gate says
  nothing about it.
- For WuBu-native constants/macros (CPU affinity, `CLONE_*`), extend the
  `wubu_gnu_compat.h` shim per the always-on rule; use a feature macro only for
  libc *function declarations* the shim cannot provide.
Verify the choice with a one-line probe before editing the TU:
`echo '#define _GNU_SOURCE 1
#include <sched.h>
int main(){return unshare(0);}' | gcc -x c -std=c11 - -o /tmp/t`

## Bulk strict-C11 audit (whole CORE_OBJ)

`-pedantic` over the whole build is a measurement, not a gate. Run it before
claiming a "strict C11" goal is close:

1. Derive the source list from the build, not from a directory listing:
   `make -pn 2>/dev/null | awk -F'= ' '/^CORE_OBJ *=/{print $2}' | tr ' ' '\n' | sed 's/\.o$/.c/'`
2. Drop non-C translation units (`.cu`, `.S`) — a naive `.o → .c` map reports a
   CUDA kernel as a missing source and poisons the count.
3. `gcc -std=c11 -pedantic -fsyntax-only -I include <file>` each one, collect
   stderr, and count `error:` lines separately from warnings.
4. Report three numbers: sources, diagnostic lines, files-with-diagnostics.
   Errors are portability defects; warnings are a long tail (braced groups,
   implicit declarations, macro redefinition).
5. Do NOT wire a failing audit into `test_all` — a gate that fails on known
   debt gets disabled within a day. It becomes a gate when the diagnostic file
   is empty.

`scripts/audit_c11.sh` runs all of the above (exit 0 only when clean).

## Pitfalls
- **Shim headers shadow libc ENUM constants.** libc exposes `FTW_*`/`DT_*` as enum constants, NOT preprocessor macros. A `#ifndef SYMBOL` guard is *always* true for an enum constant, so a fallback `#define` silently OVERRIDES the real value. The `wubu_ftw.h` defect: `FTW_DP` was `0` while glibc's enum value is `5`, so `wubu_fs_rm_rf` matched the `FTW_F` branch (`0`) and called `rmdir()` on regular files, yielding `ENOTDIR`, nftw abort, and `NtDeleteKey` returning `STATUS_UNSUCCESSFUL`. **Rule: when the host header exposes enum constants, define the fallback with the EXACT glibc numeric value and confirm with `gcc -E` that under each feature-flag combination the system header either emits the macro (so the `#ifndef` is skipped) or the fallback matches; never `#ifndef`-guard an enum value against a wrong number.** This applies to every `FTW_*`/`DT_*` shim — audit them all after any one change.
- **Implicit declarations hide ABI mismatches AND segfault.** Under `-std=c11` (no `_GNU_SOURCE`) syscalls like `rmdir`/`unlink` are not declared by `<unistd.h>`; the compiler synthesises an implicit `int` call that links and runs (UB). The segfault form: a function returning a POINTER that is called without its header (e.g. `getenv` without `<stdlib.h>`) is implicitly declared `int`, so the 64-bit return is truncated to 32 bits and the next dereference faults — the crash surfaces at a `strncpy`/write into a static buffer, NOT at the call site, so the backtrace misleads. Treat any "implicit declaration" warning as a real defect; fix the feature macro/include, not the warning. A green aggregate `make test` does NOT clear it: the truncated pointer can happen to land on a readable page under the aggregate binary's memory layout while the standalone test faults — always clear every `-Wimplicit-function-declaration` in a changed TU before trusting a green gate.
- **Stale `.o` masks a header fix.** After editing a shared shim header, `rm -f` the dependent `.o` or `touch` the source before re-running the gate, else the test relinks the old object.
- **A `const char *` assigned into a `char *argv[]` is a real warning, not noise.** exec-family calls take `const char *const argv[]`; declare local argv arrays `const char *bwrap_argv[64]` so `const`-qualified command strings assign without a `-Wdiscarded-qualifiers` warning. Fix the array type; never cast away the const at the call site.

## References
- `references/strict-c-ftw-probe-recipe.md`
