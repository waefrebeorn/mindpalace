# Gate Blindness & Pre-Existing Reds (2026-07-07 findings)

Concrete recipes for three gaps in the build that a GREEN `make test` hides.

## 1. Gate-coverage blindness — `make test` does NOT build `APP_OBJS` or `tools:`

The gate tiers compile only a specific set of `.c` files into per-target test
binaries. They NEVER build:
- `APP_OBJS` = notepad/doom/explorer/terminal/paint/control + wubu_editor/
  wubu_canvas/wubu_codec/apps etc.
- `tools:` = `src/tools/*.c` (iso9660, weight_check, screenshot, wubu_demo_record…)

A file in `src/apps/*` or `src/tools/*` can be fully broken and the gate still
goes green. **Rule: after touching an app/`tools` file, also run its build
target.**
```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
make tools          # builds src/tools/*.o (gate does NOT)
make paint          # links an app target (gate does NOT)
make doom
```

## 2. `make paint` / `make doom` fail to LINK (pre-existing, OUTSIDE gate)

Symptom: `undefined reference to wubu_theme_colors` / `startmenu_toggle`
/ `wubu_settings_save` / `desktop_show_context_menu` / `wm_spawn_holyc_term`.
Root cause: the `paint:`/`doom:` recipes PRE-req `$(GUI_OBJS)` (so they get
compiled) but the final `$(CC) … -o` link line does NOT pass `$(GUI_OBJS)`.
Verify it is pre-existing (not your regression) with `git stash`:
```bash
git stash push -k -m verify-paint   # keep untracked, shelve tracked WIP
timeout 150 make paint 2>&1 | tail -12; echo "PAINT_AT_HEAD=${PIPESTATUS[0]}"
git stash pop
```
If `PAINT_AT_HEAD=2` with the same `undefined reference` lines → pre-existing,
report don't fix. Fix (if owned): add `$(GUI_OBJS)` to the link line, or the
specific objects: `wubu_theme.o startmenu.o wubu_settings.o
desktop.o wm.o wm_systray.o wm_ctxmenu.o
wm_holyc_term.o`.

## 3. `test_math` prints literal `FAIL` but exits 0 (silent mask)

`wubu_math` prints `pow: got=25.000004 exp=25.000000 … FAIL` and four `atan2`
tolerance misses, yet `main` returns 0 → `make test` shows `GATE_EXIT=0`.
The harness tally is defeated. Verify pre-existing:
```bash
git stash push -k -m verify-math
make test_math 2>&1 | grep -E "FAIL|PASS|Results:"
git stash pop
```
Same FAIL lines at HEAD → pre-existing, not linked to any calc/desktop change
(calc links only `calc.c`+tests). Report as a test-harness bug, don't suppress.

## Habit after ANY `make test`
```bash
grep -iE "FAIL|undefined reference" /tmp/gate_full.log
```
A `FAIL` line with `GATE_EXIT=0` is a lying gate — always surface it.
