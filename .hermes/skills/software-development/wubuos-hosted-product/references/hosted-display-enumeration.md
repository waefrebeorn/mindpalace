# Display enumeration: hosted (X11/Wayland) vs bare metal (firmware)

Display information has exactly two legitimate sources on this project, and mixing
them produces a feature that works in one environment and silently returns nothing in
the other.

| Environment | Source of truth | APIs |
|---|---|---|
| Hosted (Linux desktop) | The host's display server | XRandR for outputs/modes/positions; `wl_output` events when nested under a compositor |
| Bootable image (bare metal) | The firmware / GPU | UEFI GOP mode list + EDID over the GPU bus; VBE mode list on legacy BIOS |

Never call an X11/XRandR path from kernel or boot code. It reports "no display" there
and looks like a legitimate answer rather than an unsupported call.

## Design rule: descriptors first, protocol second

Both sources should produce the same plain descriptor list (name, x, y, width, height,
physical size, refresh, connected, primary) with NO Wayland or X11 types in it. Then:

- advertising, tiling geometry, overview layout and a resolution menu all consume the
  list;
- the geometry rules (bounds across outputs, which output owns a point, primary
  selection) are unit-testable without any display server;
- a new source (GOP/EDID later) adds a reader, not a rewrite.

Keep the reader in its own leaf so a headless environment returns an honest failure
instead of inventing a zero-sized placeholder -- a phantom display is worse than none
because clients cannot tell it from a real one.

## XRandR specifics that cost time

- **Primary output comes from `XRRGetOutputPrimary(dpy, root)`, NOT from
  `XRROutputInfo`.** That struct has no `primary` member in current Xrandr; asking per
  output yields false for every display.
- **`connection == RR_Connected` is the authoritative "this is live" signal. Do NOT
  also require a CRTC.** A connected, configured output can legitimately expose
  `crtc == None` to a second client while driving the desktop -- requiring both hides
  the only real monitor and makes discovery return "nothing" on a working machine.
- **`XRROutputInfo.modes[]` holds XRandR MODE IDS, not pixel dimensions.** Reading them
  as widths produces absurd resolutions that still satisfy a `> 0` check. Resolve the
  id through `XRRScreenResources.modes[]` to get `width`/`height`/`dotClock`.
- When no CRTC is available, take the FIRST entry of `oi->modes` (preferred-first)
  and resolve THAT id, rather than guessing a resolution.

## Choosing an oracle for display tests

Parse the CLI tool's TEXT (`xrandr -q`) instead of calling the same library again. An
oracle that shares the module's code path agrees with it against a shared bug, and the
test passes while both are wrong. Assert against quantities whose real range you know
(resolution equals what the tool reports), never merely "non-zero".

When no display is reachable (headless session, unset `DISPLAY`), assert the HONEST
failure (-1, empty descriptor list) rather than skipping: a skipped test reads as a
pass in the log.

Note the practical limits of a single-monitor development box: it can prove "exactly
one output, correct geometry, disconnected ports excluded" but cannot prove
multi-monitor behaviour. Cover arrangement logic with synthetic descriptors in the
geometry unit gate, and say plainly which half is hardware-unverified.

## Binding protocol globals: a single pointer keeps only the LAST one

A client state struct holding ONE `struct wl_output *output` cannot represent more than
one display. Every `wl_registry` advertisement of `wl_output` OVERWRITES that field, so
on a two-monitor host only the last-advertised output is ever heard from -- and on a
single-monitor box everything looks correct, which hides the defect until real hardware
arrives.

- Keep an ARRAY of bound globals (`outputs[N]` + `n_outputs`), and key each listener by
  its own descriptor slot rather than a shared state pointer.
- Bind every advertised instance of a multi-instance global (`wl_output`, seats, ...),
  not just one. Protocol globals that are singletons (`wl_compositor`, `wl_shm`) are
  fine as a single pointer.
- Register the listener AT BIND TIME (in the registry handler): events can arrive
  before any later "finish setup" pass. A forward declaration of the listener variable
  may be needed when the handler appears earlier in the file than its definition.
- Release every bound resource in teardown; destroy listeners for all slots, not just
  the cached one.

## Events that arrive in bursts: commit on `done`

Geometry, mode and scale are sent as SEPARATE events, then `done`. A display read before
`done` is half-described -- using it early yields plausible-but-wrong values rather than
an obvious failure. Mark presence on `done`; until then the descriptor must not count as
a real display or be tiled onto.

For `wl_output.mode`, ignore entries without `WL_OUTPUT_MODE_CURRENT`: stale modes are
advertised too, and taking one gives a resolution the monitor is not running.
