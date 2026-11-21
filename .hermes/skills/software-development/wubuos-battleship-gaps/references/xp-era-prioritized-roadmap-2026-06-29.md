# XP-Era Classic with Modern Polish — Prioritized Roadmap (2026-06-29)

## Design Philosophy
**Target**: Windows XP (Luna/Classic) visual metaphor + **modern polish** (vsync, smooth animations, GPU compositing, search, no tearing)
**Not Target**: GNOME 46 feature parity, GTK4 toolkit, full Wayland server, D-Bus/systemd stack, accessibility suite

---

## PRIORITY 1: MUST-HAVES (Shippable MVP — 12-15 weeks)

| # | Feature | Why | Effort | Files |
|---|---------|-----|--------|-------|
| **1** | **Basic Compositor** | Vsync, no tearing, double-buffer, damage tracking — foundation for everything | 2-3 wks | `wubu_compositor.c` |
| **2** | **GPU Render Path** | OpenGL/Vulkan via VSL drivers — frees CPU, enables effects | 2 wks | `wubu_compositor_gl.c`, VSL GPU drivers |
| **3** | **Window Animations** | Minimize/maximize "genie", fade in/out, workspace slide — XP had none, this is "modern polish" | 1-2 wks | `wm.c` + compositor |
| **4** | **Snap-to-Edge (Aero Snap)** | Win7 feature, expected in modern polish. Drag to edge = half-screen tile | 1 wk | `wm.c` |
| **5** | **Taskbar Thumbnails** | Hover taskbar button → live window preview (DWM style) | 1-2 wks | `wm.c` + compositor |
| **6** | **Live Window Previews** | Alt+Tab shows actual content, not just icons | 1 wk | `wm.c` + compositor |
| **7** | **Search (Start Menu)** | Type to launch — XP had none, Vista/7 added. Essential modern polish | 1 wk | `startmenu.c` |
| **8** | **Smooth Scrolling** | Mouse wheel + touchpad momentum — basic libinput | 1 wk | Input layer + compositor |
| **9** | **Notification Center** | Win10 Action Center style — history + actions | 1 wk | `wubu_notify.c` expansion |
| **10** | **Volume/Network/Battery Flyouts** | Click tray icon → slider/menu (not separate dialogs) | 1 wk | `wm.c` systray |

**Total: ~12-15 weeks for shippable "XP + polish"**

---

## PRIORITY 2: NICE-TO-HAVES (Post-MVP)

| # | Feature | Why | Effort |
|---|---------|-----|--------|
| 11 | **Virtual Desktop Animations** | Ctrl+Win+Left/Right slides workspace (Win10) | 1 wk |
| 12 | **Window Peek (Aero Peek)** | Hover "Show Desktop" → glass preview | 1 wk |
| 13 | **Jump Lists** | Right-click taskbar → recent tasks | 1 wk |
| 14 | **Modern File Dialogs** | Places sidebar, search, thumbnails | 2 wks |
| 15 | **Dark Mode** | System-wide theme toggle (Win10+) | 1 wk |
| 16 | **High DPI / Fractional Scaling** | 4K monitors, 125%/150% | 2 wks |
| 17 | **Touch Gestures** | 3-finger swipe workspace, pinch zoom | 2 wks |
| 18 | **Clipboard History** | Win+V history panel | 1 wk |

---

## EXPLICITLY DEFERRED (Not XP-Era)

| Feature | Reason |
|---------|--------|
| Full Wayland Server | XP didn't have it. We're a Wayland *client* in hosted mode |
| GTK4 Toolkit | XP used Win32 common controls. We keep immediate-mode + lightweight widgets |
| D-Bus / systemd / UPower / NetworkManager / Polkit | XP had none. We use Styx/9P + simple daemons |
| Accessibility Suite (AT-SPI2, screen reader, magnifier) | XP had basic. Defer to post-MVP |
| Extensions Framework (JS plugins) | XP had none. HolyC scripting later |
| Activities Overview (GNOME-style) | XP had Start Menu. We enhance that, not replace |
| XDG Portals / Flatpak | Container isolation via VSL/OCI instead |
| Multi-GPU / HDR / Color Management | Overkill for XP-era target |
| IBus / Complex Input Methods | Basic Unicode + dead keys sufficient |

---

## ARCHITECTURE FOR XP + POLISH

```
┌─────────────────────────────────────────────────────────────┐
│                      USER SPACE                              │
├─────────────────────────────────────────────────────────────┤
│  shell.c          # Main shell loop (NEW - unifies)  │
│  ├─ wm.c          # Window mgmt + animations + snap  │
│  ├─ taskbar.c     # Taskbar + thumbnails + flyouts   │
│  ├─ startmenu.c   # Start menu + search + jump lists │
│  ├─ desktop.c     # Icons + wallpaper + widgets      │
│  ├─ notify.c      # Notification center + history    │
│  └─ dosgui/compositor.c   # Compositor client API            │
├─────────────────────────────────────────────────────────────┤
│  wubu_compositor.c       # COMPOSITOR (NEW - core)          │
│  ├─ Damage tracking (dirty rects)                          │
│  ├─ Double/triple buffering + vsync                        │
│  ├─ GPU path (OpenGL/Vulkan via VSL)                       │
│  ├─ Window actor / surface management                      │
│  └─ Effects: shadows, blur, transitions                    │
├─────────────────────────────────────────────────────────────┤
│  VSL (wubu_vsl.c)       # Syscalls + GPU drivers            │
│  ├─ DRM/KMS + GBM (bare metal)                             │
│  ├─ Wayland client (hosted)                                │
│  └─ Vulkan/OpenGL loader                                   │
├─────────────────────────────────────────────────────────────┤
│  ZealOS Kernel                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## FILES TO CREATE/MODIFY

### New Files
| File | Purpose |
|------|---------|
| `src/gui/wubu_compositor.c/.h` | Core compositor (damage, vsync, buffers) |
| `src/gui/wubu_compositor_gl.c` | OpenGL/Vulkan render backend |
| `src/gui/shell.c/.h` | Main shell loop (replaces ad-hoc mains) |
| `src/gui/taskbar.c/.h` | Taskbar split from wm.c (thumbnails, flyouts) |
| `src/gui/effects.c/.h` | Animation/effects engine (genie, fade, slide) |

### Major Modifications
| File | Changes |
|------|---------|
| `wm.c` | Extract rendering → compositor; add snap, animations, Alt+Tab preview |
| `startmenu.c` | Add search box, jump lists, pinned apps |
| `wubu_notify.c` | Notification center + history + actions |
| `wubu_theme.c` | Add dark mode, animation timing curves |
| `wubu_vsl.c` | Add DRM/KMS/GBM syscalls for bare-metal compositor |

---

## IMPLEMENTATION ORDER (Dependencies)

```
Week 1-2:  wubu_compositor.c (software, double-buffer, damage, vsync)
Week 2-3:  wubu_compositor_gl.c (VSL GPU → Vulkan/OpenGL)
Week 3-4:  wm.c → split rendering; integrate compositor
Week 4-5:  wm.c: snap-to-edge, window animations
Week 5-6:  taskbar.c (extract from wm.c) + thumbnails
Week 6-7:  startmenu.c: search, jump lists
Week 7-8:  wubu_notify.c: notification center
Week 8-9:  shell.c: unify main loop
Week 9-10: Polish: smooth scroll, dark mode, Aero peek
Week 10-12: Testing + bare-metal DRM/KMS bring-up
```

---

## KEY TECHNICAL DECISIONS

| Decision | Rationale |
|----------|-----------|
| **No Wayland server** | Run as Wayland client in hosted; bare-metal uses DRM/KMS directly |
| **Immediate-mode UI kept** | XP didn't retain-mode. Compositor handles presentation; UI draws to window surfaces |
| **HolyC for scripting** | Not JS. ZealOS heritage. Extensions later via HolyC |
| **Styx/9P for IPC** | Not D-Bus. 9P for compositor↔shell↔apps |
| **VSL for GPU** | Already have Vulkan/CUDA drivers. Extend for GBM/EGL |
| **Damage tracking = dirty rects** | Simple, effective. No complex scene graph needed |
| **No retain-mode scene graph** | Clutter/GTK4 overkill. Window = texture + transform |

---

## SUCCESS CRITERIA (MVP)

- [ ] Zero tearing (vsync working)
- [ ] 60fps window drag/resize
- [ ] Minimize/maximize animation < 200ms
- [ ] Snap-to-edge works on all 4 edges + corners
- [ ] Taskbar thumbnails update live
- [ ] Alt+Tab shows live previews
- [ ] Start menu search finds apps/files in < 100ms
- [ ] Notification center persists history
- [ ] Volume/network flyouts from tray
- [ ] All 171 existing tests still pass
- [ ] New tests: compositor, animations, snap, search

---

## ESTIMATED TOTAL: 12-15 WEEKS

**vs 20-25 weeks for GNOME parity** — because we build *only what XP+polish needs*, not a full modern desktop stack.