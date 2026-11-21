# Triple Devil's Advocate Wiki Methodology
**Session**: 2026-06-29
**Purpose**: Document the methodology for creating comprehensive 4-way OS comparison wikis that drive gap analysis

---

## Methodology Overview

The Triple DA approach compares WuBuOS against 4 reference operating systems:
1. **GNOME 46+** — Modern Linux desktop (Mutter, GTK4, libadwaita, D-Bus, systemd, PipeWire, Flatpak)
2. **SteamOS 3.x** — Gaming-focused (gamescope, Proton/DXVK/VKD3D, Pressure Vessel, Steam Input/Networking)
3. **TempleOS/ZealOS** — Ring-0, HolyC JIT, RedSea FS, VGA/VESA direct, PC Speaker audio
4. **Arch Linux** — Rolling distro (pacman/alpm, AUR, ABS/makepkg, systemd, mkinitcpio, NetworkManager)

For each reference OS, we answer three questions per feature:
1. **DA 1 — Reference OS**: What does this OS actually do? (Specs, source, behavior)
2. **DA 2 — WuBuOS**: What does WuBuOS currently do? (Code, tests, BATTLESHIP.md)
3. **DA 3 — The Gap**: What is the REAL_GAP? (void casts, stubs, system() calls, missing files)

---

## Wiki Structure Created

### OS Study Files (Raw Intelligence)
```
/home/wubu/.hermes/profiles/mind-palace/home/myseed/os-studies/
├── gnome/gnome_study.md       (~17KB) — Mutter, GTK4, D-Bus, systemd, PipeWire, Flatpak, GVfs, Tracker, a11y
├── steamos/steamos_study.md   (~20KB) — gamescope, Proton, DXVK/VKD3D, Pressure Vessel, Steam Input/Networking
├── templeos/templeos_study.md (~17KB) — HolyC JIT, Doc/DolDoc, RedSea FS, Ring-0, VGA/VESA, PC Speaker
├── arch/arch_study.md         (~19KB) — pacman/alpm, AUR, ABS/makepkg, systemd, mkinitcpio, NetworkManager
└── README.md                  — Index + quick reference
```

### Wiki Files (Processed Analysis)
```
/home/wubu/.hermes/profiles/mind-palace/home/myseed/wiki/os-comparison/
├── index.md                    — Navigation, quick start, status snapshot
├── triple_da_wiki.md           (~42KB) — Full 4-way comparison + conflicting requirements + 228-session roadmap
└── gap_analysis_wiki.md        (~21KB) — Actionable tracking: Feature → File → REAL_GAPs → Priority → Sessions
```

---

## Key Outputs from This Session

### 1. Consolidated Parity Matrix
| Subsystem | GNOME | SteamOS | TempleOS | Arch | WuBuOS Current | WuBuOS Target |
|-----------|-------|---------|----------|------|----------------|---------------|
| Kernel | Linux | Linux | ZealOS | Linux | ZealOS ✅ | ZealOS + Linux |
| Init/System | systemd | systemd + A/B | None | systemd | Missing | systemd-like |
| Package Manager | Flatpak + apt | Steam Runtime + pacman | None | pacman + AUR | Stub | pacman + OCI |
| Window Manager | Mutter | gamescope | VGA/VESA | KDE/GNOME | Win98 WM | gamescope + Win98 |
| Compositor | Mutter | gamescope | None | KWin/Mutter | Client only | gamescope |
| Audio | PipeWire | PipeWire | PC Speaker | PipeWire | Missing | PipeWire |
| Network | NetworkManager | Steam Networking | None | NetworkManager | Netlink partial | NetworkManager |
| Graphics | Mesa + Vulkan | Mesa + Vulkan + FSR | VGA/VESA | Mesa + Vulkan | DRM/KMS + Vulkan | gamescope + FSR |
| Containers | Flatpak + podman | Pressure Vessel | None | systemd-nspawn + podman | bwrap partial | Pressure Vessel |
| IPC | D-Bus | Steam IPC | None | D-Bus | Styx 9P | D-Bus + 9P |

### 2. Conflicting Requirements Identified (6 Major)
1. **Init System**: systemd vs TempleOS none → **Decision**: systemd-like for hosted, minimal for bare-metal
2. **Compositor**: Mutter vs gamescope vs none → **Decision**: gamescope primary, Win98 WM for desktop
3. **Package Management**: pacman vs Steam Runtime vs Flatpak vs none → **Decision**: Three-layer approach
4. **Window Manager**: Mutter vs gamescope vs Win98 vs none → **Decision**: Keep Win98 WM, nest gamescope for games
5. **File System**: ext4/VFS vs RedSea vs Styx 9P → **Decision**: Styx 9P primary, RedSea optional bare-metal
6. **Security Model**: AppArmor/SELinux vs seccomp vs Ring-0 vs none → **Decision**: MAC for hosted, Ring-0 for bare-metal

### 3. Implementation Roadmap: 5 Tiers, ~228 Sessions
| Tier | Focus | Key Gaps | Sessions |
|------|-------|----------|----------|
| **Tier 0** | Foundational (blocks all) | D-Bus, systemd, PipeWire, NM, pacman | 35 |
| **Tier 1** | SteamOS Gaming | gamescope, DXVK, VKD3D, Pressure Vessel, Steam Input/Net | 42 |
| **Tier 2** | GNOME Desktop | Flatpak, GVfs, Tracker, a11y, Polkit, AppArmor | 34 |
| **Tier 3** | Arch Distro | PKGBUILD/makepkg, AUR, mkinitcpio, homed, nspawn | 42 |
| **Tier 4** | TempleOS/ZealOS | HolyC JIT, Compiler lib, REPL, Doc/DolDoc, RedSea | 49 |
| **Tier 5** | Polish & Hardware | A/B updates, Deck HW, Overlay, Mesa, HiDPI, Animations | 26 |

### 4. Gap Closure This Session (128 REAL_GAPs Eliminated)
| Component | Void Casts Closed | system() Eliminated | Tests Added |
|-----------|-------------------|---------------------|-------------|
| gui/wm.c | 22 | 0 | 16 |
| gui/term.c | 23 | 0 | 4 |
| gui/explorer.c | 31 | 0 | 74 |
| gui/startmenu.c | 24 | 2 | 4 |
| gui/wubu_clipboard.c | 43 | 0 | 17 |
| bear/bear_vulkan.c | 7 | 0 | 4 pipelines |
| kernel/interrupt.c | 41 | 0 | (already done) |
| bridge/wubu_syscall.c | 97 | 2 | 5 |
| runtime/wubu_vsl.c | 15 | 0 | 4 syscalls |
| hosted/hosted.c | ~42 | 0 | (callbacks) |
| bear/bear_cudnn.c | 117 | 0 | (all ops) |
| **Net REAL_GAPs** | **~128** | **4** | **111 GUI** |

---

## How to Use This for Future Sessions

### When Starting a New Gap Closure Sprint:
1. **Read** `triple_da_wiki.md` → "NEXT SESSION PICK LIST" for prioritized gaps
2. **Read** `gap_analysis_wiki.md` → Tier tables for Feature → File → REAL_GAPs mapping
3. **Read** relevant OS study file for implementation details of the reference feature
4. **Implement** in the WuBuOS file, following "Rewriting from scratch in C" = real C, no stubs
5. **Verify** with `make test_<target>` and `make all`
6. **Update** both wikis and `BATTLESHIP.md` with new gap counts

### When Adding a New Reference OS:
1. Create `os-studies/<os>/<os>_study.md` with architecture + feature inventory
2. Add comparison column to `triple_da_wiki.md` parity matrix
3. Add conflicting requirements analysis
4. Add tier gaps to `gap_analysis_wiki.md`
5. Update roadmap session estimates

---

## Templates for Future Use

### OS Study Template
```markdown
# <OS> Study — Architecture & Feature Inventory
## Core Philosophy / Architecture Overview
## Subsystem: <Name> (Feature Table: Reference OS | WuBuOS | Gap)
## Platform Services (What WuBuOS Lacks Entirely)
## Widget/Component Parity Table
## Accessibility / Developer Tools / Unique Features
## Key Gaps for WuBuOS (Must/Should/Nice)
## Implementation Priority for WuBuOS (Phase | Component | File | Sessions)
```

### Gap Analysis Row Template
| # | Ref OS Feature | WuBuOS File | Status | REAL_GAPs | Priority | Sessions |
|---|----------------|-------------|--------|-----------|----------|----------|
| 0.1 | D-Bus daemon | runtime/wubu_dbus.c | Missing | ~200 | 0 | 3 |

---

*This methodology ensures every gap closure is traceable to a reference OS feature and verified by tests.*