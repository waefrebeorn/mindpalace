# Creating the WuBu Buddy pet-deck (create, don't bake)

The user's intent for the buddy's own character art is to CREATE original pixel
art guided by the reference sheets, never to copy (bake) the sheets wholesale,
and never to hand-draw a stand-in character. The deliverable is a deck of
reactive poses (idle / working / celebrate / error / read) realized as coherent
pixel art that gets baked into the render path.

## The character (keep stable across every pose prompt)

A cute chubby WHITE/pale bunny pet, bright **green aviator cap with a RED 'W'**
on the front (the W is red -- a white W is the classic generation error), two
LONG ears angled outward with PINK inner ear, small black dot eyes, tiny mouth,
pear torso, mitten arms, oversized rounded feet.

## Loop

> **Prefer slicing the user's own reference sheets over generating lookalikes.**
> Prompt generation drifts (white W, missing scarf, featureless blob) and was
> superseded by `tools/buddy_slice_sheets.py`, which cuts the supplied sheets
> into ~55 real poses with AI matting. Generate new art only when a needed pose
> does not exist in the sheets.

1. **Generate each pose** with `image_generate` and the SAME base character
   block (above) plus the pose sentence. Keep palette + framing identical:
   "Clean Nintendo SNES 32-color palette, chunky 8px pixel blocks, crisp
   hard-edged pixels, isolated full-body on a solid charcoal-grey background,
   centered square." Aspect ratio `square`. Pose examples: idle standing; work
   "sitting at a small desk typing"; celebrate "arms raised in a V, happy
   closed-eye smile"; error "alarmed, paws on cheeks, sweat-drop"; read
   "holding an open book, curious".
   - `image_generate` is a deferred tool; call it via `tool_call` with
     `name=image_generate`. A reference `image_url` must be a web URL the
     generator can fetch -- a local `/tmp` path fails with "Reference image
     not found". If no URL is available, generate from the precise verbal
     character description (do NOT hard-block on needing the image).
2. **Remove the background with AI MATTING** (`tools/buddy_key_rembg.py` ->
   rembg, u2netp model): real alpha, clean edges, works on any background.
   Never colour-key (a white-bodied character whose fill is near the background
   gets erased) and do NOT use border flood fill -- it eats dark outlines and
   smears on any gradient/vignette.
3. **Normalize** all poses to one uniform size (e.g. 128x128 RGBA) with
   `Image.NEAREST` so deck frames line up.
4. **VISION IS THE ACCEPTANCE GATE; metrics only diagnose.** Look at the deck
   (contact sheet + individual frames). Numbers can prove a bake or render is
   faithful but say nothing about whether the art READS -- a numerically perfect
   copy of a bad sprite is still bad, so never sign off on pixel counts alone.
   Useful diagnostics after the eye pass: opaque-pixel count (thousands = real
   art, hundreds = watermark/clipped), presence of signature hues (red W, green
   cap, white body, pink inner ears), bbox consistency across poses.
5. **Commit** the deck under `tools/assets/wubu_buddy_deck/` (tracked) with a
   `PROVENANCE.md` naming the tool + prompt + "created, not baked".

## Wiring (next step after the deck exists)

Bake the created deck as the buddy's reactive states and cycle them by agent/OS
state (idle when quiescent, celebrating on success, alarmed on error) -- the
petdex pattern. The kernel bonzi gets a small baked subset (embedding the full
6.8MB states header whole is too large for the freestanding kernel; bake a
kernel-sized animation subset like the current `wubu_buddy_sprite.h` default).

## Kernel pitfalls

- The bare-metal bonzi (`src/kernel/wubu_bonzi.c`) is a DIFFERENT file from the
  hosted one (`src/gui/wubu_bonzi.c`, which blits via `wubu_mascot_blit_rgba`).
  Keep the two in sync; the kernel one must render the buddy sprite too.
- Include the baked sprite header into the kernel bonzi with a relative include
  (`#include "../gui/wubu_buddy_sprite.h"`) and alpha-blit it with
  `vbe_set_pixel`; the sprite grows the freestanding kernel .rodata by ~43KB,
  which is fine within the mapped image (kernel.elf ~2MB).
- A gentle idle bob (a triangle wave on the redraw counter offsetting the blit
  origin) turns a static sprite into living motion with no new frames. Measure
  motion by capturing two screendumps apart and reading a signature colour's top
  row (e.g. the green cap) -- not by a coarse scan that starts inside the sprite.
