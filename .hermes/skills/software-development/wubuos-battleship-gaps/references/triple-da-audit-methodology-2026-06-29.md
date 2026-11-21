# Triple Devil's Advocate Audit Methodology — WuBuOS (2026-06-29)

## Overview
This document captures the comprehensive Triple DA audit methodology used to identify and classify 1,562 REAL_GAPs in the WuBuOS codebase.

## Audit Classification Framework

### What IS a REAL_GAP (Form≠Function)
1. **`(void)param;` as sole statement on success path** — Function exists but doesn't use parameters for real work
2. **`system("...")` calls** — Must be replaced with native C implementations (netlink/ioctl/fork+exec)
3. **Empty `{}` on success path** — Function body does nothing
4. **Stub/TODO/placeholder/for-later comments on success path** — Indicates missing implementation
5. **Placeholder patterns** — JIT backpatching stubs, HolyC codegen rel32 placeholders, Vulkan stub blocks
6. **Weak alias stubs** — `__attribute__((weak))` test stubs in production code
7. **`return -1` without work** — Not defensive null guards, but functions that should do work

### What is NOT a REAL_GAP
- **Defensive null checks** (`if (!ptr) return -1;`) — Correct error-path behavior
- **Input validation returns** — Fail-fast on bad input is correct
- **Error path early returns** — Proper error handling

## Audit Methodology (Phase 16)

### Step 1: Void Cast Audit
```bash
# Find all void casts in the codebase
grep -r "\(void\).*;" src/ | grep -v "static.*void" | grep -v "return" | grep -v "//"
# Filter for success-path only (not error-path null checks)
```
**Result**: 1,256 instances → filtered to success-path REAL_GAPs

### Step 2: System Call Audit
```bash
# Find all system() calls
grep -r "system(" src/
```
**Result**: 76 calls → ALL are REAL_GAPs (must reimplement in C)

### Step 3: Comment Audit
```bash
# Find stub/TODO/placeholder comments on success paths
grep -r -i "stub\|TODO\|FIXME\|not implemented\|for later\|placeholder" src/ | grep -v "//.*test"
```
**Result**: 200+ comments on success paths

### Step 4: Placeholder Pattern Audit
```bash
# JIT/Codegen/Vulkan placeholders
grep -r "placeholder\|emit_j.*_placeholder" src/
```
**Result**: 69 patterns (HolyC codegen rel32 backpatching, Vulkan stubs)

### Step 5: Weak Alias Audit
```bash
grep -r "__attribute__.*weak" src/
```
**Result**: 26 weak alias stubs in test files

### Step 6: Empty Body Audit
```bash
# Find empty function bodies on success paths
grep -r "^{}$" src/ | grep -v "static.*inline" | grep -v "define"
```
**Result**: 23 empty bodies

### Step 7: Not-Implemented Returns
```bash
# Find return -1/ENOSYS without work
grep -r "return -1\|return -ENOSYS" src/ | grep -v "if (!" | grep -v "if (.*== NULL)"
```
**Result**: 13 instances

## Gap Categories (v16 — Phase 16)

| Category | Files | REAL_GAPs | Severity |
|----------|-------|-----------|----------|
| Runtime (containers, network, OCI, snapshot, VSL, daemon, anticheat) | 13 | 420 | 🔴 CRITICAL |
| Kernel (interrupt, FAT32, tasking, memory, AHCI, TXFS, math) | 7 | 230 | 🔴 CRITICAL |
| GUI (WM, desktop, startmenu, explorer, terminal, proton, gamelib, theme, notify) | 12 | 280 | 🟠 HIGH |
| Bear RL (NN, PPO, GAAD, Vulkan, CUDA, cuDNN, env) | 8 | 190 | 🟠 HIGH |
| Hosted (metal, vulkan, display, DRM, GBM, Wayland) | 6 | 120 | 🟠 HIGH |
| Compiler (HolyC lexer, parser, codegen, PTX) | 5 | 25 | 🟡 MEDIUM |
| Apps (editor, canvas, codec, freedoom, terminal, calc, control) | 8 | 55 | 🟡 MEDIUM |
| Audio (Furnace 12 chips, SF2, Ardour DAW, AI plugins) | 2 | 0 | 🟡 MEDIUM (architectural) |
| Bridge (syscall, DOS flip) | 3 | 0 | 🟡 MEDIUM |
| Tools (ISO9660, screenshot, weight_check) | 3 | 0 | 🔵 LOW |
| Shell (unified shell) | 1 | 0 | 🔵 LOW |
| Other (JIT encoder/disasm/minic) | 5 | 222 | 🔵 LOW |
| **TOTAL** | **73** | **1,562** | |

## Prioritization Strategy

1. **Don't fix defensive returns** — They're correct behavior (fail fast on bad input)
2. **Focus on happy-path stubs** — Functions that return 0/-1 on SUCCESS path
3. **Eliminate system() calls** — Every `system("...")` = REAL_GAP (must reimplement in C)
4. **Eliminate void casts on success path** — `(void)param;` as sole statement = REAL_GAP
5. **Eliminate empty bodies on success path** — `{}` or `{ return 0; }` = REAL_GAP
6. **Eliminate stub/TODO/placeholder comments on success path** — REAL_GAP
7. **Eliminate weak alias stubs** — `__attribute__((weak))` test stubs = REAL_GAP
8. **Eliminate placeholder patterns** — JIT backpatching, codegen stubs = REAL_GAP
9. **Triple DA audit** — Verify each gap: is it actually called in tests? Does test pass?
10. **Test-first** — If a test exercises the code and passes, the gap is cosmetic

## GUI Campaign Execution Pattern

```bash
# For each file in priority order:
# 1. Inspect void casts on success path
grep -n "(void)" src/gui/explorer.c | grep -v "static.*void" | grep -v "return"

# 2. Identify each REAL_GAP (void cast, stub, placeholder, system call, empty body)

# 3. Implement real C logic (replace, use params, no system())

# 4. Run test target
make test_explorer  # Verify

# 5. Full build verification
make all

# 6. Repeat for next file
```

## Verification Commands

```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed

# Runtime Core
make test_oci test_network test_snapshot test_vsl test_holyd test_proton test_proton2 test_bottles

# Kernel/Metal
make test_fat32 test_holyc test_memory

# Bridge
make test_bridge test_bridge_flip test_syscall

# Hosted/Wayland
make test_hosted test_host_exec

# GUI
make test_clipboard test_wm test_startmenu test_explorer test_term

# Runtime/Container
make test_arch test_ramdisk test_gc test_txfs test_styx test_styxfs
make test_archd test_holyd test_drm_direct test_screenshot test_mime test_trash
make test_gamelib test_deploy test_pkgmgr test_anticheat
```

## GUI Campaign Progress (2026-06-29)

| Priority | File | Gaps | Status | Tests |
|----------|------|------|--------|-------|
| 1 | `gui/wubu_clipboard.c` | 43 | ✅ DONE | 17/17 |
| 2 | `gui/explorer.c` | 31 | ✅ DONE | 74/74 |
| 3 | `gui/startmenu.c` | 24 | ✅ DONE | 4/4 |
| 4 | `gui/term.c` | 23 | ✅ DONE | 4/4 |
| 5 | `gui/wm.c` | 22 | 🎯 NEXT | 16/16 |
| 6 | `gui/notepad.c` | 18 | 📋 | — |
| 7 | `gui/paint.c` | 17 | 📋 | — |
| 8 | `gui/calc.c` | 15 | 📋 | — |
| 9 | `gui/editor.c` | 14 | 📋 | — |

## term.c REAL_GAP Closure (2026-06-29)

- 23 void casts + placeholders closed
- PTY backend: posix_openpt/grantpt/unlockpt/ptsname fork+exec
- Tabbed sessions: Shell, HolyC REPL, Container
- VT100/ANSI parser: CSI, SGR, cursor, scrolling
- Scrollback: 10,000 line circular buffer
- Copy/paste: Shift+arrows, Ctrl+Shift+C/V
- Keyboard shortcuts: Ctrl+Shift+T/W/C/V/F/L, Ctrl+PgUp/PgDn
- Mouse: tab bar clicks, content selection
- GPU VBE double-buffer rendering
- Window management integration