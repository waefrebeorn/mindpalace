# Desktop delete → Recycle Bin closure (ReactOS CDesktopFolder::Delete lesson)

**Session 2026-07-19, commit `a4338a9`.** Closes a genuine form≠function gap in
`src/gui/wm_ctxmenu.c` + `desktop.c`. (The repo's pasted
DESKTOP_FIXUP_PLAN.md wrongly claimed the ctx actions were "empty stubs" — they
were already real; the real gap was what delete *did* with the underlying file.)

## Symptom
Right-click → Delete confirmed, but the underlying `~/Desktop` file/folder
stayed on disk and **reappeared on the next Refresh**. The icon was only hidden
in-memory (`g_delete_target->alive = false`).

## Root cause (two parts)
1. `dialog_delete_on_key` never called the already-existing Recycle Bin helper
   `wubu_trash_move(icon->target)` — it just flipped `alive`.
2. `wubu_trash_init()` was only called by the *trash unit test*, so in the real
   desktop `g_trash.trash_dir` was empty → `wubu_trash_move` returned -1
   silently (no trash dir to move into). Production deletes were no-ops.

## Fix
- `desktop_init()` now calls `wubu_trash_init()` (boot wiring — makes the
  trash dir exist at startup, like a real shell).
- `dialog_delete_on_key` confirm branch: `if (icon->target[0]) wubu_trash_move(icon->target);`
  then `alive=false`. Also loops every `alive && selected` icon and trashes each
  target → **multi-select delete** (the `selected` flag was already on
  `DosGuiIcon` but delete ignored it).
- Added `wm_compact_icons()` (`wm_icons.c`; declared in
  `wm.h`) — compacts dead (`alive==false`) entries so `icon_count` stays
  dense for refresh/sort/hit-test after a delete.

## Regression tests (wm_test.c)
- `test_icon_delete_moves_to_trash`: underlying file leaves `~/Desktop`
  (`stat` fails after move), icon count drops by 1.
- `test_icon_multiselect_delete`: selecting every live icon then delete removes
  the whole group + compacts.

## TEST-FIXTURE PITFALL (cost one debugging cycle)
`wubu_trash_move` guards against trashing the trash dir itself:
`strncmp(abs_path, g_trash.trash_dir, strlen(g_trash.trash_dir)) == 0` → return -1.
The trash dir is `<XDG_DATA_HOME>/Trash`. If your test fixture is named
**`Trash.desktop`**, its path `<desk>/Trash.desktop` matches the `Trash` prefix →
the move is rejected as "can't trash trash" and the file stays. **Name fixtures
something neutral (`Note.desktop`, `Item0.desktop`) — never a prefix of the
special dir the code guards against.**

## Makefile (link-dep cascade — see wubuos-build-integrity gotcha)
`wubu_trash.c` pulls `wubu_arch_mkdir_p` (`wubu_arch.c`) + `wubu_settings_get`
(`wubu_settings.c` already linked). Every test recipe that compiles
`wm_ctxmenu.c` (which now calls `wubu_trash_move`) must add
`wubu_trash.c` + `wubu_arch.c` to its link line, or you get
`undefined reference to wubu_trash_move` / `wubu_arch_mkdir_p`. Affected this
session: `test_wm` and `test_control`.
