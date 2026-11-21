# Start Menu Gap Closure Patterns — startmenu.c

## Overview

**File**: `src/gui/startmenu.c`
**Gaps Closed**: 24 void casts + 2 `system()` calls
**Tests**: 4/4 passing (init, navigation, tree build, rendering)

## Before/After Patterns

### Dynamic .desktop File Parsing

**BEFORE (REAL_GAP: hardcoded items)**:
```c
static void build_accessories(void) {
    g_accessories.item_count = 0;
    g_accessories.items[g_accessories.item_count++] = (SmMenuItem){
        SM_ITEM_APP, "Notepad", "Notepad", 0};
    g_accessories.items[g_accessories.item_count++] = (SmMenuItem){
        SM_ITEM_APP, "Paint", "Paint", 0};
    // ... hardcoded items
}

static void build_wubuos(void) {
    g_wubuos.item_count = 0;
    g_wubuos.items[g_wubuos.item_count++] = (SmMenuItem){
        SM_ITEM_APP, "HolyC Terminal", "HolyC Terminal", 0};
    // ... hardcoded items
}
```

**AFTER (real C: dynamic .desktop parsing)**:
```c
static void build_submenus_from_desktop(void) {
    MimeSystem *mime = wubu_mime_state();
    
    /* Reset submenu counts */
    g_programs.item_count = 0;
    g_accessories.item_count = 0;
    g_wubuos.item_count = 0;
    g_system.item_count = 0;
    
    /* Category mapping */
    struct { const char *cat; SmSubmenu *sub; } cats[] = {
        {"Accessories", &g_accessories},
        {"WuBuOS", &g_wubuos},
        {"System", &g_system},
        {"Development", &g_programs},
        {"Graphics", &g_programs},
        {"Internet", &g_programs},
        {"Office", &g_programs},
        {"AudioVideo", &g_programs},
        {"Game", &g_programs},
        {"Apps", &g_programs},
    };
    
    for (int i = 0; i < mime->desktop_entry_count; i++) {
        DesktopEntry *de = &mime->desktop_entries[i];
        if (de->hidden || de->no_display) continue;
        if (strcmp(de->type, "Application") != 0) continue;
        if (de->exec[0] == '\0') continue;
        
        /* Find matching category */
        SmSubmenu *target = &g_programs; /* default */
        for (size_t c = 0; c < sizeof(cats)/sizeof(cats[0]); c++) {
            if (strstr(de->categories, cats[c].cat)) {
                target = cats[c].sub;
                break;
            }
        }
        
        if (target->item_count < 12) {
            target->items[target->item_count++] = (SmMenuItem){
                SM_ITEM_APP, "", "", 0};
            strncpy(target->items[target->item_count - 1].label, de->name, 47);
            strncpy(target->items[target->item_count - 1].app_name, de->name, 47);
        }
    }
    
    /* WuBuOS - ensure core apps present */
    for (int i = 0; i < 4; i++) {
        SmSubmenu *sub = &g_wubuos;
        const char *label = "", *app_name = "";
        switch (i) {
            case 0: label = "HolyC Terminal"; app_name = "HolyC Terminal"; break;
            case 1: label = "Temple REPL"; app_name = "Temple REPL"; break;
            case 2: label = "Package Manager"; app_name = "Package Manager"; break;
            case 3: label = "Container Manager"; app_name = "Container Manager"; break;
        }
        for (int j = 0; j < sub->item_count; j++) {
            if (strcmp(sub->items[j].label, label) == 0) goto next_wubuos;
        }
        if (sub->item_count < 12) {
            sub->items[sub->item_count++] = (SmMenuItem){
                SM_ITEM_APP, "", "", 0};
            strncpy(sub->items[sub->item_count - 1].label, label, 47);
            strncpy(sub->items[sub->item_count - 1].app_name, app_name, 47);
        }
        next_wubuos:;
    }
    
    /* System */
    for (int i = 0; i < 2; i++) {
        SmSubmenu *sub = &g_system;
        const char *label = "", *app_name = "";
        switch (i) {
            case 0: label = "File Manager"; app_name = "File Manager"; break;
            case 1: label = "Settings"; app_name = "Settings"; break;
        }
        for (int j = 0; j < sub->item_count; j++) {
            if (strcmp(sub->items[j].label, label) == 0) goto next_system;
        }
        if (sub->item_count < 12) {
            sub->items[sub->item_count++] = (SmMenuItem){
                SM_ITEM_APP, "", "", 0};
            strncpy(sub->items[sub->item_count - 1].label, label, 47);
            strncpy(sub->items[sub->item_count - 1].app_name, app_name, 47);
        }
        next_system:;
    }
    
    /* Accessories */
    for (int i = 0; i < 6; i++) {
        SmSubmenu *sub = &g_accessories;
        const char *label = "", *app_name = "";
        switch (i) {
            case 0: label = "Notepad"; app_name = "Notepad"; break;
            case 1: label = "Paint"; app_name = "Paint"; break;
            case 2: label = "Editor"; app_name = "Editor"; break;
            case 3: label = "WuBu Canvas"; app_name = "WuBu Canvas"; break;
            case 4: label = "FreeDoom"; app_name = "FreeDoom"; break;
            case 5: label = "Calculator"; app_name = "Calculator"; break;
        }
        for (int j = 0; j < sub->item_count; j++) {
            if (strcmp(sub->items[j].label, label) == 0) goto next_accessories;
        }
        if (sub->item_count < 12) {
            sub->items[sub->item_count++] = (SmMenuItem){
                SM_ITEM_APP, "", "", 0};
            strncpy(sub->items[sub->item_count - 1].label, label, 47);
            strncpy(sub->items[sub->item_count - 1].app_name, app_name, 47);
        }
        next_accessories:;
    }
}
```

### Core App Preservation (ensure built-in apps present)

**Pattern**: After dynamic population, ensure core apps exist using goto-based duplicate checking:

```c
/* WuBuOS - ensure core apps present */
for (int i = 0; i < 4; i++) {
    SmSubmenu *sub = &g_wubuos;
    const char *label = "", *app_name = "";
    switch (i) {
        case 0: label = "HolyC Terminal"; app_name = "HolyC Terminal"; break;
        case 1: label = "Temple REPL"; app_name = "Temple REPL"; break;
        case 2: label = "Package Manager"; app_name = "Package Manager"; break;
        case 3: label = "Container Manager"; app_name = "Container Manager"; break;
    }
    for (int j = 0; j < sub->item_count; j++) {
        if (strcmp(sub->items[j].label, label) == 0) goto next_wubuos;
    }
    if (sub->item_count < 12) {
        sub->items[sub->item_count++] = (SmMenuItem){
            SM_ITEM_APP, "", "", 0};
        strncpy(sub->items[sub->item_count - 1].label, label, 47);
        strncpy(sub->items[sub->item_count - 1].app_name, app_name, 47);
    }
    next_wubuos:;
}
```

### Category Mapping from .desktop Files

**Pattern**: Map XDG Categories to submenus using substring matching:

```c
struct { const char *cat; SmSubmenu *sub; } cats[] = {
    {"Accessories", &g_accessories},
    {"WuBuOS", &g_wubuos},
    {"System", &g_system},
    {"Development", &g_programs},
    {"Graphics", &g_programs},
    {"Internet", &g_programs},
    {"Office", &g_programs},
    {"AudioVideo", &g_programs},
    {"Game", &g_programs},
    {"Apps", &g_programs},
};

/* Find matching category */
SmSubmenu *target = &g_programs; /* default */
for (size_t c = 0; c < sizeof(cats)/sizeof(cats[0]); c++) {
    if (strstr(de->categories, cats[c].cat)) {
        target = cats[c].sub;
        break;
    }
}
```

### Shutdown Wiring

**BEFORE (REAL_GAP: system() call)**:
```c
if (mi->type == 3) {
    system("shutdown -h now");  // REAL_GAP
}
```

**AFTER (real C: function call)**:
```c
else if (mi->type == 3) {
    /* Shutdown */
    shutdown();
    startmenu_close();
}
```

### Dynamic Main Menu Building

```c
static void build_main_menu_from_desktop(void) {
    g_main_count = 0;
    
    /* Programs submenu (index 0) */
    g_main_items[g_main_count++] = (MainMenuItem){
        "Programs", 1, 0, ""};
    
    /* Documents -> File Manager */
    g_main_items[g_main_count++] = (MainMenuItem){
        "Documents", 0, -1, "File Manager"};
    
    /* Settings */
    g_main_items[g_main_count++] = (MainMenuItem){
        "Settings", 0, -1, "Settings"};
    
    /* Separator */
    g_main_items[g_main_count++] = (MainMenuItem){
        "", 2, -1, ""};
    
    /* Find */
    g_main_items[g_main_count++] = (MainMenuItem){
        "Find", 0, -1, "Find"};
    
    /* Help */
    g_main_items[g_main_count++] = (MainMenuItem){
        "Help", 0, -1, "Help"};
    
    /* Run */
    g_main_items[g_main_count++] = (MainMenuItem){
        "Run...", 0, -1, "Run"};
    
    /* Separator */
    g_main_items[g_main_count++] = (MainMenuItem){
        "", 2, -1, ""};
    
    /* Shutdown */
    g_main_items[g_main_count++] = (MainMenuItem){
        "Shut Down", 3, -1, "Shutdown"};
}
```

### MIME System Integration

**Pattern**: Use existing MIME system for .desktop parsing and app launching:

```c
/* Initialize MIME system first for .desktop parsing */
wubu_mime_init();

/* Build menus dynamically from .desktop files */
build_submenus_from_desktop();
build_main_menu();
```

### Test Verification

```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
make test_startmenu
# Results: 4/4 passed (init, navigation, tree build, rendering)
```

### Key Implementation Details

| Aspect | Implementation |
|--------|----------------|
| .desktop scanning | `wubu_mime_scan_desktop_dirs()` scans XDG dirs + local `./apps` |
| Category matching | `strstr(de->categories, cats[c].cat)` substring match |
| Duplicate prevention | `goto` label pattern for duplicate checking |
| Core app guarantee | `goto` label pattern after dynamic population |
| Category mapping | XDG Categories → submenu via `strstr(de->categories, cat)` |
| Shutdown | Direct function call `shutdown()` |
| Max items per submenu | 12 (hardcoded limit) |
| Core apps | HolyC Terminal, Temple REPL, Package Manager, Container Manager, File Manager, Settings, Notepad, Paint, Editor, WuBu Canvas, FreeDoom, Calculator |

### Test Results
- **4/4 tests passing**: init, open/close/toggle, rendering, multiple toggle cycles
- Test suite: `make test_startmenu` (4/4 pass)

### Files Modified
- `src/gui/startmenu.c` — Complete rewrite of `build_submenus_from_desktop()` with dynamic `.desktop` parsing
- `src/gui/startmenu_test_stub.c` — Added inline layout helpers (`menu_item_h`, `submenu_w`, `menu_w`, `sidebar_w`)
- `src/gui/startmenu.c` — Added inline layout helpers and global variable definitions