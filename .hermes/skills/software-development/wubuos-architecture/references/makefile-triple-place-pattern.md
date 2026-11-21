# Makefile Triple-Place Pattern — Adding a GUI Module

**Date:** 2026-07-07  
**Context:** Adding `wubu_welcome.c` to WuBuOS required exactly three Makefile
changes plus zero test-target changes (welcome is only called from `hosted.c`,
not from any test code).

## The Pattern

Every source file under `src/gui/` must appear in three places in the Makefile:

### Place 1 — `GUI_OBJS` (line ~41)

Object list for the `make gui` target. Controls compilation only — no linking.

```makefile
GUI_OBJS = ... $(GUI)/wubu_welcome.o $(GUI)/desktop.o ...
```

Add in alphabetical-ish position. This automatically triggers `make gui` to
compile the new `.c` into `.o`.

### Place 2 — `hosted:` recipe (line ~173)

The hosted binary compiles `.c` files directly in one gcc invocation (it does
NOT use the `.o` files from `GUI_OBJS`). A missing `.c` here produces:
```
/usr/bin/ld: .../hosted.c:... undefined reference to `wubu_welcome_init'
```

```makefile
hosted:
	$(CC) $(CFLAGS) ... \
		... $(GUI)/wubu_wallpaper.c $(GUI)/wubu_welcome.c \
		...
```

The continuation line ends with `\` (backslash-newline). Makefiles use **tabs**
for recipe lines — always verify with `cat -A Makefile` if the build fails with
a missing-separator error.

### Place 3 — `HOSTED_OBJS` (line ~157)

Dependency list for `make` change detection. When the `.c` changes, `make
hosted` sees the `.o` dependency and recompiles. NOT used for actual linking.

```makefile
HOSTED_OBJS = ... $(GUI)/wubu_wallpaper.o $(GUI)/wubu_welcome.o ...
```

### When Test Targets Need the Module

If the new module is called by a function that a test target links, the test's
recipe also needs the `.c` file. For example, `test_wm` and
`test_control` both link `wm.c` — if the WM gains a new dependency,
both tests must get it.

Test recipes use `.c` directly:
```makefile
test_wm:
	$(CC) ... \
		... $(RT)/wubu_session.c $(RT)/wubu_compat_db.c \
		$(GUI)/wm_test.c -o $(GUI)/wm_test -lm
	$(GUI)/wm_test
```

**Rule of thumb**: if `grep -rn 'call_to_your_fn' src/gui/` finds hits in
files that are linked by a test target, add the new module to that test.

## Concrete Example — Adding `wubu_welcome.c`

On 2026-07-07, `wubu_welcome.c` was added. The three Makefile changes:

**GUI_OBJS** (line ~41):
```patch
-$(GUI)/wubu_wallpaper.o $(GUI)/desktop.o
+$(GUI)/wubu_wallpaper.o $(GUI)/wubu_welcome.o $(GUI)/desktop.o
```

**hosted: recipe** (line ~173):
```patch
-$(GUI)/wubu_wallpaper.c \
+$(GUI)/wubu_wallpaper.c $(GUI)/wubu_welcome.c \
```

**HOSTED_OBJS** (not strictly needed — hosted compiles .c files, but added
for dependency tracking consistency).

`wubu_welcome.c` is only called from `hosted.c` (not from any GUI file that
test targets link), so no test target changes were needed. The gate verified:
- `make gui` compiled `wubu_welcome.o` ✅
- `make hosted` linked `wubu_welcome_init` ✅
- `make test` ran 747+ assertions, all green ✅

## Verification Command

Always run the full gate when adding a module:
```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
make clean >/tmp/gate.log 2>&1
make runtime >>/tmp/gate.log 2>&1
make hosted >>/tmp/gate.log 2>&1
make test >>/tmp/gate.log 2>&1
tail -3 /tmp/gate.log  # Should say "GATE_EXIT=0"
grep -iE "FAIL|undefined reference|error:" /tmp/gate.log | grep -viE "Operation not permitted|Invalid argument|non-fatal|Vulkan"
```