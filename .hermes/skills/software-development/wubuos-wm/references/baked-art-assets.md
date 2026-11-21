# Baked art assets for a WM that draws only with vbe_*

The WM has no image decoder and no asset loader: every surface is drawn with
`vbe_*` primitives. To put real artwork (a mascot, an icon set, a splash) on
the desktop, bake it into a C table at build time -- the same discipline as an
embedded font. The generated header is data, not code: mark it generated and
never hand-edit it.

## Pipeline

1. **Pick one pose out of the sheet.** The Wubu sticker sheets hold several
   poses, each wearing a green hat. Grid-cluster the green pixels (~120px
   buckets) and take the largest cluster -- a hat is the anchor that works for
   every pose, unlike a colour or a shape.
2. **Crop a box, not a square.** The pose is ~3.2 hat-widths tall and ~2.4 wide.
   A square crop centred on the hat catches the neighbouring poses.
3. **Dilate the ink, then flood the background.** The clipart's outline is
   dashed at raster resolution, so a plain near-white flood leaks into the
   body. Dilate the non-white mask once or twice to close the dashes, then
   flood from the crop border over the non-ink pixels.
4. **Isolate the connected component.** Neighbouring poses are closed contours
   too, so the flood keeps them as well. Flood the non-background pixels outward
   from the pose's centroid and keep only what is reached.
5. **White -> alpha, resize, emit RGBA8888** as a C array. Soften near-white
   edge pixels to a low alpha rather than a hard cut, or the silhouette rings.
6. **Blitter module, one concern.** Alpha-composite through
   `vbe_set_pixel`/`vbe_get_pixel` so the art lands in the VBE back buffer like
   every other surface. Skip alpha 0; source-over for the rest. Do NOT take a
   caller's `fb` pointer -- the `vbe_*` primitives are the single drawing path.

Tool: `tools/mascot_encode.py SHEET.jpg --out src/gui/<name>_sprite.h --size 96`

## State poses (one surface, many moods)

When a mascot or an indicator must show several moods, keep ONE blitter and
swap the table:

- expose `wubu_mascot_blit_rgba(x, y, const unsigned char *rgba, int size)` and
  have the default `wubu_mascot_blit(x, y)` call it with the standing pose;
- give the owning surface a state enum (`DEFAULT / WORK / ERROR / SUCCESS /
  IDLE / ...`) and a `switch` mapping enum -> pose table;
- every generated table must carry the SAME size, or the blitter needs a size
  per pose.

**Wire a state only to a source that actually exists.** A "busy" pose driven
by a CPU-load reading the backend does not provide is fiction: it will fire at
random or never, and the surface stops telling the truth. Leave such states
settable by the caller (an agent, a test) and SAY SO in the commit, rather than
inventing a metric. The states worth wiring are the ones with a real reader --
a thermal zone, an input counter, a completion flag.

An activity-derived pose needs an idle timeout: mark the last-activity tick on
every input event, show the busy pose while things happen, and fall back to the
idle pose after N quiet seconds. Otherwise the surface is pinned to whichever
pose last fired.

## Generating pixel art from a recipe (no model, no decoder)

When the art should be ORIGINAL rather than extracted from a sheet, write a
deterministic generator instead of reaching for an image model: a recipe
(palette + grid + operations) always produces the same pixels, and the result
is inspectable and patchable. This is the discipline behind the agent-oriented
pixel-art tools (Pixelbolt, Atelier, pixelart-mcp) -- adopt the discipline,
not the tool.

`tools/pet_gen.py` is the in-repo example: 8 pets x 4 frames at 24x24, emitted
as one RGBA table. The craft that makes it read as a creature rather than a
blob:

- **LOCK THE PALETTE.** A pet is body / belly / outline / eye / one accent.
  Derive the shade from the base (`shade(rgb, f)`) so the ramp stays consistent
  across every pet.
- **ONE-PIXEL OUTLINE** in a dark neutral, drawn under the fill.
- **TWO-STEP SHADING RAMP** (lit / base / shade) from a single light direction.
- **MIRROR THE GRID horizontally** unless the recipe says otherwise -- symmetry
  is what makes a blob read as a face.
- **DRAW THE EYES LAST** so nothing covers them; a blink is the same drawing
  with the catchlight suppressed.
- **ANIMATION IS A FRAME INDEX, not a redraw:** idle = bob, blink = eyes
  closed, happy = wider mouth + sparkle. Emit one line per frame so the table
  stays diffable.

Scale at BLIT time with nearest-neighbour (`vbe_fill_rect` per pixel block), so
the pixels stay square on the desktop.

## Pitfalls

- **A brightness threshold cannot separate a white body from a white
  background.** The separation comes from the outline: dilate it and flood
  around it. Any approach that keys on "is this pixel near-white" eats the
  body and leaves a dashed shell.
- **A near-white ALPHA step re-eats the body even after a correct flood.** The
  encoder's final `min(r,g,b) >= 240 -> alpha 0` pass treats white fur as
  background a SECOND time, so a white-furred character blits as a faint ghost
  with no legs -- the interior flood never protected it. Draw an opaque
  procedural body (feet, legs, torso, arms, head) with `vbe_*` UNDER the blit so
  the sprite's transparent regions have something solid behind them; the cap,
  scarf, eye and outlines still show through. Verify on the product frame, not
  the generator preview, or the ghost looks like a deliberately faint sprite.
- **Too much dilation merges neighbours into the pose's component.** Dilate
  just enough to close the dashes, then CROP TIGHTER so the neighbours are
  outside the box BEFORE isolating the component.
- **The sprite's real size must drive placement.** A pixel size left over from
  a previous sprite leaves the new one hanging off the bottom edge or behind
  the taskbar. Read the size through the module's accessor at the call site,
  and subtract the taskbar height for a bottom-corner element.
- **Verify on the product frame**, not on the generator's preview: render with
  `--screenshot` and read the pixels. The generator's preview composites alpha
  a different way and hides exactly the artefacts that matter on the wallpaper.
- **Adding the blitter means adding it to EVERY recipe that links its caller**
  (`wubuos-wm` step 3) -- the caller's own recipes and the transitive ones.
