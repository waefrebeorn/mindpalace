---
name: wubu-buddy-anim-engine
description: "Use when building or animating the WuBu Buddy mascot."
category: software-development
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wubuos, buddy, mascot, animation, pixel-art, pose, emotion, pet]
    related_skills: [wubuos-sprite-asset-baking, wubuos-gui-rendering]
---
## When to Use
- Building the WuBu Buddy's big pose/emotion deck (1000 vibes, 5000 animations).
- Adding animated transitions between buddy poses.
- Creating new buddy pixel-art poses (image_generate guided by the sheets).
- Any 'desktop pet with many moods/states' animation work in WuBuOS.

# WuBu Buddy Animation Engine (pet-decks, 1000 vibes / 5000 animations)

The goal is NOT 1000 hand-drawn sprites. It is a COMBINATORIAL engine: a small
pixel rig + layer decks + an emotion matrix + procedural tweens that expresses
thousands of distinct animated states from ~15 base parts and ~12 base poses.

## Non-negotiable (user corrections -- do not relitigate)
- **JUDGE WITH EYES, NOT NUMBERS.** Numeric checks prove a bake or render is
  faithful; they say nothing about whether the art reads. A pixel-perfect copy
  of a bad sprite is still bad. Vision review is the acceptance gate -- and
  judge under the SAME camera and lights you intend to ship: a flat preview
  harness washed out every form and made a good model look like a blob.
- **THE SHEETS ARE THE SOURCE.** Slice the user's reference sheets into poses;
  do NOT replace them with prompt-guessed lookalikes. Prompt generation drifts
  (white W, missing scarf) and was superseded by slicing.
- **REJECT BOTH ENDS OF BAD GEOMETRY.** Balloon primitives read as a school
  project, and an over-fused metaball body reads WORSE (arms/legs/feet melt into
  the torso, the silhouette collapses into a ghost-blob). Distinct parts with
  Subdivision Surface applied PER PART is the better end (sculpted surfaces
  without merging forms), but it is still NOT sufficient: an invented
  approximation scores well numerically and still gets called "playdoh blob"
  because it is not the user's character. Acceptance requires DERIVATION FROM
  THE REFERENCE ART (silhouette, proportions, colours, markings), then a real
  rig (armature + weight painting). Depth in references/dkc-3d-pipeline.md.
- **METRICS ARE NECESSARY, NEVER SUFFICIENT.** A model can match the
  reference's measured silhouette profile exactly and still read as an invented
  blob. Report the metric AND the vision verdict together; when they disagree,
  the eyes win and the gap points at SHADING/contours, not more shape edits.
- **WHEN A REINTERPRETATION KEEPS FAILING, USE THE ART.** If repeated 3-D
  attempts do not look like the supplied character, the honest deliverable is
  the sliced reference sprites themselves, rigged (layered depth planes for
  parallax / the C pixel rig). Shipping the user's own perfect art beats
  shipping a third-rate 3-D impersonation.
- **DESIGN BY SILHOUETTE, NOT BY NUDGING.** Build the solid-black silhouette
  harness first (emission-black material on every mesh + white world, ortho
  camera, front/45/side/back) and judge the OUTLINE before any surface detail;
  iterate proportions against those four views and re-score. When quality
  stalls, go STUDY character-design craft (shape language, negative space,
  staggering repeated forms) rather than adjusting numbers -- every correction
  that actually moved this model came from a silhouette test or a measured
  placement, never from another shaded render. Recipe and working numbers in
  references/dkc-3d-pipeline.md.
- **SPEND SYSTEM RAM BEFORE BLAMING THE GPU.** Host RAM (~93 GB) is the real
  budget; 8 GB VRAM is not a wall. Hold big checkpoints in RAM (CPU offload),
  decimate/retopo large meshes locally, and treat VRAM as a throughput limit,
  not a hard stop -- but never claim RAM fixed a quality problem it did not.
- **A BASE MESH IS NOT ACCEPTANCE.** "Smooth clay with ears" is unfinished. The
  bar is a readable silhouette, limbs that separate in PROFILE, features sitting
  ON the surface (nothing buried, nothing floating), and surface treatment
  (contours, cloth, fur). Hold each render up against the reference sheets and
  keep fixing until it survives a harsh critique.
- **Do not generalise the concept away.** It is a 3-D model -> DKC pre-rendered
  sprites -> a living desktop mate that walks the desktop. Any shortcut that
  flattens that chain gets rejected.
- **CHECK HOSTED DEMOS BEFORE SPENDING A ONE-SHOT STEP** (user preference), but
  VERIFY the host exposes a callable headless API first. A sleeping or
  hidden-schema demo is worse than a local run; report which hosts you probed
  and their real state before committing to one.

## Architecture (from research -- see refs below; use this, don't reinvent)
- **Rig, pixel-exact.** Assign the buddy's OWN pixels to parts (head, cap,
  ear L/R, body, arm L/R, leg L/R, face layers) and move them through a bone
  hierarchy via part transforms -- pixel-exact, same palette, no redraw.
  (AI-Sprite-Animation rig method.) The `desktop-pets` repo is the cleanest
  reference: a character is just `draw(canvas, pose, palette)` + `drawSide()`;
  state -> pose -> palette is a single table; alert/fail washes derive
  automatically from the own palette.
- **Pose deck = base actions.** ~10-14 base poses: idle, blink, work, think,
  celebrate, error, read, walk, sleep, hungry, wave, done. Each pose is a set
  of PART TRANSFORMS (dx, dy, rot, scale, squash, visible) with per-part ease.
- **Expression layers = live-emoji params.** Eyes (open/blink/happy/wink/wide/
  sad/look), mouth (smile/open/frown/o/tongue), brows. Independent layers so
  any pose x any expression composes (Live-Emoji emotion-command model).
- **Emotion matrix = valence x arousal (x energy/level) -> (pose, expr, tint,
  particle env).** 1000 vibes = a tag->(valence,arousal) lexicon + 5-step
  slices; each cell maps to a composed pose+expression+palette wash. Derived
  washes (sad=blue-grey, error=red flash, calm=desat) come from the base
  palette automatically (desktop-pets), so 1000 vibes need few new sprites.
- **Transitions.** FSM state graph; most returns to rest are the move played
  BACKWARDS (free). Squash/stretch + anticipation + follow-through (2D anim
  primer) make transitions read as motion, not frame jumps. Tweens: linear
  between keyframes (onset t=0, apex t=0.5, offset t=1), EASE per part.
- **Procedural/seeded variation (ppae-engine).** A 32-bit seed varies
  morph/behaviour weights deterministically => 'one-of-a-kind' pet per seed,
  so N seeds x M states explode the deck (PixelPal blind-box personality).

## Motivation (user, 2026-11-16)
WaefreBeorn wants: more poses, ANIMATED TRANSITIONS between them, 1000
vibes/emotions, 5000 possible total animations, and online research to grow
the skills to do it. Deliver a system, not a sprite dump. Deck assets live in
`tools/assets/wubu_buddy_slices/` (sliced from the reference sheets); the early
prompt-generated `canon_*.png` set under `tools/assets/wubu_buddy_deck/` is
superseded.

## How the counts are reached (expresability, not literal assets)
- 1000 vibes/emotions: valence{-2..2} x arousal{-2..2} = 25 core cells x a
  tags lexicon (anger, joy, hope, dread, pride, awe, calm, ...) + per-cell
  palette/particle variants => combinatorially >= 1000 named states.
- 5000 animations: basePose(12) x exprDeck(eyes 7 x mouth 6) x transition
  variants + tweens + seeds => far beyond 5000 distinct loops/sequences.

## Implementing inside WuBuOS
- Hosted testable C11 module `wubu_buddy_anim.{c,h}` (opaque struct, per-concern
  split), then wire into the kernel wubu_bonzi.c draw path.
- Bake RGBA part maps from a canonical sprite via `tools/buddy_rig_bake.py`
  (segments the sprite into parts -> `wubu_buddy_rig_data.h`).
- A `tools/buddy_anim_gen.py` emits the pose/expression/emotion tables (or a
  compact C tables header), one editor of truth, reproducible.
- Reserve a full selftest asserting the enumeration counts (>=1000 vibes,
  >=5000 anims) so the deck cannot silently shrink.

## References / sources
- JatCool/AI-Sprite-Animation: rig-based pixel-exact animation.
- Pieismath/desktop-pets: character = draw(canvas,pose,palette); one table.
- Mairon31/ppae-engine: deterministic modular generation, seeded variation.
- Live Emoji (arXiv 1902.03529): emotion-command param model.
- PixelPal / Pipkin: FSM + needs + seeded 'blind-box' personality.
- gameindustrylibrary.com 2D animation primer: squash/stretch, anticipation.

## CANONICAL ANATOMY (authoritative -- from the reference sheets; verify against
## the model before generating art, it catches drift)
Chibi WHITE RABBIT, unibody (arms emerge from the torso sides -> connected
components FUSE, so segment by REGIONS not components):
- head ~40% of height, nearly circular; two LONG ears angled outward from the
  cap top with PINK inner ear.
- GREEN AVIATOR CAP low on the forehead with a RED letter 'W' emblem (the W is
  RED, not white -- the single most-repeated generation error).
- small black DOT eyes + tiny mouth.
- pear-shaped white torso wider at the bottom with a RED NECKERCHIEF/scarf
  tied at the neck, tails down the chest.
- short rounded MITTEN arms at the shoulders; very stubby legs with
  OVERSIZED rounded feet.
Generation recipe: put the WHOLE canonical spec in every prompt (not "same
character as other poses"), force "RED W", name each feature. Generation
still drifts (white W, missing scarf, X-eyes, blob torso) -> the FACIAL RIG
redraws the eyes/mouth anyway, and the audit catches the rest.

## 3-D PIPELINE (image -> mesh -> DKC sprites) and its environment traps
Envs on this box: ~/opt/b313 = Blender bpy 5.3.0 (needs cp313); ~/opt/h3d =
Hunyuan3D/torch; ~/opt/rembg = keying/slicing.
- **sm_120 (RTX 5050): CUDA-12 wheels have no kernels.** torch must come from
the cu130/cu13x index AND bring its own nvidia-* runtime deps -- installing
with --no-deps leaves libcudart.so.13 missing. cu126 "works" but silently
runs OFF-GPU (check VRAM used, not torch.cuda.is_available()). Install torch
and torchvision from the SAME index together: a torchvision pulled from PyPI
alongside a cu130 torch fails at import with `operator torchvision::nms does
not exist`.
- **Unpinned deps break old repos:** transformers 5.x renamed DINOv2 attention
(`attention.attention.query` -> `q_proj`), so Hunyuan3D-2 cannot load its own
checkpoint. Pin transformers==4.52.4 + diffusers==0.35.1 (diffusers 0.43 wants
hub>=1.0, which transformers 4.x forbids).
- **Measured:** Hunyuan3D-2 shape pass returns a FLAT bas-relief (extents
1.78 x 1.99 x 0.02) for flat vector mascot art, both from an RGBA cutout and
from opaque-on-white. Not rig-ready. Hosted HF demos (TRELLIS.2 / SF3D) are
live but hide their API schema from headless clients -- unreliable one-shot.
- Always JUDGE a generated mesh by rendering a turntable before rigging:
`~/opt/b313/bin/python tools/buddy_mesh_preview.py MESH.glb OUTDIR`.

## C RIG (the real home -- src/runtime/wubu_buddy_rig.{c,h})
- `tools/buddy_rig_bake.py` bakes canon_idle.png -> `wubu_buddy_rig_data.h`:
  palette (u32 0xRRGGBBAA), kBuddyIdx (u8/pixel, 0xFF transparent), and 8
  parts (ears/cap/head/torso/armL/armR/legL/legR) as pixel-offset lists.
- PARTS MUST BE A FULL-COVERAGE PARTITION: assign EVERY opaque pixel to
  exactly one part (horizontal bands over the bbox; arms = outer columns of
  the torso band; legs split at centre). Rectangles alone leave coverage gaps
  (~250 px) -> the rest render loses pixels.
- Binary alpha: LANCZOS resize leaves ~900 soft edge px/sprite which break
  exact baking. Requantize to <=48 colours AND threshold alpha (a>127->255).
- PROVEN: C rest frame reproduces the baked sprite EXACTLY
  (missing=0, extra=0, rgb_diff=0 over 9216 px). Keep that assertion.
- API: wubu_buddy_rig_draw(xf[PART_N], face, buf, w, h); pose_walk/pose_wave/
  pose_rest fill per-part int8 offsets. FACE_NONE=-1 keeps the baked face.
- Gates: test_buddy_anim + test_buddy_rig in the critical-runtime tier.

## Asset rules
Deck PNGs are gitignored (*.png:15) -> `git add -f`.
- Reference sheets live in tools/assets/wubu_buddy_deck/refs/. They ARE the
  canonical character: SLICE them (tools/buddy_slice_sheets.py ->
  tools/assets/wubu_buddy_slices/, ~55 poses) instead of generating
  replacements. Never edit the originals; slices are derived artifacts.
- **KEY WHITE-ON-WHITE ART BY CONNECTIVITY, NOT AI MATTING.** These sheets are
  a WHITE rabbit on WHITE paper: saliency models cannot separate fur from
  paper and ERODE THE INTERIOR (measured: 26,038 interior holes on one pose,
  fill ratio 0.326). Flood-fill the paper from the border -- the bold outlines
  stop the fill -- giving 0 holes and ~33% more artwork retained. Recipe in
  references/dkc-3d-pipeline.md; verify any keyer with binary_fill_holes().
- Prompt-generated canon_*.png is superseded; keep one only if it beats a
  sliced pose on a vision pass.
- Slicing algorithm (area-seeded poses, seed fusion <=25 px, nearest-pose
  fragment attach, connectivity keying) is in references/dkc-3d-pipeline.md.

## User correction (do not repeat)
The buddy is the WuBu Buddy (pale body, lime-green 'W' cap with a RED W, red
neckerchief, pink ears) - NOT the classic 90s Bonzi gorilla, and NOT a feature-
less blob (it surfs/guitars/drives: real arms+hands, legs+feet, accessories).
