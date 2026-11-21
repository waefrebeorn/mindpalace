# Display enumeration, wl_output advertisement, and EDID parsing

The compositor used to advertise ONE hardcoded `wl_output`: geometry `0,0,0,0` and a
single fixed mode, whatever was plugged in. Clients therefore had no resolution to
read and nothing to choose. Three independent halves must all be fixed for real display
support: the guest model, the hosted compositor's output advertisement, and -- for the
bootable image -- the firmware/EDID source.

## Guest side (wubuos)

The client listened to `wl_output` but the handlers only printed to stderr and threw
the values away -- binding also overwrote a single pointer, so on a multi-monitor host
only the last-advertised display was ever heard from. Fixed shape:

- one bind per advertised global, keyed by registry NAME (not object pointer);
- each listener writes into a per-display slot in a plain descriptor model;
- a display counts as present only after its `done` event, because geometry and mode
  arrive as separate events before that;
- teardown releases every bound output and resets the model.

Model lives in `src/hosted/hosted_display.{c,h}` -- deliberately free of Wayland types
so the geometry rules (bounds across outputs, which monitor owns a point, primary
selection) are testable without a compositor. See `hosted_display_at()`,
`hosted_display_bounds()`, `hosted_display_primary()`.

Primary selection must not depend on enumeration order: if two displays claim the
origin, pick the one whose corner is NEAREST the origin and fall back to leftmost-
topmost. An order-dependent answer is a bug that only shows on some boot orders.

## Compositor side (this repo)

`src/wcc_monitors.{c,h}` turns "what is attached" into descriptors (name, position,
resolution, physical mm, refresh, connected, primary, plus a full mode list with the
live one flagged). Keep the protocol out of the descriptor list so a different source
can feed the same structs.

**`wl_output` is a GLOBAL.** Binding it must yield THAT output, not whichever one a
shared global describes. One global per display, each carrying its own context:

```c
typedef struct { struct wcc_server *server; wcc_monitor_t *monitor; } wcc_output_ctx;
wl_global_create(s->display, &wl_output_interface, 2, &s->output_ctx[i], output_bind);
```

Advertise EVERY mode, flagging the live one `CURRENT` and the first (preferred) one
`PREFERRED`. Advertising only the current mode is a readout, not resolution support.

Per-client resource tracking: a single cached `output_res` cannot track several bound
outputs, so after a disconnect all but one dangle -- the exact class that produces the
`NULL+0x53` segfault inside libwayland-server. Store an array and have the destroy
listener clear any matching entry.

## XRandR specifics that cost real time

- `connection == RR_Connected` is the authoritative signal. Do NOT also require a CRTC:
  a connected, configured output can expose `crtc == None` to a second X client while
driving the desktop, so requiring one hides the only real monitor.
- When no CRTC is visible, `oi->modes[]` still holds MODE IDS -- resolve them through
  `res->modes[]` for width/height/dotClock. Treating ids as dimensions passes any "> 0"
  assertion and yields absurd resolutions.
- If nothing gets flagged current (no CRTC seen), flag `modes[0]` to match the
  resolution already reported. Zero current modes tells a client "nothing is running".
- The primary output comes from `XRRGetOutputPrimary(dpy, root)`, not from
  `XRROutputInfo` (which has no such member on many versions).

## Bare-metal source: EDID (`src/kernel/wubu_edid.{c,h}`)

The right leaf for the bootable path: source-independent pure parsing, so the SAME
code consumes a blob from hosted sysfs (`/sys/class/drm/<card>-<output>/edid`), from a
bare-metal DDC/CI read over the GPU bus, or from a captured fixture in a test.

Base block (128 bytes) layout worth knowing before editing:

- header `[0..7]` = `00 FF FF FF FF FF FF 00`; version at `[18]` (1.x only -- CEA-861
  replaced this layout); checksum over all 128 bytes must be `0 mod 256`.
- manufacturer ID `[8..9]`: three 5-bit letters packed big-endian, each `+ 'A' - 1`.
- image size `[21]`/`[22]` in CENTIMETRES (multiply by 10 for mm; 0 means unknown).
- monitor name lives in one of four 18-byte descriptor slots at 54/72/90/108.
  **Type `0xFC` is the standard name, but panels very often put their MODEL STRING in
  `0xFE` ("unspecified text") instead.** Accept `0xFC` first, then `0xFE`, then
  `0xFF`. Reading only `0xFC` reports no name on real hardware.
  Text starts at slot byte 5 and ends at `0x0A`.
- preferred detailed timing descriptor 1 at bytes 54..71. The high bits are PACKED
  two-per-byte: horizontal pair at offset 4, vertical pair at offset 7:
  `h_active = t[2] | ((t[4] & 0xF0) << 4)`, `v_active = t[5] | ((t[7] & 0xF0) << 4)`.
  Treating them as separate bytes gives plausible-looking nonsense that passes weak
  assertions.

**Verification recipe that actually proves correctness:** capture a real panel's blob
(`/sys/class/drm/card1-eDP-1/edid`) and cross-check against `xrandr -q --props` for the
same connector -- monitor name, physical mm (EDID rounds to whole cm, xrandr does not),
and which mode xrandr marks preferred. Running the parser on this machine's eDP-1
yields `CMN`, `N156HRA-EA1`, 340x190 mm, 1920x1080 @ 144 Hz, matching xrandr exactly.
Synthetic vectors alone prove only that the parser agrees with itself.

Buffer hygiene: descriptor slot 4 spans bytes 108..125. A fixture helper that memsets
18 bytes at the wrong offset (e.g. 0x70 = 112) overruns a 128-byte buffer by two bytes
-- glibc aborts with "buffer overflow detected", which is the correct outcome for a
broken fixture.

## HOSTED-ONLY -- read before touching the bootable path

XRandR reads an X server under Linux. On the BOOTABLE WuBuOS image there is no Linux
and no X: display information must come from the firmware interface (UEFI GOP mode
list) plus EDID over the GPU bus, or VBE on legacy BIOS. Never wire XRandR into the
kernel path -- it reports "no display" and would look like a real answer.

Still unwritten on the bootable side: the GOP mode list reader and the DDC/CI blob
fetch. The EDID leaf above is the source-independent consumer they should feed.

## Verification limits

Do NOT boot a second compositor instance on a display the user is actively using: a
second fullscreen override-redirect surface fights the running desktop. State plainly
when the wire-level behaviour has been compiled and unit-tested at the descriptor layer
but not observed live, instead of implying it was verified end to end.
