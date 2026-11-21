# wm.c Split — 2026-07-01 (Updated 2026-07-02)

## Before
`wm.c` — **2288 lines**, 7+ mixed sections in one file.

## After (Session 1 — 2026-07-01)
| File | Lines | Content |
|------|-------|---------|
| `wm.c` | 1787 | WM core: state, lifecycle, z-order, input dispatch, render pipeline, desktop icons, taskbar, systray, notification center, clock, virtual desktops, GAAD snap, wallpaper, query functions |
| `wm_holyc_term.c` | 238 | HolyCTerm struct, g_holyc_terms[], holyc_term_draw/eval/key/spawn |
| `wm_ctx_menu.c` | 192 | g_ctx_stack, ctx_menu_push/pop, all ctx_menu_* API functions |
| `wm_internal.h` | ~120 | DosGuiWM typedef + g_dwm extern + shared function declarations + WUBU_SAFE_STRING macros |

## After (Session 2 — 2026-07-02, fresh clone from GitHub, filter-repo recovery)
| File | Lines | Content |
|------|-------|---------|
| `wm.c` | 1965 | WM core (HolyC terminal removed, context menu API NOT extracted yet) |
| `wm_holyc_term.c` | 152 | Simpler version: HolycTerm struct, holyc_term_draw/on_key/eval/history/spawn |
| `wm_ctx_menu.c` | placeholder | Only includes internal header — context menu stays in wm.c for now |
| `wm_internal.h` | 109 | DosGuiWM typedef matching original struct field names + HolycTerm + internal forward decls |

## What Changed Between Sessions
1. **Context menu extraction reverted** — The original `wm.c` has ctx_menu_push/pop AND ctx_menu_create/add_item/show/hide AND dialog action callbacks (rename, delete, properties, shortcuts) all in the same TU. Extracting only the API functions causes duplicate symbol linker errors. The action callbacks must be decoupled first.
2. **wm_internal.h simplified** — Removed all DosGuiIcon/DosGuiContextMenu/CTX_ITEM_* redefinitions because `wm.h` already declares them. Internal header only adds HolycTerm, the DosGuiWM struct, and function declarations.
3. **HolycTerm struct simplified** — Was 2000-line ring buffer (matching HolyC's real compiler). Now 32-line scrollback + 16-entry history (simpler REPL).

## Filter-Repo Recovery Lesson
When `git filter-repo --invert-paths` is run a second time on an already-filtered repo, it **deletes the working tree**. Full recovery procedure:
1. Clone from remote: `git clone https://github.com/waefrebeorn/WuBuOS`
2. Reapply uncommitted changes from session transcript (rebuild files, repatch Makefile)
3. Re-run `git init` + `git add -A` to create fresh commit
4. Delete the borked repo: `rm -rf myseed-borked`

## Procedure Applied (Session 2)

1. **Created `wm_internal.h`** — included `wm.h` first, added only HolycTerm struct + DosGuiWM matching original + function forward decls. Did NOT redefine DosGuiIcon, DosGuiContextMenu, CTX_ITEM_*, etc.

2. **Extracted `wm_holyc_term.c`** — moved holyc_term_draw, holyc_term_on_key, holyc_term_eval, holyc_term_add_line, holyc_term_add_history, wm_spawn_holyc_term. Uses `vbe_draw_text` (not `vbe_set_fg`/`vbe_text` which don't exist in this repo).

3. **Made shared functions non-static** — raise_win, close_win, hit_test, draw_window, tc, theme, title_bar_height, taskbar_height_dynamic, border_width, theme_radius, draw_desktop_bg, load_default_wallpaper, draw_wallpaper, icon_grid_x, icon_grid_y, snap_icon_to_grid, snap_window_to_gaad, draw_window, spawn_window.

4. **Context menu NOT extracted** — g_ctx_stack, ctx_menu_push/pop, and all ctx_menu_* functions remain in wm.c because they share the TU with dialog callbacks (rename, delete, properties). wm_ctx_menu.c is an empty placeholder.

5. **Updated Makefile** — added wm_holyc_term.c and wm_ctx_menu.c to test_wm target.

## Key Lesson
The `static` mismatch is the #1 build error. When functions are declared non-static in the internal header, the forward declarations AND definitions in the original .c must BOTH be non-static too.

## Tests
- `test_wm` — 16/16 ✅ (unchanged)
- `test_phase4` — all pass ✅ (GUI regression suite)