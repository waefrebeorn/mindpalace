---
name: wubuos-display-stack
description: Use when working on WuBuOS displays or resolution.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [display, edid, gop, multi-monitor, wubuos, wayland]
    related_skills: [wubucompositor, wubuos-hosted-product, wubuos-wm, wubuos-wayland-migration]
---

# WuBuOS display stack

## When to Use

Adding or debugging anything about displays: monitor discovery, EDID identity,
multi-monitor geometry, resolution/mode reporting, window tiling across outputs, or the
host-side compositor's `wl_output` advertisement.

## The governing constraint: hosted is not the product

WuBuOS is a BOOTABLE image. On bare metal there is **no Linux, no X server, no
Wayland host** -- so any code that discovers displays through sysfs, `xrandr`, or
`/dev/dri` is **HOSTED-ONLY**. Never wire those paths into the kernel or firmware path:
they will report "nothing" and would look like a real answer if anyone trusted them.

The real bare-metal sources are the firmware interface (UEFI GOP mode list) and the
monitor's own EDID block read over DDC/CI. Everything downstream should consume a
source-independent descriptor so only the reader changes per environment.

## Layered discovery, best-first

1. **sysfs** (`/sys/class/drm/<card>-<connector>/{status,enabled,modes,edid}`) -- native,
   no subprocess. Identify a connector by WHICH FILES IT CONTAINS, never by matching the
   `cardN-*` name pattern: naming conventions move between kernels and vendors.
2. **`xrandr -q --props`** -- fallback when sysfs yields nothing. `--props` also carries
   the EDID in hex, so identity comes from the SAME parser.
3. **direct KMS** (libdrm: open the card, enumerate connectors, read the EDID property
   blob) -- needs only the device node; this is what `modetest -c` does. Enumeration
   only: never take DRM master in a read-only diagnostic.
4. **Bare metal**: UEFI GOP `QueryMode` records + EDID over DDC/CI. Decoder exists; the
   protocol invocation needs real firmware to verify.

All four feed ONE descriptor type and ONE parser, so callers never care which answered.
Report every connector found (including idle ports with no EDID): "port present,
nothing readable" differs from "no port", and dropping the former is how a scanner
reports one monitor where there are four.

## Rules

- **Cross-verify sources before believing either.** Assert that sysfs, xrandr and KMS
  agree on the connected panel's identity and preferred resolution. Make the oracle
  INDEPENDENT (parse `xrandr` TEXT; do not call the same library twice and call it a
  comparison).
- **Validate against REAL captured data**, not invented fixtures: capture an EDID from
  `/sys/class/drm/<conn>/edid` and an `xrandr -q --props` stream once, then embed them as
  golden fixtures. Real blobs carry the property noise that breaks naive parsers.
- **A tested module with no caller is a feature that does not exist.** Ship the tool or
  consumer (e.g. `make wubu-edid-dump`) alongside the parser; otherwise only the test
  suite can reach it.
- **Do not interpret raw flags for the user.** Report the kernel's `enabled` value
  verbatim under a neutral label; it reads disabled whenever the lid is closed or
  another session holds DRM master, which is a real state and not a failure. Point
  presence questions at `status`.
- **Never `read()` a DRM character device.** Opening it read-only for ioctls is
  correct; reading bytes from it blocks.

## Window tiling (Windows 11 parity)

Windows 11 offers SIX LAYOUTS of two-to-four UNEQUAL regions, not six equal zones:
halves; three columns; left half with the right split top/bottom; its mirror; four
quadrants; and a two-thirds + third pair. Geometry lives in the WM core as normalised
fractions (`wubu_snap_layout_*`), and the Win+Z flyout reads THAT SAME TABLE for drawing
and hit-testing -- the renderer cannot disagree with the snapping path about where a
region is. Clicking a region snaps into THAT region (Windows' "pick layout, pick spot"
collapsed to one click). Clamp edge-touching zones exactly: `(int)(frac*width)` summed
across thirds stops one pixel short and leaves a dead strip no window can occupy.

## Pitfalls

- **Map device surfaces AFTER `wubu_vmm_init()`.** The init RESETS the page-allocator bitmap; page-table pages allocated by `wubu_vmm_map_page` before it are handed out again and the surface #PFs the first time a task draws (measured: cr2=surface VA in vbe_clear). The Bochs LFB path only survives this by accident — its VA doubles as a demand-zero region that silently refills the clobbered PTE with RAM. Post-init allocations are bitmap-tracked.
- **Honest MMIO rendering under TCG is ~100x slower than RAM** (every pixel write is an uncached device exit). A render-loop heartbeat paced by full-frame redraws is NOT a reliable liveness oracle for a real-MMIO boot; use the supervisor's continuous promotions instead (run-agi.sh WUBU_AGI_LIVENESS=promoted), and give the boot window headroom (WUBU_AGI_BOOT_WINDOW).
- **EDID detailed-timing packs active-high and blank-high two-per-byte** (horizontal
  pair at offset 4 of the descriptor, vertical pair at offset 7), and refresh must be
  derived from clock and blanking. Reading them as separate fields yields plausible
  nonsense that still passes a `> 0` check.
- **Descriptor arrays hold IDs, not dimensions.** An output's mode list is an array of
  XRandR/KMS mode ids; resolve each id through the screen's mode table before using it
  as a width.
- **Monitor names often live in descriptor type 0xFE ("unspecified text"), not just
  0xFC.** Accept 0xFC first, fall back to 0xFE then 0xFF, or real panels report no name.
- **GOP stride != width.** `PixelsPerScanLine` may exceed the horizontal resolution
  because firmware pads scan lines; treating them as equal makes every blit walk off
  its row.
- **`status` answers PRESENCE; a CRTC does not.** A connected panel can legitimately
  have `crtc == NULL` -- another session holds DRM master, or the lid is closed -- and
  gating discovery on `crtc != None` (or on `enabled`) therefore hides the ONLY monitor
  on the machine and yields an empty desktop that looks like "no hardware". Accept any
  connector whose `status` says connected; let CRTC/encoder fields stay optional.
- **An `xrandr --props` EDID blob is terminated by the NEXT line's leading space, not
  by a byte count.** The block is a run of full-width hex lines, then a short line
  starting with `' '` (often the next connector's header). Two traps: consuming the
  first hex line BEFORE entering collection drops the first 16 bytes of every blob, so
  checksums can never validate; and swallowing the terminator eats the following
  connector. Parse it as a pending-buffer / `in_block` state machine keyed on the
  leading character, never on a count or on the previous line.
- **Advertise a MODE LIST with a flagged current mode, not one fixed resolution.** A
  client binding an output has nothing to choose without it, and a single hardcoded
  mode cannot express a panel's real capabilities. Flag the live mode `current` (and
  `primary`); when no CRTC is visible, flag the first entry so something is still
  advertised.
- **A comment containing `*/` ends early.** Glob characters inside a `/* ... */` path
  silently close the block and everything after compiles as code.

Wire-format offsets and field-by-field tables: `references/edid-and-gop-formats.md`.
