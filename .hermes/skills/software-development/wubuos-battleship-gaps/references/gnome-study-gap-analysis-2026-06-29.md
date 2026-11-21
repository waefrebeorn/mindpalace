# GNOME Study & Gap Analysis — WuBuOS vs GNOME 46 (2026-06-29)

## Context
Cloned and analyzed GNOME 46 core repositories to `/home/wubu/gnome-study/`:
- **mutter** (Compositor + WM, C)
- **gnome-shell** (Desktop Shell, JS + C)
- **gtk** (GTK4 Toolkit, C)
- **glib** (Core library, C)

## Architecture Comparison

| Layer | WuBuOS | GNOME |
|-------|--------|-------|
| **Compositor** | None (immediate mode VBE) | Mutter (Clutter/Cogl, OpenGL/Wayland) |
| **Window Manager** | wm.c (2301 lines) | Mutter core (meta-window-*.c, stack.c, place.c, constraints.c) |
| **Shell/UI** | C immediate-mode (*.c) | GNOME Shell (JS + Clutter actors, 100+ files) |
| **Toolkit** | None (raw VBE drawing) | GTK4 (CSS, accessibility, layout, rendering) |
| **Input** | Raw mouse/keyboard polling | libinput + Wayland protocols |
| **Graphics** | Software framebuffer (VBE) | GPU-accelerated (OpenGL/Vulkan via Clutter/Cogl) |
| **IPC** | Styx/9P + shared memory | D-Bus + Wayland protocols |
| **Theming** | 4 hardcoded themes | CSS + GTK theming engine |

## Missing Major Subsystems (8 Categories)

### 1. Compositor (CRITICAL)
```
GNOME: Mutter compositor.c (50KB) + Clutter scene graph + Cogl GPU
WuBuOS: NOTHING - immediate mode blitting to VBE framebuffer
```

### 2. Modern Window Management
```
GNOME: meta-window.c (7828 lines) - types, states, placement, constraints, animations, groups
WuBuOS: Basic (2301 lines) - rects, z-order, 9 fixed desktops
```

### 3. Input System
```
GNOME: libinput + Wayland seat/pointer/keyboard/touch + IBus + AT-SPI2
WuBuOS: Raw mouse/keyboard polling
```

### 4. Graphics/Rendering Pipeline
```
GNOME: Clutter + Cogl + GSK + Vulkan/GL + dmabuf + fractional scaling
WuBuOS: VBE framebuffer + 8x8 font + basic rect/line drawing
```

### 5. Desktop Shell Features
```
GNOME: 100+ JS modules (overview, dash, search, notifications, lock, extensions...)
WuBuOS: Start menu, taskbar, desktop icons, basic notify
```

### 6. GTK4 Widget Toolkit
```
GNOME: Widgets, layout, CSS, accessibility, text, DnD, printing, media
WuBuOS: NO toolkit - immediate mode drawing everywhere
```

### 7. System Integration
```
GNOME: D-Bus, systemd, UPower, NetworkManager, Polkit, Flatpak, Tracker, keyring
WuBuOS: Styx/9P, simple settings/pkgmgr
```

### 8. Wayland Protocol Implementation
```
GNOME: Full protocol suite (xdg_shell, dmabuf, fractional_scale, etc.)
WuBuOS: NO Wayland server, client only (hosted mode)
```

## What WuBuOS Has (171 Tests Passing)

| Feature | File | Status |
|---------|------|--------|
| Window management (basic) | wm.c | ✅ Working |
| Virtual desktops (9) | wm.c | ✅ Working |
| Taskbar + Start button | wm.c | ✅ Working |
| Desktop icons | wm.c + desktop.c | ✅ Working |
| File explorer | explorer.c | ✅ Working (74 tests) |
| Start menu (dynamic .desktop) | startmenu.c | ✅ Working |
| Terminal (VT100 + container) | term.c | ✅ Working |
| Clipboard (MIME, primary) | wubu_clipboard.c | ✅ Working (17 tests) |
| Theming (4 themes) | wubu_theme.c | ✅ Working |
| Settings persistence | wubu_settings.c | ✅ Working |
| Notifications | wubu_notify.c | ✅ Basic |
| Screenshots | wubu_screenshot.c | ✅ Basic |
| Trash | wubu_trash.c | ✅ Basic |
| Package manager | wubu_pkgmgr.c | ✅ Basic |
| MIME handling | wubu_mime.c | ✅ Working |
| VSL syscalls | wubu_vsl.c | ✅ 56 tests pass |
| HolyC REPL | holyc_*.c | ✅ Working |
| Proton (Win32→VSL) | wubu_proton.c | ✅ 32 tests |
| OCI containers | wubu_oci.c | ✅ 10/10 tests |
| Network (netlink) | wubu_network.c | ✅ 139/139 tests |
| Snapshots | wubu_snapshot.c | ✅ 132/132 tests |

## Design Documents Created

| Document | Path | Purpose |
|----------|------|---------|
| `WUBUOS_VS_GNOME_GAP_ANALYSIS.md` | `/home/wubu/gnome-study/` | 8 major missing subsystems, effort estimation |
| `XP_ERA_PRIORITIZED_ROADMAP.md` | `/home/wubu/gnome-study/` | 10 must-haves for "XP + polish" (12-15 weeks) |
| `WUBUOS_WAYLAND_NATIVE_ROADMAP.md` | `/home/wubu/gnome-study/` | 6 phases, 20 weeks for Wayland-native + better-than-GTK4 |

## Priority Roadmap: XP-Era Classic + Modern Polish (12-15 weeks)

### Must-Haves (Shippable MVP)

| # | Feature | Why | Effort |
|---|---------|-----|--------|
| **1** | **Basic Compositor** | Vsync, no tearing, damage tracking | 2-3 wks |
| **2** | **GPU Render Path** | OpenGL/Vulkan via VSL | 2 wks |
| **3** | **Window Animations** | Minimize/maximize genie, fade, slide | 1-2 wks |
| **4** | **Snap-to-Edge (Aero Snap)** | Win7 feature, expected in modern polish | 1 wk |
| **5** | **Taskbar Thumbnails** | Hover → live preview (DWM style) | 1-2 wks |
| **6** | **Live Window Previews** | Alt+Tab shows actual content | 1 wk |
| **7** | **Search (Start Menu)** | Type-to-launch (Vista/7 feature) | 1 wk |
| **8** | **Smooth Scrolling** | Momentum + touchpad | 1 wk |
| **9** | **Notification Center** | Win10 Action Center style | 1 wk |
| **10** | **Volume/Network/Battery Flyouts** | Click tray → slider/menu | 1 wk |

### Explicitly Deferred (Not XP-Era)

| Feature | Reason |
|---------|--------|
| Full Wayland Server | We're a Wayland *client* in hosted mode |
| GTK4 Toolkit | XP used Win32 controls; keep immediate-mode |
| D-Bus/systemd/UPower/NetworkManager/Polkit | Styx/9P + simple daemons instead |
| Accessibility Suite | XP had basic; defer to post-MVP |
| Extensions Framework (JS) | XP had none; HolyC scripting later |
| Activities Overview (GNOME-style) | We enhance Start Menu, not replace |
| XDG Portals / Flatpak | Container isolation via VSL/OCI instead |
| Multi-GPU / HDR / Color Management | Overkill for XP-era target |
| IBus / Complex Input Methods | Basic Unicode + dead keys sufficient |

## Wayland-Native + Better-Than-GTK4 Standards

| Mistake | Legacy System | WuBuOS Solution |
|---------|---------------|-----------------|
| X11 Protocol | 40yr cruft | **Wayland-only** from day 1 |
| D-Bus | Stringly-typed broker | **9P/Styx** — capability files, no broker |
| GObject | 50KB boilerplate | **WuBuObject** — opaque struct, single alloc |
| CSS Theming | Selector matching | **WuBuStyle** — C structs, variables, hot-reload |
| GTK4 Layout | Constraint solver | **Flex/Grid only** — deterministic |
| Clutter/Cogl | 2 scene graphs | **Single compositor** — surface + transform |
| AT-SPI2 | D-Bus a11y | **Built-in** — compositor tree = a11y tree |
| Flatpak Portals | D-Bus permissions | **9P namespaces** — container FS = sandbox |
| Input (X11) | Grab/ungrab | **libinput + Wayland protocols** — gestures, tablet |
| Fractional Scaling | Hacky | **Compositor-owned** — render at scale |

## WuBuKit Toolkit API (Better Than GTK4)

```c
// ONE allocation, NO refcount, NO GObject
WuBuWindow *win = wubu_window_new(WUBU_WINDOW_TOPLEVEL);
wubu_window_set_title(win, "Hello");
wubu_window_set_layout(win, wubu_flex_new(WUBU_FLEX_COLUMN));

WuBuButton *btn = wubu_button_new("Click me");
wubu_widget_append(win->root, btn);
wubu_button_on_click(btn, ^(WuBuButton *b) { printf("clicked\n"); });

wubu_window_present(win); // Compositor handles rest
```

## Implementation Files Created (2026-06-29)

| File | Approach | Lines | Status |
|------|----------|-------|--------|
| `src/gui/wubu_compositor.c` | wlroots-based (DRM/KMS, Vulkan, xdg_shell, decorations) | 900+ | ✅ Written |
| `src/gui/wubu_compositor.h` | API: WuBuObject, window mgmt, output mgmt, damage, a11y | 200+ | ✅ Written |
| `src/gui/wubu_compositor_standalone.c` | Zero-dep: Wayland server + libdrm + GBM + Vulkan + pixman | 1100+ | ✅ Written |
| `Makefile` | Added `wubu_compositor.o` to GUI_OBJS, pkg-config flags | — | ✅ Updated |

## Verification Blocked: Missing Dependencies

| Package | Required For | Status |
|---------|--------------|--------|
| `libwlroots-dev` | wlroots headers (wlr/*.h) | ❌ Need sudo |
| `libgbm-dev` | gbm.h | ❌ Need sudo |
| `libpixman-1-dev` | pixman.h | ❌ Need sudo (runtime only) |
| `libwayland-dev >= 1.23` | Wayland protocols | ⚠️ Have 1.22 |

```bash
# To unblock (requires sudo):
apt-get install libwlroots-dev libgbm-dev libpixman-1-dev libwayland-dev
```

## Next Steps When Dependencies Available

1. **Build compositor core** (DRM/KMS + Vulkan + damage + vsync)
2. **xdg_shell + xdg_decoration + fractional_scale** protocols
3. **libinput + zwp_tablet_v2 + zwp_text_input_v3**
4. **Built-in accessibility tree** (no AT-SPI2)
5. **XP visual metaphor** on modern foundation (animations, snap, thumbnails, search)
6. **WuBuKit toolkit** (WuBuObject, WuBuStyle, Flex/Grid, HarfBuzz)