---
name: c-glx-rendering
description: Build/verify standalone C GLX OpenGL apps on this Mint box.
version: 1.0.0
author: Hermes Agent
license: CC-BY-4.0
metadata:
  hermes:
    tags: [glx, opengl, c, screensaver, cinnamon, headless-verification]
    related_skills: [claude-design, p5js, linux-shell-terminal-setup]
---

# C GLX rendering (standalone OpenGL apps / screensavers)

## When to Use
Trigger when you must build any standalone C program that opens its own X11/GLX
window and renders OpenGL (a custom screensaver, a fullscreen viz, an idle
demo), or when you need to prove a GL render works without being able to view
the screen. Also the reference for the Mint/Cinnamon screensaver + lock
settings.

For building a single-file C program that opens its own fullscreen GLX window
and renders with fixed-function (GL 1.x) OpenGL on the Mint/Cinnamon box, and
verifying the render without a viewable screen.

## Build without dev packages
- Only incompatible headers are required. Here they exist: `gl.h`, `glx.h`,
  `Xlib.h`. NO `glu.h` — so write pure core GL (use `glFrustum`/`glOrtho` for
the projection, never `glu*`).
- Link against versioned runtime libs instead of `.so` dev symlinks so no
  `-dev` packages are needed:
  `gcc -O2 -o app app.c -l:libGL.so.1 -l:libX11.so.6 -lm`
- `glXCreateContext`/`glXMakeCurrent`/`glXSwapBuffers` come from `libGL.so.1`
  on Mesa (GLX lives in libGL, not a separate lib). No `-lGLU` at all.

## Fullscreen GLX window skeleton (the parts that bite)
- Create with `override_redirect=True` + full `DisplayWidth/Height`, map,
  then `glXMakeCurrent`; double-buffer visual via `glXChooseVisual` attrs
  `GLX_DOUBLEBUFFER|GLX_RGBA|GLX_DEPTH_SIZE,24`.
- Loop: drain X events, animate from `CLOCK_MONOTONIC`, `render()`, then
  `glXSwapBuffers`. `XGrabKeyboard` on the root so a keypress offers an easy
  exit. No WM involvement needed.
- See `templates/glx_fullscreen.c` for a working skeleton.

## PITFALL: glColor is IGNORED while lighting is on
In fixed-function GL, with `glEnable(GL_LIGHTING)`, per-vertex `glColor*` does
NOT color the object — the material (default gray) does. So the model renders
invisible/gray even though every color call looks right. Fix: set material per
object inside your draw routine:
```c
GLfloat mat[4]={(GLfloat)R,(GLfloat)G,(GLfloat)B,1};
glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, mat);
// plus optionally GL_SPECULAR + GL_SHININESS for a shiny rubber look
```
Starfield/nebula billboards drawn with lighting disabled can keep using glColor.

## Modern-GL path (this box: OpenGL 4.6 core, Mesa 25.2, GLSL 330 available)
For a real shader pipeline instead of fixed-function faking: create a core
profile context and write GLSL. Key facts proven on this host:
- **Create a 3.3+ core context**: `glXChooseFBConfig` (attrs
  DOUBLEBUFFER|RGBA|DEPTH24) + `glXCreateContextAttribsARB(dpy, fb, 0, True,
  {GLX_CONTEXT_MAJOR_VERSION_ARB,3, GLX_CONTEXT_MINOR_VERSION_ARB,3,
  GLX_CONTEXT_PROFILE_MASK_ARB, GLX_CONTEXT_CORE_PROFILE_BIT_ARB, None})`,
  visual via `glXGetVisualFromFBConfig`, make current with
  `glXMakeContextCurrent`. GLX_ARB_create_context is on this Intel/Mesa box.
- **PITFALL: glxCreateContextAttribsARB MUST get a proper prototype.**
  glxext.h gates it behind version macros so it is not declared; calling it
  implicitly-declared (returns `int`) TRUNCATES the returned pointer on x86-64
  (caller reads %eax). Add `extern GLXContext glXCreateContextAttribsARB(
  Display*,GLXFBConfig,GLXContext,Bool,const int*);`.
- **PITFALL: Mesa's gl.h declares only GL1.x prototypes; glext.h skips the
  2.0-4.6 entry points** because gl.h already defines the GL_VERSION_n_m
  macros, so `glCreateShader`/`glGenVertexArrays`/etc. are NOT declared even
  though libGL.so.1 exports them. Add the handful of prototypes you use
  (`glCreateShader`, `glGenVertexArrays`, `glBufferData`, `glUniform*`,
  `glActiveTexture`, ...) with `GLAPI ... APIENTRY`. Canonical signatures.
- **Immediate mode is gone in core**: no `glBegin/glVertex/glColor/glMaterial`;
  use VAO/VBO/EBO, `glVertexAttribPointer`, `gl_DrawElements`. Per-vertex
  colors are attributes; per-part material goes in a uniform set each draw.
- **Text**: rasterize your embedded 5x7 glyphs into a GL_R8 texture atlas,
  sample bilinearly (LINEAR) for crisp anti-aliased text at any size; radix
  one UI shader (`uUse` uniform: 0 = flat color quads, 1 = sample atlas).
  Two dynamic VBOs (text-textured, flat-color) keep the passes unambiguous.
- **Per-open Linked glsl**: `GL_PROGRAM_POINT_SIZE` + `gl_PointSize` in the VS
  makes GL_POINTS into variably-scaled sprites; radial falloff in the FS
  (`gl_PointCoord`) fakes soft glows/stars/nebula with additive blending.
- Blinn-Phong per-pixel: pass light arrays + camera pos as uniforms; a back
  light at larger |z| than the object gives the Fresnel-rim edge glow.
*The fixed-function notes below still hold for a compatibility-context fallback;*
both rendering paths were verified on this box.

## Zero-sudo idle screensaver via the MIT-SCREEN-SAVER X extension (libXss)
When you cannot install XScreenSaver (no sudo), drive the screensaver yourself
with a tiny user-level daemon that polls input-idle and spawns/kills your app:
- Link the runtime lib only: `-l:libXss.so.1` (no -dev). Header is absent on
  Mint; declare the API yourself. **CRITICAL: `XScreenSaverInfo` field order is
  `state, kind, window, til_or_since, idle, eventMask`** — putting `window`
  before `kind` makes you read eventMask as idle (constant 0). idle is ms.
- **Idle reads 0 forever unless the server's own screen-saver timer is on.**
  If `xset q` shows `timeout: 0`, call `xset s 6000 0` once so the extension
  accrues idle (100-min timeout, so Xorg never actually blanks).
- Idle loop: poll `XScreenSaverQueryInfo(dpy, root, info)` each ~1 s; when
  `idle >= threshold` fork+exec your fullscreen app; when idle drops below
  ~80% of threshold (hysteresis), SIGTERM the child and waitpid. Reap on
  SIGCHLD; ignore X errors with `XSetErrorHandler`.
- While your app runs, `xset -dpms s off` keeps the panel/monitor awake;
  restore `xset s on +dpms` when you hide it (check `command -v xset`).
- Autostart at login without root: a `~/.config/autostart/*.desktop` whose
  `Exec=` is the watcher binary (DISPLAY is already set at login).
- To test hide-on-activity headlessly, inject a pointer tick: declare
  `extern int XTestFakeMotionEvent(Display*,int,int,int,unsigned long);` and
  link `-l:libXtst.so.6` (no header needed) to reset the idle counter.

## Visual design: give a screensaver a HOUSE system, not rainbow-shine
The classic mistake that reads as "AI slop" is coloring EVERY UI element with
the per-scene theme (text, banners, progress bars, vignette all tinted). Fix per
the Anthropic frontend-design/brand/theme-factory skills: spend boldness in ONE
place. Concretely over the HUD:
- **Fixed neutral ground**: deep cool near-black clear + warm off-white text
  (~0.94,0.92,0.88), a muted ~0.62 neutral for secondary labels.
- **One accent** (e.g. amber ~1.0,0.74,0.30) reserved for the single memorable
  element (saga title, active storyboard frame, progress fill). Keep it out of
  every other UI element.
- **Second hand-cold color** (0.55,0.75,0.95) for one subtitle role.
- **Per-scene color only where it carries meaning**: the speaking character's
  name and the environment (nebula/planet). Do NOT tint generic text/panels.
- **Atmosphere beat flat color**: a subtle per-frame film grain (150-250
  randomised 1px squares, alpha ~0.05) + a deeper vignette (~0.36) over a
  vertical sky gradient makes it feel graded, not flat. Bars/panels stay in
  neutral while only the accent pops.
Give it a nameable theme ("Midnight Galaxy / golden amber on deep blue").

## Retime a story screensaver by CUTTING beats, never dwell
Compressing a long-form story to a short run compresses the per-beat dwell in
proportion, and below ~4 s a line becomes unreadable — a real bug, not style.
When a saga/act is short (<60 s), drop the NUMBER of displayed beats (show 4
of N) so each keeps ~4 s on screen; reveal all on long runs. Verify a live
frame that beats are readable after retiming. Cheap "epic" polish that helps: a
thin cinematic letterbox, a short amber/white flash (~1.5 s) at each chapter
boundary, and a chapter card that crossfades in/out instead of snapping.

## PITFALL: lit model can read DARK because light sits behind the camera
With a key light positioned in world space (e.g. at +z ahead of the camera),
the camera-facing side of a sphere/duck can fall in shadow and render as a
dark, muddy version of its color — it renders, but is almost invisible.
Fix: keep a dim *headlight* at the viewer so the facing side is never black.
```c
float hd[4]={0.40f,0.38f,0.30f,1}, hp[4]={0,0,0,1};   /* w=1 = positional at origin = at camera */
glEnable(GL_LIGHT3); glLightfv(GL_LIGHT3,GL_DIFFUSE,hd); glLightfv(GL_LIGHT3,GL_POSITION,hp);
```
Also raise `GL_LIGHT_MODEL_AMBIENT` (e.g. 0.36) so one side is never pitch
black.

## On-screen text with NO libs (no GLU, freetype, or font files)
Render text as filled `GL_QUADS` from an embedded 5x7 (or 3x5) bitmap font,
in a 2D `glOrtho(0,W,H,0,-1,1)` overlay (y down). Store each glyph as 7 rows
of 5 chars, '#'=on bit; `toupper()` input (needs `<ctype.h>`) and keep the
font uppercase-only to halve authoring. Look up glyph by char, uppercase
fallback to space. Every set bit becomes one quad of size (cellh*0.62) x
cellh; advance the pen 6*cellw per char. Center a line by measuring
`6*cellw*strlen(txt)`. This avoids glBitmap/glPixelZoom entirely and is
resolution-independent.

## Faking modern effects in fixed-function GL (no shaders)
- **Fake bloom / glow:** layered additive `GL_TRIANGLE_FAN` disks, sizes
  `scale*(1+k*0.45)` for k=3..0, alpha `base*(0.5/(1+0.7k))`, blend
  `(GL_SRC_ALPHA, GL_ONE)`. Stack = soft radial glow around a duck/bulb/sun.
- **Fresnel-style rim:** add a *back* light positioned beyond the object
  (e.g. at `(0,0,-8)` world when camera is at `-5.5`, object near `-4`),
  tinted with a thematic color — the far side glows so silhouettes get bright
  edges. Combine with the camera headlight so the facing side is never black.
- **Vignette:** in the 2D ortho HUD pass, draw 4 `GL_TRIANGLES` (top/bottom/
  left/right) whose corner vertices are `alpha=0.30` black and the
  center-ward vertex is `alpha=0` — vertex-color interpolation darkens the
  corners. Center vs corner brightness is a good pixel-check for it.
- **Gradient sky:** draw a full-view `GL_QUADS` at `z=-46` (behind everything)
  with per-vertex colors (deep indigo at top to near-black at bottom) instead
  of a flat clear color.
- **Star life:** twinkle = scale star color by `0.6+0.4*sin(t*f+phase)`;
  shooting stars = periodic additive `GL_LINES` whose length/position follow
  `p=fmod(t*rate+i*offset,1)` with envelope `sin(p*PI)`.
- **Per-entity light cap:** max 8 GL lights. Budget: key(L0)+saga fill(L1)+
  accent(L2)+headlight(L3)+rim(L4) = 5, leaves room. A scene with 3 char
  orbs + duck + prop needs ~5-6 different fills; reusing one light per frame
  (reset position/color per frame) keeps you under the cap while still
  lighting many things — just set GL_LIGHTn params each frame, not per obj.

## Headless verification (no viewable screenshot / non-multimodal model)
Verify the render from pixel stats instead of eyeballing a screenshot.
- Capture: `xwd -root -out f.xwd` then convert with ffmpeg (ImageMagick is
  absent on this box): `ffmpeg -y -loglevel error -i f.xwd out.png`.
- Analyze with PIL: count near-black pixels (=clear color: space background),
  count pixels in your object's color band, centroid them. A duck/object that
  is 0% present + ~full dark background means the model is drawn but unlit
  (above lighting pitfall) or simply missing.
- Prove animation/rotation: capture two frames ~3 s apart, compare the object's
  centroid and pixel-mass. Moving centroid/shape = it actually transforms.
- The background clear color will appear as the *sum of* your clear RGB (e.g.
  `glClearColor(0.02,0.02,0.05)` reads back ~ (5,5,13)) — match on that.

## PITFALL: pkill -f self-kills your own shell
`pkill -f "\./duck_saver"` matches your own wrapper because the eval'd command
text contains that string, SIGTERM-ing the shell mid-job. Use exact process
name matching instead: `pkill -x duck_saver` (matches the exec'd binary name),
or `pgrep -x` to probe liveness.

## Cinnamon screensaver integration (Mint)
- To run a custom saver with NO sudo, use the zero-sudo idle-watcher section
  above (libXss + fork/exec your app), and STOP Cinnamon's own blanker from
  firing on its default timer or it will grab the screen from your app:
  `gsettings set org.cinnamon.desktop.screensaver idle-activation-enabled false`
  and `gsettings set org.cinnamon.desktop.session idle-delay 0`. Key facts:
  `idle-activation-enabled` defaults TRUE with `idle-delay` 900, so the
  built-in blank/clock pops at 15 min REGARDLESS of `lock-enabled` — that is
  the "screensaver kept defaulting" the user sees. No password on SLEEP is the
  separate key `lock-on-suspend` (live, no sudo).
- XScreenSaver (sudo apt install xscreensaver xscreensaver-gl) is the
  alternative when you want Cinnamon's idle owned by XScreenSaver instead of a
  watcher. Register any executable as a hack by adding to `~/.xscreensaver`
  `programs:` block (follows a `\` line-continuation row):
  `-root  "Name"  /usr/local/bin/app \` then `lock: False`, enable a
  `~/.config/autostart` `xscreensaver -no-splash` entry, and
  `xscreensaver-command -activate` to preview.</｜DSML｜parameter
