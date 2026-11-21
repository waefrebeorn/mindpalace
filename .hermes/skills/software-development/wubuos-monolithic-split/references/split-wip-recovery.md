# Split WIP Recovery Patterns (WuBuOS monolith split)

Condensed from the 2026-07-11 session that resumed a half-finished split. The
WIP had extracted many `.c` files and rewired the Makefile but left the work
UNCOMMITTED and UNVERIFIED. Recovering it surfaced four repeatable failure
classes. This file is the supporting detail for the Pitfalls section of
`wubuos-monolithic-split` SKILL.md.

## 0. First move: build from CLEAN before touching anything
```bash
make clean && make runtime      # object-graph targets
make hosted                    # SPECIAL inline-link target
make test                      # full gate
```
A half-split often still "links" because stale `.o` files mask missing
objects. Clean build is the only honest signal. `make runtime` green does NOT
imply `make hosted` green (different link lines).

## 1. PHANTOM MODULE (form≠function) — top silent failure
A split file with ONLY a header comment + `#include`s (zero function bodies)
while the real code still sits in the parent is SCAFFOLDING, not a split. It
compiles, so it hides. Detect before/after every split:
```bash
for f in $(git ls-files --others --exclude-standard 'src/**/*.c'); do
  n=$(grep -cE '^\s*(static\s+|inline\s+)?[A-Za-z_].*\(\s*\)\s*\{' "$f")
  [ "$n" = "0" ] && echo "PHANTOM: $f"
done
```
Correct fix = ACTUALLY extract the block from the parent into it (brace-safe:
find the `/* ===` banner, then the function whose line ends with `{`, count
braces `depth = line.count('{')-line.count('}')` until depth==0). Do NOT delete
it. Real example: `wm_render.c` was a 12-line phantom; fixed by
extracting the 107-line render + dirty-tracking block from `wm.c`
(parent 873→766, module 123 lines, 6 real defs).

## 2. `.o` vs `.c`: object-graph targets vs test recipes
The single most iterated trap. Two wiring styles — never conflate:

- **Object-graph targets** (`runtime`, `hosted`, `GUI_OBJS`, `RT_OBJS`,
  `BEAR_OBJS`, `HOSTED_OBJS`) link PREBUILT `$(DIR)/foo.o` from the
  `$(DIR)/%.o: $(DIR)/%.c` rule. Add the module's `.o`.
  - `hosted:` is SPECIAL: its link recipe is an INLINE `.o` list (not the
    `HOSTED_OBJS` var). Add `$(HOSTED)/foo.o` in BOTH the var and the inline
    line, or it won't reach the binary.
- **Test recipes** (e.g. `test_proton2`, `test_control`, `test_launch`,
  `test_wubu`, `test_bridge`, `test_worldsim`) compile SOURCES inline:
  `$(CC) ... $(RT)/styxfs.c ... -o $(RT)/test`. They have NO prebuilt `.o`.
  So a recipe compiling a split parent needs the SPLIT SOURCE form:
  `$(RT)/styxfs_path.c`, `$(GUI)/wm_layout.c` — NOT `.o`
  ("cannot find styxfs_path.o: No such file").

Rule of thumb per recipe line:
- If it says `$(RT)/styxfs.c` and you need `styxfs_path`: ADD
  `$(RT)/styxfs_path.c`. Don't flip the existing `styxfs.c` to `.o`.
- If the recipe ALSO already lists the submodule (e.g. `wm_taskbar.c`),
  do NOT add it again — dedupe or get "multiple definition of
  taskbar_height".
- Don't switch a working `.c` test recipe to `.o` form — the `.o` won't exist
  after `make clean`.

Dedup helper (run over every patched recipe line):
```python
import re
def dedup_line(l):
    out=[]; seen=set()
    for t in l.split(' '):
        t=t.strip()
        if not t: continue
        m=re.match(r'\$\(GUI\)/(wm_\w+)\.[oc]$', t)
        if m:
            if m.group(1) in seen: continue
            seen.add(m.group(1))
        out.append(t)
    return ' '.join(out)
```
Full-sweep audit that found all breakage: grep every recipe line containing
`styxfs.c` but missing `styxfs_path`; grep every line with `wm.c` and
ensure each `wm_*` submodule appears at most once.

## 3. `_legacy_bak` relocation silently breaks `test_*` recipes
An earlier "relocate 27 non-build-graph .c into src/_legacy_bak/" commit moved
sources that some test recipes STILL referenced. Symptom:
`cc1: fatal error: src/worldsim/test_worldsim.c: No such file` during
`make test`, even though your split was fine. These are renamed
`<dir>__<file>.c` (e.g. `worldsim__terrain.c` -> `terrain.c`).
Fix: restore the real source from the backup:
```bash
cp src/_legacy_bak/worldsim__terrain.c   src/worldsim/terrain.c
cp src/_legacy_bak/worldsim__entity.c   src/worldsim/entity.c
cp src/_legacy_bak/worldsim__physics.c  src/worldsim/physics.c
cp src/_legacy_bak/worldsim__render.c    src/worldsim/render.c
cp src/_legacy_bak/worldsim__sim.c       src/worldsim/sim.c
cp src/_legacy_bak/worldsim__test_worldsim.c src/worldsim/test_worldsim.c
```
Pre-check across all recipes: extract every `src/.../*test*.c` path referenced
and assert the file exists. (Don't `git mv` — these were deliberately
relocated; just re-create the build-graph source at its referenced path.)

## 4. Shared GLOBALS need promotion too (not just functions)
When the extracted block reads/writes a global the parent owns, declare it
`extern` in the internal header and make its definition non-static in the
parent. Do NOT re-declare the global in the submodule (double storage -> desync).
One canonical definition + `extern` decl = single source of truth.
Example (bear_env / bear_env_npole): `g_episode_return` is defined in
`bear_env.c`, declared `extern` in `bear_env_internal.h`, read by
`bear_env_npole.c`. `ensure_episode_arrays` likewise promoted to non-static.

## 5. Honest end-to-end verification (don't trust the link)
- `make runtime` + `make hosted` + `make test` all green from CLEAN.
- Phantom scan returns empty.
- For physics/RL splits, compile the parent + new module + deps standalone and
  RUN a few steps; assert output is finite (no NaN) and sane:
  ```bash
  gcc -std=c11 -I src/bear smoke.c src/bear/bear_env.c src/bear/bear_env_npole.c \
      src/bear/bear_arena.c -lm -o /tmp/smoke && /tmp/smoke
  # npole(3 poles,4 envs) step OK, reward sum=8.241  (sane, no NaN)
  ```
- `make bear_train` may already be broken for an UNRELATED reason — but that
  does NOT mean "leave it". See §6: a deleted-build-target source is a REAL
  bug the user wants fixed, and the fix is usually to recover the genuine
  source from git history (it's often still 100% compatible).

## 6. BROKEN BUILD TARGETS = REAL BUGS, FIX THEM (not "pre-existing, skip")
The user's standing order: **fixing broken code is always a good move.**
When a Makefile target references a `.o` whose `.c` was deleted (e.g. by a
"purge orphan files" commit), that target is BROKEN, not "not your
regression". Recover the genuine source and make it build + RUN.

Concrete case (2026-07-11): `make bear_train` failed with
`No rule to make target 'src/bear/bear_train.o'` because commit `045ed3a`
("purge 60+ orphan files") deleted `src/bear/bear_train.c` while the Makefile
`bear_train:` target still listed `$(BEAR)/bear_train.o`. The deleted file was
the real BearRL training entry point (`main()` + PPO loop), fully compatible
with the current API. Fix:
```bash
git show 045ed3a^:src/bear/bear_train.c > src/bear/bear_train.c   # recover 193-line real source
```
Then verify EVERY symbol it calls still exists (grep the recovered source's
`bear_*`/`Bear*` tokens against current `src/bear`), restore it, build, and
actually RUN a few iters to prove it does real work (returns finite, steps
accumulate). Recovery > deletion. The purge mis-classified a live target as
orphan.

## 7. INCOMPLETE INCLUDE in a split module (the silent link-time trap)
When you split `foo.c` → `foo_sub.c`, the new module only keeps the includes
it *visibly* needs. But it may call a helper that was previously pulled in
TRANSITIVELY through `foo.c`'s includes. After the split, that transitive
include is gone → "undefined reference to `helper`" at link, even though the
helper is declared `static inline` in some header the submodule now doesn't
include.
Concrete case (2026-07-11): `bear_cudnn_cublas.c` (split from `bear_cudnn.c`)
calls `bear_gemm`, which is `static inline` in `bear_simd.h`. The new module
included only `bear_cudnn.h` (which does NOT include `bear_simd.h`) → undefined
reference. Fix: add the missing `#include "bear_simd.h"` to the split module.
Audit rule after ANY split: grep the new module for calls to symbols whose
definition lives in a header it doesn't directly include; add that include.
"Minimal includes" means include what you USE — not omit what you USE.

## 8. EXTRACTED MODULE COMES OUT TRUNCATED / CORRUPTED (2026-07-13, hosted.c)
Brace-counting/line-slice write-back can silently truncate the new module. In
the `hosted.c` -> `hosted_wayland.c` split the first write landed at **500 lines,
mid-function** (`pointer_button` cut off, every callback after `touch_cancel`
gone) and compiled with `error: expected declaration or statement at end of
input`. Verify integrity right after writing:
1. `wc -l <module>.c` — must match source-region size + added header/entry-point
   lines; a shortfall = truncation.
2. `grep -c <last-fn-in-region> <module>.c` — must be ≥ 1. (For hosted, `touch_down`
   is the last callback — `grep -c touch_down` must be ≥ 1.)
3. If corrupt, **regenerate from pristine HEAD, not the working tree** (`git show
   HEAD:src/hosted/hosted.c`, slice the region by content anchors, rewrite). The
   working tree may already hold the half-corrupt version.
4. `make clean && make <target>` after — stale `.o` from a prior broken link masks
   missing-symbol errors.

## 9. ENTRY-POINT FACADE when the trimmed core still calls moved internals
After trimming, if the core still names a moved symbol (`wl_*_listener`,
`shm_buffer_create`, `wayland_frame_render`, SHM globals, etc.), the split is NOT
clean. Don't leave dangling refs and don't duplicate the code in both TUs.
Expose **non-static entry points** from the module and rewire the core:
- `hosted_wl_connect(state)` = wl_display_connect + bind globals + create surface
  + wire all listeners + create SHM buffers.
- `hosted_wl_disconnect()` = destroy globals, disconnect.
- `hosted_wl_dispatch()` = dispatch_pending + flush.
- `hosted_wl_frame_render()` = the actual blit body.
Core: `hosted_init`->`hosted_wl_connect`, `hosted_run`->`hosted_wl_dispatch` +
`hosted_wl_frame_render`, `hosted_shutdown`->`hosted_wl_disconnect`,
`hosted_blit`->`hosted_wl_frame_render`. Module-owned globals stay `static`; only
the entry-point prototypes + shared types go in the internal header. See
`references/extraction-integrity-and-facade.md` for the full worked example.

## 10. SHARED TYPE USED BY BOTH TUs -> internal header
If a header declaration (e.g. an entry-point prototype) references a type defined
inside one `.c` (`shm_buffer_t` + `SHM_BUFFERS`), the other TU can't compile it.
Move the `typedef`/`#define` into the shared internal header. A global used by both
TUs is `extern` in the header and defined **once** (non-`static`) in one TU.

## 11. PRE-EXISTING Makefile GAP != YOUR BUG (discipline, not a fix)
`make hosted` failed `cannot find src/runtime/wubu_archd_fs.o`;
`make test_hosted` failed `undefined reference to fs_add_dir`. Confirmed BOTH
fail identically on pristine HEAD (`git stash` your split files, run the target,
`git stash pop`). They are latent recipe gaps (link line references a `.o` with no
build rule; test recipe missing source files). Note them, keep the split proven
by `make runtime`+`make hosted`+`make test` green, and move on — don't rabbit-hole
unrelated Makefile debt unless explicitly asked. (Contrast with §6: a target whose
SOURCE was *deleted* is a real bug to recover; a target merely missing a prebuilt
`.o`/source in its recipe is pre-existing gap, not your regression.)
