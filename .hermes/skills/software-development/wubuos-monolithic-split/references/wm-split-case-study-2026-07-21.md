# WM Split Case Study — 2026-07-21

## Source
`src/gui/wubu_wm.c` (548 lines, 5 concerns) was split into:

| File | Lines | Concern |
|------|-------|---------|
| `wubu_wm.c` | 186 | Core init, window lifecycle, GAAD snap |
| `wubu_wm_desktop.c` | 61 | Virtual desktop management |
| `wubu_wm_input.c` | 180 | Keyboard & mouse, drag operations |
| `wubu_wm_render.c` | 142 | Chrome, taskbar, snap preview rendering |
| `wubu_wm_internal.h` | 18 | `extern WubuWM g_wm` for sub-modules |

## Pattern: extern-global internal header

Unlike the opaque struct pattern where internals are hidden, the WM split
exposes the global state singleton via `extern WubuWM g_wm` in the internal
header. Sub-modules include the internal header and access `g_wm` directly.

**When to use this pattern:**
- Singleton state that multiple sub-modules need to share
- Tightly coupled concerns that share the same global state
- Converting a `static` global to `extern` to enable extraction

**When NOT to use this pattern:**
- State that should be instantiated multiple times (use factory + opaque)
- State that external consumers need to access (keep in public header)
- State where thread safety matters (use accessor functions with locking)

## Makefile update pattern

```makefile
# Add to GUI_OBJS (or appropriate object list):
GUI_OBJS += $(GUI)/wubu_wm_desktop.o $(GUI)/wubu_wm_input.o $(GUI)/wubu_wm_render.o

# Test targets linking wubu_wm.c must also add the new .c files:
test_wubu_wm:
	$(CC) ... $(GUI)/wubu_wm.c $(GUI)/wubu_wm_desktop.c $(GUI)/wubu_wm_input.c $(GUI)/wubu_wm_render.c ...
```

## Pre-existing test bugs found during split

1. `test_wubu_wm` couldn't link (STUB → missing `wubu_container_validate`/`parse`)
   - **Fix:** Add `$(RT)/wubu_container.c` to the test's compile line
2. Theme cycle test failed — expected 4 themes to wrap, but THEME_COUNT=5
   - **Root cause:** Zune theme was added, making 5 themes total (Win98, XP Luna,
     XP Media, WuBu, Zune). Test expected wrap after 4 cycles but needed 5.
   - **Fix:** Add 5th cycle step for Zune before wrap
3. Teal desktop color test used `0x00808000` instead of `0x008080`
   - **Root cause:** RGB macro produces `(r<<16 | g<<8 | b)` = `0x008080`, but
     test expected bytes in wrong order
   - **Fix:** expected value corrected to `0x008080`
