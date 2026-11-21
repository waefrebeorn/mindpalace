# WuBuOS Parity Audit: SteamOS / Ubuntu / TempleOS / Arch

**Date**: 2026-06-28  
**Method**: Triple DA cross-reference against reference implementations

---

## SteamOS Parity (Valve Steam Deck / SteamOS 3.x)

| SteamOS Component | Implementation | WuBuOS Status | Gap | Effort |
|-------------------|----------------|---------------|-----|--------|
| **Steam Client** | CEF-based UI, store, library, friends, chat | Missing | 100% | ~5000 LOC |
| **Steam Input** | Controller configs, action sets, haptics, gyro | Missing | 100% | ~2000 LOC |
| **Steam Networking** | Relay, P2P, NAT traversal, certificates | Missing | 100% | ~3000 LOC |
| **Proton** | Wine + DXVK + VKD3D + D3DMetal + patches | Stub (7 gaps in wubu_proton.c) | 95% | ~5000 LOC |
| **gamescope** | Wayland compositor, VRR, HDR, FSR, nested | Stub (4 gaps in wubu_proton2.c) | 90% | ~3000 LOC |
| **Pressure Vessel** | Container runtime, seccomp, namespaces, bind mounts | Partial (wubu_ct_isolate.c) | 60% | ~2000 LOC |
| **Shader Pre-cache** | fossilize, dxvk-cache, background compile | Missing | 100% | ~1500 LOC |
| **ProtonDB Integration** | Compat reports, user ratings, auto-config | Missing | 100% | ~1000 LOC |
| **Steam Cloud** | Remote storage sync, conflict resolution | Missing | 100% | ~1000 LOC |
| **Steam Deck UI** | Game mode, desktop mode, quick access, notifications | Missing | 100% | ~3000 LOC |

**Key Insight**: SteamOS is a **product integration layer** on top of Arch Linux. WuBuOS has the Arch base but none of the Steam integration.

---

## Ubuntu / Arch Parity (Desktop Linux Standard)

| Component | Ubuntu/Arch | WuBuOS | Gap | Effort |
|-----------|-------------|--------|-----|--------|
| **systemd** | Init, services, sockets, timers, units, journald | Missing | 100% | ~5000 LOC |
| **apt / pacman** | Repos, deps, hooks, transactions, signing | Stub (wubu_pkgmgr.c) | 80% | ~3000 LOC |
| **NetworkManager** | WiFi, Ethernet, VPN, DHCP, DNS, WWAN | Stub (wubu_network.c) | 85% | ~3000 LOC |
| **Polkit** | Authorization, privilege escalation, rules | Missing | 100% | ~1500 LOC |
| **D-Bus** | System/session bus, activation, introspection | Missing | 100% | ~2000 LOC |
| **PipeWire** | Audio graph, Bluetooth, devices, sessions | Missing | 100% | ~3000 LOC |
| **CUPS** | Printing, IPP, drivers, PPD | Missing | 100% | ~1000 LOC |
| **AppArmor / SELinux** | MAC, profiles, confinement | Missing | 100% | ~2000 LOC |
| **systemd-homed** | User management, portable homes | Missing | 100% | ~1000 LOC |
| **mkinitcpio / dracut** | Initramfs generation, modules, hooks | Partial (create-initramfs.sh) | 70% | ~1000 LOC |
| **GRUB / systemd-boot** | Bootloader, secure boot, TPM | Partial (limine.conf) | 60% | ~1000 LOC |
| **Flatpak** | Sandbox, portals, permissions, runtimes | Stub (wubu_bottles.c) | 70% | ~2000 LOC |

**Key Insight**: WuBuOS replaces the **desktop shell layer** (GNOME/KDE → Win98 WM) but lacks the **system integration layer** (systemd, D-Bus, PipeWire, etc.).

---

## TempleOS / ZealOS Parity (The Soul)

| TempleOS Feature | TempleOS | WuBuOS | Gap | Effort |
|------------------|----------|--------|-----|--------|
| **HolyC JIT** | AOT + JIT, whole-program optimization | Partial (minic + JIT backends) | 70% | ~3000 LOC |
| **Doc / DolDoc** | Hyperlinked docs, graphics, songs, live code | Missing | 100% | ~2000 LOC |
| **Compiler-as-library** | `Compile()` from string, JIT from REPL | Partial (jit_minic.c) | 60% | ~2000 LOC |
| **Identity-mapped memory** | No paging in user mode, single address space | Different (Ring-0) | Different (VSL) | N/A | N/A |
| **RedSea FS** | File system = database, no paths, metadata | Different (Styx 9P) | N/A | N/A |
| **VGA/VESA direct** | Raw hardware, no GPU drivers | DRM/KMS layer | Different | N/A |
| **PC Speaker + PCM** | Raw audio, no mixer/daemon | Missing | 100% | ~1000 LOC |
| **Air-gapped design** | No network stack by philosophy | Different threat model | N/A | N/A |
| **God Word / Oracle** | Divine intellect, randomness as prayer | Missing | Philosophical | N/A |

**Key Insight**: TempleOS is a **philosophical OS** — identity-mapped, single-address-space, compiler-as-shell. WuBuOS adopts the **HolyC compiler** and **VBE paradigm** but runs on Linux with processes, paging, and network.

---

## DA Consensus: What "Rewriting from Scratch in C" Means for Parity

| Parity Target | What We Must Build (Not Port) |
|---------------|-------------------------------|
| **SteamOS** | Proton wrapper (not Wine), gamescope clone (not wlroots), Pressure Vessel clone (not bubblewrap) |
| **Ubuntu/Arch** | Package manager (not apt), init system (not systemd), audio server (not PipeWire) |
| **TempleOS** | HolyC JIT (not interpreter), Doc format (not markdown), RedSea-alike (not ext4) |

The 412 REAL_GAPs in BATTLESHIP.md v14 are the **WuBuOS-native implementations** of these parity targets — not ports, not bindings, not wrappers.