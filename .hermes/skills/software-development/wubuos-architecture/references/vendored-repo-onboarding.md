# Onboarding an external WaefreBeorn repo into WuBuOS

Bringing a sibling repo (WuBuPad, WuBuOffice, WWW, WuBuContainer, wubuwizard)
under the WuBuOS tree. Done five times; the steps below are the ones that
actually cost time.

## 1. Add it as a submodule -- do not vendor a copy

```bash
cd /home/wubu/wubuos
git submodule add https://github.com/waefrebeorn/<Repo>.git src/apps/<repo>
```

Path by role: apps under `src/apps/`, interpreters/engines under `src/lua/`,
existing precedent under `src/brain/` and `src/runtime/container/`.

## 2. Wire the BUILD without duplicating theirs

- **CMake-based repos** (WuBuPad, WuBuOffice): add a driver file
  `mk/vendored.mk` with targets that shell out to their own CMake. Do NOT
  re-express their source list in the WuBuOS Makefile -- it rots immediately.
  Include it from the top-level `Makefile`.
  ```make
  wubupad:
  	@mkdir -p $(WUBUPAD_BUILD)
  	@cd $(WUBUPAD_BUILD) && cmake .. >/dev/null
  	@$(MAKE) -C $(WUBUPAD_BUILD) -j$$(nproc)
  ```
  Declare the dependency order explicitly (WuBuOffice compiles WuBuPad's
  editor core, so `wubuoffice: wubupad`).
- **Makefile-based repos**: add the objects to the matching `mk/objects.mk`
  list and sweep every test recipe that needs them.

## 3. Fix cross-repo paths -- they assume the ORIGINAL checkout layout

Moving a repo changes relative paths. Two recurring shapes:

- **Sibling lookups.** `../WuBuPad/src` assumes WuBuPad is a sibling of the
  including repo. In WuBuOS they may be siblings under `src/apps/`, so the
  path is right but the CASE or depth is wrong. Grep for the sibling name:
  `grep -rn '<Sibling>' --include='*.txt' --include='*.cmake' --include='*.c' .`
- **Module includes.** `#include "../wubuoxml/package.h"` implies an
  `apps/wubuoxml/` directory; if the module actually lives at `src/wubuoxml/`
  the correct form is `"../../src/wubuoxml/package.h"`. Two conventions can
  coexist in one tree -- fix the broken ones, do not normalise the working
  ones.

## 4. Wire the GATES

Run the repo's own suite first (`ctest` for CMake, `make test` otherwise) and
fix what is actually broken. Then wire the driver into a tier if it should run
with the WuBuOS gate.

Two recurring gate defects in onboarded repos:

- **A gate that hardcodes an external tool path** (a shared `tooling/`
  directory) FAILs everywhere but the author's checkout. Make the path a cache
  variable and SKIP cleanly -- see the gate-honesty rule in
  `wubuos-test-suite`.
- **A test that reads a fixture nothing generates.** Generate it as a build
  dependency (`add_custom_target` + `add_dependencies`, NOT
  `add_custom_command ... POST_BUILD` -- POST_BUILD only runs when the target
  relinks). A stdlib-only generator script is the house preference for
  hand-rolled formats.

## 5. Fix UPSTREAM, then bump the pointer

Edits made inside a submodule checkout are invisible to the WuBuOS commit and
are lost on the next `submodule update`. The order is:

```bash
# 1. commit + push in the submodule's own repo
cd src/apps/<repo> && git add -A && git commit -m "..." && git push origin HEAD
# 2. bump the pointer in WuBuOS
cd /home/wubu/wubuos
git submodule update --remote --init src/apps/<repo>
git add src/apps/<repo> && git commit -m "submodules: bump <repo> (...)"
```

`git submodule update --remote` also picks up commits the other owner pushed,
so re-run it before reporting the tree clean.

## 6. Verify

```bash
make -k -j24 test          # RC=0, 0 errors, 0 segfaults
make -j24                  # RC=0
make desktop_shot          # still writes its frames
```

Plus the onboarded repo's own suite. A green WuBuOS gate does not prove the
submodule builds -- it may not be linked into any target.
