# Localising a display artifact: client render / presentation / host

A defect the user describes as "a bar across the screen", "flashing", "a frozen
window" or "it looks wrong" can originate in three places. Capture all three
before theorising; each capture eliminates one layer.

## The three captures

1. **The client's own framebuffer.** `./src/hosted/wubu --screenshot /tmp/c.ppm`
   runs headless with no compositor. An artifact present here is the RENDER
   path. Caveat: this captures at the initial mode size (1024x768), not the
   resized live surface -- a size-dependent bug will not reproduce here and
   needs the live session.
2. **The compositor's own capture of its window.**
   `cd /home/wubu/wubucompositor && ./wubucompositor --screenshot /tmp/w.ppm`
   boots the client, captures the compositor's X window, exits. An artifact
   present here but absent from (1) is the PRESENTATION handoff.
3. **The host screen with the compositor killed.** `gnome-screenshot` after
   `pkill -x wubucompositor`. An artifact present here is the HOST desktop
   showing through, not the product. The host wallpaper and the product's
   desktop background are different colours, so a colour match identifies the
   layer immediately.

## Pixel-scan instead of trusting a description

"A dark band" does not give you its height or its colour. Scan one column and
print the transitions:

```python
from PIL import Image
im = Image.open(path).convert('RGB'); px = im.load()
prev = None
for y in range(im.size[1]):
    c = px[960, y]
    if c != prev:
        print(f'y={y}: {c}'); prev = c
```

The first transition is the artifact's true extent. Compare the band colour
with the theme's `desktop_bg` and with the wallpaper's top row: an exact match
to `desktop_bg` means something filled background over the wallpaper, which
points at render ORDER rather than at the wallpaper rect or the window
geometry.

## Burst capture for an intermittent artifact

An artifact that "appears and disappears" needs a burst, not a single frame:

```bash
for i in $(seq 1 12); do gnome-screenshot -f b_$i.png; sleep 0.25; done
```

Count how many frames show it, and diff consecutive frames
(`PIL.ImageChops.difference(a, b).getbbox()`). A diff bbox starting at y=0 means
the change touches the top edge.

## Which buffer did the compositor read?

When the artifact is presentation-side, two one-line probes settle it. Both are
temporary and must be removed before committing.

- Compositor `blit()`: print the first pixel of the compositor-owned XImage
  (`s->ximg->data`) -- what the compositor actually showed.
- Client `wm_render()`: print the first pixel of `vbe_framebuffer()` -- what the
  client rendered.

Client correct + compositor wrong => the compositor read a stale or partial
buffer. Both wrong => the render is at fault.

## The rule

A single buffer shared between a producer that paints row-by-row from the top
and a consumer that reads on its own schedule WILL tear, and the tear always
looks like a band across the TOP of the screen in whatever colour the producer
paints first. Fix it with a second buffer, not with a sync.
