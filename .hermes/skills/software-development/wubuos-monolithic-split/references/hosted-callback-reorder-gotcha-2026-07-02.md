# hosted.c Callback Reorder Gotcha

## The Bug

After splitting `wm.c` into `wm`/`systray`/`ctxmenu`/`holyc_term`, the hosted binary build failed with:

```
src/hosted/hosted.c:295:12: error: 'g_key_map' undeclared
```

## Root Cause

C requires variables/declarations to appear before their first use in each translation unit. In `hosted.c`, the functions are ordered as they appear in the Wayland callback list:

```
keyboard_enter()     // uses g_key_map
keyboard_leave()     // uses g_key_map  -- LINE 295
static g_key_map[256];   // declared AFTER its users! -- LINE 299
keyboard_key()       // uses g_key_map
keyboard_modifiers() // uses g_key_map
```

The `g_key_map` array was declared *after* `keyboard_leave()`. The file compiled before because the `.o` files were stale and never triggered a recompile of `hosted.o`. After `make clean`, the fresh compile hit the C error.

## Fix

Moved the global declaration before `keyboard_leave()`:

```c
/* Global key state map (256 keys, 0=up, 1=down) */
static uint32_t g_key_map[256];

static void keyboard_leave(...) {
    ...
    memset(g_key_map, 0, sizeof(g_key_map));
    ...
}
```

## Lesson

When you split a monolithic file and externalize `static` globals or functions, C's declaration-before-use rule can bite you if:
1. The global was originally at the *bottom* of the file (after all its users) — C only requires declaration-before-use within a TU, and `static` globals at file scope *can* be declared after functions that use them as long as both are in the same TU and the compiler sees the declaration before the use in a single pass.
2. You move the global to an internal header that gets `#include`d at the top — then it's before all users, which is correct.
3. But if you keep the global definition in the host .c and just remove `static` from it, its position relative to callers matters.

**Always place globals and auxiliary declarations at the top of the file or in an internal header, not in the middle/bottom.**

This is particularly common in callback-heavy files where the "natural" ordering follows the callback list (enter → leave → key → modifiers) rather than declaration-before-use.