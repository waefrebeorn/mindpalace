---
name: wubuos-sprite-asset-baking
description: "Use when baking clipart sheets into C sprite tables."
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wubuos, gui, sprite, mascot, assets, image, bake]
    related_skills: [wubu-tree-standardization, wubuos-desktop-capture-harness, wubuos-wm]
---

## When to Use

- The user sends a clipart/sticker sheet and asks for the buddy or desktop mascot
  moods to be extended or fixed.
- Regenerating `src/gui/wubu_buddy_sprite.h` or `src/gui/wubu_buddy_states.h`.
- Any "bake an image into a C table" task in this tree (the WM draws sprites with
  `vbe_*` primitives only -- no image decoder, no asset loader).

## Tools and where things live

| Path | Role |
|---|---|
| `tools/mascot_encode.py` | one pose -> one RGBA table (`--pose N`, `--hat x,y`) |
| `tools/mascot_bake_all.py` | all moods -> ONE consolidated states header (uses a baked-in MOOD_POSES map) |
| `tools/assets/*.jpg` | committed source sheets, so the bake is reproducible |
| `src/gui/wubu_buddy_states.h` | generated: `BUDDY_STATE_<NAME>[96*96*4]` arrays |
| `src/gui/wubu_buddy_sprite.h` | generated: default pose as `wubu_buddy_rgba` |
| `src/gui/wubu_bonzi.{c,h}` | consumer; enum `WUBU_BUDDY_STATE_*` + `buddy_state_rgba()` switch |

```bash
python3 tools/mascot_bake_all.py --out src/gui/wubu_buddy_states.h   # regenerate all
python3 tools/mascot_encode.py tools/assets/<sheet>.jpg \
        --out src/gui/wubu_buddy_sprite.h --size 96 --pose 5           # single pose
make hosted && make test_wm
```

Deeper algorithm notes, the research sources behind the isolation method, and the
cut-scoring details live in `references/sprite-isolation-methods.md`.

New sheets go in `tools/assets/` and MUST be committed -- an unbaked source is not
reproducible and the next person cannot regenerate your work.

For CREATING new buddy pixel-art poses (the reactive pet deck) instead of baking
existing sheets, see `references/buddy-petdeck-creation.md` -- image_generate
prompt recipe, flood-fill alpha, metric verification, and the kernel wiring
caveats.

## Procedure

1. **Save the sheet** to `tools/assets/`, then run `find_hats()` over it and print
   the detected centroids before trusting any `--pose` index.
2. **Order poses row-major with y-clustering**, then verify with a numbered overlay
   (draw red dots + yellow indices on a downscaled sheet, view it). Every marker
   must sit on a mascot's hat; flag any that do not.
3. **Pick only poses that map to a state we do NOT already have.** Two arrays for
   one mood is duplication the covenant forbids; note the skip in the commit body.
4. **Extend the enum** (`WUBU_BUDDY_STATE_*`, before `COUNT`) AND the baker's
   MOOD_POSES in the SAME order, because `wubu_bonzi.c` indexes by state id. Add the
   matching `case` in `buddy_state_rgba()`.
5. **Rebuild and verify by rendering**, not by reading code: capture a frame, and
   also decode the generated header in Python and inspect the isolated sprite at
   4x. Count opaque pixels and measure the bounding box numerically.

## Rules that make the bake correct

- **Alpha comes from CONNECTIVITY, never from pixel colour.** If the subject's fill
  equals the background value (a white rabbit on a white sheet), ANY colour key
  erases the body and leaves semi-transparent rims -- the sprite renders as a
  watermark. Background = whatever reaches the crop border through non-ink pixels;
  enclosed white stays opaque.
- **Bound the crop by CELL MIDPLANES between detected hats**, not by a box sized
  from the hat. A hat-sized box does both of these wrong: it CLIPS wide poses
  (a desk with mugs and a monitor loses its edges) and it REACHES INTO THE NEXT
  ROW, swallowing the top of the pose below -- which shows up as a partial second
  character head inside the sprite.
- **Isolate in three stages, in this order:** cell -> border flood -> connected
  component seeded at the hat centroid. Prefer UNDILATED ink for the component
  flood; dilation closes dashed outlines but also bridges a pose to a nearby prop.
  Fall back to dilated only if the strict pass fragments the shape.
- **The final trim is the bounding box of the KEPT component**, not of raw colour:
  `content_bbox` keys on "any non-white pixel", and a neighbouring pose's green hat
  IS non-white, so trimming by colour keeps neighbours.
- **Row-major ordering must cluster by y within a tolerance (~80px), then sort by
  x.** Grouping by `round(cy / N)` mis-sorts any sheet whose hats sit at slightly
  different heights and SILENTLY RENUMBERS every pose after it.
- **Canvas = max(w,h) * 1.08**, centred. Without the margin a tall pose fills the
  whole height and its ears/feet sit flush on the sprite edge, which reads as
  clipping even though nothing is truncated.
- **Get that margin from the CANVAS, never by enlarging the crop.** Widening the
  trim (`bx0 -= mw`) samples MORE source pixels, so on a grid sheet it pulls the
  neighbouring pose into the sprite -- you trade flush edges for a stray second
  character. The cell midplanes are the outer bound; anything beyond them is
  another pose's art.
- **Sever bridges with a MINIMUM-COST CUT, not morphology.** Scan candidate cut
  bands along both axes; score each by how many kept pixels must be sacrificed to
  detach a small side blob; cut the cheapest band whose detached part is small and
  whose remainder is intact. Morphology only works while the neck is thinner than
  its structuring element and silently does nothing on a thick contact -- which is
  exactly the failure this replaces.

## Pitfalls

- **A fused prop may be inherent to the source art, not a bug in your pipeline.**
  When a stray element survives every segmentation method, MEASURE before tuning
  further: compare the opaque-pixel count before and after the attempted cut.
  Byte-identical counts mean the two objects share a wide contact area and no
  straight cut separates them without inventing a boundary the artist never drew.
  Ship with the artefact documented rather than burning time on threshold tweaks.
- **Removing an underlay workaround orphans its helpers -- sweep for them.** Grep
  the consumer for every function and struct field that existed only to serve the
  removed path (a dedicated eye renderer, an anim field feeding nothing). Dead
  renderers left behind still compute values nobody reads, and they read as living
  code to the next session.
- **Do not leave a hand-drawn underlay once the sprite is correct.** A vector body
  drawn beneath the bitmap to hide ghosting becomes a double draw the moment alpha
  is baked right. See `wubu-tree-standardization` for the general rule.
- **Never hand-draw a DIFFERENT mascot than the user's.** The desktop buddy is the
  WuBu Buddy (pale body, lime-green 'W' cap, pink ears); a hand-drawn geometric
  gorilla (or any other proxy) is a regression that reads as "restoring the classic
  90s Bonzi". Render the baked/created buddy sprite; if the user's own sprite is
  not in the path yet, put IT in -- do not improvise a stand-in character.
- **Creating new mascot art is NOT the same as baking sheets.** The reference
  sheets guide the character design; the poses are CREATED with `image_generate`
  (one consistent prompt, same palette/framing, per pose). Baking the sheets
  wholesale misses the intent, which is original pixel art + a reactive pose deck.
- **Verify geometry numerically before believing or denying a clipping claim.**
  A cropped screenshot's own boundary is easily mistaken for the screen edge; two
  independent vision passes reported clipping that a pixel scan disproved (11px and
  10px of real margin). Scan the region for the sprite's colour range and print
  min/max x/y. Same discipline for contact sheets.
- **Opaque-pixel count is the quick health check.** A ghosted sprite measures ~1.5k
  of 9216 opaque; a correctly baked one measures 3.5k-8.6k depending on the pose.
  A drop after a change means you lost art; a rise usually means you stopped
  clipping.
- **`git add -f` any new test sources** -- `.gitignore` has `src/*/test_*`.
- **`tools/__pycache__/` must not be committed**; it is gitignored now, but delete
  it before staging a tooling change so it never rides along.
