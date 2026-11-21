# WuBuOS Lossless C11 Wrapper Architecture — 2026-06-16 Session Artifacts

## Architecture Realized This Session

The "lossless C11 wrapper bundling Arch Linux + ZealOS + Fable sauce" pattern was fully implemented in code for the first time.

### Three Tiers Status

| Tier | Name | Status | Description |
|------|------|--------|-------------|
| 1 | **WuBuOS** | ✅ Complete | Hosted binary with Win98 shell — runs on any Wayland compositor |
| 2 | **WuBuDos** | 🔄 Pending | Bare-metal TempleOS on RamDisk — ZealOS kernel + WuBu shell |
| 3 | **WuBuNT** | 📋 Future | Arch backend desktop — WuBuOS shell + Proton native |

### In-Process ZealOS Kernel

- **mmapped JIT**: HolyC → mmap RWX → emit x86-64 → mprotect RX → call
- **64/96 ZealOS functions** mapped via `zealos_parity.h` (1:1 C11 snake_case)
- **Single address space**: No processes, tasks = coroutines
- **VBE/DRM graphics**: Framebuffer via Wayland SHM or DRM/KMS direct

### Fable Windowing Agent Integration

Fable bare-metal kernel code ported as **rendering backbone** inside hosted WuBuOS:

```
src/kernel/vbe.c     → Double-buffer + Fable primitives (font, gradient, circle, shade, clip, cursor, title_bar, close_box)
src/gui/wm.c  → Cell 400: WM (z-order, drag, focus, taskbar, desktop icons)
src/gui/desktop.c → Cell 401: Desktop with 8 launchable icons
src/gui/startmenu.c → Cell 402: Cascading Start → Programs/{Accessories,WuBuOS,System}
```

### Styx/9P Namespace Bridge

- Plan 9 9P2000 over Unix sockets
- .wubu containers → host `fork+chroot+exec` (no syscall emulation)
- Proton runs native, `C:\` exported as 9P mount

## Build & Test This Session

```bash
# Full build
make all
# → "✅ WuBuOS built" (zero errors)

# DosGui WM tests (16/16)
make test_wm

# Legacy tests all pass
make test_wm test_dbuf test_gaad test_wubu_wm
```

## Anti-Patterns Avoided (This Session)

- ❌ No system call emulation (User Mode Linux, gVisor)
- ❌ No X11 dependency (Wayland native, DRM/KMS direct)
- ❌ No libdrm/libgbm/libwayland (header-only, custom ioctl)
- ❌ No stdlib dependency (`-DWUBU_NO_LIBM`, wubu_math.h replaces libm)
- ❌ No config files (compile-time constants, theme switching at runtime)

## Key Files That Embody This Architecture

| File | Role |
|------|------|
| `src/hosted/hosted.c` | Wayland binary entry, main loop, input/render pipeline |
| `src/kernel/vbe.c` | Double-buffer framebuffer + Fable primitives |
| `src/gui/wm.c` | Cell 400: Window manager |
| `src/gui/desktop.c` | Cell 401: Desktop icons + launch |
| `src/gui/startmenu.c` | Cell 402: Cascading menu |
| `src/kernel/zealos_parity.h` | 96/96 ZealOS name mappings |
| `DESIGN_BIBLE.md` | Living architecture doc (v1.2) |
| `Makefile` | Single-source build (all targets) |

## Migration Path (Current → Future)

```
Phase A (Done): DosGui WM + Desktop + StartMenu (Cells 400-402)
Phase B: Wire apps (calc, terminal, explorer) → DosGui windows
Phase C: WuBuDos bare-metal (MBR+stage2+kernel+initrd)
Phase D: WuBuNT Proton integration (DXVK/VKD3D on Vulkan)
```

## Mind Palace Links (Created This Session)

- `slate.md` — Active context with next actions
- `wubuos-architecture.md` — Cross-reference entry
- Skills: `fable-windowing-agent-port`, `wubuos-lossless-wrapper-architecture`