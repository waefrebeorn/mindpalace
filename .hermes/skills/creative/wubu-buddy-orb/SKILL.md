---
name: wubu-buddy-orb
description: wubu_buddy as a live metaball shader orb.
version: 1.0.0
---

# wubu_buddy = live metaball orb (NO images)

User directive (2026-11-17): the buddy is named `wubu_buddy`, is a shader orb
built from metaballs, is live-sculpted and rendered, has a bounded render space,
and NO bitmaps.  Image pipelines are superseded -- do not resurrect sprite
sheets or reference-image rigs for the buddy.

## What exists
- `src/runtime/wubu_buddy_orb.{c,h}` -- opaque C11 core. Blob choreography
  (per-blob tilted orbit + breathing radius), field f=sum r^2/d^2, iso surface,
  `render_box()`. Form is a pure function of t -> reproducible.
- `tools/wubu_buddy_orb_demo.c` -- GLX 3.3 raymarcher + wire box; controls
  arrows/zoom/Space/Esc. Writes /tmp/bod_snap.ppm after ~1 s.
- `tools/xwd_to_png.py` -- real XWD reader.

## Build / run
```
make buddy                                # -> build/wubu-buddy
DISPLAY=:0 timeout 40 ./build/wubu-buddy  # snapshot in /tmp/bod_snap.ppm
ffmpeg -y -i /tmp/bod_snap.ppm /tmp/snap.png
```
The target compiles the four runtime sources FRESH: do not link the prebuilt
`src/runtime/*.o`, those are built with kernel flags and without `-Iinclude`
(so their headers fail). Manual fallback:
```
gcc -O2 -std=c11 -o /tmp/bod tools/wubu_buddy_orb_demo.c \
    src/runtime/wubu_buddy_orb.c src/runtime/wubu_buddy_emotion.c \
    src/runtime/wubutime.c src/runtime/wubu_posix.c \
    -Isrc/runtime -Iinclude -lGL -lX11 -lm
```
Gate: `make test_buddy_orb` (10 pass).

## Pitfalls measured here
- This box's X display :0 is only **320x200**; ffmpeg's xwd decoder
  mis-parses captures. Use glReadPixels snapshots + tools/xwd_to_png.py.
- The WM parks un-hinted windows at -10,-8 (off-screen); set XSizeHints.
- GPU entries: resolve with glXGetProcAddress; hand-written prototypes must be
  pointer typedefs (`typedef GLuint (*PFNglCreateShader)(GLenum)`).
- GLSL: `#define MAXB 16` must be injected into shader text -- C macros are not
  visible to GLSL.
- Raymarch speckle: raise min stride (~0.014) and hit epsilon (~0.0075).

## Mascot anatomy (procedural, no images)
- Author the figure as SDF: ellipsoid body (blobs still breathe it), head blended
  for a neck, `sdRoundCone` tapered ears, green crown cap + red W strokes,
  scarf band at head/body junction. Do NOT derive the head anchor from blobs.
- `hd` = uHead uniform is the head CENTRE (authored constant ~ (0,0.75,0)).

## SNAPSHOT ORIENTATION (cost several audit rounds)
`glReadPixels` returns rows BOTTOM-UP; writing them straight to PPM flips the
image vertically. Symptom: authored "up" features render at the bottom, so
every vision verdict is inverted. Emit rows reversed (top-down) before judging.

## Raymarch correctness (learned the hard way)
- `1/sqrt(field)` is NOT a distance estimator: it overshoots and punches false
  holes + contour banding. Use smooth-min SDF:
  `d = smin(d, length(p-c)-r*1.35, 0.62)`.
- Render offscreen into an FBO (960x540); this host's X screen is 320x200.
  glReadPixels -> PPM is the only trustworthy visual verification. `ffmpeg -i
  snap.ppm snap.png` then view that, never a window capture.
- Live sculpt keys: 1-9 select blob, w/s/a/d move, [ ] radius, r reset,
  Space freeze, Esc quit. Add noise bump to kill the sterile-plastic look.
- vision_analyze 429 is a fair-share limit: wait out retry_after, do not
  substitute numeric checks for the visual verdict.

## Emotion + time wiring
- `include/wubu_buddy_emotion.h` / `src/runtime/wubu_buddy_emotion.c`: reads
  coretemp, nvme, loadavg, GPU (env override else nvidia-smi cached 4 s) and
  maps heat+load into energy/stress/warmth/mood. Test: `make test_buddy_emotion`
  (the forced run proves thermal coupling).
- Shader reacts through uEmo = (energy, stress, warmth, mood): ears droop with
  stress, rim amber->hot red, eye shape per mood, hop with energy.
- Motion clock comes from WuBuTIME (`include/wubutime.h`), not libc timing.
- HUD prints live vitals every 1.5 s to stderr.

## wubu_posix / WuBuTIME (reuse, do not duplicate)
- `include/wubu_posix.h`: slerm'd C11 POSIX surface, no libc headers; x86-64
  inline-asm syscall traps with our own numbers. Files, dirs (getdents64),
  memory (mmap/mprotect), process ids, pipe/dup, clock/nanosleep all live here.
- `include/wubutime.h`: monotonic/wall via the layer above, epoch offset,
  civil calendar + ISO-8601 both ways, alarm wheel, TSC calibration, fixed-pool
  instances, hand-rolled number formatting.
- Gates: `make test_wubutime` (also compiles both .c with
  `-ffreestanding -nostdinc` = proof of zero libc header dependency).
- Gotcha: GCC's include dir is needed for stddef.h even under -nostdinc; scalar
  types come from __UINT64_TYPE__ etc. in freestanding mode.
- Comment gotcha: writing `hwmon*/name` inside a block comment TERMINATES it.

## Desktop launch
`src/hosted/hosted.c` main() calls `wubu_hosted_spawn_buddy()` right after the
boot-attestation publish: fork + setsid + exec of `build/wubu-buddy` as a
detached GLX child, so the orb lives in its own window beside the desktop.
Rules: `WUBU_BUDDY=0` opts out; a missing binary is a silent no-op, so `-h`
headless runs are unaffected; the prototype must sit ABOVE main() or C's
implicit declaration makes the later `static` definition an error.

### Never exec a relative path (the launcher owns the cwd)
The desktop normally boots through OUR compositor -- `tools/run-wubucompositor.sh`
(see the `wubucompositor` skill) -- and WuBuCompositor forks the wubu client
with **its own** directory as cwd. `./build/wubu-buddy` therefore resolves to
nothing there and the buddy silently vanishes (no process, no snapshot).
Resolve instead:
1. `WUBU_BUDDY_BIN` if set;
2. else `readlink(/proc/self/exe)`, then walk UP from the executable directory
   (<=5 levels) looking for `build/wubu-buddy` (`src/hosted/wubu` sits two
   levels below the repo root);
3. if nothing is executable -> no-op.
Keep the child's output when diagnosing: `WUBU_BUDDY_LOG=/tmp/buddy.log` redirects
the orb's stdout/stderr to a file; otherwise stdio goes to /dev/null.

Verified end-to-end on our compositor: `tools/run-wubucompositor.sh` -> hosted
-> `wubu-buddy` process -> fresh 960x540 framebuffer snapshot + live vitals log.
Caveat: X-level screen capture on this box returns blank frames, so prove the
composed scene by the orb's own glReadPixels dump plus process/window state,
not by capturing the root window.
