# Recovering a Half-Committed Split After a Crash (2026-07-22)

Exact command transcript from the recovery session. The WM 4-submodule split +
macOS/VSL syscall split were left uncommitted by a crashed session; the in-flight
build had only PARTIALLY wired the new split files.

## 1. Enumerate damage
```
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
git status --short          # M src/gui/wubu_wm.c  +  ?? src/gui/wubu_wm_desktop.c ...
git diff --stat             # shows modified tracked files (what the edit touched)
```
Symptom: a `M` base module (lines removed) + `??` new split files (untracked).

## 2. Find link lines that reference the base module
```
grep -n "wubu_wm" Makefile
# every target whose recipe mentions wubu_wm.c may ALSO need the split files
```
Do NOT stop at the gate target — other `test_*` targets consume the base too.

## 3. Map undefined symbol -> DEFINING file
```
grep -rn "mac_trap_table\|mac_bsd_table" src/runtime/vsl/
# defs: vsl_syscall_mac_bsd.c:783  vsl_syscall_mac_mach.c:220
# refs: vsl_syscall_mac.c:29,40
```
The dispatch file (`vsl_syscall_mac.c`) was wired; the DEFINING files were not ->
`ld: undefined reference to mac_trap_table` / `mac_bsd_table`. Add the DEFINERS.

## 4. Wire the split files into every link line
- `test_syscall` (Makefile ~568): add `vsl_syscall_mac_bsd.c vsl_syscall_mac_mach.c`
- `test_screenshot` (~621): add `wubu_wm_desktop.c wubu_wm_input.c wubu_wm_render.c`
- `test_gui_screenshot` (~630): same three WM files
- `test_wubu_wm` was already covered by the in-flight edit.

## 5. Verify — gate is NOT enough
```
make test                                  # GATE: all tiers PASS
                                       #   BUT does NOT run test_screenshot / test_gui_screenshot
make test_vsl_mac && make test_vsl_macho   # 23/23, 24/24 (macOS split)
make test_screenshot                        # PASS  (direct WM consumer)
make test_gui_screenshot                    # PRE-EXISTING broken — see below (not crash damage)
```
Rule: after ANY split, explicitly run the split's DIRECT consumers, not just `make test`.

## 6. Pre-existing defect found, deliberately left
`test_gui_screenshot` was already broken BEFORE the crash (unrelated to the split):
- links `hosted.c` (own `main()` at hosted.c:208) + `wubu_screenshot_test.c`
  (also `main()`) -> `multiple definition of main`
- references `hosted_wayland_surface.o` / `xdg-shell-private.o` /
  `primary-selection-private.o` — Wayland-codegen `.o` files with NO `.c` sources.
Judgment during crash recovery: do NOT scope-creep into pre-existing defects
unless they're in the `make test` gate or the user explicitly directs. Note them,
finish the recovery commit, flag them in the handoff.

## 7. Hygiene before commit
```
printf '\n# Local reference dump (kept locally, not committed)\ndarling-ref/\n' >> .gitignore
git add .gitignore Makefile <split sources...>
# do NOT add the regenerated binary src/runtime/wubu_dos_emu_smoke (build artifact)
git config user.name "WuBu"; git config user.email "wubu@wubuos.local"  # identity missing in repo
```
