# Theme Cycle Verification Protocol (2026-07-21)

## Current Capture Cycle (wubu_gui_shot.c)

The capture harness cycles through 5 themes in hardcoded phases:

| Frame | File | Theme | Expected Colors |
|-------|------|-------|-----------------|
| 01 | `01_desktop_win98.png` | Win98 Classic | Teal desktop (0,128,128), Navy title (0,0,128), Silver taskbar |
| 02 | `02_apps_win98.png` | Win98 Classic | Same as Frame 01, with apps |
| 03 | `03_controlpanel.png` | Win98 Classic | Navy title (0,0,128) on Control Panel |
| 04 | `04_apps_xp.png` | XP Luna Blue | Blue gradient title (0,83,138) |
| 05 | `05_apps_wubu.png` | WuBu Green | Green title (0,128,80) |

**Removed:** XP Media Orange theme (was Frame 04 in older builds)
- `THEME_XP_MEDIA_ORANGE` palette: `win_title_active=RGB(0xE8,0x6C,0x00)` = orange

## Verification Commands

```bash
# Generate fresh frames
cd /home/wubu/wubuos && make gui_shot && ./wubu_gui_shot

# Convert PPM to PNG
mkdir -p /tmp/ppng && for f in /tmp/wubu_gui_shots/*.ppm; do convert "$f" "/tmp/ppng/${f%.ppm}.png"; done

# Pixel-verify with PIL
python3 << 'EOF'
from PIL import Image
frames = [
    ("01_desktop_win98.png", "teal bg", (0,128,128), "navy title", (0,0,128)),
    ("02_apps_win98.png", "teal bg", (0,128,128), "navy title", (0,0,128)),
    ("03_controlpanel.png", "teal bg", (0,128,128), "navy title", (0,0,128)),
    ("04_apps_xp.png", "blue title", (0,83,138)),
    ("05_apps_wubu.png", "green title", (0,128,80)),
]
for fname, label1, c1, label2, c2 in frames:
    im = Image.open(f"/tmp/ppng/{fname}").convert("RGB")
    w,h = im.size
    # Sample title bar area (y<30)
    pixels = list(im.getdata())
    c1_count = sum(1 for p in pixels[:w*30] if abs(p[0]-c1[0])<=5 and abs(p[1]-c1[1])<=5 and abs(p[2]-c1[2])<=5)
    c2_count = sum(1 for p in pixels[:w*30] if abs(p[0]-c2[0])<=5 and abs(p[1]-c2[1])<=5 and abs(p[2]-c2[2])<=5)
    print(f"{fname}: {c1_count} {label1}, {c2_count} {label2}")
EOF
```

## Debugging Orange Window Complaints

If user reports "orange window":

1. **Check which frame they're viewing** - Frame 04 (XP Luna Blue) was previously XP Media Orange in older builds
2. **Verify fresh build** - `make gui_shot && ./wubu_gui_shot` must show EXIT=0
4. **Pixel-verify** - Count orange pixels (R>180, 50<G<150, B<50) in ALL frames
5. **Check cycle** - `grep -n "wubu_theme_set" wubu_gui_shot.c` should show:
   - Phase 1/2/3: `THEME_WIN98_CLASSIC`
   - Phase 4: `THEME_XP_LUNA_BLUE`
   - Phase 5: `THEME_WUBU_CUSTOM`
   - NO `THEME_XP_MEDIA_ORANGE`

## Verification Gate (Theme Changes)

- [ ] All 5 frames render (EXIT=0)
- [ ] PIL analysis confirms expected colors per frame
- [ ] No orange pixels in Frames 01-03, 05
- [ ] Frame 04 shows blue (XP Luna), NOT orange (Media Center)
- [ ] No "orange box" artifacts in Win98 or WuBu frames