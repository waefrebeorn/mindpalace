# Theme CLI + Zune Theme Verification Commands (2026-06-23)

## CLI Flags

```bash
./src/hosted/wubu --theme zune --gui-screenshot /tmp/zune.ppm
./src/hosted/wubu --theme xp --gui-screenshot /tmp/xp.ppm
./src/hosted/wubu --theme xp-media --gui-screenshot /tmp/xp-media.ppm
./src/hosted/wubu --theme wubu --gui-screenshot /tmp/wubu.ppm
./src/hosted/wubu --theme win98 --gui-screenshot /tmp/win98.ppm
```

## Verification Scripts

### Zune Theme Verification
```bash
#!/bin/bash
# verify_zune_theme.sh

./src/hosted/wubu --theme zune --gui-screenshot /tmp/zune.ppm
ffmpeg -y -i /tmp/zune.ppm -update 1 /tmp/zune.png

python3 -c "
from PIL import Image
img = Image.open('/tmp/zune.png')
pixels = list(img.getdata())
non_black = [p for p in pixels if p != (0, 0, 0)]
orange = sum(1 for p in pixels if p == (232, 108, 0))  # E86C00
dark = sum(1 for p in pixels if p == (26, 26, 26))    # 1A1A1A
gray = sum(1 for p in pixels if p == (17, 17, 17))    # 111111
total = len(pixels)
print(f'Total pixels: {total}')
print(f'Non-black: {len(non_black)} ({100*len(non_black)/total:.1f}%)')
print(f'Zune orange (E86C00): {orange} ({100*orange/total:.1f}%)')
print(f'Dark (1A1A1A): {dark} ({100*dark/total:.1f}%)')
print(f'Gray (111111): {gray} ({100*gray/total:.1f}%)')

# Assertions
assert orange > 3000, 'Expected ~3915 orange pixels'
assert dark == 0, 'Expected no pure 1A1A1A pixels'
assert gray > 25000, 'Expected ~29459 gray pixels'
print('✅ Zune theme verification PASSED')
"
```

### All Themes Verification
```bash
#!/bin/bash
# verify_all_themes.sh

for theme in zune xp xp-media wubu win98; do
    echo "Testing $theme theme..."
    ./src/hosted/wubu --theme $theme --gui-screenshot /tmp/${theme}.ppm
    ffmpeg -y -i /tmp/${theme}.ppm -update 1 /tmp/${theme}.png
    echo "  Saved /tmp/${theme}.png"
done
```

### Color Verification Helper
```python
# verify_theme_colors.py
from PIL import Image
import sys

EXPECTED = {
    'zune': {'orange': (232, 108, 0), 'gray': (17, 17, 17)},
    'xp': {'blue': (0, 83, 158), 'gray': (192, 192, 192)},
    'win98': {'teal': (0, 128, 128), 'gray': (192, 192, 192)},
}

def verify(theme, png_path):
    img = Image.open(png_path)
    pixels = list(img.getdata())
    target = EXPECTED.get(theme, {})
    for name, color in target.items():
        count = sum(1 for p in pixels if p == color)
        print(f'{theme}: {name} {color} = {count} pixels')
```

## Expected Results

| Theme | Key Colors | Expected Pixel Counts |
|-------|------------|----------------------|
| Zune | Orange #E86C00 | ~3,900 pixels |
| Zune | Gray #111111 | ~29,400 pixels |
| XP Luna | Blue #00539E | ~3,900 pixels |
| XP Luna | Gray #C0C0C0 | ~277,000 pixels |
| Win98 | Teal #008080 | ~3,900 pixels |
| Win98 | Gray #C0C0C0 | ~277,000 pixels |

## CI Integration
```yaml
# .github/workflows/theme-test.yml
name: Theme Verification
on: [push]
jobs:
  theme-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install deps
        run: sudo apt-get update && sudo apt-get install -y ffmpeg python3-pil
      - name: Build
        run: cd /home/wubu/.hermes/profiles/mind-palace/home/myseed && make hosted
      - name: Test themes
        run: |
          for theme in zune xp xp-media wubu win98; do
            ./src/hosted/wubu --theme $theme --gui-screenshot /tmp/${theme}.ppm
            python3 verify_theme.py $theme /tmp/${theme}.ppm
          done
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| All black screenshot | Missing `vbe_swap()` | Call `vbe_swap()` after render |
| Wrong colors (yellow tint) | RGB macro bug | Fix RGB macro in wubu_theme.c:12 |
| Theme not applied | Missing `wubu_theme_init()` | Call before `wm_init()` |
| Theme flag ignored | Missing `--theme` parsing | Check hosted.c arg parsing |
| Missing THEME_ZUNE enum | wubu_theme.h not updated | Add THEME_ZUNE=4, THEME_COUNT=5 |