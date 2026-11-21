# Crash recovery: central dispatch-router fan-out link break (2026-07-22)

A crash mid-edit left `vsl_syscall_dispatch()` in `src/runtime/vsl/vsl_syscall.c`
extended with TWO new class routes — CP/M BDOS (`class_bits == 0xC0`) and Classic
Mac OS 68K A-line (`class_bits == 0xB0`) — plus the already-present XNU macOS
route (`num & 0xFF000000`). The new *personality modules*
(`vsl_syscall_cpm.c`, `vsl_syscall_macclassic.c`) were written, declared in
`vsl_syscall_internal.h`, and **only wired into their own dedicated test target**
(`test_vsl_cpm`). The crash did NOT wire them (or the XNU mac modules) into the
*shared* link sites that compile the router.

Result: every link line that compiles `vsl_syscall.c`/`.o` failed with
`undefined reference to vsl_cpm_syscall_dispatch` and
`vsl_macclassic_syscall_dispatch`. Whole VSL suite red: `test_vsl`, `test_vsl_nt`,
`test_syscall`, `APP_RT_OBJS`, and even `test_vsl_cpm` itself (it compiles
`vsl_syscall.c` inline so it also needs macclassic).

## Damage pattern (the distinct sub-pattern)
A SINGLE fan-out module (`vsl_syscall.c`) gained new unconditional call sites to
new personality modules. The new modules were wired only into their dedicated
`test_vsl_<os>` target — NOT into the shared link sites. This is NOT a file split
(moved-`const`-table) case; it's a *router gained callees* case. The shared
router link sites break even though the dedicated test passes.

## Diagnostic sequence (reuse this)
1. **See the in-flight router change.** `git diff src/runtime/vsl/vsl_syscall.c`
   — the new `if (class_bits == 0xC0)` / `0xB0` blocks revealed the new callees.
2. **Find every link site that compiles the router.** Grep the Makefile for both
   the `.o` and the `.c` forms (some targets compile `.c`, some link `.o`):
   `grep -nE "vsl_syscall\.o|vsl_syscall\.c" Makefile`. There will be ~5 sites:
   `VSL_OBJS`, `VSL_NT_OBJS`, `APP_RT_OBJS`, `test_vsl_cpm` (inline `.c`),
   `test_syscall` (inline `.c`).
3. **Build the dedicated test first** (cheapest — already wired). Confirms the
   new module compiles and its own test passes:
   `make test_vsl_cpm` / `make test_vsl_macclassic`.
4. **Run EACH shared site; collect the distinct undefined-reference symbols.**
   Each undefined sym is a missing personality `.o`. Don't fix just the first —
   run all and list them:
   - `undefined reference to vsl_cpm_syscall_dispatch` → needs `vsl_syscall_cpm.o`
   - `undefined reference to vsl_macclassic_syscall_dispatch` → needs `vsl_syscall_macclassic.o`
   - `undefined reference to vsl_mac_syscall_dispatch` → needs `vsl_syscall_mac.o` + `_mac_bsd.o` + `_mac_mach.o` (XNU)
   - `undefined reference to vsl_macho_validate/load/is_macho` → needs `vsl_macho.o`
5. **Wire ALL missing `.o` into ALL shared sites** (the dedicated target fix is
   NOT sufficient — it only heals that one test). Add:
   `vsl_syscall_cpm.o vsl_syscall_macclassic.o vsl_syscall_mac.o vsl_syscall_mac_bsd.o vsl_syscall_mac_mach.o vsl_macho.o`
   to `VSL_OBJS`, `VSL_NT_OBJS`, `APP_RT_OBJS`, and the inline-`.c` link lines of
   `test_vsl_cpm` and `test_syscall`. (The main `test_vsl` already had the XNU +
   macho objects; it just needed cpm + macclassic.)

## Transitive surprise worth remembering
`vsl_process.c` (in `VSL_NT_OBJS`) calls `vsl_macho_validate/load/is_macho`
unconditionally, but `VSL_NT_OBJS` omitted `vsl_macho.o`. The main `test_vsl`
links `vsl_macho.c` directly so it masked the gap. When a shared `.c` in a list
calls a symbol whose `.o` is absent from THAT list, you get undefined refs — even
if another target in the repo links it fine. Suspect missing transitive `.o` on
any "this target only" link error.

## Verification (the real bar)
Run every affected target; a warm-cache pass is not proof:
```
make test_vsl            # main: 87/87 passed
make test_vsl_nt         # 251 passed, 0 failed
make test_vsl_cpm        # ALL PASSED
make test_vsl_macclassic # ALL PASSED (24 checks)
make test_syscall        # 5/5 passed
```
A new personality with no test is a "form-without-function" orphan (see Mode D in
SKILL.md) — the Classic Mac module had a module but no test; write a real one
driving `vsl_syscall_dispatch()` with the encoded class number
(`num = 0xB0000000 | (trap & 0xFFF)`), asserting real host effects (file
round-trip, memory alloc/free), not just non-crash.

## Lesson
When you extend a central fan-out dispatcher (router/switch table) with a new
callee personality, the dedicated `test_<os>` target is the WRONG unit of
wiring. Grep for EVERY link site that compiles the router and add the new `.o`
there. The dedicated test passing is a false-green.
