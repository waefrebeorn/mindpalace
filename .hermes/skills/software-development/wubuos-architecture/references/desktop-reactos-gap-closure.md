# Desktop Vision & ReactOS Gap-Closure — 2026-07-12 (Stream A)

Study of the three "desktops" the user named (Win98/XP shell, Wayland hosted
display, ReactOS explorer/desktop.cpp) and the technique used to close the
remaining real desktop gaps. The 6-layer WuBuOS vision these map to:

```
TempleOS HolyC DOS soul   wubu_holyd REPL/JIT            (done: E4)
  └ ZealOS microkernel    ring-0, single-address-space   (done)
     └ Styx9 (our 9P)      file-backed IPC namespace      (partial: styxfs 11/11, NT bridge 20/297)
        └ NT personality   ReactOS-transliterated ABI    (spine exists; E1 20/297)
           └ Win98/XP shell wm/desktop/startmenu  (Stream A below)
              └ SteamOS      Arch container + Proton      (E2: gamescope/input/cloud = 0%)
```

Full plan: `DESKTOP_VISION_PLAN.md` in the repo root.

## The ReactOS lesson (explorer/desktop.cpp + shell32/CDesktopFolder)

The desktop is a **LIVE filesystem namespace**, not a constant array. WuBuOS's
gap was that `desktop_init()` registered a fixed app-array and `~/Desktop`
shortcuts only appeared after a manual Refresh.

### Technique — `wm_refresh_desktop()` enumerates folders + files + .desktop

Previously it scanned only `*.desktop`. Fixed to classify each `~/Desktop`
entry and surface it as a live icon:

- **directory** → `DESK_ICON_FOLDER` (green)
- **`*.desktop`** → `DESK_ICON_SHORTCUT`, display name strips the `.desktop`
- **other regular file** → `DESK_ICON_FILE` (cyan)

Dedup by display name. Skip `.` / `..`. Stat the path to classify dirs.

### Technique — `desktop_init()` refreshes on boot

Call `wm_refresh_desktop()` at the end of `desktop_init()` so the
namespace is live at startup (ReactOS init behavior), not only on manual Refresh.

### Technique — New Folder / New Text Document create REAL fs objects

`wm_new_folder()` (`mkdir ~/Desktop/New Folder` with `EEXIST` counter)
and `wm_new_text_doc()` (`open ~/Desktop/New Text Document.txt` `O_EXCL`)
then re-enumerate + reflow. Reuse the existing explorer create logic
(`explorer_new_folder` / `explorer_new_file`) but target `~/Desktop`
via `desktop_dir_path()` instead of the explorer's `current_path`.

### Technique — Sort modes resolve live metadata via `stat(target)`

`wm_sort_icons(DosGuiSortMode)` with Name / Size / Type / Date. Size/Type/
Date read `stat(icon->target)`. Note the test assertion expects **larger-first**
for Size — match the implementation or flip the comparator consistently.

### Technique — wire the previously-NULL context-menu actions

`wm_ctxmenu.c` had 5 `NULL` menu actions: `New → Folder`,
`New → Text Document`, `Sort By → Size/Type/Date Modified`. Wire each to the
real handlers (`ctx_action_new_folder`, `ctx_action_new_text_doc`,
`ctx_action_sort_by_size/type/date`).

## Regression-test pattern (isolated XDG_DESKTOP_DIR)

- `setenv("XDG_DESKTOP_DIR", tmpdir, 1)` BEFORE `wm_init`.
- Call `wm_init(w,h)` THEN `wm_refresh_desktop()` — do NOT call
  `desktop_init()` in a unit test (it spawns the service manager /
  autostart, side effects you don't want in `test_wm`).
- Assert the real fs object exists (`stat` + `S_ISDIR`/`S_ISREG`) AND `icon_count`
  grew AND sort order is correct.
- **Pitfall (cost real time):** when injecting a `wm_refresh_desktop()`
  call into multiple new tests via `s.replace(pat, repl, 1)`, the `1` (count)
  replaces only the FIRST match — often a DIFFERENT test (e.g. the persistence
  test). Verify each test individually afterward; the stray injection produces
  confusing `DBG` refreshes at the wrong path. Better: edit each test body
  explicitly or use distinct anchors.

## Status (2026-07-12)

Stream A **DONE** — `test_wm` 23/23 (+4 tests). Full gate green; hosted +
apps build clean. Commits: `3530c7b` (desktop closure), `01ce177` (vision doc +
STATE/slate). Remaining: E1 NT batches, E2 SteamOS gamescope/input/cloud, Styx9
registry-namespace glue.
