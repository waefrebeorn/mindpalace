# WuBuOS Subsystem Development Pattern

Documentation of the consistent pattern used for creating new C subsystems in WuBuOS (Phase 3 Items 1-4, Phase 4 Item 1).

## Pattern Overview

Every new subsystem follows this uniform structure:

```
src/gui/
├── wubu_<name>.h      # Public API (types, enums, function declarations)
├── wubu_<name>.c      # Implementation
├── wubu_<name>_test.c # Unit tests (can run standalone)
```

plus Makefile integration and config persistence.

## File Templates

### 1. Header File (`wubu_<name>.h`)

```c
#ifndef WUBU_<NAME>_H
#define WUBU_<NAME>_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================
 * Public Types
 * ============================================================ */
typedef enum {
    WUBU_<NAME>_TYPE_A = 0,
    WUBU_<NAME>_TYPE_B,
    WUBU_<NAME>_COUNT
} wubu_<name>_type_t;

typedef struct {
    /* configuration fields */
    int field1;
    const char* field2;
} wubu_<name>_config_t;

typedef struct {
    /* state fields */
    int id;
    char name[64];
} wubu_<name>_entry_t;

/* ============================================================
 * Public API
 * ============================================================ */

/* Lifecycle */
bool wubu_<name>_init(void);
void wubu_<name>_shutdown(void);

/* Configuration */
void wubu_<name>_get_default_config(wubu_<name>_config_t* config);
bool wubu_<name>_validate_config(const wubu_<name>_config_t* config);

/* Core operations */
bool wubu_<name>_create(...);
bool wubu_<name>_destroy(...);
int wubu_<name>_list(wubu_<name>_entry_t* out, int max);

/* Persistence (JSON at XDG paths) */
bool wubu_<name>_save_config(void);
bool wubu_<name>_load_config(void);

#ifdef __cplusplus
}
#endif

#endif /* WUBU_<NAME>_H */
```

### 2. Implementation File (`wubu_<name>.c`)

```c
#include "wubu_<name>.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <json-c/json.h>  /* or built-in minimal JSON parser */

/* ============================================================
 * Internal State
 * ============================================================ */
typedef struct {
    bool initialized;
    int next_id;
    wubu_<name>_entry_t entries[256];
    int count;
    char config_path[512];
    wubu_<name>_config_t config;
} <Name>State;

static <Name>State g_state = {0};

/* ============================================================
 * Helpers
 * ============================================================ */
static bool ensure_config_dir(void) {
    const char* home = getenv("HOME");
    const char* xdg_config = getenv("XDG_CONFIG_HOME") ?: home "/.config";
    snprintf(g_state.config_path, sizeof(g_state.config_path), "%s/wubu/<name>.json", xdg_config);
    
    char dir[512];
    snprintf(dir, sizeof(dir), "%s/wubu", xdg_config);
    return mkdir(dir, 0755) == 0 || errno == EEXIST;
}

/* Minimal JSON parser for zero-dep builds (or use json-c if available) */
static bool parse_json(const char* json, /* out */ ...) { ... }
static bool write_json(FILE* f, /* data */ ...) { ... }

/* ============================================================
 * Public API Implementation
 * ============================================================ */
bool wubu_<name>_init(void) {
    if (g_state.initialized) return true;
    ensure_config_dir();
    wubu_<name>_load_config();
    g_state.initialized = true;
    return true;
}

void wubu_<name>_shutdown(void) {
    if (g_state.initialized) {
        wubu_<name>_save_config();
        g_state.initialized = false;
    }
}

void wubu_<name>_get_default_config(wubu_<name>_config_t* config) {
    memset(config, 0, sizeof(*config));
    config->field1 = 10;
    config->field2 = "default";
}

bool wubu_<name>_validate_config(const wubu_<name>_config_t* config) {
    return config && config->field1 > 0 && config->field2;
}

bool wubu_<name>_create(...) {
    /* ... */
    return true;
}

bool wubu_<name>_save_config(void) {
    FILE* f = fopen(g_state.config_path, "w");
    if (!f) return false;
    write_json(f, &g_state.config);
    fclose(f);
    return true;
}

bool wubu_<name>_load_config(void) {
    FILE* f = fopen(g_state.config_path, "r");
    if (!f) { wubu_<name>_get_default_config(&g_state.config); return true; }
    char buf[4096];
    size_t n = fread(buf, 1, sizeof(buf)-1, f);
    buf[n] = '\0';
    fclose(f);
    return parse_json(buf, &g_state.config);
}
```

### 3. Test File (`wubu_<name>_test.c`)

```c
#include "wubu_<name>.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TEST_ASSERT(cond, msg) \
    do { if (!(cond)) { fprintf(stderr, "FAIL: %s (%s:%d)\n", msg, __FILE__, __LINE__); return false; } } while (0)

#define TEST_ASSERT_EQ(a, b, msg) \
    do { if ((a) != (b)) { fprintf(stderr, "FAIL: %s - expected %d, got %d (%s:%d)\n", msg, (b), (a), __FILE__, __LINE__); return false; } } while (0)

static int tests_passed = 0, tests_failed = 0;

#define RUN_TEST(fn) \
    do { printf("Running %s... ", #fn); fflush(stdout); \
         if (fn()) { printf("PASS\n"); tests_passed++; } else { printf("FAIL\n"); tests_failed++; } } while (0)

bool test_<name>_lifecycle(void) {
    TEST_ASSERT(wubu_<name>_init(), "init");
    TEST_ASSERT(wubu_<name>_validate_config(&some_config), "validate");
    wubu_<name>_shutdown();
    return true;
}

bool test_<name>_crud(void) {
    wubu_<name>_init();
    TEST_ASSERT(wubu_<name>_create(...), "create");
    wubu_<name>_entry_t entries[10];
    int count = wubu_<name>_list(entries, 10);
    TEST_ASSERT_EQ(count, 1, "list count");
    TEST_ASSERT(wubu_<name>_destroy(...), "destroy");
    wubu_<name>_shutdown();
    return true;
}

bool test_<name>_persistence(void) {
    wubu_<name>_init();
    wubu_<name>_create(...);
    wubu_<name>_save_config();
    wubu_<name>_shutdown();
    
    wubu_<name>_init();
    wubu_<name>_entry_t entries[10];
    int count = wubu_<name>_list(entries, 10);
    TEST_ASSERT_EQ(count, 1, "persistence");
    wubu_<name>_shutdown();
    return true;
}

int main(void) {
    printf("=== WuBuOS <Name> Tests ===\n\n");
    RUN_TEST(test_<name>_lifecycle);
    RUN_TEST(test_<name>_crud);
    RUN_TEST(test_<name>_persistence);
    printf("\n=== Results: %d passed, %d failed ===\n", tests_passed, tests_failed);
    return tests_failed == 0 ? 0 : 1;
}
```

## Makefile Integration

Add to `GUI_OBJS`:
```makefile
GUI_OBJS = ... $(GUI)/wubu_<name>.o ...
```

Add to `HOSTED_OBJS` and `hosted:` target:
```makefile
HOSTED_OBJS = ... $(GUI)/wubu_<name>.o ...

hosted: $(HOSTED_OBJS) ...
    $(GUI)/wubu_<name>.c ...
```

Add test target:
```makefile
test_<name>:
    $(CC) -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM \
        -I$(GUI) -I$(KERNEL) \
        $(GUI)/wubu_<name>.c $(GUI)/wubu_settings.c $(GUI)/wubu_theme.c \
        $(GUI)/wubu_<name>_test.c \
        -o $(GUI)/wubu_<name>_test
    $(GUI)/wubu_<name>_test
```

Add to `test:` dependency list:
```makefile
test: test_<name> ...
```

## XDG Config Paths

| Data Type | Path Variable | Fallback |
|-----------|---------------|----------|
| Config    | `$XDG_CONFIG_HOME/wubu/<name>.json` | `~/.config/wubu/<name>.json` |
| Data      | `$XDG_DATA_HOME/wubu/<name>/` | `~/.local/share/wubu/<name>/` |
| State     | `$XDG_STATE_HOME/wubu/<name>/` | `~/.local/state/wubu/<name>/` |
| Cache     | `$XDG_CACHE_HOME/wubu/<name>/` | `~/.cache/wubu/<name>/` |

```c
static const char* get_config_path(const char* filename) {
    static char path[512];
    const char* home = getenv("HOME");
    const char* xdg = getenv("XDG_CONFIG_HOME") ?: home "/.config";
    snprintf(path, sizeof(path), "%s/wubu/%s", xdg, filename);
    return path;
}
```

## Common Pitfalls

1. **Hardcoded paths**: Always use XDG environment variables
2. **JSON parsing**: Use built-in minimal parser (no json-c dependency)
3. **Thread safety**: Current pattern is single-threaded; add mutex if needed
4. **Symlinks in rootfs**: Must create inside rootfs, not host paths
5. **Format specifiers**: `uint64_t` uses `%lu` not `%llu` on Linux
6. **Test linkage**: Test files include `.c` files directly, not `.o` files
7. **Duplicate test targets**: Check Makefile for existing `test_<name>` before adding

## Subsystems Created Using This Pattern

| Subsystem | Files | Config Path | Test |
|-----------|-------|-------------|------|
| Settings | `wubu_settings.h/c`, `wubu_settings_test.c` | `~/.config/wubu/settings.conf` | `test_settings` |
| Session | `wubu_session.h/c`, (no dedicated test) | `~/.config/wubu/autostart/`, `~/.local/state/wubu/session.json` | N/A |
| Notifications | `wubu_notify.h/c`, (tested via `test_hosted`) | Memory only (history) | N/A |
| Clipboard | `wubu_clipboard.h/c` | Wayland selections | N/A |
| Screenshot | `wubu_screenshot.h/c`, `test_gui_screenshot` | `~/Pictures/WuBuOS/` | `test_gui_screenshot` |
| MIME | `wubu_mime.h/c`, `wubu_mime_test.c` | `~/.local/share/applications/` | `test_mime` |
| Trash | `wubu_trash.h/c`, `wubu_trash_test.c` | `~/.local/share/Trash/` | `test_trash` |
| Proton | `wubu_proton.h/c`, `wubu_proton_test.c` | `~/.local/share/wubu/proton/config.json` | `test_proton` (GUI) |
| GameLib | `wubu_gamelib.h/c`, `wubu_gamelib_test.c` | `~/.local/share/wubu/games/gamelib.json` | `test_gamelib` |
| Container | `wubu_container.h/c`, `wubu_container_test.c` | `~/.local/share/wubu/containers/config.json` | `test_container` |
| HolyC | `wubu_holyc.h/c`, `wubu_holyc_test.c` | `~/.config/wubu/holyc.json` | `test_holyc` |
| Deploy | `wubu_deploy.h/c`, `wubu_deploy_test.c` | N/A (build-time only) | `test_deploy` |