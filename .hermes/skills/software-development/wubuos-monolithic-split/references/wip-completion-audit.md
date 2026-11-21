# WIP Monolith-Split Completion — Audit Playbook

Copy-paste commands used to finish a half-wired split (functions moved to new
files but the link/recipes never updated, or a phantom module left behind).
Run from repo root `/home/wubu/.hermes/profiles/mind-palace/home/myseed`.

## 0. Establish ground truth
Do NOT trust session summaries. Inspect the working tree:
```bash
git status --short
git diff Makefile | grep -E '^\+' | grep -E '\.o'   # what objects got added
# top monoliths
find src -name '*.c' | while read f; do n=$(wc -l < "$f"); [ "$n" -gt 500 ] && echo "$n $f"; done | sort -rn
```

## 1. Phantom-module scan (0 function bodies = scaffolding)
```bash
for f in $(git ls-files --others --exclude-standard 'src/**/*.c'); do
  n=$(grep -cE '^\s*(static\s+|inline\s+)?[A-Za-z_].*\([^;]*\)\s*\{' "$f")
  [ "$n" = "0" ] && echo "PHANTOM: $f ($(wc -l < "$f") lines)"
done
```
If a phantom exists, extract the real block from the parent into it (brace-count,
keep bodies identical) — do NOT just delete it.

## 2. Build from clean, ALL THREE targets
```bash
make clean >/dev/null 2>&1; make runtime >/tmp/r.log 2>&1 && echo RUNTIME_OK || { echo RUNTIME_FAIL; grep -iE 'error|undefined' /tmp/r.log|head; }
make clean >/dev/null 2>&1; make hosted  >/tmp/h.log 2>&1 && echo HOSTED_OK  || { echo HOSTED_FAIL;  grep -iE 'error|undefined|undeclared' /tmp/h.log|head; }
make clean >/dev/null 2>&1; timeout 2400 make test >/tmp/t.log 2>&1 && echo TEST_OK || { echo TEST_FAIL; grep -iE 'undefined|multiple def|error:|cannot find|fatal error' /tmp/t.log|head; }
```
`runtime` passing does NOT imply `hosted`/`test` pass — they use different link lists.

## 3. Link error => moved symbol not wired / still static
Pattern: consumer calls `foo()` "undeclared"/"undefined" after the split.
Fix:
- Create `<module>_internal.h`: `extern` the shared globals (e.g. `extern styxfs_file_t g_fs[...];`),
  declare the moved funcs non-static.
- In the new `.c`: define the shared globals ONCE, drop `static` from the moved funcs.
- In the old `.c`: `#include` the internal header, remove the now-shared globals/defs.

## 4. Makefile `.o` vs `.c` trap (the #1 recurring bug)
- The `hosted:` target links **prebuilt `.o`** listed in `HOSTED_OBJS`.
  A fix that adds a `.c` to a *test* recipe does NOT help `hosted`, and vice-versa.
- Audit `HOSTED_OBJS` (around line 168):
  ```bash
  mk=$(grep -A40 '^HOSTED_OBJS =' Makefile)
  echo "$mk" | grep -oE '\$\([A-Z]+\)/[a-z_/]+\.[oc]' | sort | uniq -d   # dups
  echo "$mk" | grep -oE '\$\([A-Z]+\)/[a-z_/]+\.c'                         # should be NONE
  ```
  Add split submodules (e.g. `styxfs_path.o styxfs_host.o styxfs_server.o`) to the
  `HOSTED_OBJS` styx line, and `hosted_styxfs.o` after `hosted.o`.
- Test recipes compile **`.c` inline** on the `$(CC) ... -o` line. Adding
  `styxfs_path.o` to the prerequisite line is useless — the compile line uses
  `styxfs.o` (object form). Change the COMPILE line to `styxfs.c styxfs_path.c`.
  For GUI tests, add the WM submodules (`wm_layout.c render.c taskbar.c
  desktop.c icons.c systray.c ctxmenu.c holyc_term.c`) — but only those NOT
  already present on that line (dedup to avoid "multiple definition").

## 5. Pre-existing breaks NOT caused by your split
e.g. `test_bridge`/`test_worldsim` fail with "No such file: src/worldsim/terrain.c".
An earlier commit relocated real sources into `src/_legacy_bak/` (renamed
`worldsim__terrain.c`) without deleting the recipe. Restore the real sources:
```bash
cp src/_legacy_bak/worldsim__terrain.c src/worldsim/terrain.c   # + entity/physics/render/sim/test_worldsim
```
Verify each restores with only benign warnings: `gcc -fsyntax-only -std=c11 -I src ... file.c`.

## 6. Final gate
- No phantom modules (re-run step 1).
- `make runtime && make hosted && make test` all green from `make clean`.
- Commit WIP-completion with a message listing the real defects found+fixed.
