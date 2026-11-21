# Migrating a WuBuOS surface onto the metric owner

Use when a GUI audit flags literal margins/gaps/radii/heights in a live
surface, or when unifying chrome across surfaces.

## 1. Enumerate, fresh

Saved audit JSON has stale line numbers (files shift under you). Re-scan:

```bash
# off-grid spacing-like defines (2,3,5,6,7,10,14,18,20,22,26,30,34 ...)
python3 - <<'PY'
import re,glob
bad={2,3,5,6,7,9,10,11,13,14,15,18,20,22,26,30,34}
for f in glob.glob("src/gui/**/*.c",recursive=True)+glob.glob("src/gui/**/*.h",recursive=True):
    if "/test" in f or "stub" in f or "legacy" in f: continue
    for i,l in enumerate(open(f,errors="ignore"),1):
        m=re.match(r"\s*#define\s+(\w*(?:PAD|GAP|MARGIN|SPACE|H|W|RADIUS|BORDER|INDENT)\w*)\s+(\d+)\b",l)
        if m and int(m.group(2)) in bad: print(f,i,m.group(1),m.group(2))
PY
```

## 2. Map each value to a token

| value seen | canonical token |
|---|---|
| 4 inset, 8 padding, 12 card gap | `WUBU_METRIC_MARGIN_XS/SM/MD`, `WUBU_METRIC_GAP_SM/MD` |
| row/item heights 22,24,26,30 | `WUBU_METRIC_ROW_H` (text rows) or `WUBU_METRIC_CONTROL_H` (tappable rows) |
| 30/34 button height | `WUBU_METRIC_CONTROL_H` |
| corner radius 6, 10 | `WUBU_METRIC_RADIUS_CONTROL`; 8 on panels/windows -> `WUBU_METRIC_RADIUS_WINDOW` |
| hairline frames | `WUBU_METRIC_BORDER_W` (2) |
| window caption | `WUBU_METRIC_TITLEBAR_H` (32) |
| taskbar band | `WUBU_METRIC_TASKBAR_H` (48) |

Leave alone: glyph/cell sizes (`GLYPH_ADVANCE 6`, `TERM_RENDER_CHAR_W`), item
counts, physics/visual offsets (slime seam in/out), progress-bar thickness.

## 3. Header consumers: alias, never restate

A header that cannot link the runtime `.c` uses the compile-time defines:

```c
#include "wubu_gui_metrics.h"
#define DOSGUI_TITLE_H   WUBU_METRIC_TITLEBAR_H
#define GR_BTN_H         WUBU_METRIC_CONTROL_H
```

Never write the number again in a second header -- the second copy is the
next disagreement.

## 4. Kill dead duplicates

Before adding a token, count its stem's users:

```bash
grep -rn "TOKEN_NAME" --include=*.c --include=*.h src/ | wc -l   # 1 == its own define only
```

A count of 1 means the name is dead; if a sibling spelling is the one actually
used, delete the dead copy and note why in a comment.

## 5. Gate it

Extend `src/gui/test_wubu_gui_metrics.c` with cross-owner assertions
(`WUBU_SPACE_XS == WUBU_METRIC_GAP_XS`, `DOSGUI_TITLE_H == m.titlebar_h`, grid
membership). Then:

```bash
make test_gui_metrics
make <affected surface suite>     # e.g. test_explorer, test_greeter, test_wm
make -k -j24 test                 # full gate; shared headers ripple widely
```

## Pitfall: a chrome-height change moves hit-test anchors

Tests that compute click coordinates from a frozen caption offset (e.g.
`wy + 24`) break the moment the canonical caption changes. Make such tests
call the real helpers (`title_bar_height()`, `border_width()`) or read the
canonical define, so a design change does not read as a product bug.
