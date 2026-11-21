# Triaging a Wayland client that is dropped or shows black

Depth for the three contract rules in SKILL.md. Run these in order; each
step isolates one layer, and skipping ahead wastes time on the wrong layer.

## 1. Is the client even reading its socket?

A client that calls only `wl_display_dispatch_pending()` never reads. Its
events pile up in the socket buffer, `configure` is never acked, and the
compositor eventually drops it.

Symptom: the client renders happily for a few seconds, then
`Error sending request: Broken pipe`. The client's own trace shows only
outgoing requests and no `<-` events at all.

Check: `WAYLAND_DEBUG=1 ./client` and count the incoming event lines. Zero
`<-` lines while the compositor is clearly sending configures means the read
path is missing, not the protocol.

Fix: poll the display fd and dispatch when readable, non-blocking:

```c
struct pollfd pfd = { wl_display_get_fd(dpy), POLLIN, 0 };
if (poll(&pfd, 1, 0) > 0 && (pfd.revents & (POLLIN|POLLHUP|POLLERR))) {
    if (wl_display_dispatch(dpy) < 0) { /* compositor gone */ }
} else {
    wl_display_dispatch_pending(dpy);
}
wl_display_flush(dpy);
```

## 2. Is a request using a method the bound version does not have?

Symptom: the compositor logs `libwayland: error in client communication
(pid N)` (weston) or `wl_display@1.delete_id` followed by a disconnect.
The client keeps committing frames until EPIPE.

The client's trace does NOT show the error -- it shows the last request it
sent. Read the COMPOSITOR's log for the reason; read the CLIENT's trace for
the last request. Match them.

Common case: `wl_surface.damage_buffer()` is `since="5"` in the core
protocol. Binding `wl_compositor` at v1 and calling it is invalid even though
the compositor advertises v5. Bind the version you use, and gate the call:

```c
uint32_t want = version < 5 ? version : 5;
g_wl.compositor = wl_registry_bind(reg, name, &wl_compositor_interface, want);
...
if (wl_surface_get_version(g_wl.surface) >= 5)
    wl_surface_damage_buffer(g_wl.surface, 0, 0, w, h);
else
    wl_surface_damage(g_wl.surface, 0, 0, (int)w, (int)h);
```

## 3. Is a buffer attached before the configure?

Symptom: `xdg_surface@N: error 3: xdg_surface has never been configured`.

Order the client must follow: create surface + toplevel, commit once with
NO buffer, wait for `xdg_surface.configure`, `ack_configure(serial)`, then
attach and commit. Gate the attach on a flag set in the configure handler:

```c
static void xdg_surface_configure(void *d, struct xdg_surface *xs, uint32_t serial) {
    xdg_surface_ack_configure(xs, serial);
    g_wl.configured = 1;          /* a buffer may be attached from here */
}
```

## Verifying a nested compositor: do not trust X11 readback

When the client runs inside a nested compositor (weston's x11 backend,
Xephyr, cage), capturing the nested window with `xwd -id <wid>` on the
host X server is unreliable:

- **A full-screen lock screen on the host covers the nested window.** The
  capture shows the lock screen's dark background and nothing else. Check
  for a covering full-screen window before concluding the surface is blank.
- GL-composited windows may not be readable through X11 readback at all.

Reliable checks, in order:
1. The client's own buffer contents -- dump a few pixels from the SHM
   buffer in the frame path. If the expected colour is there, the client is
   correct and the pipeline is fine.
2. The compositor's log stays clean across many frames.
3. Capture from INSIDE the nested compositor, not from the host X server.
   With weston, XWayland listens on its own display (`:1`) -- but note that
   captures on that display show only X11 clients, not native Wayland
   surfaces.

A black capture of a nested compositor proves nothing until the covering
window and the readback path are both ruled out.

## Useful environment facts

- weston 13 nested in a window on an X11 session:
  `DISPLAY=:0 weston --backend=x11-backend.so --width=1280 --height=800 --xwayland`
  Clients then use `WAYLAND_DISPLAY=wayland-1` (the first free socket) and
  the same `XDG_RUNTIME_DIR`.
- `weston --help` has no `--screenshot` in 13; compositor-side capture
  needs the debug extension or a client that speaks it.
