# Devil's Advocate Limit Break — Parity Audit Expansion (2026-07-04)

## Context
User issued "limit break our limits" with devil's advocate review of SteamOS/Ubuntu/Arch/TempleOS parity gaps. The rule "rewriting from scratch in C" = REAL_GAP was expanded to: **EVERY parity gap = REAL_GAP**.

## Scope Reclassification

### Previous Rule (Triple DA v16)
Only these patterns = REAL_GAP:
- Void casts `(void)param;` on success paths
- Placeholders/stubs/TODOs
- `system()` calls
- Weak aliases
- `not_impl` returns
- Empty bodies `{}`

**Count**: 1,562 REAL_GAPs (triple DA verified)

### New Rule (Limit Break)
**Every parity gap with SteamOS/Ubuntu/Arch/TempleOS/ZealOS/ReactOS = REAL_GAP**

**Expansion**: ~860+ new REAL_GAPs added from parity audits

## Parity Audit Results

| Target | Parity Missing | New REAL_GAPs | Key Gaps |
|--------|---------------|---------------|----------|
| **SteamOS** | 95% | ~300+ | Steam Client (CEF UI, store, library, friends), Proton (Wine+DXVK+VKD3D), gamescope (Wayland compositor, VRR, HDR, FSR), Pressure Vessel (container runtime), Deck UI, Steam Input, Steam Networking, Shader pre-cache, ProtonDB, Steam Cloud |
| **Ubuntu/Arch** | 80-95% | ~250+ | systemd (init, services, timers, units), apt/pacman (repos, deps, hooks), NetworkManager, D-Bus, Polkit, PipeWire, CUPS, AppArmor/SELinux, systemd-homed, mkinitcpio/dracut, GRUB |
| **TempleOS/ZealOS** | 70% | ~180+ | HolyC JIT (AOT+JIT), Doc/DolDoc, Compiler-as-library, RedSea FS, Ring-0/identity-mapped memory, VGA/VESA direct, PC speaker audio |
| **Arch Daemon (wubu_archd)** | 95% | ~50+ | pacman -Syu, AUR, ABS, hooks, signing, repo management |
| **TempleOS Daemon (wubu_holyd)** | 80% | ~80+ | Real-time REPL, persistent compiler state, symbol table, macro expansion |

**Total Parity Expansion**: ~860+ new REAL_GAPs

## Updated Critical Tier (from BATTLESHIP.md)

| # | Subsystem | File | Gaps | Status |
|---|-----------|------|------|--------|
| 1 | VSL Syscalls | runtime/vsl/vsl_syscall.c | 173 void casts | PARTIAL |
| 2 | Package Manager | gui/wubu_pkgmgr_test.c | 14 void + 9 system() | NOT STARTED |
| 3 | Audio Engine | audio/wubu_audio.c | 13 void + placeholders | NOT STARTED |
| 4 | Arch Daemon | runtime/wubu_archd.c | 50+ parity | NOT STARTED |
| 5 | TempleOS Daemon | runtime/wubu_holyd.c | 80+ parity | PARTIAL |
| 6 | Proton/Wine | runtime/wubu_proton.c | 95% SteamOS parity | PARTIAL |
| 7 | Bear Vulkan | bear/bear_vulkan.c | 26 void casts | PARTIAL |
| 8 | SteamOS Parity | N/A | ~300+ | 95% MISSING |
| 9 | Ubuntu/Arch Parity | N/A | ~250+ | 80-95% MISSING |

## ReactOS Mission Added

**Source**: `/home/wubu/.hermes/profiles/mind-palace/home/myseed/reactos-study/reactos/`

### NT Syscall Emulation → Styx9/VSL Transliteration

| ReactOS Component | Path | Target WuBuOS Layer |
|-------------------|------|---------------------|
| NT syscall dispatch | `ntoskrnl/ke/` + `dll/ntdll/` + `sysfuncs.lst` | VSL syscall bridge |
| Memory manager | `ntoskrnl/mm/` (VAD, paging, sections) | VSL mmap/brk + ZealOS memory |
| Object manager | `ntoskrnl/ob/` (handles, security, types) | Styx9 fid/namespace + VSL fd table |
| I/O manager | `ntoskrnl/io/` (IRP, device stack, drivers) | VSL read/write/ioctl + Styx9 9P |
| Win32k | `win32ss/user/` + `gdi/` | Win98 WM + wm.c |
| NTDLL stubs | `dll/ntdll/*.c` | VSL syscall entry points |

### Transliteration Pipeline
```
ReactOS NT syscall (0x0-0x400+) 
    → WuBuOS VSL syscall bridge (runtime/vsl/vsl_syscall.c)
    → Styx9/9P namespace (runtime/styxfs.c)
    → ZealOS kernel services (tasking, memory, vbe, input)
    → TempleOS layer (HolyC JIT, compiler-as-library)
```

## Key Implementation Insight

The "limit break" changes the workflow from:
- **OLD**: "Pick ONE gap → implement → test → commit → repeat"
- **NEW**: **PARALLEL GAP CLOSURE** — all 9 critical tier items worked on simultaneously until 1562 → 0

## Files Updated This Session

- `BATTLESHIP.md` — Roadmap reduced to 9 items, VSL gap count corrected to 173, hosted.c marked COMPLETE
- `slate.md` — Active work surface updated with 10 parallel work items
- `STATE.md` — Full architecture status with devil's advocate parity tables
- `reactos-study/reactos/` — Cloned (28,365 files) for NT syscall study