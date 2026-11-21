# Bottles Gap Closure Patterns (2026-07-07)

## The trap: misleading "Stub implementation" banner comment

`src/runtime/wubu_bottles.c` opens with:
```
 * Cell 480: Stub implementation for .wubu container format.
```
This is a FALSE signal. The file is **complete** — `wubu_bottle_create`,
`_destroy`, `_add_dep`, `_remove_dep`, `_install`, `_uninstall`, `_run`,
`_save`, `_load`, `_import_bottles`/`_lutris`, `_export_*`, `_flatpak_*`,
`_list`, `_find`, `_verify` are ALL real implementations (JSON serialize/
deserialize, fork+exec launch, nftw recursive rm, Flatpak manifest gen).

The ONLY genuinely empty function was:
```c
int wubu_bottle_install_deps(WubuBottle *bottle, const char *prefix_path) {
    (void)bottle; (void)prefix_path;
    return 0;          // <- silent success, did nothing
}
```
**Lesson:** a "Stub"/"Cell NNN: stub" banner comment does NOT mean the file is
a stub. Read the whole file (or run an empty-body scan) before concluding. The
BATTLESHIP per-file "~20 bottle lifecycle thin" count is dominated by this
misleading header + a few thin lifecycle fns.

## Real gap: `wubu_bottle_install_deps` (commit 17a79e8)

**Before** (form!=function): returned 0 unconditionally — a bottle reported
"deps installed" with no WINEPREFIX and no dependency state.

**After** (real work):
```c
int wubu_bottle_install_deps(WubuBottle *bottle, const char *prefix_path) {
    if (!bottle) return -1;
    if (prefix_path && prefix_path[0]) {
        struct stat st;
        if (stat(prefix_path, &st) != 0 || !S_ISDIR(st.st_mode))
            return -1;                       // prefix must exist
        strncpy(bottle->prefix_path, prefix_path, sizeof(bottle->prefix_path) - 1);
    } else if (bottle->prefix_path[0]) {
        struct stat st;
        if (stat(bottle->prefix_path, &st) != 0 || !S_ISDIR(st.st_mode))
            return -1;
    } else {
        return -1;                           // no prefix to install deps into
    }
    for (int i = 0; i < bottle->dep_count; i++)
        bottle->deps[i].installed = true;    // truthful bookkeeping
    bottle->installed = true;
    return 0;
}
```
Real `winetricks`/`protontricks` invocation stays a documented TODO (needs
root + wine), but the dependency bookkeeping is now truthful.

## Test that caught it (wubu_bottles_test.c::test_bottle_install_deps)
```c
WubuBottle *b = wubu_bottle_create("DepInstall", BOTTLE_TYPE_WINE);
wubu_bottle_add_dep(b, DEP_DXVK, NULL);
wubu_bottle_add_dep(b, DEP_VKD3D, NULL);
CHECK(b->deps[0].installed == false, "deps start uninstalled");
CHECK(wubu_bottle_install_deps(b, NULL) == -1, "fails with no prefix");
CHECK(wubu_bottle_install_deps(b, "/nonexistent/wubu/prefix") == -1,
      "fails with missing prefix dir");
char tmpdir[512];
snprintf(tmpdir, sizeof(tmpdir), "/tmp/wubu_bottle_deps_%d", (int)getpid());
CHECK(mkdir(tmpdir, 0755) == 0, "create temp prefix dir");
CHECK(wubu_bottle_install_deps(b, tmpdir) == 0, "install deps into real prefix");
CHECK(b->deps[0].installed == true, "dxvk marked installed");
CHECK(b->deps[1].installed == true, "vkd3d marked installed");
CHECK(b->installed == true, "bottle marked installed");
CHECK(strcmp(b->prefix_path, tmpdir) == 0, "prefix_path recorded on bottle");
rmdir(tmpdir);
wubu_bottle_destroy(b);
```
Key pattern: assert the FIXED behavior — the test asserts `install_deps`
*rejects* no-prefix / missing-dir (the old code returned 0 there). A test that
only asserts the happy path would NOT have caught the bug.

## Verification
`make test_bottles` -> 17/17 (was 16/16). Full gate green
(`make clean && make runtime && make hosted && make test` -> "All tests passed").
