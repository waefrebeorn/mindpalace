# Wayland-Native Compositor Design — WuBuOS (2026-06-29)

## Context
Based on GNOME study (mutter, gnome-shell, gtk, glib cloned to `/home/wubu/gnome-study/`) and user direction: "XP-era classic with modern polish" + "Wayland and modern better than GTK4 standards" + "we are making our own OS so we can learn from historical mistakes."

## Historical Mistakes We Avoid

| Mistake | Legacy System | WuBuOS Solution |
|---------|---------------|-----------------|
| X11 Protocol | 40yr cruft, no security, tearing | **Wayland-only** from day 1 |
| D-Bus | Stringly-typed broker | **9P/Styx** — capability files, no broker |
| GObject | 50KB boilerplate/class | **WuBuObject** — opaque struct, single alloc, no refcount |
| CSS Theming | Selector matching | **WuBuStyle** — C structs, variables, hot-reload |
| GTK4 Layout | Constraint solver | **Flex/Grid only** — deterministic |
| Clutter/Cogl | 2 scene graphs | **Single compositor** — surface + transform |
| AT-SPI2 | D-Bus a11y | **Built-in** — compositor tree = a11y tree |
| Flatpak Portals | D-Bus permissions | **9P namespaces** — container FS = sandbox |
| Input (X11) | Grab/ungrab | **libinput + Wayland protocols** — gestures, tablet, touch |
| Fractional Scaling | Hacky | **Compositor-owned** — render at scale, present integer |

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        USER SPACE (Wayland Clients)                     │
├────────────────────────────────────────────────────────────────────────┤
│  shell (compositor client)                                      │
│  ├─ wm, taskbar, startmenu, desktop, notify → all Wayland surfaces    │
│  └─ HolyC REPL, terminal, explorer → Wayland clients                  │
├────────────────────────────────────────────────────────────────────────┤
│  wubu_compositor (Wayland SERVER + Compositor)                         │
│  ├─ wl_compositor, xdg_shell, xdg_decoration, xdg_activation          │
│  ├─ zwp_linux_dmabuf_v1, zwp_linux_explicit_synchronization_v1        │
│  ├─ fractional_scale_v1, viewport_v1, presentation_time               │
│  ├─ zwp_pointer_constraints_v1, zwp_relative_pointer_v1               │
│  ├─ zwp_tablet_v2, zwp_text_input_v3 (IM)                             │
│  ├─ session_lock_v1, security_context_v1                              │
│  ├─ Damage tracking + triple-buffer + explicit sync                   │
│  ├─ Vulkan render path (VSL) + software fallback                      │
│  └─ Accessibility tree (built-in, not AT-SPI2)                        │
├────────────────────────────────────────────────────────────────────────┤
│  VSL (wubu_vsl.c) - Syscall + GPU + Container Layer                    │
│  ├─ DRM/KMS/GBM (bare metal)                                           │
│  ├─ Vulkan/OpenGL/EGL loader                                           │
│  ├─ OCI container runtime (sysbox-style)                               │
│  └─ Styx/9P namespace (IPC = file ops)                                 │
├────────────────────────────────────────────────────────────────────────┤
│  ZealOS Kernel (bare metal)                                            │
└────────────────────────────────────────────────────────────────────────┘
```

## Implementation Files Created

| File | Approach | Lines | Status |
|------|----------|-------|--------|
| `src/gui/wubu_compositor.c` | wlroots-based (DRM/KMS, Vulkan, xdg_shell, decorations) | 900+ | ✅ Written |
| `src/gui/wubu_compositor.h` | API: WuBuObject, window mgmt, output mgmt, damage, a11y | 200+ | ✅ Written |
| `src/gui/wubu_compositor_standalone.c` | Zero-dep: Wayland server + libdrm + GBM + Vulkan + pixman | 1100+ | ✅ Written |
| `Makefile` | Added `wubu_compositor.o` to GUI_OBJS, pkg-config flags | — | ✅ Updated |

## WuBuObject — Better Than GObject

```c
// wubu_object.h - 200 lines total
typedef struct WuBuObject WuBuObject;
typedef void (*WuBuObjectFini)(WuBuObject *self);

struct WuBuObject {
    const char *type_name;
    WuBuObjectFini fini;
    // NO refcount, NO weak refs, NO signals
};

// Single alloc: type + instance data together
#define WUBU_OBJECT_NEW(type, ...) \
    ({ \
        struct { WuBuObjectHeader _header; type inst; } *obj = calloc(1, sizeof(*obj)); \
        obj->_header.type_name = #type; \
        obj->_header.fini = (WuBuObjectFini)type##_fini; \
        type##_init(&obj->inst, ##__VA_ARGS__); \
        &obj->inst; \
    })

// Usage — zero boilerplate
typedef struct { int x, y; } Point;
void Point_init(Point *p, int x, int y) { p->x = x; p->y = y; }
void Point_fini(Point *p) {}
WuBuObject *pt = WUBU_OBJECT_NEW(Point, pt, 10, 20);
```

## WuBuStyle — Better Than CSS

```c
// Declarative C, hot-reloadable, variables
WuBuStyleSheet *sheet = wubu_style_new();

wubu_style_var(sheet, "bg", 0x2D2D2DFF);
wubu_style_var(sheet, "accent", 0x0078D7FF);

wubu_style_rule(sheet, "Window",
    "background: var(bg);"
    "border: 1px solid shade(var(bg), 0.8);"
    "radius: 0;"
);

wubu_style_rule(sheet, "Button",
    "background: var(bg);"
    "color: white;"
    "padding: 6 12;"
    "radius: 0;"
    "&:hover { background: shade(var(bg), 1.2); }"
    "&:active { background: var(accent); }"
);

wubu_style_apply(window->root, sheet); // Single pass, no selector matching
```

## 9P IPC — Better Than D-Bus

```c
// Everything is a file. No broker. Capability-based.
// Clipboard:
int fd = open("/mnt/clipboard/text", O_RDWR); // Returns capability
write(fd, "hello", 5);

// File picker (no portal):
int fd = open("/mnt/portal/open", O_WRONLY);
write(fd, "~/Documents\n*.txt\n", 18);
int file_fd = open("/mnt/portal/result", O_RDONLY); // Returns selected file FD

// Secrets:
int fd = open("/mnt/secrets/github_token", O_RDONLY); // Capability = permission
```

## Compositor-First Rendering — Better Than Clutter/GTK4

```
Traditional (GTK4/Clutter):
App → GSK Nodes → Shader → GPU → Compositor → Display
         ↑          ↑
    Scene graph  Re-render on any change

WuBuOS:
App → Window Surface (dmabuf) → Compositor → Display
                    ↑
              App draws directly to surface
              Compositor only composites (transform + blend)
              Zero copy via dmabuf + explicit sync
```

## Phased Implementation Plan (20 weeks)

| Phase | Weeks | Focus |
|-------|-------|-------|
| **1** | 1-4 | Wayland Compositor Core (DRM/KMS, Vulkan, dmabuf, explicit sync) |
| **2** | 4-6 | Modern Wayland Protocols (decoration, activation, fractional scale) |
| **3** | 6-8 | Input + Built-in Accessibility (libinput, tablet, a11y tree) |
| **4** | 8-12 | XP Visual Metaphor on Modern Foundation (animations, snap, search) |
| **5** | 12-16 | WuBuKit Toolkit (WuBuObject, WuBuStyle, Flex/Grid, HarfBuzz) |
| **6** | 16-20 | Container/Security (OCI+9P sandbox, capabilities, secrets) |

## Phase 1 Detail: Compositor Core

### Key Components

1. **Wayland Server** — `wl_display`, globals for compositor, shm, xdg_wm_base, xdg_decoration, fractional_scale, linux_dmabuf
2. **DRM/KMS Backend** — Scan connectors, create GBM surfaces, modeset
3. **Vulkan Renderer** — VSL GPU driver integration, swapchain, triple-buffer, explicit sync
4. **Damage Tracking** — pixman_region32, dirty rects per output
5. **Frame Timing** — `presentation_time`, vsync, frame throttling

### Implementation Decisions

**Use wlroots for Phase 1-3:**
- Proven protocol implementations (xdg_shell, dmabuf, fractional_scale, etc.)
- No X11 baggage — pure Wayland
- DRM/KMS + Vulkan + GBM backends ready
- Can swap to raw Wayland later (Phase 5+)

**Standalone version** (`wubu_compositor_standalone.c`):
- Zero external deps beyond wayland-server, libdrm, gbm, vulkan, pixman
- Good for bare-metal bringup where wlroots not available

### API Surface (wubu_compositor.h)

```c
// Window = Surface + Transform (no scene graph)
typedef struct {
    double x, y, width, height;
    double scale;        // Fractional scale
    float opacity;       // 0-1
    float transform[9];  // 3x3 matrix
} WuBuWindowGeometry;

// Core
WuBuCompositor *wubu_compositor_create(void);
void wubu_compositor_destroy(WuBuCompositor *comp);
int wubu_compositor_run(WuBuCompositor *comp);
struct wl_display *wubu_compositor_get_display(WuBuCompositor *comp);

// Window management
WuBuWindow *wubu_window_create(WuBuCompositor *comp, WuBuWindowType type);
void wubu_window_set_geometry(WuBuWindow *win, const WuBuWindowGeometry *geom);
void wubu_window_set_opacity(WuBuWindow *win, float opacity);
void wubu_window_activate(WuBuWindow *win);
void wubu_window_close(WuBuWindow *win);

// Damage/rendering
void wubu_compositor_damage_window(WuBuCompositor *comp, WuBuWindow *win, int x, int y, int w, int h);

// Screenshot (for 9P)
int wubu_compositor_screenshot(WuBuCompositor *comp, WuBuOutput *out, void **data, size_t *size);

// Accessibility (built-in)
void wubu_compositor_a11y_tree_get_root(WuBuCompositor *comp, WuBuA11yNode *root);
void wubu_compositor_a11y_announce(WuBuCompositor *comp, const char *message);
```

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

## Design Documents Created

| Document | Path | Purpose |
|----------|------|---------|
| `WUBUOS_VS_GNOME_GAP_ANALYSIS.md` | `/home/wubu/gnome-study/` | 8 major missing subsystems vs GNOME 46 |
| `XP_ERA_PRIORITIZED_ROADMAP.md` | `/home/wubu/gnome-study/` | 10 must-haves for "XP + modern polish" (12-15 weeks) |
| `WUBUOS_WAYLAND_NATIVE_ROADMAP.md` | `/home/wubu/gnome-study/` | 6 phases, 20 weeks for Wayland-native + better-than-GTK4 |

## Success Criteria (MVP)

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