# Distro Roadmap & GUI Glitches — Session 2026-06-16

## Context
User asked to:
1. Fix Win98 GUI → XP Classic themed with 4 themes (done in prior session)
2. Fix remaining GUI glitches
3. Build GNOME-parity desktop ecosystem
4. Become "Ubuntu through our own paradigm" — full distro with Proton + ZealOS compatibility

## Current Architecture (v0.5)

### Three Tiers
| Tier | Name | Description |
|------|------|-------------|
| 1 | **WuBuOS** | Hosted binary with XP Classic shell — runs on any Wayland compositor |
| 2 | **WuBuDos** | Bare-metal TempleOS on RamDisk — ZealOS kernel + WuBu shell, boots on metal |
| 3 | **WuBuNT** | Arch backend desktop — WuBuOS shell on Arch userspace, Proton native |

### Hosted Binary = Product (Inferno emu pattern)
- Single binary: `src/hosted/wubu` (720KB)
- Wayland xdg-shell + SHM double-buffer
- ZealOS kernel in-process (mmapped JIT, single address space)
- Styx/9P namespace bridge to host FS

### GUI Stack (Cells 400-412)
| Component | File | Status |
|-----------|------|--------|
| Theme Engine | `src/gui/wubu_theme.c` | ✅ 4 themes, Ctrl+T cycle |
| Window Manager | `src/gui/wm.c` | ✅ Rounded/flat, gradient/flat, shadows, GAAD φ-snap |
| Desktop | `src/gui/desktop.c` | ✅ Icons, drag-drop, wallpaper, FreeDoom launch |
| Start Menu | `src/gui/startmenu.c` | ✅ XP sidebar, Luna orb, cascading submenus, keyboard nav |
| Taskbar | In `wm.c` | ✅ Window buttons, system tray, desktops, clock |

### Theme Variants (4)
| Theme | Title Bar | Buttons | Start Button | Colors |
|-------|-----------|---------|--------------|--------|
| Win98 Classic | Flat navy | Square 3D | "+ NEW" green | Teal desktop, silver face |
| XP Luna Blue | Gradient blue | Rounded | Green Luna orb | Blue taskbar, Bliss blue |
| XP Media Orange | Gradient orange | Rounded | Orange orb | Near-black desktop, orange accent |
| WuBu Green | Gradient green | Rounded | Green orb | Dark green desktop, WuBu branding |

## GUI Glitches (Phase 1 — Must Fix)

| # | Bug | File:Line | Severity | Fix |
|---|-----|-----------|----------|-----|
| 1 | **Theme leakage in VBE** | `vbe.c:411,425` | **Critical** | `vbe_3d_raised_rounded` / `vbe_3d_sunken_rounded` call `wubu_theme_colors()`. VBE must be theme-agnostic — move to GUI layer or pass colors as params. |
| 2 | **Hardcoded icon color** | `wm.c:752` | Medium | `vbe_fill_rect(..., 0x008080)` → use `tc()->icon_bg` or `tc()->btn_face` |
| 3 | **Shutdown handler missing** | `startmenu.c` | High | Type 3 (shutdown) item has no callback. Wire to `hosted_shutdown()` |
| 4 | **Theme cycle no re-render** | `wm.c:412` | High | `wubu_theme_cycle()` called but open windows/taskbar don't refresh until next frame |
| 5 | **Maximize ignores dynamic taskbar** | `wm.c:426` | Medium | Uses hardcoded `task_h` instead of `taskbar_height_dynamic()` |
| 6 | **Drag state not reset on resize** | `hosted.c:233` | Low | `wm_init()` reinit but `g_dwm.drag_id` not cleared |

## Test Failure
```
test_bridge: undefined reference to wubu_theme_colors
```
**Fix**: Add `-Isrc/gui $(GUI)/wubu_theme.o` to test_bridge link line.

## Distro Roadmap (WUBUOS_DISTRO_ROADMAP.md — 6 Phases)

### Phase 1: GUI Fixes + Polish (Weeks 1-2)
- Fix 6 glitches above
- Smooth animations, tooltips, context menus, keyboard nav, window snapping

### Phase 2: GNOME-Standard Desktop Services (Weeks 3-6)
| Service | Purpose | New File |
|---------|---------|----------|
| Settings Daemon | Theme, fonts, keyboard, mouse, display | `src/shell/wubu_settings.c` |
| Session Manager | Auto-start, shutdown, logout, restart | `src/shell/wubu_session.c` |
| Notification Daemon | Desktop notifications (libnotify compat) | `src/gui/wubu_notify.c` |
| Clipboard Manager | Wayland primary + clipboard selection | `src/hosted/wubu_clipboard.c` |
| Screenshot Tool | PrintScr, Alt+PrintScr, region select | Extend `src/tools/screenshot.c` |
| File Associations | MIME → app mapping, .desktop files | `src/runtime/wubu_mime.c` |
| Trash/Recycle Bin | `.local/share/Trash` implementation | `src/apps/wubu_trash.c` |

### Phase 3: Proton/Wine Integration (Weeks 7-10)
- Proton prefix manager (`wubu_proton.c`)
- Steam integration (`wubu_steam.c`)
- DXVK/VKD3D detection (`wubu_vulkan.c`)
- Game .desktop file generation
- Controller support (SDL2 GameControllerDB)
- Anti-cheat documentation

### Phase 4: TempleOS/ZealOS Compatibility (Weeks 11-14)
- HolyC stdlib port: core.hc, graphics.hc, filesystem.hc, network.hc, audio.hc, gui.hc, kernel.hc
- ZealOS app ports: Browser, Compiler, Games, Tools
- Self-hosting HolyC compiler

### Phase 5: Multi-Target Deployment (Weeks 15-18)
| Target | Kernel | GUI | Container | Boot |
|--------|--------|-----|-----------|------|
| Bare metal (x86_64) | ZealOS native | DRM/KMS | bubblewrap | Limine |
| WSL2 | In-process | Wayland | bubblewrap | `wubu` binary |
| Container | In-process | Headless/Xvfb | Nested bubblewrap | `FROM scratch` |
| QEMU/KVM | ZealOS native | virtio-gpu | bubblewrap | ISO |
| macOS (AVF) | In-process | Metal/Cocoa | N/A | `.app` bundle |

### Phase 6: Package Manager + App Store (Weeks 19-22)
- `.wubu` format: manifest.yaml + squashfs rootfs + runtime + metadata
- Git-based repository (like AUR)
- bubblewrap + seccomp sandboxing
- Delta updates via rsync/zstd
- Default repos: core, extra, holyc, steam, community

## Build System
```makefile
# Pure C11, single Makefile
all: kernel jit compiler runtime tools gui bridge apps worldsim metal audio shell bear hosted
hosted: -lwayland-client -lxkbcommon -lm  # Single binary product
```

## Key Anti-Patterns
- ❌ No syscall emulation (gVisor, UML)
- ❌ No X11 dependency (Wayland native)
- ❌ No libdrm/libgbm (custom ioctl)
- ❌ No stdlib dependency (`-DWUBU_NO_LIBM`, wubu_math.h)
- ❌ No config files (compile-time constants, runtime theme switching)

## Next Steps
1. Fix VBE theme leakage (architectural — VBE must not know theme)
2. Wire shutdown handler
3. Add theme cycle re-render trigger
4. Fix maximize math
5. Update test_bridge Makefile
6. Begin Phase 2: Settings daemon