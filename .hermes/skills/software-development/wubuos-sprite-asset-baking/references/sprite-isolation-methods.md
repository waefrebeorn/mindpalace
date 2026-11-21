# Sprite isolation from sheets — method notes

Depth behind the always-on rules in SKILL.md. Read this when a bake comes out
wrong and the three-stage pipeline (cell -> border flood -> connected component)
is not producing a clean sprite.

## Why colour keying is never the answer here

A white-furred mascot on a white sheet has its fill at the SAME value as the
background. Any test of the form `if min(r,g,b) >= threshold: alpha = 0` erases
the body and leaves semi-transparent rims -- the sprite renders as a watermark.
Colour cannot distinguish the two whites; only CONNECTIVITY can, because the fur
is enclosed by an outline while the background touches the sheet edge.

## What established tools do

Method references worth consulting rather than re-deriving:

- **Sprite-Extractor** (EricsonWillians/Sprite-Extractor): flood-fill background
  removal with an explicit mode for pale/low-contrast subjects so facial features
  do not fragment; `--min-size` drops noise blobs; `--padding`; auto-crop.
- **sprite-gen** (aldegad/sprite-gen): `connected_components()` flood-fills alpha
  blobs and records bbox + area + x-center per blob. For poses JOINED BY THIN
  BRIDGES it uses projection profiles plus a minimum-cost cut instead of
  morphology -- this is the technique the SKILL.md rule encodes.
- Standard computer-vision practice: scan-and-flood connected-component labelling
  (union-find, two passes) gives identical results to repeated seed flood fills and
  additionally returns per-blob statistics for free.

The common shape: label the foreground ONCE, then select the blob you want by a
seed, and treat everything else as foreign. Do not re-derive a mask per pose.

## Cut scoring (minimum-cost bridge cut)

Used when two poses are joined by a narrow neck and you must detach one.

```
for axis in (x, y):
    span = width if axis == x else height
    for c in range(2, span - 2):
        band   = columns (or rows) [c-1 .. c+1]
        cost   = kept pixels inside the band
        left   = kept pixels strictly before the band
        small  = min(left, total - left - cost)
        big    = max(left, total - left - cost)
        if small <= total * 0.08 and big >= total * 0.85:
            keep the cheapest such band
apply the cut by clearing the detached side
```

Reject a candidate that costs more than a couple of percent of the sprite: a
expensive cut means the objects are genuinely merged, not bridged.

## Diagnosing an incurable artefact

Before assuming your pipeline is broken, establish whether the contact is real:

1. Render the isolated sprite and view it at 4x -- confirm the artefact is INSIDE
   the sprite and not an artefact of your screenshot crop.
2. Compare the opaque-pixel count before and after the attempted fix.
   Byte-identical counts mean the cut never fired, i.e. no straight band separates
   the objects.
3. Check whether the neighbouring artwork physically overlaps this pose's cell in
   the source sheet. If it does, the fusion is the artist's, not yours.

When (2) and (3) both say the contact is wide, stop tuning and document the
artefact. Endless threshold search on an unfixable input is pure time loss.

## Framing sanity numbers

At 96x96 (9216 px), opaque counts by health:

| Opaque px | Meaning |
|---|---|
| ~1.5k | ghosted -- a colour key ate the body |
| ~3.5k-8.6k | healthy, varies with pose bulk |
| drop after a change | you lost art |
| rise after a change | you stopped clipping |

Bounding-box extremes are also diagnostic: content touching row 0 or row N-1 means
the trim was tight against a neighbour or the canvas had no margin.
