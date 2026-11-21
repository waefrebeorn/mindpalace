---
name: wubu-module-registry
description: Wire orphaned modules into the build; no deletion.
category: devops
version: 1.0.0
tags: [wubuwizard, organization, makefile, integration, modules]
---

# The Spell Book (2026-11-11) -- a module is a SPELL

WuBuOS's DLL analogue. A reusable module is a **spell**, filed in a **book**
(a broad need) under a **genre** (a category); **casting** one is a standard,
fail-closed, idempotent operation. Spells live IN the OS as third-party lego
bricks -- they are never a separate repo.

```
src/spells/<book>/<genre>/<spell>/<spell>.spell   <- the manifest
                                    <sources>       <- the code
                                    <tests>         <- its gate
```

The manifest is `key value` text: `spell`, `version`, `book`, `genre`,
`origin` (first-party|third-party), `provides`, `needs`, `requires`,
`source`, `test`.  `#` begins a comment.

**`needs` and `requires` are deliberately different.**  `needs` is a capability
another SPELL provides -- resolved, provider cast first, and casting REFUSES
to proceed when unmet.  `requires` is a platform prerequisite (a Vulkan
driver, libc) -- reported, NOT resolved; treating a driver as an unmet need
makes every spell in the book look broken.

**Conflicts are never silently resolved.**  Two spells claiming one capability
record both names and the contested capability; the book picks no winner.
Also reported: duplicate names, missing declared sources, a manifest that
disagrees with its directory, unknown keys.

The layout rule is `<book>/<genre>/<spell>/<spell>.spell` -- the leaf
DIRECTORY is the spell's own name.  Getting this wrong made a 3-level path
parse as genre `render/vkd3d` instead of `render`.

The whole book is a GATE: `test_spellbook` scans the real tree, so a spell
filed wrong or a broken manifest fails the build.  `src/spells/README.md` is
the doctrine.

# The Module Registry Doctrine (2026-08-09)

The user's standing rule: **no code is deleted — everything is integrated
properly, then cleaned up.** "Get into all of our optimizers and research and
start actually making them usable tools instead of leaving them in the
toolbox." When memory fills up, make SKILLS — that's how cleanup works.

## The three-way module status (MODULES.md at repo root)
Every src/ module is exactly one of:
1. **WIRED** — compiled into the build (CORE_OBJ or EXTRA_OBJ) + a gate
2. **SUPERSEDED** — kept, marked in MODULES.md, replaced by the live version
3. **BROKEN** — fixed in place (never just left broken)

## The integration procedure (proven 2026-08-09, 48 orphans -> 41 wired)
1. **Inventory by STEM, not by `.o`.** `ls src/*.c` vs the Makefile text: a
   module is an orphan only when its stem (`wubu_cv`, not `wubu_cv.o`) appears
   nowhere, because many test targets link `src/X.c` directly instead of an
   object. Counting `.o` references over-reports: on this tree 24 "orphans"
   became 8 once the rule was "stem absent from the whole Makefile". Grep all
   makefiles (`Makefile mk/*.mk`), not just the root one.
2. **Compile-test each orphan**:
   `gcc -O2 -std=c11 -D_POSIX_C_SOURCE=200809L -I include -c src/X.c -o /tmp/X.o`
3. **Collision check vs CORE_OBJ** (duplicate symbols = superseded):
   `nm -g --defined-only` on both, diff the symbol sets. Common culprits:
   `wubu_mobius_new.c` dupes `wubu_mobius_gyrate`, `wubu_ngram_cascade.c`
   dupes `wubu_spec_cascade`, `wubu_mtp.c` dupes wubu_model.c's loader.
4. **Fix the mechanical breaks** (never delete): missing `stdint.h`/
   `stddef.h`/`stdio.h` includes, `M_PI` defines, CUDA `__device__` leaking
   into C headers (guard with `#if defined(__CUDACC__)` — close the guard
   BEFORE the CPU struct decls, keep the include-guard `#endif` last),
   missing `QK_K` defines, `immintrin.h` for `_MM_HINT_T0`.
5. **Wire into EXTRA_OBJ** in the Makefile (a single line list) + the
   pattern rule:
   ```
   EXTRA_OBJ = src/mod1.o src/mod2.o ...
   $(EXTRA_OBJ): src/%.o: src/%.c
       $(CC) $(CFLAGS) -I include -c -o $@ $<
   .PHONY: module-registry
   module-registry: $(EXTRA_OBJ)
       @echo "=== MODULE REGISTRY: $(words $(EXTRA_OBJ)) EXTRA modules ==="
   all: module-registry <existing targets>
   ```
6. **Wire the missing gates** (test_X.c exists but no Makefile target):
   follow the house pattern `test_X: tools/test_X.c src/X.c include/X.h` +
   `./$@` run.
7. **Update MODULES.md** — the registry is the source of truth.
8. `make module-registry` + `make all` must be 0 errors.

## The agnostic-naming doctrine (user, 2026-08-09)
"wubu35 is a depreciation term, we need agnostic name." Deprecated era-names
get AGNOSTIC renames — `wubu35_dims` -> `wubu_runtime_dims` (dims are data).
The rename procedure (124 refs / 19 files):
1. `git mv` the .c/.h first (git tracks the rename).
2. sed-replace the identifiers IN ORDER: the most specific first
   (`wubu35_dims_probe` before `wubu35_dims.h`, `.o` before `.c`), and
   include the TYPE name (`wubu35_dims_t`) — it's easy to miss.
3. Grep the WHOLE tree after: `grep -rn "oldname" src/ include/ tools/
   Makefile` — leftover hits are usually STALE .o files (rm them) and the
   Makefile header-dependency block (lines ~2090+, the
   `src/X.o: src/X.c include/X.h` tracking rules — update BOTH the
   left side and the deps).
4. Rebuild clean: the old-named .o objects carry the old macros baked in
   (undefined-reference to the old global) — `make clean` first.
5. Update docs/THEORY/research mentions + the Makefile rule NAMES
   (`test_wubu35_dims` -> `test_runtime_dims`) and the `*_run` variant.

## Pitfalls
- **Before writing a "missing" module, grep the WHOLE tree + the sibling
  compiler repo for the symbol — it often exists but unwired.** This session
  I created a duplicate `wubu_sf.c` soft-float module because compiler targets
  threw `undefined reference to wubu_sf_*`, then found `wubu_softfloat.c`
  already existed (its own test: 906/906) but was never in the OS's
  `COMP_OBJS`. Writing a second one is a covenant violation. Grep
  `grep -rln '<symbol>' src/` AND the symlinked compiler repo
  (`/home/wubu/wubunos`, flat at its root) — `src/compiler` is a symlink, so
  "source not in this repo" is often "source in the other repo". The fix is
  adding `$(COMP)/wubu_softfloat.o` to `COMP_OBJS` (and `rm`-ing any version
  you already wrote). Cost of the miss: ~100 lines of redundant code + lost
  time, undone.
- **An orphan `.o` listed in RT_OBJS-consume but defined in a never-linked
  leaf is an "undefined reference" for EVERY target that links the consumer.
  `wubu_image.c` (in RT_OBJS) called `wubu_arch_name`/`wubu_os_name`, which
  live in `wubu_image_names.c` — a module not in any object list. It broke
  every target touching wubu_image, not just the one under test. Wire the
  orphan into RT_OBJS; verify `test_high_gui` still green after.
- **A recipe that passes `.o` prerequisites must have them declared as
  prerequisites.** `test_era_apps` put `$(RT)/oci/*.o`, `wubu_wine_env.o`,
  `styxfs_vfs.o`, etc. on the `$(CC)` link line but not on the target's
  prerequisite line, so make never compiled them and `ld` reported
  `cannot find <path>.o`. Align the prereq line with the link line.
  (Note: `test_era_apps` ALSO is blocked by a pre-existing incomplete
  `COMP_OBJS` — `wubu_isa_driver.c` references `wubu_isa_pic/amdgpu/vulkan/`
  `wasm` and `wubu_mir_alloc_regs`/`wubu_tgemm` that are absent from the list
  — the same known-red `test_isa_driver` class, unrelated to era_apps. Don't
  half-fix by adding era-specific objects that merely shift the failure.)
- **A consumer-orphan fix must land on the LINK line, not the prerequisite
  line.** A recipe's `test_X:` prerequisite line lists source deps but make
  links only the TUs on the `$(CC)` command. A broad scan/sed that appends the
  provider to "the first line containing the missing symbol" tends to hit the
  prereq line (identical text), so an "already present" guard passes while
  `ld` still reports the undefined ref. Verify with `make -n test_X`
  (dry-run prints the exact link command) -- not by grepping recipe text.
  (The consumer-orphan class is ONE red family that bites many recipes at once:
  `styxfs_host.o`/`wm_desktop.c`/`wubu_hosted_hw.c` each need
  `wubu_guest_root.c`/`wubu_thermal_read.c`/`wubu_spawn.c`. A provider every
  shared consumer needs is best wired once into the object list that feeds
  those recipes, so the defect cannot recur recipe-by-recipe.)
- **Sweep both stem forms.** Some recipes compile the consumer fresh
  (`styxfs_host.c`) while others link the prebuilt object (`styxfs_host.o`);
  a `.o`-only grep misses the `.c` recipes and they stay red. Grep the bare
  stem when hunting a provider's consumers.
- **After ANY scripted Makefile rewrite, dry-run the edited targets.** A
  scripted append can splice a stray character that fuses a dead duplicate
  recipe into a live one (`make: tgcc: No such file` / Error 127, reported at
  a line whose source looks byte-perfect). `make -n <target>` shows the exact
  command lines; a clean C-compile recipe is a handful of lines, a corrupted
  one shows a stray token (`tgcc`) as the first word.
- **Real provider vs weak stub: check both collision directions first.**
  Before adding a real TU, check (a) the TEST does not already strongly stub
  the symbol (real TU is then a redefinition — `first_run_test.c` stubbed the
  wallpaper, so wiring `wubu_wallpaper.c` double-defined three functions), and
  (b) the provider's own transitive deps that cascade one more undefined ref
  (`wubu_account.c` pulls `wubu_pw_crypt_sha512` from `wubu_pwcrypt.c`;
  `vbe.c` in a non-`-DVBE_HOSTED` GUI test pulls `klog_printf` + `mem_alloc`).
  Prefer adding the missing WEAK symbol to the designated stub file
  (`wm_test_stub.c` / `desktop_stubs.c`, whose header contract says second
  shell dependencies belong there) over dragging the whole real module into a
  unit test; compile `vbe.c` under `-DVBE_HOSTED` so its kernel-log/allocator
  calls compile out.
- **Read the FULL failing-target set, never the head.** `grep ... | head` on
  the aggregate `make -k` Error list silently truncates -- the real count can
  be 3-4x the first ten lines. Extract the complete deduped set:
  `grep -a "make: \*\*\*" log | grep -aoE '\[mk/tests.mk:[0-9]+: [A-Za-z0-9_]+\]' | sort -u`.
- **The `test:` aggregate may omit standalone-failing recipes.** Measure the
  aggregate's own set, then run strays separately; a standalone red is not
  necessarily part of the gate.
- **An opaque handle the impl ignores is a design boundary, not a link fault.**
  When a test asserts fields of an opaque struct passed as `void*` to a
  function that deliberately `(void)`s it, the fix is a design decision, not a
  Makefile wiring, and not a layering-violating include of the struct's header
  into the runtime TU.
- **A bogus aggregate `test:` target can shadow the real one.** A leftover
  `test: test_ssm` / `	./test_ssm` with no matching source makes `make test`
  die on "No rule to make target 'test_ssm'" even though every per-target rule
  is fine. Symptom: `make test` fails instantly while `make test_<one>` works.
  FIX: repoint the aggregate at the real suite target (e.g. `test: test_400`)
  and grep for duplicate `^test:` definitions plus the "overriding/ignoring old
  recipe" warnings — duplicates mean a drifted Makefile where the LAST
  definition wins. Do this BEFORE running a full gate so you're not debugging
  a red that is pure Makefile drift.
- Makefile `all:` line is single-line with ~30 targets — patch by replacing
  the whole line, not appending after it.
- A file that includes `<cuda_runtime.h>` and uses GPU types is a BENCH
  fragment (e.g. kv_paged_attention.c used by tools/build_bench.sh) — mark
  bench-only, don't force it into a C build.
- "Duplicate basenames" across the tree are usually vault/ session archives
  (intentional preservation) — check the paths before flagging.
- The user's optimizer research (rsgd/qlearner/PID/TGT) is recorded in
  research/069: RSGD = Riemannian SGD for non-Euclidean params, qlearner =
  Q-learns the LR, TGT = gravitational-pole odometer for ravine
  navigation. The flat body Muons; the hyperbolic cells roll.
