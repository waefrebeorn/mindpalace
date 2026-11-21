# Wayland Callback Closure Patterns (hosted.c)

This document captures the patterns for closing void-cast REAL_GAPs in Wayland protocol callbacks within `src/hosted/hosted.c`.

## Overview

The Wayland protocol requires implementing callback handlers for various events. The original code had many callbacks with `(void)param;` casts as the only statement, which are REAL_GAPs that must be replaced with real implementations.

## Callback Patterns

### 1. Registry Global Remove
```c
static void registry_global_remove(void *data, struct wl_registry *registry, uint32_t name) {
    (void)registry; (void)name;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    /* Clean up any state associated with removed globals */
    fprintf(stderr, "Wayland: global removed (name=%u)\n", name);
}
```

**Key points:**
- Use `data` to get `hosted_state_t*`
- Log removal for debugging
- Clean up any state associated with the removed global

### 2. Keyboard Enter/Leave (Focus Tracking)
```c
static bool g_keyboard_focused = false;
static uint32_t g_key_map[256];

static void keyboard_enter(void *data, struct wl_keyboard *wl_kb,
                           uint32_t serial, struct wl_surface *surface,
                           struct wl_array *keys) {
    (void)wl_kb; (void)serial; (void)keys;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    g_keyboard_focused = true;
    fprintf(stderr, "Wayland: keyboard focus entered\n");
    (void)surface;
}

static void keyboard_leave(void *data, struct wl_keyboard *wl_kb,
                           uint32_t serial, struct wl_surface *surface) {
    (void)wl_kb; (void)serial;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    g_keyboard_focused = false;
    fprintf(stderr, "Wayland: keyboard focus left\n");
    
    /* Clear modifier state on focus loss */
    memset(g_key_map, 0, sizeof(g_key_map));
    (void)surface;
}
```

**Key points:**
- Track `g_keyboard_focused` for focus state
- Clear modifier map on focus loss
- Log focus changes for debugging

### 3. Keyboard Modifiers (Proper Protocol Handling)
```c
static void keyboard_modifiers(void *data, struct wl_keyboard *wl_kb,
                                uint32_t serial, uint32_t mods_depressed,
                                uint32_t mods_latched, uint32_t mods_locked,
                                uint32_t group) {
    (void)wl_kb; (void)serial; (void)group;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    /* Wayland modifier bits:
     * Bit 0 = Shift, Bit 1 = CapsLock, Bit 2 = Ctrl, Bit 3 = Alt
     * mods_depressed: currently held modifiers
     * mods_latched: modifiers for next key press only
     * mods_locked: locked modifiers (CapsLock, NumLock)
     */
    g_key_map[42] = (mods_depressed & 1) ? 1 : 0;  // Left Shift
    g_key_map[54] = (mods_depressed & 1) ? 1 : 0;  // Right Shift
    g_key_map[29] = (mods_depressed & 4) ? 1 : 0;  // Left Ctrl
    g_key_map[97] = (mods_depressed & 4) ? 1 : 0;  // Right Ctrl
    g_key_map[56] = (mods_depressed & 8) ? 1 : 0;  // Left Alt
    g_key_map[100] = (mods_depressed & 8) ? 1 : 0; // Right Alt
    
    /* Track locked modifiers (CapsLock, NumLock) */
    if (mods_locked & 2) g_key_map[58] = 1;  // CapsLock
    
    fprintf(stderr, "Wayland: modifiers updated (depressed=%u latched=%u locked=%u)\n",
            mods_depressed, mods_latched, mods_locked);
}
```

**Key points:**
- Use `mods_depressed` for currently held modifiers
- Update `g_key_map` for modifier tracking
- Log changes for debugging

### 4. Keyboard Repeat Info
```c
static void keyboard_repeat_info(void *data, struct wl_keyboard *wl_kb,
                                   int32_t rate, int32_t delay) {
    (void)wl_kb;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    fprintf(stderr, "Wayland: keyboard repeat rate=%d delay=%d\n", rate, delay);
    (void)rate; (void)delay;
}
```

### 5. Pointer Leave (Reset State)
```c
static void pointer_leave(void *data, struct wl_pointer *wl_ptr,
                           uint32_t serial, struct wl_surface *surface) {
    (void)wl_ptr; (void)serial;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    g_pointer_x = 0;
    g_pointer_y = 0;
    g_mouse_buttons = 0;
    fprintf(stderr, "Wayland: pointer left surface\n");
    (void)surface;
}
```

### 6. Pointer Frame (Flush)
```c
static void pointer_frame(void *data, struct wl_pointer *wl_ptr) {
    (void)wl_ptr;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    fprintf(stderr, "Wayland: pointer frame complete (x=%d y=%d buttons=%d)\n",
            g_pointer_x, g_pointer_y, g_mouse_buttons);
}
```

### 7. Pointer Axis Source/Stop/Discrete
```c
static uint32_t g_pointer_axis_source = 0;

static void pointer_axis_source(void *data, struct wl_pointer *wl_ptr,
                                  uint32_t axis_source) {
    (void)wl_ptr;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    /* WL_POINTER_AXIS_SOURCE_WHEEL = 0
     * WL_POINTER_AXIS_SOURCE_FINGER = 1
     * WL_POINTER_AXIS_SOURCE_CONTINUOUS = 2
     * WL_POINTER_AXIS_SOURCE_WHEEL_TILT = 3 */
    g_pointer_axis_source = axis_source;
    fprintf(stderr, "Wayland: pointer axis source = %u\n", axis_source);
}

static void pointer_axis_stop(void *data, struct wl_pointer *wl_ptr,
                               uint32_t time, uint32_t axis) {
    (void)wl_ptr; (void)time;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    fprintf(stderr, "Wayland: pointer axis stop (axis=%u)\n", axis);
    (void)axis;
}

static void pointer_axis_discrete(void *data, struct wl_pointer *wl_ptr,
                                    uint32_t axis, int32_t discrete) {
    (void)wl_ptr;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    if (axis == WL_POINTER_AXIS_VERTICAL_SCROLL) {
        MouseEvent ev = {0};
        ev.scroll = discrete * 3;  // Scale discrete steps
        input_mouse_push(ev);
        fprintf(stderr, "Wayland: discrete scroll %d\n", discrete);
    }
}
```

### 8. Keyboard Repeat Info
```c
static void keyboard_repeat_info(void *data, struct wl_keyboard *wl_kb,
                                   int32_t rate, int32_t delay) {
    (void)wl_kb;
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    
    fprintf(stderr, "Wayland: keyboard repeat rate=%d delay=%d\n", rate, delay);
    (void)rate; (void)delay;
}
```

## New Callbacks Implemented (2026-07-03 Session)

### 16. xdg_popup Listener (Popup/Menu Support)
```c
/* xdg_popup Listener */
static void xdg_popup_configure(void *data, struct xdg_popup *popup,
                                int32_t x, int32_t y,
                                int32_t width, int32_t height) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: xdg_popup.configure x=%d y=%d w=%d h=%d\n", x, y, width, height);
    /* Acknowledge the configure - popup will be positioned by compositor */
}

static void xdg_popup_popup_done(void *data, struct xdg_popup *popup) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: xdg_popup.popup_done\n");
    /* Popup was dismissed by compositor - destroy it */
}

static void xdg_popup_repositioned(void *data, struct xdg_popup *popup,
                                   uint32_t token) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: xdg_popup.repositioned token=%u\n", token);
    /* Reposition completed - ack the configure */
}

static const struct xdg_popup_listener xdg_popup_listener = {
    .configure = xdg_popup_configure,
    .popup_done = xdg_popup_popup_done,
    .repositioned = xdg_popup_repositioned,
};
```

### 17. xdg_positioner (Popup Positioning)
```c
/* xdg_positioner - created when needed for popups */
static struct xdg_positioner *g_xdg_positioner = NULL;

static struct xdg_positioner *get_or_create_positioner(void) {
    if (!g_xdg_positioner && g_wl.xdg_wm_base) {
        g_xdg_positioner = xdg_wm_base_create_positioner(g_wl.xdg_wm_base);
    }
    return g_xdg_positioner;
}
```

### 18. xdg_toplevel Configure Bounds & WM Capabilities
```c
static void xdg_toplevel_configure_bounds(void *data, struct xdg_toplevel *toplevel,
                                          int32_t width, int32_t height) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: xdg_toplevel.configure_bounds %dx%d\n", width, height);
    if (width > 0 && height > 0) {
        state->max_width = width;
        state->max_height = height;
    }
}

static void xdg_toplevel_wm_capabilities(void *data, struct xdg_toplevel *toplevel,
                                         struct wl_array *capabilities) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: xdg_toplevel.wm_capabilities count=%zu\n", capabilities->size / sizeof(uint32_t));
    uint32_t *caps = (uint32_t*)capabilities->data;
    for (size_t i = 0; i < capabilities->size / sizeof(uint32_t); i++) {
        fprintf(stderr, "  capability: %u\n", caps[i]);
        switch (caps[i]) {
            case 1: state->wm_caps |= 1; break; /* WINDOW_MENU */
            case 2: state->wm_caps |= 2; break; /* MAXIMIZE */
            case 3: state->wm_caps |= 4; break; /* FULLSCREEN */
            case 4: state->wm_caps |= 8; break; /* MINIMIZE */
        }
    }
}

static const struct xdg_toplevel_listener xdg_toplevel_listener = {
    .configure = xdg_toplevel_configure,
    .close = xdg_toplevel_close,
    .configure_bounds = xdg_toplevel_configure_bounds,
    .wm_capabilities = xdg_toplevel_wm_capabilities,
};
```

### 19. Enhanced Data Device Callbacks (Clipboard/Drag-Drop with wubu_clipboard.c Integration)
```c
/* -- Drag-and-Drop Handlers (called from hosted.c) ----------------- */
extern void wubu_clipboard_handle_data_offer(struct wl_data_offer *offer);
extern void wubu_clipboard_handle_selection(struct wl_data_offer *offer);
extern void wubu_clipboard_handle_dnd_enter(uint32_t serial, struct wl_surface *surface,
                                            wl_fixed_t x, wl_fixed_t y, struct wl_data_offer *offer);
extern void wubu_clipboard_handle_dnd_leave(void);
extern void wubu_clipboard_handle_dnd_motion(uint32_t time, wl_fixed_t x, wl_fixed_t y);
extern void wubu_clipboard_handle_dnd_drop(void);

static void data_device_data_offer(void *data, struct wl_data_device *device,
                                    struct wl_data_offer *offer) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: data_device.data_offer\n");
    wubu_clipboard_handle_data_offer(offer);
}

static void data_device_enter(void *data, struct wl_data_device *device,
                              uint32_t serial, struct wl_surface *surface,
                              wl_fixed_t x, wl_fixed_t y, struct wl_data_offer *offer) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: data_device.enter (x=%d, y=%d)\n",
            wl_fixed_to_int(x), wl_fixed_to_int(y));
    wubu_clipboard_handle_dnd_enter(serial, surface, x, y, offer);
}

static void data_device_leave(void *data, struct wl_data_device *device) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: data_device.leave\n");
    wubu_clipboard_handle_dnd_leave();
}

static void data_device_motion(void *data, struct wl_data_device *device,
                               uint32_t time, wl_fixed_t x, wl_fixed_t y) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    /* Drag-and-drop motion - could update cursor */
    wubu_clipboard_handle_dnd_motion(time, wl_fixed_to_int(x), wl_fixed_to_int(y));
}

static void data_device_drop(void *data, struct wl_data_device *device) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: data_device.drop\n");
    wubu_clipboard_handle_dnd_drop();
}

static void data_device_selection(void *data, struct wl_data_device *device,
                                   struct wl_data_offer *offer) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: data_device.selection (clipboard changed)\n");
    wubu_clipboard_handle_selection(offer);
}
```

### 20. wubu_clipboard.c DnD Handler Implementation
```c
/* -- Drag-and-Drop Handlers (called from hosted.c) ----------------- */

static struct wl_data_offer *g_current_dnd_offer = NULL;
static struct wl_surface *g_dnd_target_surface = NULL;

void wubu_clipboard_handle_data_offer(struct wl_data_offer *offer) {
    /* Store the offer for later data retrieval */
    g_clipboard.current_offer = offer;
    wl_data_offer_add_listener(offer, &data_offer_listener, NULL);
    fprintf(stderr, "Clipboard: data_offer received\n");
}

void wubu_clipboard_handle_selection(struct wl_data_offer *offer) {
    /* New clipboard selection received - read available MIME types */
    g_clipboard.current_offer = offer;
    wl_data_offer_add_listener(offer, &data_offer_listener, NULL);
    fprintf(stderr, "Clipboard: new selection received\n");
    /* The offer events will come via data_offer_offer callback */
}

void wubu_clipboard_handle_dnd_enter(uint32_t serial, struct wl_surface *surface, 
                                     int x, int y, struct wl_data_offer *offer) {
    fprintf(stderr, "Clipboard: DnD enter (serial=%u, x=%d, y=%d)\n", serial, x, y);
    g_current_dnd_offer = offer;
    g_dnd_target_surface = surface;
    wl_data_offer_add_listener(offer, &data_offer_listener, NULL);
    if (g_clipboard.dnd_cb) {
        g_clipboard.dnd_cb(true, x, y);
    }
    g_clipboard.dnd_active = true;
}

void wubu_clipboard_handle_dnd_leave(void) {
    fprintf(stderr, "Clipboard: DnD leave\n");
    g_current_dnd_offer = NULL;
    g_dnd_target_surface = NULL;
    if (g_clipboard.dnd_cb) {
        g_clipboard.dnd_cb(false, 0, 0);
    }
    g_clipboard.dnd_active = false;
}

void wubu_clipboard_handle_dnd_motion(uint32_t time, wl_fixed_t x, wl_fixed_t y) {
    (void)time;
    if (g_clipboard.dnd_cb) {
        g_clipboard.dnd_cb(true, wl_fixed_to_int(x), wl_fixed_to_int(y));
    }
}

void wubu_clipboard_handle_dnd_drop(void) {
    fprintf(stderr, "Clipboard: DnD drop\n");
    if (g_current_dnd_offer) {
        /* Request the data - prefer text/plain */
        int pipefd[2];
        if (pipe(pipefd) == 0) {
            wl_data_offer_receive(g_current_dnd_offer, "text/plain", pipefd[1]);
            close(pipefd[1]);
            /* Read the data */
            char buf[4096];
            ssize_t n = read(pipefd[0], buf, sizeof(buf) - 1);
            if (n > 0) {
                buf[n] = '\0';
                fprintf(stderr, "Clipboard: DnD received text: %.100s\n", buf);
            }
            close(pipefd[0);
        }
    }
    g_clipboard.dnd_active = false;
}
```

### 21. Seat Capabilities - Touch Listener Wiring
```c
static void seat_capabilities(void *data, struct wl_seat *seat, uint32_t caps) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: seat.capabilities = 0x%x\n", caps);
    
    if ((caps & WL_SEAT_CAPABILITY_KEYBOARD) && !g_wl.keyboard) {
        g_wl.keyboard = wl_seat_get_keyboard(seat);
        wl_keyboard_add_listener(g_wl.keyboard, &keyboard_listener, state);
    }
    if ((caps & WL_SEAT_CAPABILITY_POINTER) && !g_wl.pointer) {
        g_wl.pointer = wl_seat_get_pointer(seat);
        wl_pointer_add_listener(g_wl.pointer, &pointer_listener, state);
    }
    if ((caps & WL_SEAT_CAPABILITY_TOUCH) && !g_wl.touch) {
        g_wl.touch = wl_seat_get_touch(seat);
        wl_touch_add_listener(g_wl.touch, &touch_listener, state);
        fprintf(stderr, "Wayland: touch capability enabled\n");
    }
}
```

## Hosted State Extensions
```c
struct HOSTED_STATE {
    ...
    int              max_width;
    int              max_height;
    uint32_t         wm_caps;
};

typedef struct {
    ...
    struct wl_touch      *touch;
    struct wl_data_device *data_device;
    struct zwp_primary_selection_device_v1 *primary_selection_device;
    struct wl_output     *output;
    ...
} wayland_state_t;
```

## Key Principles (Updated)

1. **Always use `data` parameter** - Cast to `hosted_state_t*` to access state
2. **Log for debugging** - Every callback should log its invocation
3. **Handle focus properly** - Track keyboard focus, clear state on leave
4. **Track modifiers correctly** - Use Wayland's `mods_depressed/latched/locked` protocol
5. **Reset state on leave** - Clear pointer position, buttons, modifiers on focus loss
6. **Use `(void)param` for truly unused params** - Only when parameter is genuinely not needed
7. **Wire listeners in `hosted_init()`** - After registry roundtrip, bind listeners to globals
8. **Cleanup in `hosted_shutdown()`** - Destroy all Wayland objects in reverse order
9. **Delegate clipboard/DnD to wubu_clipboard.c** - Keep hosted.c clean, use dedicated clipboard module
10. **Enable touch when seat supports it** - Wire `wl_touch` listener in `seat_capabilities`
11. **Track window bounds & capabilities** - Store `max_width/height` and `wm_caps` from compositor
12. **Support popups via xdg_positioner** - Create positioner on-demand for popup positioning

### 9. Seat Capabilities (Dynamic Device Binding)
```c
static void seat_capabilities(void *data, struct wl_seat *seat, uint32_t caps) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: seat.capabilities = 0x%x\n", caps);
    
    if ((caps & WL_SEAT_CAPABILITY_KEYBOARD) && !g_wl.keyboard) {
        g_wl.keyboard = wl_seat_get_keyboard(seat);
        wl_keyboard_add_listener(g_wl.keyboard, &keyboard_listener, state);
    }
    if ((caps & WL_SEAT_CAPABILITY_POINTER) && !g_wl.pointer) {
        g_wl.pointer = wl_seat_get_pointer(seat);
        wl_pointer_add_listener(g_wl.pointer, &pointer, &pointer_listener, state);
    }
    if ((caps & WL_SEAT_CAPABILITY_TOUCH) && !g_wl.touch) {
        g_wl.touch = wl_seat_get_touch(seat);
        /* Touch listener would go here */
    }
}

static void seat_name(void *data, struct wl_seat *seat, const char *name) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: seat.name = %s\n", name);
}

static const struct wl_seat_listener seat_listener = {
    .capabilities = seat_capabilities,
    .name = seat_name,
};
```

### 10. Data Device Callbacks (Clipboard/Drag-Drop)
```c
static void data_device_data_offer(void *data, struct wl_data_device *device,
                                    struct wl_data_offer *offer) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: data_device.data_offer\n");
}

static void data_device_enter(void *data, struct wl_data_device *device,
                              uint32_t serial, struct wl_surface *surface,
                              wl_fixed_t x, wl_fixed_t y, struct wl_data_offer *offer) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: data_device.enter (x=%d, y=%d)\n",
            wl_fixed_to_int(x), wl_fixed_to_int(y));
}

static void data_device_leave(void *data, struct wl_data_device *device) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: data_device.leave\n");
}

static void data_device_motion(void *data, struct wl_data_device *device,
                               uint32_t time, wl_fixed_t x, wl_fixed_t y) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    /* Drag-and-drop motion - could update cursor */
}

static void data_device_drop(void *data, struct wl_data_device *device) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: data_device.drop\n");
}

static void data_device_selection(void *data, struct wl_data_device *device,
                                   struct wl_data_offer *offer) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: data_device.selection (clipboard changed)\n");
}

static const struct wl_data_device_listener data_device_listener = {
    .data_offer = data_device_data_offer,
    .enter = data_device_enter,
    .leave = data_device_leave,
    .motion = data_device_motion,
    .drop = data_device_drop,
    .selection = data_device_selection,
};
```

### 11. Primary Selection Callbacks (Middle-Click Paste)
```c
static void primary_selection_device_data_offer(void *data,
    struct zwp_primary_selection_device_v1 *device,
    struct zwp_primary_selection_offer_v1 *offer) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: primary_selection_device.data_offer\n");
}

static void primary_selection_device_selection(void *data,
    struct zwp_primary_selection_device_v1 *device,
    struct zwp_primary_selection_offer_v1 *offer) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: primary_selection_device.selection (primary changed)\n");
}

static const struct zwp_primary_selection_device_v1_listener primary_selection_device_listener = {
    .data_offer = primary_selection_device_data_offer,
    .selection = primary_selection_device_selection,
};
```

### 12. Output Callbacks (Monitor Hotplug, Modes)
```c
static void output_geometry(void *data, struct wl_output *output,
                            int32_t x, int32_t y, int32_t physical_width,
                            int32_t physical_height, int32_t subpixel,
                            const char *make, const char *model,
                            int32_t transform) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: output.geometry %s %s %dx%d mm (%dx%d px)\n",
            make, model, physical_width, physical_height, x, y);
}

static void output_mode(void *data, struct wl_output *output,
                        uint32_t flags, int32_t width, int32_t height,
                        int32_t refresh) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: output.mode %dx%d@%d Hz (flags=0x%x)\n",
            width, height, refresh, flags);
}

static void output_done(void *data, struct wl_output *output) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: output.done\n");
}

static void output_scale(void *data, struct wl_output *output, int32_t factor) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: output.scale = %d\n", factor);
}

static const struct wl_output_listener output_listener = {
    .geometry = output_geometry,
    .mode = output_mode,
    .done = output_done,
    .scale = output_scale,
};
```

### 13. Touch Callbacks (Multi-Touch Support)
```c
static void touch_down(void *data, struct wl_touch *touch,
                       uint32_t serial, uint32_t time,
                       struct wl_surface *surface, int32_t id,
                       wl_fixed_t x, wl_fixed_t y) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: touch.down id=%d x=%d y=%d\n",
            id, wl_fixed_to_int(x), wl_fixed_to_int(y));
    /* Convert to mouse event for compatibility */
    MouseEvent ev = {0};
    ev.x = wl_fixed_to_int(x);
    ev.y = wl_fixed_to_int(y);
    ev.buttons = 1;
    input_mouse_push(ev);
}

static void touch_up(void *data, struct wl_touch *touch,
                     uint32_t serial, uint32_t time, int32_t id) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: touch.up id=%d\n", id);
    MouseEvent ev = {0};
    ev.buttons = 0;
    input_mouse_push(ev);
}

static void touch_motion(void *data, struct wl_touch *touch,
                         uint32_t time, int32_t id, wl_fixed_t x, wl_fixed_t y) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: touch.motion id=%d x=%d y=%d\n",
            id, wl_fixed_to_int(x), wl_fixed_to_int(y));
    MouseEvent ev = {0};
    ev.x = wl_fixed_to_int(x);
    ev.y = wl_fixed_to_int(y);
    ev.buttons = 1;
    input_mouse_push(ev);
}

static void touch_frame(void *data, struct wl_touch *touch) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: touch.frame\n");
}

static void touch_cancel(void *data, struct wl_touch *touch) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: touch.cancel\n");
    MouseEvent ev = {0};
    ev.buttons = 0;
    input_mouse_push(ev);
}

static const struct wl_touch_listener touch_listener = {
    .down = touch_down,
    .up = touch_up,
    .motion = touch_motion,
    .frame = touch_frame,
    .cancel = touch_cancel,
};
```

### 14. Tablet Tool Callbacks (Stylus Support) - Stubbed
```c
// Stubs for tablet support (no protocol headers available)
static void tablet_tool_type(void *data, struct zwp_tablet_tool_v2 *tool,
                              uint32_t type) { (void)data; (void)tool; (void)type; }
static void tablet_tool_proximity(void *data, struct zwp_tablet_tool_v2 *tool,
                                   uint32_t serial, uint32_t time,
                                   struct wl_surface *surface) { (void)data; (void)tool; (void)serial; (void)time; (void)surface; }
static void tablet_tool_tip(void *data, struct zwp_tablet_tool_v2 *tool,
                             uint32_t serial, uint32_t time, uint32_t tip_state) { (void)data; (void)tool; (void)serial; (void)time; (void)tip_state; }
static void tablet_tool_pressure(void *data, struct zwp_tablet_tool_v2 *tool,
                                  uint32_t pressure) { (void)data; (void)tool; (void)pressure; }
static void tablet_tool_motion(void *data, struct zwp_tablet_tool_v2 *tool,
                                wl_fixed_t x, wl_fixed_t y) { (void)data; (void)tool; (void)x; (void)y; }
static void tablet_tool_button(void *data, struct zwp_tablet_tool_v2 *tool,
                                uint32_t serial, uint32_t time, uint32_t button,
                                uint32_t state) { (void)data; (void)tool; (void)serial; (void)time; (void)button; (void)state; }

static const struct zwp_tablet_tool_v2_listener tablet_tool_listener = {
    .type = tablet_tool_type,
    .proximity = tablet_tool_proximity,
    .tip = tablet_tool_tip,
    .pressure = tablet_tool_pressure,
    .motion = tablet_tool_motion,
    .button = tablet_tool_button,
};
```

### 15. Tablet Seat Callbacks
```c
static void tablet_seat_tablet_added(void *data, struct zwp_tablet_seat_v2 *seat,
                                      struct zwp_tablet_v2 *tablet) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: tablet_seat.tablet_added\n");
    (void)tablet;
}

static void tablet_seat_tool_added(void *data, struct zwp_tablet_seat_v2 *seat,
                                    struct zwp_tablet_tool_v2 *tool) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: tablet_seat.tool_added\n");
    zwp_tablet_tool_v2_add_listener(tool, &tablet_tool_listener, state);
}

static void tablet_seat_pad_added(void *data, struct zwp_tablet_seat_v2 *seat,
                                   struct zwp_tablet_pad_v2 *pad) {
    hosted_state_t *state = (hosted_state_t*)data;
    if (!state) return;
    fprintf(stderr, "Wayland: tablet_seat.pad_added\n");
    (void)pad;
}

static const struct zwp_tablet_seat_v2_listener tablet_seat_listener = {
    .tablet_added = tablet_seat_tablet_added,
    .tool_added = tablet_seat_tool_added,
    .pad_added = tablet_seat_pad_added,
};
```

## Global State Additions
```c
/* Keyboard focus tracking for proper Wayland protocol handling */
static bool g_keyboard_focused = false;

/* Pointer axis source tracking for scroll handling */
static uint32_t g_pointer_axis_source = 0;
```

## Key Principles

1. **Always use `data` parameter** - Cast to `hosted_state_t*` to access state
2. **Log for debugging** - Every callback should log its invocation
3. **Handle focus properly** - Track keyboard focus, clear state on leave
4. **Track modifiers correctly** - Use Wayland's `mods_depressed/latched/locked` protocol
5. **Reset state on leave** - Clear pointer position, buttons, modifiers on focus loss
6. **Use `(void)param` for truly unused params** - Only when parameter is genuinely not needed
7. **Wire listeners in `hosted_init()`** - After registry roundtrip, bind listeners to globals
8. **Cleanup in `hosted_shutdown()`** - Destroy all Wayland objects in reverse order