# DKC-style 3-D buddy pipeline (model -> rig -> sprites)

Donkey Kong Country sprites are PRE-RENDERED 3-D downsampled to pixels. Building
the buddy as a real model gives consistent anatomy across every pose and native
alpha (transparent film) -- no background removal anywhere in that path.

## Environments (all under ~/opt)
- `rembg` -- py3.12 + rembg/numpy/scipy/PIL: AI keying and sheet slicing.
- `b313` -- CPython 3.13 + bpy 5.3.0: Blender scripting. bpy 5.3 pins
  `requires_python ==3.13.*` exactly, and pip's default index has no bpy wheel:
  `uv python install 3.13 && uv venv --python 3.13 ~/opt/b313 &&
  uv pip install --python ~/opt/b313/bin/python bpy`.
- `h3d` -- py3.12 + torch/torchvision from the **cu130** CUDA index (see the
  GPU note below). A mismatched torchvision fails at import with
  `operator torchvision::nms does not exist`.

## GPU toolchain (RTX 5050 = sm_120)
The laptop GPU is compute capability 12.0 (Blackwell). CUDA-12 wheels ship no
sm_120 kernels, so torch imports, reports `torch.cuda.is_available() == True`,
and silently runs OFF-GPU (VRAM stays ~15 MiB). Never trust `is_available()`
-- confirm with a real matmul and watch `nvidia-smi` memory.

    uv pip install --python ~/opt/h3d/bin/python --reinstall \
        --index-url https://download.pytorch.org/whl/cu130 torch torchvision

Install WITH dependencies: `--no-deps` skips the CUDA 13 runtime packages and
the next import dies on `libcudart.so.13: cannot open shared object file`.
The same sm_120 wall applies to nvcc (CUDA 12 has no native sm_120; compile for
compute_80 and let the driver JIT).

## Mesh acquisition -- the one expensive step
Quality-vs-VRAM for an 8 GB card:

| model | VRAM | verdict |
|---|---|---|
| TRELLIS.2 (MIT) | 24 GB | best open quality, does not fit |
| Hunyuan3D-2.1 | 10 GB shape / 29 GB textured | does not fit |
| Hunyuan3D-2.0 shape-only | ~6 GB | fits, but MEASURED FLAT (bas-relief) -- do NOT spend a one-shot on it |
| Stable Fast 3D / SPAR3D / TripoSR (MIT) | ~6 GB | fit, ranked lower |

Run the SHAPE pass only (skip the paint pipeline): `--octree 256 --steps 30`
fits 8 GB. Hunyuan3D-2 is Tencent non-commercial licensed -- fine for WuBuOS,
not for a commercial ship.

Input image rules: ONE clean, front-facing, full-body, PROP-FREE pose. Props
(ladder, guitar, go-kart, desk, dog) bake straight into the geometry. Pick the
input by eye from the sliced sheets, not by filename.

Hosted HF Spaces -- PROBE BEFORE PROMISING THEM. `gradio_client.Client(space,
 token=...)` (it is `token=`, NOT `hf_token=`, in 2.x), then `view_api()` only
AFTER warming the Space: a cold Space returns zero endpoints yet still answers
`predict`, which refuses with "specify api_name". Observed states: TRELLIS.2
live but schema hidden; stable-fast-3d live but schema hidden; TripoSR
RUNTIME_ERROR; TRELLIS v1 CONFIG_ERROR; mukaist/Hunyuan3D-2 PAUSED. For a
one-shot asset, run locally rather than betting on a Space.

## Sheet slicing (reference sheets -> pose cutouts)
Connected components alone neither fuse a character with its prop nor keep
poses apart. Rule that works on these sheets (poses sit ~57 px apart):
- components >= BIG_AREA are POSE SEEDS;
- FUSE seeds whose bbox gap <= 25 px (car+driver, bed+sleeper are one pose);
- ATTACH every smaller fragment ('Zzz', floating tools) to its NEAREST seed;
- naive proximity merging at any gap >= ~60 px fuses entire sheets.
KEY BY CONNECTIVITY FOR THIS ART. It is a WHITE character on WHITE paper, so
AI saliency cannot tell fur from paper and ERODES THE INTERIOR: rembg/u2netp
produced 26,038 interior holes on explore__01 and kept only 0.326 fill ratio.
Correct method (`key_paper()`): mark near-white pixels, label connected
components, treat every component touching the border as background. The bold
outlines close the silhouette, so enclosed white fur survives -> 0 holes,
0.434 fill (~33% more artwork). Verify any keyer with `binary_fill_holes()`:
interior holes must be 0.
(AI matting is still right for photos / non-white backgrounds: BiRefNet for
edges/hair/glass, isnet-general-use for speed, u2netp as universal default.)

## Modelling pitfalls (each cost real iterations)
- Build limbs hanging DOWN from their joint origins. Extending them upward
  inverts the joints: feet detach, swings barely read.
- Parent hands to arms (with matrix_parent_inverse) so they ride along when the
  arm rotates; otherwise hands float while the arm moves.
- Animate with ABSOLUTE joint eulers. Additive Euler deltas compose into
  nonsense -- an intended overhead wave came out sideways.
- Set `scene.view_settings.view_transform = 'Standard'`. Blender's default AgX
  bleaches saturated brand colours (a red scarf renders salmon).
- Render with `film_transparent=True` and an orthographic camera for the DKC
  read; downsample the render to ~96 px for the pre-rendered pixel look.
- **Subdivision Surface per part (applied) is the right smoothing tool.** It
  removes faceting WITHOUT fusing parts. Metaball fusion is the wrong tool for a
  readable character: arms/legs/feet melt into the torso and the silhouette
  collapses into a blob (measured regression vs a plain primitive assembly).
- **Emblems/logos = primitive bars, never converted font glyphs.** A text object
  turned into a mesh subdivides into a blurry smudge that stops reading as a
  letter at any angle.
- **EEVEE does NOT render Freestyle contour lines**, and a naive inverted-hull
  ink shell shows black artifacts through the model. Cartoons need outlines, so
  solve that deliberately (Cycles+Freestyle or a corrected hull); ship ink
  shells OFF by default until proven.
- **Limbs must separate in SILHOUETTE, not merely exist.** Pull shoulders, hands
  and feet outward until a gap reads between arm and torso at rest; otherwise
  white-on-white forms merge in the render. Working numbers that produced visible
  daylight: torso elements 0.190/0.215 wide, arms at x=+-0.335, hands at
  +-0.425, legs at +-0.105 -- vision score went 6 -> 7 with that change alone.
- **MEASURE the surface; never hand-place features.** Query the sculpt's own
  vertices near the target (x,z) and take the most-forward Y (`front_y`), then
  put eyes/mouth a hair proud of it and emblems just proud of the CAP shell.
  Hand-computed offsets buried the eyes inside the enlarged head and floated
  the W in front of the face across several iterations; measured placement got
  every feature right on the first render. Recipe: head r~0.22 at z~0.78;
  eyes (+-0.090, front_y+0.008, 0.800); mouth (0, front_y+0.006, 0.722);
  cap sphere r=0.235 scaled (1.02,1,0.80) at (0,0.005,0.865); W bars at
  z=0.885, y~-0.229. A brim in front of the cap slices through the W -- omit it
  or place it above the emblem.
- **Judge the SILHOUETTE, not the shaded render.** Flat lighting washes out
  white-on-white forms and makes a good model look like a blob, so a shaded
  render is a poor acceptance gate. Harness: give every mesh one black
  EMISSION material (nodes cleared, ShaderNodeEmission -> Output), white world,
  orthographic camera, then render azimuths 0/45/90/180. Judge: head vs
  shoulders, arm vs torso, gap between legs, whether ears/cap/feet break the
  outline. Re-score after each change. On this model: 6 -> 7 overall, with
  front 8 / back 8 / 45deg 7 / side 5.
- **Blending only ADDS volume -- subtraction defines a boundary.** Once forms
  touch, no amount of smoothing separates them again: the profile stayed one
  featureless column (no neck, feet fused) because a neck element merely filled
  space. Fix with NEGATIVE metaball elements (`element.use_negative = True`) to
  CARVE: a flat wide ellipsoid at the neck for a crease, one between the feet,
  one between the ears. Same principle as "know where one shape starts and
  another ends".
- **Stagger repeated forms so they read in PROFILE.** Two identical ears at
  +-x fuse into one spike when viewed edge-on, and two identical feet merge into
  a pedestal. Give the pair different y-offset/tilt (one ear tipped forward, one
  back; feet at different depths) so both survive the side view.
- **Bent limbs read; straight ones fuse.** An arm angled straight down merges
  into the torso silhouette at 45 degrees. Angle the upper arm out and put the
  hand further out and lower -- the elbow kink is what breaks the outline.

## Measure against the reference PROFILE, not against your eye
Profile the clean front-view slice row by row (width vs height on the alpha
mask) and compute three numbers: head width as a fraction of max width, the
neck notch (minimum width across the 30-50% height band), and the height of the
widest point. Reference values: **head 0.72, neck 0.29, widest at 80%**.
Run the identical measurement on the model's silhouette render. This converges
fast (no vision needed, immune to provider rate limits) and catches what shaded
renders hide: a model can match every number and STILL read as an invented blob
in shading -- so metrics drive layout, eyes give acceptance, and disagreement
points at shading/contours rather than more shape edits.

## Construction: separate resolved forms, not carved creases
Metaball blending plus negative-element carving PLATEAUS: smoothing refills the
crease as fast as it is cut, and cutting harder SEVERS the head (measured neck
ratio 0.00 = decapitated). What works is TWO lobes (head, body) built as
separate metaball objects and joined afterwards -- they cannot blend across
objects, so the neck notch is genuine empty space (neck 0.51 -> 0.23).
Rule: where a boundary must exist between two masses, give it real separation;
do not carve it out of one blended volume.

## UV pitfall
Voxel Remesh rebuilds topology and DISCARDS UV maps -> image textures sample
black. Use Solidify (+Subsurf) instead whenever the model is textured; if a
remesh is unavoidable, re-project UVs afterwards.

## Tools
- `tools/buddy_gen3d.py` -- one-shot Hunyuan3D shape pass (IN.png OUT.glb).
- `tools/buddy_mesh_preview.py` -- orbit turntable so a mesh can be inspected
  before building anything on it.
- `tools/buddy3d.py build|render` -- distinct-part character (subdiv-smoothed,
  geometric W emblem, separated limbs) animated by per-part joint transforms.
  Current best-looking hand-built model; always render it with ITS OWN camera
  and lights, not the flat preview harness.
- `tools/buddy_sculpt.py build|render` -- metaball body + 17-bone armature
  (root/spine/head/ears/arms+hands/legs+feet), with `front_y()` surface
  measurement placing the face features. v1 fused the limbs into a blob;
  v2 (measured above) separates them and scores ~7/10 -- still a base mesh
  (no contours, no surface detail), so treat the distinct-part `buddy3d.py`
  model as the look of record unless a sculpt pass adds real detail.
- `tools/buddy_slice_sheets.py` -- reference sheets -> individual pose cutouts
  (connectivity keying; see above).
- `tools/buddy_from_ref.py` -- WIP, NOT USABLE: extrudes a reference mask into a
  solid and projects the art. Its hand-rolled back/rim faces tore the surface
  into crumpled sheets, and its remesh step destroyed the UVs (texture rendered
  black). Kept for the idea, not as a workflow.
- `tools/buddy_rig_bake.py` / `src/runtime/wubu_buddy_rig.{c,h}` -- pixel-exact
  C rig over a baked sprite (the non-3-D path).
