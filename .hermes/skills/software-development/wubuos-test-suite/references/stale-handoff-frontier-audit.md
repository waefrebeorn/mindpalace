# Stale-Handoff Frontier Audit (2026-07-13 lesson)

A prestige-update / next-session prompt's "remaining gaps" list is a HYPOTHESIS,
not ground truth. The 2026-07-13 v27 handoff claimed "10 remaining `system()`
calls" and named a "monolith frontier" (`startmenu.c`, `explorer.c`,
`wubu_pkgmgr_pkg.c`, `wubu_metal.c`). A fresh audit proved BOTH wrong:
- Real `system()` calls in `src/`: exactly **1** (`vsl_nt_registry.c:215`). Every
  other grep hit was a *comment* ("replaces system()") from a prior closure.
- Every "monolith frontier" file was ALREADY split into 3–10-module families in
  an earlier session (the OBJS list names the siblings).

## Re-audit commands (run before acting on any "N remaining" claim)

1. **Real `system()` calls (exclude comment-noise):**
   ```bash
   grep -rEn '\bsystem\s*\(' src --include='*.c' \
     | grep -vE '_test\.c' \
     | grep -vE 'replaces system|no system|system\('
   ```
   Only lines that are actual calls remain. Count them.

2. **Confirm a "monolith frontier" file is already decomposed:**
   Find the OBJS variable it lives in and check for sibling `_<subsys>.c` modules:
   ```bash
   grep -nE 'startmenu\.o' Makefile   # -> GUI_OBJS lists _search/_tree/_power
   grep -nE 'wubu_metal\.o' Makefile         # -> METAL_OBJS lists _evdev/_x11/_vulkan/_audio
   ```
   If siblings exist, the file is a thin facade - NOT a monolith to split.

3. **Empty non-test stub bodies (real no-ops):**
   ```bash
   for f in $(grep -rEl '^\w.*\([^)]*\)\s*\{$' src --include='*.c' \
              | grep -vE '_test\.c|test_stub'); do
     awk '/^\w.*\([^)]*\)\s*\{$/{n=$0; getline; if ($0 ~ /^\s*\};?$/) print FILENAME": "n}' "$f"
   done
   ```
   This session: only ONE hit (`wubu_deploy_shutdown(void){}`) - a legitimate no-op.

## Rule
Never start a split on a file the handoff *names* as a monolith without first
confirming it isn't already split. The boss's standing order: "don't trust stale
probes/handoffs." A green gate + a re-audit is the only honest frontier.
