# Extracted-but-dead builders (form-without-function)

When splitting a monolith, the extracted functions may have been **defined but
never called** in the original file — a pre-existing form-without-function gap.

## Detection (run AFTER extraction, BEFORE declaring done)
```sh
# For each function you moved into foo_db.c, confirm it has a caller:
grep -rn 'startmenu_build_main_menu\|startmenu_build_submenus' src/
```
If the only hit is the definition, the code was dead. The dynamic menu in
`startmenu.c` was rendering an EMPTY Programs/Accessories/WuBuOS/System
list because the builders were never invoked.

## Fix
Wire the extracted builders into the owning lifecycle/init function:
```c
void startmenu_init_enhanced(void) {
    startmenu_build_main_menu();   /* was dead: defined, never called */
    startmenu_build_submenus();    /* was dead: defined, never called */
    startmenu_build_programs_db();
    startmenu_search_init();
    startmenu_tree_build();
}
```
This is the SAME discipline as wiring the new `.o` into `GUI_OBJS` + test prereqs:
the symbol must be *linked* AND *called*. One without the other is a half-fix.

## Verified green
`make clean && make test` — `test_startmenu` 4/4; full gate green.
