---
description: Use when building/debugging the WuBuCompositor compositor.
name: wubucompositor
---
# WuBuCompositor - own Wayland compositor (slerm'd, no wlroots)

Hand-written compositor for the wubu desktop client. libwayland-server (the wire-protocol machinery, NOT a compositor) + Xlib output + libxkbcommon keymap. All compositor logic (globals, surface/shm bookkeeping, xdg-shell role, seat, paint) is ours, for exactly one client, fullscreen.

Live: /home/wubu/wubucompositor (branch main), remote waefrebeorn/wubucompositor. Build `make` -> ./wubucompositor; nested run needs DISPLAY set; auto-launches the client (override WUBU_START_CMD). Deps: libwayland-dev, libx11-dev, libxkbcommon-dev, libxext-dev (XShm). Output is a FULLSCREEN override-redirect X window at the screen size, not a developer window.

protocols/ = wayland-scanner server bindings (server-header + private-code) on /usr/share/wayland/wayland.xml + /usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml.

## Guest launch: one owner (src/wcc_spawn.{c,h})

The spawn concern lives in its own leaf: `wcc_spawn_guest()` handles
WUBU_NO_SPAWN / WUBU_START_CMD and derives the default guest path from the
executable's own location — `/proc/self/exe` on Linux, `_NSGetExecutablePath`
(+ realpath) on macOS (`<exe_dir>/../wubuos/src/hosted/wubu`) — never add a
hardcoded absolute guest path back into the monolith. Headless gate:
`make test-spawn` (no X needed) drives the real fork/exec and the knobs.
`src/main.c` is the DEAD wlroots-era entry point, banner-marked LEGACY;
the Makefile builds only the slerm.

## Portability: the WSL-replacement seam

WuBuOS is the WSL replacement — develop in Linux, run in macOS. The guest
is a pure C11 Wayland client (host-agnostic); THIS compositor is the host
seam: X11 today, a Quartz/Metal backend replaces the host side tomorrow
with the protocol logic unchanged. Rules that keep the seam real:

- **No Linux-only headers in portable code.** `memfd_create`/`<linux/memfd.h>`
  are Linux-only — the keymap transport uses POSIX `shm_open` + immediate
  `shm_unlink` (the fd stays valid, no filesystem residue), which works on
  Linux AND macOS. Grep a change for `linux/`, `SYS_*`, `/proc/`, `/sys/`
  before calling it portable.
- **Executable-path derivation is per-host**: `/proc/self/exe` (Linux) vs
  `_NSGetExecutablePath` (macOS, may return a relative path — realpath it).
  The same pattern lives in the guest's buddy launcher (`hosted.c`); keep
  both branches when touching either.
- **Host-bound code lives in leaves, not the protocol core.** Split status:
  `wcc_spawn.{c,h}` (launch), `wcc_internal.h` (shared state), `wcc_gpu.c`
  (GLX present — first host leaf) are extracted; present/capture, seat,
  surface/globals, output, xdg, x11+entry are mapped in the wubuos census
  ledger (`docs/compendium/04-roadmap/hardcoding-census.md`). A second
  backend replaces host leaves; it must not touch protocol logic.
- The README carries the honest portability map (what is verified on Linux,
  what is compile-pending on a Mac, what is open). State plainly when a leg
  is not verified on its target host — do not imply end-to-end proof.

## Verify self (no ffmpeg needed)
`./wubucompositor --screenshot out.ppm` boots the client, captures its own window as PPM after 4 commits, and exits 0. Check the PPM isn't mono (a real desktop has 100s of colours).

**The palette assertion in `wcc_test.sh` is theme-dependent.** It currently
asserts the Win98 palette (192,192,192 window grey + 0,0,128 navy highlight).
Changing the product's default theme -- e.g. to the Win11-dark theme, whose
window face is 0x2B2B2B -- makes those exact-colour checks fail even though
the desktop is perfectly healthy. When the default theme changes, update the
assertion to the new theme's colours, or weaken it to "not mono + enough
distinct colours" and drop the exact palette. A red self-test after a theme
change is the assertion being stale, not a render regression.

## CI verify loops (free, agent-driven, live in .github/workflows/)

- `macos-verify.yml`: compiles the Apple branches on real macOS (Intel +
  M1 matrix) and runs `test-spawn` there — the only place the macOS
  branches are compile-verified. Phase 2 (full build via MacPorts wayland
  + epoll-shim) commented until the Quartz backend lands.
- `linux-verify.yml`: full build + spawn gate + Xvfb startup smoke
  (window + socket, WUBU_NO_SPAWN=1, no guest needed); phase 2 = full
  hosted e2e capture with the guest built from the sibling repo.
- The bare-metal side is proven by wubuos `boot-verify.yml` (one ISO
  booted under QEMU on Linux/Windows/macOS runners — see
  wubuos-interboot-deploy). Dossier + research: `wubuos/buy-wubu-a-mac/`.
- CI assertions must be machine-conditional (runners lack the sibling
  checkout); long runs: background `gh run watch`, poll the jobs API for
  step status. gh auth via stored git credential (waefrebeorn-repo-creation).

## Debug: capture a core, don't guess
A flaky SIGSEGV that hides under -O0/gdb (ptrace slows the inferior and changes timing) still fires under -O2 in the live session. Capture a real core, don't guess at the cause:
  sudo sysctl -w kernel.core_pattern=/tmp/wcc-core.%p       # sudo auth path in skill wubuos-sdcard-ds4-memory
  cd /home/wubu/wubucompositor && ulimit -c unlimited && ./wubucompositor   # let it crash
  gdb -batch -ex bt ./wubucompositor /tmp/wcc-core.*
Handle the forked client: it inherits your stdout, so redirect the compositor's output to a FILE (stdout=PIPE makes communicate() block on EOF forever).
Restore the system pattern verbatim after (sudo auth path):
  kernel.core_pattern=|/usr/lib/systemd/systemd-coredump %P %u %g %s %t 9223372036854775808 %h %d

## Boot path: tools/run-wubucompositor.sh (this is how the desktop runs)
The wubuos-side entry point is `tools/run-wubucompositor.sh [ -w W H ]` (also a
make target, size from $SIZE). It settles a clean desktop first (pkills stale
compositor + client, deletes stale `wayland-*` sockets so add_socket_auto names
fresh), then **`cd`s into the compositor directory** and execs the binary.

Consequence that bites every child process: anything the client spawns inherits
the COMPOSITOR's cwd, not the wubuos tree. A client-side `exec("./build/x")`
silently resolves to nothing there -- no error, just an absent process and an
absent window. Resolve executables from `/proc/self/exe` and walk up to the
project root, or take an explicit env override. See the buddy launch rules in
the `wubu-buddy-orb` skill.

## One client owns the output

The compositor AUTO-LAUNCHES the guest (`sh -c $WUBU_START_CMD`, default
derived from the binary's location by `wcc_spawn` — the sibling wubuos
checkout, never a hardcoded home path). **Never also start `./wubu` by hand** --
you get two clients on one seat and `tried to use an object from one client in
wl_keyboard.enter for a different client`. Run `./wubucompositor` alone; set
`WUBU_NO_SPAWN=1` when you want to start the guest yourself.

Ownership is `s->client`: the first client to bind `wl_compositor` wins, and a
destroy listener clears it so a replacement is accepted after a disconnect.
Every input send path is gated on `wcc_is_owner()`, and a non-owner's globals
bind to no-op implementations (no surface, no seat capabilities, no
`s->seat_res` theft).

**Do not refuse a client by posting an error and destroying it.** Tried both
inline and deferred via `wl_event_loop_add_idle`; either way the COMPOSITOR
segfaults at NULL+0x4 inside libwayland-server. Tearing a client down during
its own bind sequence walks libwayland's resource list mid-mutation. Refusing
by binding to no-ops gets the same effect -- the intruder can do nothing --
without touching that list.

## Pitfalls (each caused a real crash, verified by core dumps)
- xdg_wm_base.get_xdg_surface handler arg order is (client, resource, uint32 id, wl_resource surface) - new_id SECOND, not last. Reversed => the small id (0xb) lands in the surface slot and wl_resource_get_user_data segfaults. Read the generated signature in xdg-shell-server-protocol.h for every (new_id object) request.
- Version negotiation with the wubu client: advertise wl_compositor, wl_seat, xdg_wm_base at v1, wl_output at v2. Compositor v6 => client aborts 'listener function for opcode 9 of wl_surface is NULL'; wl_output v1 => 'have 1, wanted 2'.
- **wl_output is a GLOBAL -- one per display.** A single shared global means a client binding it once receives whichever monitor that global happens to describe; any other display is unreachable by construction. Give each monitor its own global carrying its own context, advertise ALL of its modes (advertising only the current mode is a readout, not resolution support), and track bound output resources in an ARRAY -- a single cached `output_res` dangles after a disconnect for every output but the last, which is the NULL+small-offset segfault class above. Depth and the descriptor model: `references/display-and-wl-output.md`.
- **XRandR is HOSTED-ONLY.** The bootable WuBuOS image has no Linux and no X server; bare-metal display information must come from the firmware interface (UEFI GOP mode list) plus EDID over the GPU bus, or VBE on legacy BIOS. Never wire XRandR discovery into the kernel path -- it reports "no display" and would look like a real answer. The source-independent EDID leaf is `src/kernel/wubu_edid.{c,h}`.
- wl_output_send_geometry args are (x,y,phys_w,phys_h,subpixel, make[], model[], transform): make/model are STRINGS, pass "" not 0 (else 'null value passed for arg 5').
- SHM: wl_display_init_shm(display) + wl_display_add_shm_format(display, WL_SHM_FORMAT_XRGB8888) is what makes wl_shm_buffer_get()/get_data work for client pools.
- Do not run `pkill -9 -f <compositor-name>` in the SAME command that launches it — `-f` matches your own shell's full command line and kills it. Use the `[w]ubucompositor` bracket trick (`pkill -9 -f '[w]ubucompositor'`) or do the cleanup as a separate, prior call.
- **A cached `wl_resource` needs a destroy listener.** Every resource the compositor caches (seat, pointer, keyboard, output, xdg_wm_base, wl_compositor, wl_surface, xdg_surface, xdg_toplevel) must be created with a destroy listener that clears the cached pointer. With a NULL listener the cache outlives the client, and the next `wl_keyboard_send_*` / `wl_pointer_send_*` dereferences a NULL interface pointer — SIGSEGV inside libwayland-server at a small fixed offset from NULL. Signature: the compositor is perfectly stable until the client is killed, then it dies on the next input event, so it reads as a client-disconnect bug rather than a cache bug. Clear the pointers only — do NOT free the shared surface object in the listener: wl_surface and the xdg resources share one user_data and destruction order is not guaranteed.

## Protocol pitfalls (each verified broken in the live product)
- `wl_pointer_send_motion()` and `wl_pointer_send_enter()` take `wl_fixed_t`
  (24.8 fixed point), NOT pixel ints. Passing raw `ev.xmotion.x` truncates to
  an int and the client's `wl_fixed_to_int()` divides by 256 -- the pointer reads
  as stuck at the top-left, so every click, drag, icon and shortcut lands in the
  corner while motion still looks like it works. Convert with
  `wl_fixed_from_double()`.
- Send `wl_keyboard_send_modifiers()` on every key press/release and on
  keyboard enter. Without it the client has no modifier state, so Ctrl/Alt/Win
  shortcuts are dead even though the keys themselves arrive.
- Send `wl_pointer_send_enter()` on button press as well as on motion. A click
  with no preceding motion event otherwise carries no position and lands at
  (0,0).
- Fullscreen output: create the X window with `CWOverrideRedirect` at
  `WidthOfScreen`/`HeightOfScreen`, and report that SAME size in
  `wl_output_send_mode()` and the xdg configure. A window smaller than the
  reported mode makes the client render at the wrong size and fires the resize
  path.
- XShm blit: `XShmCreateImage` + `shmget`/`shmat` + `XShmAttach`, and link
  `-lXext` (`pkg-config --libs x11 xext`). The XImage's own backing store IS the
  last-shown copy, so the present-on-change memcmp is free.
- Positioner requests: `set_anchor_rect` takes FOUR ints and `set_parent_size`
  takes TWO ints. A 2-int stub compiled into those slots is an
  incompatible-pointer-type warning that corrupts the call if a client ever
  opens a popup. Read the generated header for every request, not just the
  new_id ones.

## Present-on-change (anti-flashing)
In the commit handler copy the client buffer into a compositor-owned XImage, memcmp vs the last-presented copy, and SKIP the put when identical. Copy (never hand the X server a pointer into the client's shm pool, which the client may reuse on release) removed a class of flaky segfault. Flush, do not sync: `XSync` blocks until the X server has processed every request, adding a round trip of input latency to every repaint. Safety comes from owning the copy, not from syncing.

**The compositor re-reads the client's SHM buffer outside the commit handler** — the X `Expose` handler repaints from `surf->buf`. So copying into the compositor-owned XImage at commit time is necessary but NOT sufficient: the client must ping-pong two SHM buffers so the compositor never holds the buffer being rendered. Without that, the compositor catches the client mid-render and the tear reads as a band of background colour across the top of the screen (the client paints its desktop background row-by-row from the top). See `wubuos-hosted-product` for the client side and the measured artifact.

## GPU present (GLX) -- default path; XShm is the fallback
The compositor draws through the GPU by default: pick a GLX-capable visual,
upload the client's shm buffer to a texture, draw a fullscreen quad.  Link
`-lGL` and add `glx` to both pkg-config lines.

- **Choose the GLX visual BEFORE `XCreateWindow`.** A window created with
  `CopyFromParent` visual cannot be bound by `glXMakeCurrent`; the call fails,
  the code silently falls back to XShm, and nothing in the output says so.
  Call `glXChooseVisual()` first and pass its `visual`/`depth` into
  `XCreateWindow`, with a matching colormap and `CWColormap` in the attribute
  mask.
- **Client byte order is B,G,R,00.** WuBuOS writes `0x00RRGGBB`, so byte 3 is
  always zero.  Upload with `GL_BGRA` + `GL_UNSIGNED_BYTE` and leave blending
  OFF -- otherwise the unused alpha byte composites the whole desktop as
  transparent.
- **Verify with `GL_RENDERER` / `GL_VERSION`** (a 10-line GLX probe or
  `glxinfo -B`), not by looking at the screen: a silent fallback renders
  identically.
- Keep a compositor-owned last-presented buffer and memcmp against it.  The
  present-on-change rule below is just as cheap on the GPU path -- one memcmp,
  no upload on an unchanged frame.
- Set `glPixelStorei(GL_UNPACK_ROW_LENGTH, stride/4)` before `glTexSubImage2D`
  and reset it to 0 after, when the client's stride differs from `width*4`.

## Xlib: never let an X error kill the compositor; focus on Expose
- Install XSetErrorHandler that returns 0 (logs, recovers). Xlib's default handler calls exit(1) on a *transient* BadRequest/BadMatch -- e.g. XSetInputFocus right after XMapWindow, when the window is not yet viewable. That exit(1) surfaced as "the compositor died at startup", which made keyboard look broken (no compositor left to forward keys).
- Take keyboard focus on the FIRST Expose (window viewable then), not immediately after the async map. Raise the window there too.
- **Grab the keyboard too (`XGrabKeyboard`) or the host WM steals the Super press.** A nested compositor running under a desktop session receives the Super RELEASE but never the PRESS: the host's passive grab fires first, so Win+W / Win+Z / Win+L never arrive and every Win-key shortcut reads as broken while plain keys work fine. Call `XGrabKeyboard(xd, xw, True, GrabModeAsync, GrabModeAsync, CurrentTime)` on the first Expose. Signature: the client logs `evdev=125 pressed=0` with no matching `pressed=1`.
- With the error handler + focus-on-expose, both pointer hover AND keyboard navigation reach the client (verified by pixel diff on a Down-arrow changing the desktop). Without it the window never gets keys (motion needs no focus, keys do).

## Verify input transport at the code level, then stop

Pointer/keyboard/button events are verifiable WITHOUT pixels: trace the whole
chain and confirm each link matches. The compositor sends BTN_LEFT as
0x110 = 272; the client's handle_wl_pointer_button matches `button == 272`;
absolute motion is carried as surface coords with `dx=dy=0` meaning absolute;
the render loop maps the kernel mouse event to `wm_handle_mouse(x, y,
buttons, kind)` with `kind` taken from the event's own `MouseEvent.kind`
(0=move, 1=down, 2=up; -1 = derive from the button mask). Once every link matches by
code inspection, transport works even if a synthetic click opens no window —
the client's WM owns click-to-activate, so a probe that lands on a non-activating
control is client geometry, not a transport fault. Don't debug the client's
app-launch through the compositor; confirm travel and stop. To drive the client
programmatically, recompile the compositor with a `fprintf(stderr,"[wcc] ...")`
in the X event switch, rebuild, and check the log for the keycode/button arriving
— a one-line probe, no vision needed.

Verified valid: client binds all 5 globals, attaches 1024x768 framebuffer, reaches GUI mode, desktop painted + stable; pointer hover and keyboard nav both drive the client.

## Display support: what exists, what does not

Done: the guest models N displays from `wl_output` events (resolution, position,
scale, primary, virtual-desktop bounds) in `wubuos src/hosted/hosted_display.{c,h}`;
the compositor enumerates real outputs and their full mode lists via XRandR in
`src/wcc_monitors.{c,h}` and advertises one `wl_output` global per display.

Still open: wire-level confirmation that a client actually RECEIVES two distinct
outputs (booting a second compositor on `:0` would fight the running desktop);
a resolution MENU in the guest; and the BOOTABLE source (UEFI GOP + EDID reader)
producing the same descriptors -- XRandR here is hosted-only by design.

Say plainly when something is compiled and unit-tested at the descriptor layer but
not observed live. Do not imply end-to-end verification you did not perform.
