---
name: wubu-desktop-pet-pipeline
description: Build the WuBu desktop mate and its animation assets.
version: 1.0.0
---

# Desktop-pet pipeline (the standard workflow, not ad-hoc 3D)

## Why
Hand-invented geometry cannot reproduce a designed character -- four attempts
(primitives, metaballs, silhouette extrusion) all read as invented blobs. The
mainstream pipeline keeps the CHARACTER as a fixed asset and varies only
action/environment.

## The pipeline (dsh-pet / Nano Banana + Seedance style)
1. **Master reference** - ONE approved neutral-pose full-body image. Every
   later asset references THIS FILE, never a later output.
2. **Reference kit** - turnaround (front/3-4/side/back) + expressions, cut from
   the same art. One change per prompt ("same character, smiling").
3. **Green-screen animation** - image-to-video from the approved still, short
   clips (~10 s), each action generated twice and the best kept. Idle clip must
   start and end in the SAME standing pose at a FIXED position.
4. **Chroma key** - HSV hue keying of the green screen, output alpha.
5. **Normalize** - fixed canvas (2160x1215 in the reference toolkit), character
   centred in a standing pose, consistent scale across all clips.
6. **Review gate** - check silhouette, colours, eyes, outfit details, expression
   against the master BEFORE accepting a clip. Reject drift immediately.
7. **Player** - WuBuOS reads the normalized frames/clips.

## Rules that matter
- Mascot is a FIXED ASSET; environment/action are variables.
- Do not generate video from text -- always start from an approved image.
- Fast motion and extreme angles drift most: review those first.
- Background removal for these sheets is CONNECTIVITY (flood fill from the
  border), because the character is WHITE on WHITE paper: AI saliency matting
  erodes the fur (measured 26k interior holes).

## Status
Reference kit: DONE (55 poses sliced, 0 holes -- tools/assets/wubu_buddy_slices).
Green-screen generation: BLOCKED -- needs a video-model account/key.
Asset pipeline + player: build next.
