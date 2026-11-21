---
name: wubuos-hosted-product
description: Use when building, running or verifying the hosted product.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wubuos, hosted, wayland, weston, verification]
    related_skills: [wubuos-wm, wubuos-qol-surface-audit, wubuos-test-suite]
---

# The hosted WuBuOS product

## When to use
- Building, running or debugging `./src/hosted/wubu` (the Win98/XP shell as a
  Wayland client on the host display).
- Verifying that a GUI change actually appears and works in the product, not
  just in a capture harness or a gate.
- Driving the desktop with synthetic input (clicks, keys) to test an input path
  end to end.
- Anything about frames being presented to the compositor (flashing, frozen
  window, a surface that renders but never appears).

The audit skill (`wubuos-qol-surface-audit`) finds the gap; `wubuos-wm` carries
the six-step wiring order for adding a surface. This skill is about running and
proving the product.

## Build and run

```bash
make hosted                                  # -> ./src/hosted/wubu
./src/hosted/wubu --screenshot out.ppm       # one real frame, headless
make window [SIZE=1280x720]                  # weston + the desktop in a window
```

## Answering "does the product work on Linux?"
Do not answer this from gates alone, and do not report a milestone as done
while the product has not been exercised. In this order:

1. Read the current HEAD and rebuild from it — a stale binary older than
   HEAD proves nothing about the tree you are claiming works.
   `make -j$(nproc) hosted` and check the binary timestamp.
2. Boot headless: `./src/hosted/wubu --screenshot <out.ppm>`; require a
   non-empty 1024x768 frame and the `WuBuOS running` log line.
3. Start the real window with `make window SIZE=1024x768`; confirm the
   client logs `Mode: GUI` and a live surface exists.
4. Run `make test_linux_product` (`tools/linux_product_gate.sh`) and require
   `PASS: 1 headless boot + 5 distinct real-GUI frames`.
5. Read at least the apps frame with the vision tool to confirm windows,
   taskbar and text are present; then kill the test weston/client by exact
   PID and remove the stale Wayland socket.

Re-run this whole sequence after every integration that touches the hosted
link, GUI, or runtime before making any claim about the Linux product. A
product check asked for explicitly takes priority over background audit or
child-leg integration; pause integration until it is green.

## The product compositor is OURS first
`make window` above is the weston FALLBACK / verification harness. The desktop a
user actually sees runs on **WuBuCompositor** (own slerm'd compositor, no
wlroots): `tools/run-wubucompositor.sh [WxH]` boots `src/hosted/wubu` fullscreen
inside it (`make compositor` is the target). When the user says "the compositor",
they mean ours -- do not propose weston as the product path.

Corollary that matters for any child process the product spawns: the compositor
forks the client from ITS OWN directory, so every path the product execs must be
resolved from `/proc/self/exe` (walk up to `<root>/build/<bin>`), never from `./`.
A cwd-relative path silently resolves to nothing there.

### A Linux X11 app window inside the compositor = the X server side
"Open a Linux window in the WuBu compositor" is the WSLg shape, and the tree
already does it through `src/hosted/wubu-weston.sh`: weston runs with
`--backend=x11-backend.so --renderer=pixman ... --xwayland`, so ordinary Linux
X11 applications can launch into the same compositor window beside the WuBuOS
surface. WuBuCompositor itself currently has NO X-server side (its `src/` is
only `main.c`, `wcc_monitors.*`, `wubucompositor.c`), so that capability lives in
the weston script today; extending our compositor means implementing the X side,
not the Wayland client path.

Search order before declaring a capability missing: `scripts/*.sh`, `tools/*.sh`,
`src/**/*.sh`, then the C tree. A feature that exists usually has a launcher
script written earlier.

`make window` runs `src/hosted/wubu-weston.sh`, which starts weston (X11
backend, pixman renderer) and runs the desktop inside it. The pixman renderer
is deliberate: it makes the window readable by ordinary X11 screenshot tools,
where the GL renderer returns black on readback.

Manual weston, when you need the env explicit:

```bash
DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 \
  weston --backend=x11-backend.so --renderer=pixman \
         --width=1024 --height=768 --socket=wubu-wayland &
WAYLAND_DISPLAY=wubu-wayland XDG_RUNTIME_DIR=/run/user/1000 \
  HOME=/tmp/<fresh> ./src/hosted/wubu -w 1024 768 &
```

Force first-boot behaviour with the SENTINEL, not a fresh `$HOME`: move
`$HOME/.config/wubu/onboarding` aside, boot, verify, and put it back. A fresh
home also lacks `settings.conf` (theme, preferences), so what you capture is not
the product a returning user gets. Either way the underlying rule holds -- an
existing sentinel silently skips the greeter, so every first-boot code path is
dead code on any box already booted once and must be FORCED to be exercised at
all.

## The render/present boundary -- do not cross it

**The renderer draws; the presentation layer decides whether to hand a frame to
the compositor.** These are separate concerns and must stay in separate modules.

- Render path: `hosted_run.c` -> `hosted_render_desktop()` -> `wm_render()`.
  Owns HOW the desktop is drawn. It must not know that frames can be skipped.
- Presentation: `hosted_wl_frame_render()` in `hosted_wayland_shm.c`. Owns the
  SHM buffers and the `wl_surface_commit()`. This is the ONLY place that may
  decide to present or not.

Putting a present-on-change comparison, a throttle, or a dirty check anywhere in
the render path intermixes two rendering policies in one function and breaks the
render contract (double-buffered VBE -> damage -> commit). The user's rule:
*you intermixed rendering policies and broke the laws of rendering*. If frames
must be committed less often, the decision belongs inside
`hosted_wl_frame_render()`, which already owns the buffers.

### The present-on-change implementation

`hosted_wl_frame_render()` keeps a shadow of the content it last presented and
skips `attach`/`damage_buffer`/`commit` when the current buffer is identical.
Measured on the real thing with `WAYLAND_DEBUG=1`: ~30 commits/s unconditional
-> **0.5 commits/s idle**, the residue being the taskbar clock.

### Presentation is DOUBLE-buffered, and must stay that way

The renderer draws into `g_shm_bufs[g_shm_render_idx]` and the index flips
after every commit, so the compositor only ever holds a buffer the client has
finished with. `hosted_run.c` retargets the VBE render surface each frame with
`vbe_set_render_target()` -- never `vbe_set_backend()`, which FREES the previous
surface and would free the SHM mapping.

**Do not collapse this back to a single buffer.** The compositor reads the
client's SHM buffer on its own schedule -- the commit handler, the X `Expose`
handler, and any repaint between them -- not only at the instant of commit.
With one shared buffer the compositor catches the client mid-render, and because
`wm_render` fills the desktop background first, row by row from the top, the
artifact is a band of background colour across the TOP of the screen that
appears and disappears with timing. Measured on the real panel: 31 px on the
XShm path, 217 px on the GLX path, roughly a third of frames in a 12-frame
burst. The second buffer costs no extra copy -- the client renders straight into
it -- so there is nothing to reclaim by going back to one.

## Driving the desktop with the injector

`src/hosted/wubu_inject` (`make wubu_inject`) sends XTEST events through the
host X server, so weston delivers them to the client:

```bash
./src/hosted/wubu_inject move 399 556      # move (root coordinates)
./src/hosted/wubu_inject click 1           # press + release button 1
./src/hosted/wubu_inject key Return
./src/hosted/wubu_inject type 'holyd hello.hc'
```

**Coordinates are ROOT, and weston's window has an origin offset.** The
injector moves the host pointer; weston's X11 window sits at some `+X+Y` in root
space (measured `+50+82` on one 1024x768 layout). Derive it every time:

```bash
DISPLAY=:0 xwininfo -root -tree | grep -i weston
```

Then `root = weston_origin + surface_position`. Getting this wrong makes every
click land somewhere else -- and the failure reads as "the click handler is
broken" when the handler is fine. Confirm by clicking and checking the WM's
received coordinates before blaming the hit-test.

Under WuBuCompositor (the product compositor) there is no origin math and no
injector needed -- `xdotool --window` takes window-relative coordinates:

    WID=$(xdotool search --name WuBuCompositor | head -1)
    xdotool mousemove --window $WID 36 132   # window-relative: no origin offset
    xdotool click 1
    xdotool key super+l
    gnome-screenshot -f out.png             # capture, then crop to the window

`--window` is the point: it resolves the window's absolute origin for you, so
the weston `+X+Y` derivation above is unnecessary. Verify a click landed by
diffing before/after captures, or by reading the client's own stderr log.

## The keyboard path: scancodes arrive, text widgets want ASCII

The hosted input layer translates X keycodes to **Set-1 PS/2 scancodes**
(`hosted_wayland_input.c`). The WM matches both forms in its hotkeys
(`key == 0x2C || key == 'z' || key == 'Z'`), but the text widgets -- the DOS
terminal, the Start-menu search -- test ASCII only (`key == '\n'`, `key == 8`,
`key >= 32 && key < 127`). With no translation, typing `not` into search
yields `1` (scancode 0x31 IS ASCII `'1'`) and the terminal accepts nothing.

`input_scancode_to_key(scancode, mods)` in `src/kernel/input.{c,h}` is the
single translation: ASCII for printable keys (Shift-aware), the matching
control code for Enter/Backspace/Escape/Tab/Space, and the scancode unchanged
for arrows and function keys. **Modifiers must return NO code at all.** They
have no text form, and their scancodes coincide with printable ASCII:
LEFTSHIFT is 0x2A = `'*'` and LEFTALT is 0x38 = `'8'`. Returning the raw
scancode made every Shift press type a literal asterisk -- "DOS Box" became
"*D*O*S *Box", corrupting every filename, search box and text field in the
product. Modifier STATE travels in the `modifiers` bitmask that the dispatcher
computes separately; it does not need to be a key press. The hosted path also
skips queuing any event whose translated code is 0.

**Filter to `KEY_EVENT_DOWN` at the dispatch** (`hosted_input_dispatch`). The
input queue holds both down and up and the WM is press-driven, so without the
filter a hotkey toggle fires twice (Win+W opens the widgets board and
immediately closes it) and a text widget appends twice (`not` becomes
`nno oott`). Key-up is not an event the WM consumes.

Reading the client's stderr key log: a steady flood of `key=0` is the AGI play
loop injecting game actions (`wubu_agi_play.c` sets `ev.scancode` only, leaving
`ev.keycode` zero). Treat it as noise when READING the log, but never leave that
loop injecting into a live desktop: `agi_act()` also pushes REAL mouse events,
and `AGI_ACT_FIRE` is a press with no release at the user's pointer -- so the
shell clicks, drags and closes its own windows while the user watches. Input
injection is opt-in via `wubu_agi_play_set_input_injection()`; the hosted
session calls it with 0 immediately after `wubu_agi_play_start()`. Signature of
the old behaviour: a window vanishes mid-typing, or a drag is stuck with no
button held.

## The agent channel into the window

The MCP server (`src/hosted/wubu_mcp.py`) runs on the HOST, not inside the
OS, so it cannot call the WM or any desktop API. It writes its requests into
the agent's own namespace -- `$HOME/.wubu/n/agent/` -- and the desktop acts
on them from the frame loop:

    hosted_agent_channel_poll()   src/hosted/hosted_agent_channel.c
                                  one concern: read the namespace, turn it
                                  into a desktop action. Never draws, never
                                  touches the render path.

    ~/.wubu/n/agent/buddy_state       mood name (work, error, success, ...)
    ~/.wubu/n/agent/open_walkthrough  flag file; the desktop clears it after
                                       acting, so a request fires once
    ~/.wubu/n/agent/speak             a vowel name (a e i o u); the desktop
                                       says it once through the device sink,
                                       then clears the flag

MCP tools: `wubu_buddy(state)`, `wubu_walkthrough(open)`, `wubu_state()`.
The namespace is the federation's agent surface, so any agent on any WuBuOS
box uses the same channel -- do not invent a side file for a new request.
The `speak` request needs the device sink open (the desktop opens it at boot);
with no backend it is a quiet no-op, not an error.

**The MCP and the desktop must share `$HOME`.** A host agent and a guest
desktop with different homes write and read different namespaces and silently
talk past each other; the tool reports success and nothing happens on screen.

## Baked art, and the one decoder the OS does have

The WM carries no runtime asset loader: desktop bitmaps (mascot, pets, icons)
are baked into C tables at build time and drawn through `vbe_*` -- the same
discipline as an embedded font. The `wubuos-wm` skill carries the extraction
pipeline and the blitter shape in ITS `references/baked-art-assets.md` (a
separate skill; not part of this one).

The OS DOES have a decode path, for USER images: `src/gui/wubu_image_ffmpeg.c`
adopts ffmpeg as the codec backbone (a subprocess speaking rawvideo/RGBA), so
a photograph can be a wallpaper and an agent can read a sprite sheet. BMP
keeps a native decoder so a bare-metal install with no ffmpeg still works;
everything else (PNG/JPEG/GIF/WebP/TIFF/AVIF) goes through ffmpeg. Do not add
a second hand-written decoder for a format ffmpeg already carries -- import the
backbone, do not reimplement it.

## Verifying a change in the product

1. Build, then capture a frame: `./src/hosted/wubu --screenshot /tmp/f.ppm`.
2. Convert with PIL and READ it (`Image.open(p).save(png)`), or use the vision
   tool on the PNG. Pixel-diff consecutive frames when the question is "does
   this animate / does this flicker".
3. For behaviour, drive it: move + click, then capture. A render-only check
   cannot prove an input path.
4. For the window, capture the weston window by id:
   `xwd -id $(xwininfo -root -tree | grep -i weston | head -1 | awk '{print $1}') -out /tmp/w.xwd`
   then decode the XWD header in Python (25 big-endian uint32s; pixel data at
   `header_size + ncolors*12`, row stride `bytes_per_line`).

ImageMagick is NOT installed on this box (`import`, `convert` absent); `xwd`
and PIL are. Under WuBuCompositor the desktop is one fullscreen
override-redirect X window, so `xwd -root -silent -out f.xwd` captures the
whole product in one shot and needs no window id:

```bash
DISPLAY=:0 xwd -root -silent -out /tmp/root.xwd   # ~8 MB for 1920x1080
python3 - <<'PY'                                  # decode to PNG, no ImageMagick
import struct; from PIL import Image
d=open('/tmp/root.xwd','rb').read(); h=struct.unpack('>25I', d[:100])
hsz,w,ht,bpp,bpl,bo,nc=h[0],h[4],h[5],h[11],h[12],h[7],h[19]
img=Image.new('RGB',(w,ht)); px=img.load(); off=hsz+nc*12
for y in range(ht):
    row=d[off+y*bpl:off+y*bpl+bpl]
    for x in range(w):
        i=x*(bpp//8)
        v=int.from_bytes(row[i:i+bpp//8],'big' if bo==0 else 'little')
        px[x,y]=((v>>16)&255,(v>>8)&255,v&255)
img.save('/tmp/shot.png')
PY
```

Reading the result: `vision_analyze` will tell you WHAT is on screen but is not
a measurement -- for geometry, scan rows/columns programmatically.

### Localising a display artifact to one of the three layers

A defect reported as "a bar across the screen", "flashing", "a frozen window"
or "it looks wrong" can originate in the client's render, in the presentation
handoff, or in the host. Three captures discriminate them, and a column
pixel-scan settles the artifact's true extent and colour.
`references/display-artifact-localization.md` carries the exact commands, the
burst-capture recipe for intermittent artifacts, and the two-buffer probe that
shows which buffer the compositor actually read.

## Pitfalls

- **A clean worktree cannot link `make hosted` until recipe-only objects exist.** The hosted recipe links `src/audio/wubu_audio*.o` and `src/runtime/oci/oci_*.o` that are NOT in its prerequisite list (same class as the documented HOSTED_LINK_ONLY fix), so a fresh tree dies with `ld: cannot find ...o`. Build them explicitly first (`make -j24 <the missing .o paths>` — grep them out of the link error), then `make hosted`. Also: an interrupted `git submodule update --init --recursive` (e.g. brain's vendored lean `.lake` packages have no URL) can leave OTHER submodules cloned-but-empty with HEAD already at the pin — the next non-recursive update skips them because the gitlink matches. Symptom: `git -C <sub> status` shows every file staged-deleted and the worktree is empty; fix with `git -C <sub> reset --hard HEAD`, then init nested submodules per-path (`-- src/gui/vws src/lua/www ...`) skipping brain.
- **The desktop PE path needs a REAL wine prefix and a sandbox wine can live in.** `hosted_pe_executor` -> GUI proton manager -> bwrap+wine. Three host-shape traps, each proven by a crash before the fix: (1) Ubuntu's `/usr/bin/wine` is a wrapper that demands wine32 for non-PE tools like `wineboot` — probe `wine64` in PATH AND `/usr/lib/wine/wine64` (libexec, out of PATH); (2) bwrap must bind `/tmp` (the staged PE), `/proc`, `/dev` and a WRITABLE `XDG_RUNTIME_DIR` — wineserver keeps its socket/lock there and aborts (double free) without it; (3) never `unlink` the staged PE before wine exits — the launch must wait, then clean up. Gate it with `make test_hosted_pe` (unit argv/prefix leg + full WUBU_ERA_WIN.OK marker leg through the DESKTOP executor).
- **A `:=` variable defined late in an included .mk is EMPTY in earlier rules' prerequisites.** `CACHE := build/testobj` sat at the bottom of tests.mk, so `$(CACHE)/x.o` in target PREREQUISITES expanded to `/x.o` ("No rule to make target") while recipes (lazy expansion) worked — clean-tree tier builds failed on objects that incremental builds already had. Define such vars in mk/vars.mk before any rule reads them; recipe-only object references still need to be prerequisites or make never builds them.
- **A vision model's description of a screenshot is NOT a measurement.** Asked
  for a caption bar height it will confidently answer "~30px" when the code
  says 32, and "16x16 buttons" when the code says 46x32 -- plausible, certain
  and wrong. Use the vision tool for "does this look broken / is anything
  clipped / is a colour wrong", never for "how many pixels". For geometry,
  either scan the pixels programmatically (a PIL row/column run over the PNG)
  or expose an accessor and assert it in a gate.
- **`input_mouse_push()` reads `dx == 0 && dy == 0` as an ABSOLUTE position.**
  A Wayland pointer handler that pushes button or motion events with `dx/dy`
  set but `x/y` left at zero is telling the input layer "the pointer is at
  (0,0)" -- so every click lands in the top-left corner and no key or click
  appears to work. Both handlers must push the pointer's absolute surface
  coordinates (`ev.x`, `ev.y`, with `dx = dy = 0`). Wayland reports absolute
  coordinates already; never accumulate from (0,0).
- **A stale weston shows a BLACK window and looks like a rendering bug.** After
  killing weston or the client, remove the socket and restart both:
  `rm -f /run/user/1000/wubu-wayland*`. A black frame with a live process is
  almost always a dead compositor, not a broken render path.
- **Several weston or client instances repainting one display cause visible
  flashing.** Kill by exact pid from `ps -eo pid,comm`, then start exactly one of
  each. Orphaned clients from earlier launches keep running with no compositor
  and are easy to mistake for the live one.
- **`pgrep -f "hosted/wubu$"` misses a binary invoked with arguments.**
  `./src/hosted/wubu -w 960 540` ends in `540`, not `wubu`. Match on
  `ps -eo pid,comm` (`comm` is `wubu`) or a looser pattern.
- **Never kill by a `-f` pattern that appears in your own shell command.**
  `pkill -f "src/hosted/wubu"` matches the shell running it and SIGTERMs your
  own session. Collect pids with `ps` and `kill` them individually, or use
  `pkill -x <comm>` (exact process name, e.g. `pkill -x wubucompositor`), which
  cannot match the shell. Note `pkill -f 'name$'` is the worst of both: the `
  $` anchor matches any wrapper whose command line ends in that path -- including
  the `sh -c` running your own `pkill`.
- **A surface can be created and drawn and still not appear.** Check the
  z-order first (`wubuos-wm`: creation order IS the z-order), then whether the
  presentation layer is skipping the frame.
- **Creation order IS the z-order.** A window created before the initial
  windows is drawn UNDER them. The first-boot greeter used to be created
  before `launch_app("My Computer")` / `launch_app("HolyC Terminal")`, so
  the desktop covered it and first boot showed no onboarding at all -- the
  greeter existed and was alive, just invisible. Create overlays last, or
  raise them explicitly.
- **Writing a setting to a file is not APPLYING it -- sign last, after the
  change is real.** A first-run/OOBE flow that writes the user's choice into a
  signature or sentinel while never calling the setter and never persisting
  through the settings object leaves the product running whatever the previous
  value was. The signature then claims a state that is not in effect: two sources
  of truth disagreeing about one visible setting, and the user's most prominent
  choice is decorative. Order that cannot lie: apply through the settings object
  (`*_mut()` + save), THEN write the record. Gate it by asserting the LIVE value
  changed, not just that the file exists.
- **A modal greeter hides whatever its own offer launches.** Taking an offer
  that opens a window must also close the greeter, or the window appears
  behind it and reads as "the button did nothing".
- **Draw desktop elements through `vbe_*`, never through the caller's `fb`.**
  `wm_render` can pass `fb == NULL` (the hosted path does, once the VBE is
  bound to the SHM surface). A draw callback that indexes `fb[...]`
  segfaults on the first frame; the greeter, the mascot and the walkthrough
  all use `vbe_*` for exactly this reason. The quieter form of the same bug is
  a GUARD -- `if (!win || !fb) return;` -- which draws nothing and does not
  crash: the window opens with its title bar and buttons (the chrome comes from
  `chrome_draw_window`, which uses `vbe->back`) and a blank body, so it reads as
  "this app is empty" rather than as a missing draw. Notepad and Calc ignore
  `fb` entirely; any new app draw path must too.
- **When the product segfaults, take a backtrace before reading code.** This
  host pipes cores to systemd (`core_pattern` -> `systemd-coredump`), so a crash
  leaves
  `/var/lib/systemd/coredump/core.<comm>.<uid>.<hash>.<pid>.<ts>.zst`
  even when `ulimit -c` is 0 in your shell. Decode only the newest one and hand
  it to gdb:

  ```bash
  zstd -d -f $(ls -t /var/lib/systemd/coredump/core.wubu.*.zst | head -1) -o /tmp/core.bin
  gdb -batch -ex 'bt 30' ./src/hosted/wubu /tmp/core.bin
  ```

  Cores are hundreds of MB and the guest heap dominates the dump, so decode one
  at a time and delete it after. One backtrace turned "clicking DOS Box kills
  the desktop" into `dos_win_draw ... fb=0x0` immediately; without it you will
  read render paths for an hour and guess. Do NOT run the client under gdb and
  drive it with synthetic keys -- the surface size differs between the two
  modes and the reproduction stops reproducing.
- **A GUI test asserting theme-derived pixels must call `wubu_theme_init()`
  first.** Without it every `wubu_theme_colors()` field is zero, so chrome
  fills, row backgrounds and text all draw black-on-black and a pixel-count
  assertion sees ONLY hardcoded colors (an 8x8 status dot = exactly 64
  pixels is the signature). `wm_init()` does not initialize the theme.
  Order: `wubu_theme_init(); vbe_init(w,h); wm_init(w,h);` then draw.
- **Fresh hosted worktree: the exact nested submodules to init.** Top-level
  `git submodule update --init <paths>` for everything EXCEPT `src/brain`
  recursive (its lean `.lake` packages have no URL); a NON-recursive
  `--init src/brain` is fine and needed (`src/brain/src/wubu_uuid.c` is
  compiled by hosted). Then the nested ones hosted compiles:
  `git -C src/gui/vws submodule update --init externals/wet`,
  `git -C src/gui/wet submodule update --init externals/wua`,
  `git -C src/lua/www submodule update --init '~WuBu~/src/lv'`.
  Missing them reads as `cc1: fatal error: .../wet_app.c: No such file`.
- **Assert on rendered pixels through `vbe_get_pixel`, and `vbe_init()`
  first.** The whole desktop draws through `vbe_*`, so the pixels live in the
  VBE back buffer -- hashing `wm_render`'s `fb` measures nothing. Without
  `vbe_init()` every `vbe_set_pixel` is a bounds-checked no-op, so every state
  renders identically and a "these states are different" test passes or fails
  for entirely the wrong reason.
- **Drawing lands in `g_vbe.back`, so you must clear it AND `vbe_swap()` before
  reading pixels back.** `vbe_set_pixel` writes the back buffer; `vbe_framebuffer()`
  returns the front. A test that memsets `fb` and compares after drawing is
  measuring an untouched surface and fails four checks for a reason that has
  nothing to do with the code under test. Set up: `memset(vbe_state()->back,
  0, stride*height); draw(); vbe_swap(); read fb`.
- **A dialog captured inside the weston window may belong to the HOST, not the
  product.** Before filing a product bug for a lock screen, an unlock prompt,
  a notification or an "are you still there" dialog, grep the WuBuOS source for
  its exact text (`grep -rn "<string>" --include=*.c --include=*.h src/`). If it
  is not there it is the host's -- Mint's `cinnamon-screensaver` keeps running
  after its gsettings are changed, and its window lands in the same capture,
  where it reads exactly like a product lock screen. Kill the host process;
  do not "fix" the product for it.
- **A product frame is not the gate.** Run the gate (`make -k -j24 test`) for
  regressions and the product for behaviour; neither substitutes for the other.
- **A gate's `-D` flag is not the product's backend.** Gate harnesses often
  compile the module with the feature macro explicitly, while `make hosted`
  selects a backend from a generated config where another backend can win by
  preprocessor precedence. After changing a default backend, grep the actual
  product compile command for the macro AND `nm` the shipped object for the
  banned symbols; then make the macro explicit in the product CFLAGS and give
  the intended backend precedence over detected alternatives. A green gate
  with the old backend still linked is a false closure.
- **A clamshell/lid guard can leave the X root smaller than the weston
  window.** With a 320x200 root and a 1024x768 weston window, `xwd -id`
  raises BadMatch and a root capture reads black. Treat that as a capture
  limitation, not a renderer failure; use `--screenshot` or the
  `gui_shot` frames as the product evidence and leave the host display
  settings untouched.
- **Parallel GUI gates must use per-process guest names.** The container
  Styx socket path is keyed by guest name, so two gates started by
  `make -j` with the same name steal each other's socket; the symptom is a
  click or relaunch that fails only in the full suite. Derive the test
  guest name from the PID, and wait for the old registry entry to be
  reaped (driving the state poll) before asserting a relaunch.
- **Do not force `-f png` on ffmpeg's encode side.** Distro builds differ:
  Ubuntu's ffmpeg carries no `png` muxer (only `image2`/`apng`), so
  `-f png` dies with "Requested output format 'png' is not known" while the
  same command without `-f` succeeds. Let ffmpeg infer the muxer from the
  output file's extension. Likewise get dimensions from
  `ffprobe -show_entries stream=width,height -of csv=p=0` -- never by parsing
  ffmpeg's stream banner, where the `WIDTHxHEIGHT` pair appears several times.
- **`popen` needs `_POSIX_C_SOURCE` -- which now means including the egojar.**
  A subprocess wrapper compiled with `-std=c11` and no feature macro gets an
  implicit `int popen()` declaration; the returned pointer is truncated and the
  process segfaults on first use, which reads as a bug in the wrapper's logic.
  Do NOT write the macro into the module -- that is exactly the scattered-flag
  practice the egojar exists to end. `#include "../egojar.h"` as the FIRST
  include of the .c (see the `wubunos-runtime-integrity` skill, which owns
  `references/egojar-posix-seam.md`).
- **A 0-height window is a stale binary, not a render bug.** `make window`
  failing with a 960x0 surface (the SHM mmap of a zero-height buffer fails)
  means the binary predates the fix. Rebuild before debugging the renderer.
- **The weston window origin offset is not a constant.** It moves with the
  layout and the compositor; derive it every time with
  `xwininfo -root -tree | grep -i weston` rather than reusing a value measured
  in an earlier session.
- **A hosted session must turn the guest screensaver and lock screen OFF.** The
  host desktop owns idle blanking and session locking; the guest saver dims the
  screen and shows a clock after its timeout and reads as "the screen went off
  and a clock lock came back", and the guest lock overlay swallows every key.
  `hosted_init()` calls `wubu_screensaver_set_enabled(false)` and
  `wubu_lock_screen_set_enabled(false)`; the bare-metal path keeps both. This is
  the product's own saver, distinct from the host `cinnamon-screensaver` dialog
  described above -- grep the product source to tell them apart before acting.
- **Display enumeration is HOSTED-ONLY when it reads X11.** XRandR answers "what is
  plugged into this Linux box"; the BOOTABLE image has no Linux and no X server, so
  the same call there always reports nothing while looking like a real answer. On
  bare metal the source of truth is the FIRMWARE: the UEFI GOP mode list for what
  resolutions the GPU can drive, plus EDID over the GPU bus for physical size /
  identity (VBE mode list on legacy BIOS). Split display code by ENVIRONMENT, never
  by convenience: a descriptor list produced by either source keeps everything
  downstream shared. If a display feature appears "working" only because the
  hosted path faked it, that is exactly the failure to catch before it reaches the
  bootable image. See `references/hosted-display-enumeration.md`.
- **Never call `wm_init()` from the xdg-toplevel configure resize path.** It
  `memset`s `g_dwm`, wiping every open window and desktop icon. Use
  `wm_set_screen_size()`, which re-anchors the buddy/rim/slime and re-lays out
  the existing windows in place.
- **Detach the VBE backend before destroying the SHM buffers on resize.**
  `vbe_shutdown()` `free()`s `g_vbe.fb`/`back`, which point at
  `g_shm_bufs[0].pixels` -- an `mmap` region that `shm_buffer_destroy()` has
  already `munmap`'d. Freeing it is an instant SIGSEGV. Save the backend pointer,
  NULL `fb`/`back`/`backend`, destroy the buffers, then `vbe_shutdown()`,
  `vbe_init()`, recreate the buffers and re-attach the backend.
- **Icon clicks must dispatch on the icon's TYPE, and every type constant must be
  READ somewhere.** `icon_add_ex(..., NULL)` registers icons without a per-icon
  closure, so the click handler decides what the icon IS; falling back to
  `launch_app(icon->name)` makes a shortcut try to launch something named after
  the FILE. `DESK_ICON_SHORTCUT` was written at its definition site and never
  consulted anywhere else, so double-clicking a user's own shortcut consumed the
  press, set drag state, and opened nothing. Grep each enum member for READS,
  not just definitions: a type that appears exactly once is dead.
  `desktop_launch_icon()` parses the shortcut's `.desktop` through the MIME layer
  and runs its Exec line; folders and files go to `wubu_mime_launch()`.
- **Remove per-frame `fprintf(stderr, ...)` from draw paths.** A diagnostic in a
  window's draw callback fires every frame for every open window; it is pure
  I/O latency and the log flood hides real messages. Keep the rare error-path
  prints, delete the per-frame geometry dumps.
- **A persisted setting overrides the code default.** `wubu_settings_init()`
  applies `settings_apply_defaults()` first and then lets the JSON override it,
  so changing `settings_default_theme()` alone changes nothing on a box that
  already has `~/.config/wubu/settings.conf`. Update the saved file too (or
  delete it for a fresh install) and verify by reading the live value, not the
  default factory. This applies to every setting, not just the theme.
- **`xdotool key --window <id>` sends XSendEvent, which a Wayland compositor may
  not forward; use plain `xdotool key` (XTEST) for keys.** Mouse move/click with
  `--window` is reliable, but synthetic key events can be swallowed. If a
  Win-key shortcut never fires while the same key typed into a host app works,
  suspect the injection method before the hotkey handler -- confirm by logging
  the keycodes the client receives.
- **A lowercase buffer filled by a loop must be NUL-terminated at the loop
  bound.** `buf[strlen(buf)] = '\0'` on a stack buffer that was never
  initialised reads garbage past the last byte written, so `strstr()` matches
  against junk and every search returns empty with no error and no crash.
  Terminate at the length you actually wrote (`buf[len] = '\0'`) and clamp
  that length to the buffer size. Same rule for any copy built byte-by-byte.
- **A screenshot tool grabs the pointer.** `gnome-screenshot` and friends take
  a grab; a mouse move + click issued immediately afterwards can land at (0,0)
  or not arrive at all. Move/click first and capture afterwards, or leave a
  gap. Signature: the client logs a click at (0,0).
- **A bare printable key must never be a system hotkey.** Once the input layer
  delivers ASCII, `key == 111` IS the letter `o`, `key == 0x57` IS `W`, and
  `key == 0x3F` IS `?` -- so "close window", "maximize" and "cycle theme" all
  fired in the middle of typing, and the app being typed into disappeared.
  A hotkey a user can hit by accident needs a modifier: Alt+F4 closes, Win+arrow
  snaps, Ctrl+T cycles the theme. Before shipping any text path, grep the
  dispatcher for `key == <value in 32..126>` comparisons with no `mods &` guard.
- **Terminate a terminal line at its LENGTH, not at the cursor.** A pty sends
  CRLF; a `\r` handler that resets the column to 0 before the `\n` makes the
  newline's `screen[row][col] = '\0'` land at index 0 and wipe the entire line.
  The shell runs the command, the pty returns the bytes, and the screen stays
  blank with no error -- the hardest kind of "the terminal does nothing".
  Write the NUL where the last character went (the put helper terminates the
  row itself) and let `\r` only move the cursor. Diagnose a parser that seems
  to drop data by dumping the raw bytes as hex (`%02x`): a `%s` log hides the
  ESC and CR bytes the parser is actually eating, so the data looks clean when
  it is not.
- **Clear the focus BEFORE launching from an icon click, not after.**
  `launch_app()` -> `wm_create()` sets `focused_id` to the new window; a
  `focused_id = -1` placed after the launch leaves nothing focused and the
  brand-new window never receives a key. Signature: the window opens, looks
  focused, and typing goes nowhere. When tracing it, log the launch and the
  focus change in one line each -- the order is the whole bug.
- **A child exiting 127 is NOT proof that exec failed.** `execvp` failure exits
  127 having written nothing -- but `/bin/sh` ALSO exits 127 for its own
  "command not found", and it writes that message to stderr on the way out.
  Treating every 127 as "could not start" discards the one line that explains
  the failure, so mistyped commands read as never having started. Distinguish
  by output: NULL only when the status is 127 AND zero bytes were produced.
  (`wubu_popen_read`, `src/runtime/wubu_spawn.c`.)
- **Never raise a host signal on behalf of a guest API call.** An exception or
  debug-hook handler implemented as `raise(SIGTRAP)` kills whichever process
  made the call -- here, WuBuOS itself -- instead of reporting an error. A
  capability you cannot honestly deliver returns a status code and says so in
  the commit body; it does not take the desktop down with it.
- **Run-dialog command output is a document, not a log line.** Capture both
  streams, write `$ <command>` + separator + output into a guest file, flush,
  and open it in Notepad. That makes the result survive like any other file and
  gives the user somewhere to put a real name. Sharing ONE executor between the
  Run dialog and shortcut Exec lines keeps the two paths from drifting.
- **One owner for geometry that is both drawn and hit-tested.** Expose a single
  accessor (e.g. `chrome_button_rects()`) and make the renderer AND every
  hit-test call it. Three copies of the same title-bar button rect drifted by
  2px and 4px, so Close/Maximize were drawn in one place and clicked in
  another -- which reads as "the button does nothing" rather than as a
  geometry mismatch. Measure the drawn rect from the framebuffer and compare
  it to the hit-test rect before blaming the handler.
- **Pointer motion is a MOVE, not a press -- give the event its own kind.**
  Deriving the WM's `kind` from the button mask (`buttons ? 1 : 2`) makes every
  drag look exactly like a fresh press, because a motion with a button held has
  the same mask as the press that started it. The WM sets `drag_id` on a press
  and only MOVES the window on kind 0, so title-bar dragging then does nothing
  while the release re-anchors the window under the cursor. Carry an explicit
  `kind` on the mouse event (0=move, 1=down, 2=up; -1 = derive) and tag pointer
  motion as a move at the source. Signature: the window will not follow the
  pointer, but clicking its buttons still works.
- **Throttle the render loop when idle; do not redraw at full rate forever.**
  A full-rate redraw of a 1080p desktop pins a whole core, and the box runs hot
  for no visual benefit. Drive the frame period off input freshness: full rate
  (60 fps) while events are arriving -- input is sampled once per loop, so the
  loop rate IS the input latency -- and a reduced rate (~20 fps) after ~1.5 s
  idle, which still keeps the clock and any animated mascot alive. Measured
  82% -> 30% CPU. Guard the idle path by confirming the clock still advances on
  screen, or the throttle silently freezes the one thing that proves it works.
- **The guest filesystem has ONE owner per API, but there are currently TWO
  stores.** The namespace array (`g_fs`) belongs to
  `src/hosted/hosted_styxfs.c`; applications reach it only through
  `src/apps/guest_file.h` -- `guest_file_read/write/exists`, nothing else, and no
  host types in that header. Do not let Paint, Notes or Notepad grow their own
  lookup of the array.
  BUT a second implementation exists: `src/runtime/styxfs_host.c` maps Styx paths
  onto host directories (`styxfs_opendir` -> `styxfs_path_to_host`), and Explorer
  browses THAT. So Explorer cannot see what Notepad saved until the two are
  unified under one root -- see `references/guest-filesystem.md`. When an app
  "does nothing" with its files, first establish WHICH store it talks to.
  Names are FLAT strings matched literally (`notes/todo.txt`) because the
  namespace has no tree yet; interpreting `/` belongs in that one place, not in
  every editor.
  `references/guest-filesystem.md` carries both stores, the wire format, the
  failure policy and the durability rules.

- **A server callback that is not wired is a silently missing capability.**
  `styx_server_t` declares attach/walk/open/read/write/clunk/remove/stat/wstat,
  but only the first five were ever assigned -- so the filesystem was strictly
  READ-ONLY no matter what the Explorer offered, and writes had nowhere to go.
  Worse, `styx_stat_cb` forgot `dir->length`, so EVERY reader believed every file
  was zero bytes long while read itself worked fine. When auditing a server,
  print the whole callback table and confirm each member is assigned OR
  deliberately NULL; a NULL member reads as "unsupported" only if you know it
  is NULL.

- **Durability is a separate step from writing, and it must be loud on failure.**
  A mutation marks the namespace dirty; `hosted_fs_flush()` performs the disk
  I/O on clean shutdown. Never save inline inside a Styx callback -- that puts
  file I/O in the message-dispatch path. And a FAILED save must be reported
  rather than swallowed: continuing quietly tells the user their work is safe
  when it is not.

- **Load a durable image into a scratch buffer and commit only on full
  success.** A half-loaded namespace is worse than no load -- the desktop shows
  files whose contents do not exist. Refuse bad magic, a truncated header, a
  truncated record, a count beyond capacity, an oversized data_len, an unknown
  qtype, and a name with no terminator inside its field. Reserve 0 for a
  MISSING store (first boot is not an error) and -1 for a CORRUPT one; keep the
  live namespace untouched in the latter case.

- **Writing past EOF must extend, and a write that cannot fit exactly must be
  refused.** Truncating a write to fit leaves the client believing the file holds
  bytes that are not there. Note the boundary: a write of exactly the buffer
  size at offset 0 FITS -- probe one byte past it in tests instead of assuming.

- **Kernel sources linked into hosted tests lack the metal-only objects.** A
  reference added to `src/kernel/interrupt.c` (e.g. `lapic_eoi()`,
  `lapic_timer_init()`, any `apic_*`) builds fine for the product but breaks
  GUI-tier targets that compile `interrupt.c` WITHOUT `interrupt_apic.c`:
  `undefined reference to lapic_eoi` in `test_first_run`, `test_wet_applet`,
  `test_vws_designer`, `test_tutorial`. Guard every such symbol with
  `#ifdef MYSEED_METAL` in the kernel source (the PIT handler stays shared), and
  re-run those four targets after touching interrupt code -- the full gate
  catches it late, one target at a time.
- **A new module the WM calls must be reachable by EVERY test target that
  links the WM.** Adding `run_dialog.c`/`win11_widgets.c` to `GUI_OBJS` is not
  enough: `mk/tests.mk` links `wm_input.c`/`wm_render.c` in a dozen separate
  recipes, and the link fails one target at a time. Add weak stubs to
  `wm_test_stub.c` AND to the handful of `src/apps/*_test.c` files that carry
  their own startmenu stubs instead of linking it -- those are the ones the
  stub file does not rescue. Cheaper than chasing targets: make the new module
  weak-callable at the WM boundary.
- **When an application gains a real dependency, every target that links that
  app must link the dependency too.** Giving Notepad a file API broke
  `test_apps` (`undefined reference to guest_file_write`) even though the
  product built fine, because that recipe compiles `notepad.c` without the
  hosted layer. Fix the link graph in the same commit as the dependency; do
  not leave the product green and a gate red.
- **New test files under `src/` are GITIGNORED.** The pattern `src/*/test_*`
  in `.gitignore` catches every test placed next to its module, so a brand-new
  test silently never reaches a commit. `git add -f` it, and mention the force
  in the commit body so the next reader does not think it was omitted.
- **A test written against a STUB's fabricated values asserts the stub, not
  the product.** When a test target links a hand-rolled stand-in for a module
  it does not build (an in-mem `chrome_draw_window` returning `0,0,100,100`,
  a fake `wm_init`), any assertion about that module's OUTPUT encodes the
  stand-in's made-up numbers. Linking the real module -- which you must, once
  the real one defines a symbol the test also defines -- then fails the test,
  and the fix is to the TEST, not the code: derive the expected value from the
  real API (`chrome_draw_window(win, ...)`) instead of a literal. Symptom: a
  caret/label/hit-test lands at 0,0 or at the stub's rect while the real
  geometry is elsewhere. Before "fixing" the product to satisfy such a test,
  check whether the test's expected numbers came from a stub.
- **A stub and the real module in one link must not both define the symbol.**
  "multiple definition of `chrome_draw_tabs`" means the test carries a strong
  stand-in for something now linked for real. Mark the stand-in
  `__attribute__((weak))` so the real definition wins, and leave a comment
  saying why -- the next reader will otherwise "clean up" the weak and
  reintroduce the collision.
- **A registry/name lookup that is case-sensitive makes typed input silently
  fail.** `app_find_by_name()` used `strcmp`, so a run dialog that accepted
  "notepad" resolved nothing and closed with no error and no window. Users
  type what they see; match exact first, then case-insensitively. Verify a
  name-driven launch with the name in a DIFFERENT case than the registry key,
  or the bug ships.

- **When EVERY instance of a class of output looks wrong -- including strings
  hardcoded in the source that nobody typed -- the defect is in the SHARED
  RENDERER, not in whatever produced the data.** The whole OS rendered in
  capitals because the UI font is a 64-glyph table covering ASCII 32..95 only;
  with no lower-case glyphs to draw, `vbe_draw_char()` folded `a-z` upward. A
  capture showing `ECHO HELLO` for lower-case keystrokes reads exactly like an
  input bug -- until you notice the dialog's OWN hard-coded instruction string
  is also capitals. Diff a CONSTANT against typed input first; it is the
  cheapest discriminator between "the bytes are wrong" and "the pixels are
  wrong". Corollary for the fix: keep the two glyph tables separate rather than
  merging into one 96-entry table -- merging shifts every existing index and
  silently changes what each upper-case glyph draws. When a glyph-level claim
  matters, assert the drawn cell against the table entry pixel by pixel
  (`make test_font_case`), not by eye.
