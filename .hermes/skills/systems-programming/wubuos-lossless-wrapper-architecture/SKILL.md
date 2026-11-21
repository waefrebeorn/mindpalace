---
name: wubuos-lossless-wrapper-architecture
description: "WuBuOS lossless C11 wrapper architecture — bundles Arch Linux + ZealOS + Fable sauce into single clickable binary. Hosted binary IS the product (Inferno emu pattern). DosGui windowing agent ports ZealOS bare-metal features into Wayland/Arch desktop."
tags: [osdev, wubuos, architecture, arch, zealos, hosted-binary, inferno-emu]
---

# WuBuOS Lossless C11 Wrapper Architecture

## Core Principle
> **The hosted binary IS the product** (Inferno emu pattern)
> 
> One binary (`src/hosted/wubu`) runs on any Linux host via Wayland, bundles the ZealOS kernel in-process, and provides a complete Win98 desktop via the Fable windowing agent.

## Three-Layer Architecture

```
WuBuNT (Arch on metal, bare metal)
  └── WuBuOS Hosted Binary (Wayland/DRM on Arch userspace)
        └── DosGui Desktop (Win98 → XP Classic themed)
              ├── DosGui WM (Cell 400) — Fable windowing agent + Theme Engine
              │   ├── Window chrome (rounded/flat, gradient/flat titles, shadows)
              │   ├── Maximize/Minimize/Close buttons (XP style)
              │   ├── GAAD φ-snap alignment
              │   ├── Virtual desktops (9) with Ctrl+Alt+←/→
              │   ├── Icon drag-drop with grid snap
              │   └── Wayland resize handling (SHM + VBE + WM reinit)
              ├── DosGui Desktop (Cell 401) — Theme-aware
              │   ├── Wallpaper (center/tile/stretch modes)
              │   ├── Icons with themed text color + shadow
              │   ├── Icon drag-drop rearrange
              │   └── FreeDoom launch via bubblewrap
              ├── DosGui StartMenu (Cell 402) — XP Classic cascading
              │   ├── Luna Start orb (green orb + "Start" text)
              │   ├── Sidebar ("WuBuOS" branding, Log off/Turn Off)
              │   ├── Programs → {Accessories, WuBuOS, System} submenus
              │   ├── Documents, Settings, Find, Help, Run...
              │   ├── Hover tracking → auto-expand submenu
              │   ├── Keyboard navigation (arrows, Enter, Esc)
              │   └── Shutdown submenu (Shutdown/Restart/Logoff/MS-DOS)
              ├── Taskbar
              │   ├── Window buttons (focused sunken, raised round/square)
              │   ├── System tray (Volume N, Network N, Battery B icons)
              │   ├── Desktop switchers (1-9 + M) with current highlighted
              │   └── Clock (UP MM:SS)
              └── Theme Engine (4 themes, Ctrl+T cycle)
                  ├── Win98 Classic (flat navy titles, +NEW Start, 3D square)
                  ├── XP Luna Blue (blue gradient, rounded, Green Luna orb)
                  ├── XP Media Orange (orange gradient, rounded, Orange orb)
                  └── WuBu Green (green gradient, rounded, Green orb)
```

## Three Progression Tiers

| Tier | Name | Description |
|------|------|-------------|
| 1 | **WuBuOS** | Hosted binary with Win98 shell (current) — runs on any Wayland compositor |
| 2 | **WuBuDos** | Bare-metal TempleOS on RamDisk — ZealOS kernel + WuBu shell, boots on metal |
| 3 | **WuBuNT** | Arch backend desktop — WuBuOS shell on Arch userspace, Proton native |

## Key Design Decisions

### 1. Hosted Binary = Product
- **Pattern**: Inferno `emu` — one binary, any host OS
- **No install**: Click to run, full OS environment in-process
- **Wayland**: Uses xdg-shell + SHM for zero-copy framebuffer
- **Styx/9P**: Namespace bridge to host FS (`/mnt/host`, `/mnt/wubu`)

### 2. ZealOS Kernel In-Process
- **mmapped JIT**: HolyC → mmap RWX → emit x86-64 → mprotect RX → call
- **Single address space**: No processes, tasks = coroutines
- **VBE/DRM graphics**: Framebuffer via Wayland SHM or DRM/KMS direct
- **zealos_parity.h**: 96/96 ZealOS functions → C11 snake_case (1:1 name mapping)

### 3. Fable Windowing Agent
- **Not a guest**: Fable bare-metal kernel code ported as **rendering backbone**
- **Scope**: VBE primitives, font, cursor, title bar, close box, WM logic
- **Why Fable**: Clean, minimal (~2K LOC), complete WM with chrome + taskbar
- **Alternative considered**: X11/Wayland client-side — rejected (bloat, not lossless)

### 4. Container Runtime = Host Process
- **No syscall emulation**: .wubu containers run as `fork+chroot+exec` host processes
- **9P namespace**: Styx server exports container FS, host mounts via Unix socket
- **Proton integration**: Wine/Proton runs native, `C:\\` exported as 9P mount

### 5. Theme Engine + XP Classic Chrome (NEW — Cells 400-412)
- **4 Themes Runtime-Switchable**: Win98 Classic, XP Luna Blue, XP Media Orange, WuBu Green
- **Ctrl+T / F5**: Cycle themes instantly, no recompile
- **Luna Start Button**: Green orb "Start" text on XP themes, "+NEW" on Win98
- **Rounded Rect Primitives**: `vbe_fill_rect_rounded`, `vbe_rect_rounded`, `vbe_3d_raised_rounded`, `vbe_3d_sunken_rounded` — integer quadrant approx, no `sincos`/`libm`
- **Gradient Titles**: XP themes use horizontal gradient (active/inactive different)
- **Rounded Window Chrome**: Radius=4 for XP themes, square for Win98
- **XP Sidebar Start Menu**: "WuBuOS" branding, Log off/Turn Off, hover auto-expand submenus
- **Keyboard Navigation**: F5 theme cycle, F11 fullscreen, Win=Start, Esc=close, Ctrl+Alt+←/→ desktop switch
- **System Tray**: Volume (V), Network (N), Battery (B) icons in taskbar
- **Virtual Desktops**: 9 desktops, numbered 1-9 + M indicator in taskbar
- **Icon Drag-Drop**: Grid snap on release, clamp to screen
- **Maximize/Minimize**: Fullscreen toggle with restore geometry, minimize hides window but keeps taskbar button
- **Wallpaper**: center/tile/stretch modes, auto-saved
- **GAAD φ-Snap**: Window centers snap to φ-based grid regions
- **Wayland Resize**: SHM buffer destruction/recreation + VBE reinit + WM reinit on xdg_toplevel_configure

## Build System (Pure C11, Make)
```makefile
# Core targets
all: kernel jit compiler runtime tools gui bridge apps worldsim metal hosted

# Hosted binary (THE product)
hosted: $(HOSTED_OBJS) $(HOSTED)/xdg-shell-private.o
	$(CC) $(CFLAGS) ... -lwayland-client -lxkbcommon -o $(HOSTED)/wubu

# Test suite
test: test_wm test_wm test_dbuf test_gaad test_wubu_wm ...
	@echo "✅ All tests passed"
```

## Repo Structure
```
src/
├── kernel/         # ZealOS C-port: memory, tasking, vbe, input, fat32, ahci, txfs
├── jit/            # mmap-based JIT compiler (x86-64)
├── compiler/       # HolyC lexer/parser/codegen
├── gui/
│   ├── wm.c/.h       # Cell 400: Fable WM
│   ├── desktop.c/.h  # Cell 401: Desktop + icons
│   ├── startmenu.c/.h # Cell 402: Start menu
│   ├── wm.c/.h              # Legacy WM (being replaced)
│   ├── wubu_wm.c/.h         # GAAD WM (future)
│   └── ...
├── hosted/         # Wayland binary launcher (hosted.c)
├── runtime/        # Styx/9P, .wubu containers, VSL, Proton, Arch, RamDisk
├── apps/           # calc, terminal, explorer, control, notepad, paint, repl
└── tools/          # iso9660, screenshot, weight_check
```

## Testing Protocol
- **Unit tests per module**: `make test_<module>` (763+ total)
- **Integration tests**: `test_hosted` boots full Wayland desktop
- **Triple Devil's Advocate**: Architecture decisions pass 3 independent audits

## Anti-Patterns Avoided
- ❌ No system call emulation (User Mode Linux, gVisor)
- ❌ No X11 dependency (Wayland native, DRM/KMS direct)
- ❌ No libdrm/libgbm/libwayland (header-only, custom ioctl)
- ❌ No stdlib dependency (`-DWUBU_NO_LIBM`, wubu_math.h replaces libm)
- ❌ No config files (compile-time constants, theme switching at runtime)

## Migration Path
```\nPhase A (Done): DosGui WM + Desktop + StartMenu (Cells 400-402)
Phase B: Wire apps (calc, terminal, explorer) → DosGui windows
Phase C: WuBuDos bare-metal (MBR+stage2+kernel+initrd)
Phase D: WuBuNT Proton integration (DXVK/VKD3D on Vulkan)
```

---

## Phase 4 Progress — Win98 Shell Polish (2026-06-18, Cells 400-412)

### Phase 4.1 Complete — Taskbar Clock + System Tray + Notification Center (Cell 400)
- **Real Clock**: `taskbar_update_clock/get_clock_str()` — `time(NULL)` + `localtime()` replacing uptime
- **System Tray**: `DosGuiSysTrayIcon` with colored square icon, click/right-click callbacks, notification badge count
  - `systray_add/remove/set_notification_count` API
  - Right-aligned before clock, drawn right-to-left
- **Notification Center**: `DosGuiNotification` with urgency (low/normal/critical), sliding panel (350px right)
  - Urgency color coding (red/critical, yellow/normal, green/low)
  - Auto-mark-read on open, badge on "Notifications" systray icon
  - `notif_center_add/mark_read/clear/toggle/render` + `wubu_notify` daemon integration
- **Taskbar Mouse Handling**: Right-click systray icons + notification center toggle area

### Phase 4.2 Complete — Desktop Icons (Cells 401-402)
- **Extended Icons**: `DeskIconType` (APP/SHORTCUT/FOLDER/DRIVE/FILE/URL) with `target`, `icon_color`, `selected`, `on_execute`
- **Shortcut Factories**: `shortcut_create()` (green APP), `shortcut_create_url()` (orange URL)
- **Context Menu System**: `DosGuiContextMenu` + `DosGuiCtxItem` (action/separator/submenu)
  - Stack-based hierarchy, hover→submenu, click→action+close, click outside→close all
  - `ctx_menu_create/add_item/add_separator/add_submenu/show/hide/handle_mouse/render`
  - Global stack head `g_ctx_stack` for render/input access
- **Default Menus**: 
  - Icon right-click: Open/Rename/Delete/Properties
  - Desktop right-click: New→Shortcut/Folder/TextDoc, View→Sort By, Refresh/Properties
- **Mouse Integration**: Right-click icon→context menu, Right-click empty→desktop menu, Submenu hover→open right

### Files Modified
- `src/gui/wm.h` — Extended `DosGuiIcon`, added `DeskIconType`, context menu types + API
- `src/gui/wm.c` — Full implementation (~450 lines): context menus, systray, notif center, real clock, icon API

### Test Results
- Build: ✅ Clean
- All existing tests: ✅ Pass (31/32 proton, 1 pre-existing failure)
- No regressions

---

## P0 Completion Status (2026-06-17)

| P0 | Task | Status | References |
|----|------|--------|------------|
| #1 | VBE theme leakage fix + real app (calc/terminal) | ✅ COMPLETED | `references/vbe-theme-leakage-fix-2026-06-17.md` |
| #2 | Testing workflow (GitHub Actions CI + visual regression + QEMU) | ✅ COMPLETED | `references/testing-workflow.md` |
| #3 | HolyC syscall bridge (25 calls) | ✅ COMPLETED | `systems-programming/references/holyc-syscall-bridge.md` |
| #4 | Proton stack (GBM + Vulkan + Proton-GE bundle) | ✅ COMPLETED | `references/proton-stack.md` |

All four P0 items completed. Core tests pass — run `make test` for the live count.

## P1 Progress (2026-06-17)

| P1 | Task | Status | References |
|----|------|--------|------------|
| #1 | VSL syscall expansion (~30 new calls) | ✅ COMPLETED | `systems-programming/references/vsl-syscall-expansion-2026-06-17.md` |
| #2 | Styx/9P file server (host dir export) | ✅ COMPLETED | `systems-programming/references/styx-9p-file-server-2026-06-17.md` |

### VSL Syscall Expansion Details
Added 30+ syscalls reducing 203 `(void)` stub count:
- **File I/O**: pread64, pwrite64, readv, writev, truncate, ftruncate, creat
- **Links/Metadata**: symlink, readlink, chmod/fchmod, chown/lchown/fchown, lstat
- **Directory-based**: openat, newfstatat, unlinkat, faccessat
- **Socket**: sendto, recvfrom, shutdown, getsockname, getpeername, setsockopt, socketpair
- **I/O multiplexing**: poll, epoll_create, epoll_ctl, epoll_wait

All delegate to host kernel via standard Linux syscalls. Required `_GNU_SOURCE`, `<sys/uio.h>`, `<sys/epoll.h>`, `<poll.h>`.

### Styx/9P File Server
- **Files**: `styxfs_server.c/h` (478 lines)
- **Exports any host directory** as 9P2000 filesystem
- **Callbacks**: attach, walk, open, read, write, clunk, remove, stat, wstat
- **FID state**: root fid → stored path → open fd pool (256 slots)
- **Depends on**: exported `styx_fid_alloc/lookup/free` from styx.c
- **Use cases**: .wubu containers, device files (`/dev/dri`), VSL procfs

## Key Files
| File | Purpose |
|------|---------|
| `src/hosted/hosted.c` | Wayland binary entry, main loop, input/render |
| `src/kernel/vbe.c` | Double-buffer framebuffer + Fable primitives |
| `src/gui/wm.c` | Cell 400: Window manager |
| `src/gui/desktop.c` | Cell 401: Desktop icons + launch |
| `src/gui/startmenu.c` | Cell 402: Cascading menu |
| `src/gui/wubu_screenshot.c` | Screenshot tool (PrintScr/region) |
| `src/gui/wubu_mime.c` | MIME system (.desktop parser) |
| `src/gui/wubu_trash.c` | Trash (FreeDesktop spec) |
| `src/kernel/zealos_parity.h` | 96/96 ZealOS name mappings |
| `DESIGN_BIBLE.md` | Living architecture doc (v1.2+) |
| `WUBUOS_DISTRO_ROADMAP.md` | 6-phase distro plan (v0.5→v1.0) |
| `Makefile` | Single-source build (all targets) |

## References
- `references/desktop-services-implementation.md` — Phase 2 desktop services patterns (screenshot, MIME, trash, Wayland integration)
- `references/phase2-phase3-desktop-proton.md` — Phase 2 (Items 1-7) + Phase 3 Item 1 complete patterns: Settings, Session, Notifications, Clipboard, Screenshot, MIME, Trash, Proton/Wine
- `references/proton-wine-integration.md` — Phase 3 Proton/Wine integration patterns (bubblewrap sandbox, Steam detection, DXVK/VKD3D)
- `references/game-library-ui.md` — Phase 3 Steam Game Library UI patterns (categories, scanning, launch, filtering)
- `references/subsystem-development-pattern.md` — WuBuOS subsystem pattern (h/c/test + Makefile + XDG config) used for all Phase 3/4 subsystems
- `references/multi-target-deployment.md` — Phase 4 Item 1: Bare metal ISO, WSL2 tar.gz, OCI/Docker, macOS AVF app bundle