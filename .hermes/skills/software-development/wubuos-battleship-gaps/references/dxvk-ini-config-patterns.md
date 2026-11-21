# DXVK INI Config Implementation Patterns

## Overview
Implemented in `src/runtime/wubu_proton.c` — 7 REAL_GAPs closed (2026-06-29).

All functions now do **real file I/O** to Wine prefix directories instead of `(void)` casts.

## Wine Prefix Directory Structure
```
~/.local/share/wubu/prefixes/{prefix_id}/
├── drive_c/
│   ├── users/
│   │   └── steamuser/
│   │       └── AppData/
│   │           └── Local/
│   │               └── DXVK/
│   │                   └── dxvk.conf   <-- DXVK config file
│   ├── windows/
│   │   └── system32/
│   ├── Program Files/
│   └── Program Files (x86)/
```

Created by `wubu_proton_create_prefix()` using recursive `mkdir_p()`.

## Core Functions

### `wubu_proton_prefix_path()`
```c
static int wubu_proton_prefix_path(const char *prefix_id, char *out_path, size_t size) {
    const char *home = getenv("HOME");
    if (!home) home = "/tmp";
    return snprintf(out_path, size, "%s/.local/share/wubu/prefixes/%s", home, prefix_id);
}
```

### `wubu_proton_mkdir_p()` — Recursive Directory Creation
```c
static int wubu_proton_mkdir_p(const char *path) {
    char tmp[512];
    strncpy(tmp, path, sizeof(tmp) - 1);
    tmp[sizeof(tmp) - 1] = '\0';
    
    for (char *p = tmp + 1; *p; p++) {
        if (*p == '/') {
            *p = '\0';
            if (mkdir(tmp, 0755) != 0 && errno != EEXIST) return -1;
            *p = '/';
        }
    }
    if (mkdir(tmp, 0755) != 0 && errno != EEXIST) return -1;
    return 0;
}
```

### `wubu_proton_dxvk_config_write()`
```c
int wubu_proton_dxvk_config_write(const char *prefix_id, const char *config_content) {
    char prefix_path[512];
    if (wubu_proton_prefix_path(prefix_id, prefix_path, sizeof(prefix_path)) < 0) return -1;
    if (wubu_proton_ensure_prefix(prefix_id) < 0) return -1;
    
    char dxvk_conf[512];
    snprintf(dxvk_conf, sizeof(dxvk_conf), 
             "%s/drive_c/users/steamuser/AppData/Local/DXVK/dxvk.conf", prefix_path);
    
    FILE *f = fopen(dxvk_conf, "w");
    if (!f) return -1;
    fprintf(f, "%s", config_content);
    fclose(f);
    return 0;
}
```

### `wubu_proton_dxvk_config_read()`
```c
int wubu_proton_dxvk_config_read(const char *prefix_id, char *out_config, size_t size) {
    char prefix_path[512];
    if (wubu_proton_prefix_path(prefix_id, prefix_path, sizeof(prefix_path)) < 0) return -1;
    
    char dxvk_conf[512];
    snprintf(dxvk_conf, sizeof(dxvk_conf), 
             "%s/drive_c/users/steamuser/AppData/Local/DXVK/dxvk.conf", prefix_path);
    
    FILE *f = fopen(dxvk_conf, "r");
    if (!f) { out_config[0] = '\0'; return 0; }
    
    size_t n = fread(out_config, 1, size - 1, f);
    out_config[n] = '\0';
    fclose(f);
    return 0;
}
```

## INI Key Manipulation Pattern

All `set_*` functions follow the same pattern:
1. Read existing config
2. Find the key line (e.g., `async = true`)
3. Replace the line, or append if not found
4. Write back

```c
int wubu_proton_dxvk_set_async(const char *prefix_id, bool async) {
    char config[4096];
    wubu_proton_dxvk_config_read(prefix_id, config, sizeof(config));
    
    char new_config[4096];
    char *p = strstr(config, "async =");
    if (p) {
        // Replace existing line
        char *line_start = p;
        while (line_start > config && line_start[-1] != '\n') line_start--;
        char *line_end = p;
        while (*line_end && *line_end != '\n') line_end++;
        if (*line_end == '\n') line_end++;
        snprintf(new_config, sizeof(new_config), "%.*sasync = %s\n%s",
                 (int)(line_start - config), config,
                 async ? "true" : "false",
                 line_end);
    } else {
        // Append new key
        snprintf(new_config, sizeof(new_config), 
                 "%s\n[dxvk]\nasync = %s",
                 config[0] ? config : "",
                 async ? "true" : "false");
    }
    return wubu_proton_dxvk_config_write(prefix_id, new_config);
}
```

## Struct ↔ INI Serialization

### `wubu_proton_dxvk_config_ui_set()` — Struct → INI
```c
int wubu_proton_dxvk_config_ui_set(const char *prefix_id, const DxvkConfigUI *ui) {
    char config[4096] = "[dxvk]\n";
    size_t pos = 7;
    
    if (ui->dxvk_hud_enabled) {
        pos += snprintf(config + pos, sizeof(config) - pos, "hud = %s\n", 
                        ui->dxvk_hud_options[0] ? ui->dxvk_hud_options : "fps");
    }
    pos += snprintf(config + pos, sizeof(config) - pos, "async = %s\n", ui->dxvk_async ? "true" : "false");
    pos += snprintf(config + pos, sizeof(config) - pos, "nvapiHack = %s\n", ui->dxvk_nvapi_hack ? "true" : "false");
    pos += snprintf(config + pos, sizeof(config) - pos, "presentMode = %d\n", ui->dxvk_present_mode_mailbox ? 1 : 0);
    if (ui->dxvk_max_device_memory > 0) {
        pos += snprintf(config + pos, sizeof(config) - pos, "maxDeviceMemory = %d\n", ui->dxvk_max_device_memory);
    }
    if (ui->dxvk_max_shared_memory > 0) {
        pos += snprintf(config + pos, sizeof(config) - pos, "maxSharedMemory = %d\n", ui->dxvk_max_shared_memory);
    }
    pos += snprintf(config + pos, sizeof(config) - pos, "d3d10 = %s\n", ui->dxvk_d3d10 ? "true" : "false");
    pos += snprintf(config + pos, sizeof(config) - pos, "d3d10_1 = %s\n", ui->dxvk_d3d10_1 ? "true" : "false");
    pos += snprintf(config + pos, sizeof(config) - pos, "stateCache = %s\n", ui->dxvk_state_cache ? "true" : "false");
    
    return wubu_proton_dxvk_config_write(prefix_id, config);
}
```

### `wubu_proton_dxvk_config_ui_get()` — INI → Struct
```c
int wubu_proton_dxvk_config_ui_get(const char *prefix_id, DxvkConfigUI *out_ui) {
    memset(out_ui, 0, sizeof(DxvkConfigUI));
    strncpy(out_ui->prefix_id, prefix_id, sizeof(out_ui->prefix_id) - 1);
    
    char config[4096];
    wubu_proton_dxvk_config_read(prefix_id, config, sizeof(config));
    
    char *p = strstr(config, "hud =");
    if (p) {
        out_ui->dxvk_hud_enabled = true;
        p += 5;
        while (*p == ' ' || *p == '=' || *p == '\t') p++;
        char *end = p;
        while (*end && *end != '\n' && *end != '\r') end++;
        if (end > p) {
            size_t len = end - p;
            if (len >= sizeof(out_ui->dxvk_hud_options)) len = sizeof(out_ui->dxvk_hud_options) - 1;
            memcpy(out_ui->dxvk_hud_options, p, len);
            out_ui->dxvk_hud_options[len] = '\0';
        }
    }
    
    p = strstr(config, "async =");
    if (p) out_ui->dxvk_async = (strstr(p, "true") != NULL);
    
    p = strstr(config, "nvapiHack =");
    if (p) out_ui->dxvk_nvapi_hack = (strstr(p, "true") != NULL);
    
    p = strstr(config, "presentMode =");
    if (p) out_ui->dxvk_present_mode_mailbox = (strstr(p, "1") != NULL);
    
    // ... similar for maxDeviceMemory, maxSharedMemory, d3d10, d3d10_1
    
    return 0;
}
```

## Default DXVK Config Created
```ini
[dxvk]
async = true
nvapiHack = false
presentMode = 0
d3d10 = true
d3d10_1 = true
stateCache = true
```

## Test Coverage
All 32 `test_proton` tests pass, including:
- `test_dxvk_config_write_read`
- `test_dxvk_hud_options`
- `test_dxvk_async_toggle`
- `test_dxvk_nvapi_hack`
- `test_dxvk_present_mode`
- `test_dxvk_memory_limits`
- `test_dxvk_reset_config`
- `test_dxvk_config_ui_get_set`

## Key DA Audit Rule Applied
> "Rewriting from scratch in C" = the work.
> - `(void)param;` as sole statement → REAL_GAP → implement real logic
> - `return 0;` on success path → REAL_GAP → implement and return result