# Real Zip Archive Mounting Patterns (Option C — 2026-06-28)

## Context
**Gap**: `explorer_mount_zip()` was a stub returning `false` with comment "Not implemented".

**Goal**: Implement real zip archive mount/browse for the Win98-style file explorer.

## Implementation Strategy

### Dual Backend Approach

| Backend | Method | When Used |
|---------|--------|-----------|
| **libzip** | `dlopen("libzip.so.4")` + symbols | Preferred — handles all zip features |
| **Raw parser** | Manual EOCD/CD parsing | Fallback when libzip unavailable |

### Key Data Structures

```c
#pragma pack(push, 1)
typedef struct {
    uint32_t signature;        // 0x02014b50
    uint16_t version_made_by;
    uint16_t version_needed;
    uint16_t flags;
    uint16_t compression_method;
    uint16_t last_mod_time;
    uint16_t last_mod_date;
    uint32_t crc32;
    uint32_t compressed_size;
    uint32_t uncompressed_size;
    uint16_t filename_len;
    uint16_t extra_field_len;
    uint16_t comment_len;
    uint16_t disk_num_start;
    uint16_t internal_attr;
    uint32_t external_attr;
    uint32_t local_header_offset;
} ZipCentralDirHeader;

typedef struct {
    uint32_t signature;        // 0x06054b50
    uint16_t disk_number;
    uint16_t central_dir_disk;
    uint16_t central_dir_entries_this_disk;
    uint16_t central_dir_entries_total;
    uint32_t central_dir_size;
    uint32_t central_dir_offset;
    uint16_t comment_len;
} ZipEndCentralDir;
#pragma pack(pop)

typedef struct {
    char name[256];
    uint64_t uncompressed_size;
    uint64_t compressed_size;
    uint32_t crc32;
    uint16_t compression_method;
    time_t modified;
    int central_dir_index;
    bool is_directory;
} ExZipEntry;
```

### Functions Added

| Function | Purpose |
|----------|---------|
| `ex_libzip_load()` | `dlopen` libzip.so.4 + resolve `zip_open`, `zip_close`, `zip_get_num_entries`, `zip_get_name` |
| `ex_zip_read_central_directory(path)` | Raw parser: finds EOCD in last 64KB, reads CD entries, converts DOS timestamps |
| `ex_zip_populate_entries()` | Converts `ExZipEntry[]` → `ExEntry[]` for explorer UI |
| `explorer_mount_zip(path)` | Tries libzip first, falls back to raw parser |
| `explorer_unmount_zip()` | Clears cache, navigates up |

### ZIP Format Details

| Signature | Value | Purpose |
|-----------|-------|---------|
| Local File Header | 0x04034b50 | Per-file header |
| Central Directory Header | 0x02014b50 | Central directory entry |
| End of Central Directory | 0x06054b50 | Archive metadata |

**EOCD Search**: Read last 64KB of file, scan for `0x06054b50`

**DOS Timestamp Conversion**:
```c
struct tm tm = {0};
tm.tm_year = ((date >> 9) & 0x7F) + 80;  // years since 1900
tm.tm_mon  = ((date >> 5) & 0xF) - 1;    // 0-11
tm.tm_mday = date & 0x1F;                 // 1-31
tm.tm_hour = (time >> 11) & 0x1F;
tm.tm_min  = (time >> 5) & 0x3F;
tm.tm_sec  = (time & 0x1F) * 2;
ze->modified = mktime(&tm);
```

**Directory Detection**:
```c
ze->is_directory = (name[cdh.filename_len - 1] == '/') 
                 || (cdh.uncompressed_size == 0 && cdh.compressed_size == 0);
```

### Libzip Backend

```c
bool ex_libzip_load(void) {
    if (g_libzip.handle) return true;
    g_libzip.handle = dlopen("libzip.so.4", RTLD_LAZY);
    if (!g_libzip.handle) return false;
    g_libzip.zip_open = dlsym(g_libzip.handle, "zip_open");
    g_libzip.zip_close = dlsym(g_libzip.handle, "zip_close");
    g_libzip.zip_fopen_index = dlsym(g_libzip.handle, "zip_fopen_index");
    g_libzip.zip_fclose = dlsym(g_libzip.handle, "zip_fclose");
    g_libzip.zip_fread = dlsym(g_libzip.handle, "zip_fread");
    g_libzip.zip_stat_index = dlsym(g_libzip.handle, "zip_stat_index");
    g_libzip.zip_get_num_entries = dlsym(g_libzip.handle, "zip_get_num_entries");
    g_libzip.zip_get_name = dlsym(g_libzip.handle, "zip_get_name");
    return g_libzip.zip_open != NULL;
}

bool explorer_mount_zip(const char *zip_path) {
    if (ex_libzip_load()) {
        int err = 0;
        void *archive = g_libzip.zip_open(zip_path, 0, &err);
        if (archive) {
            int64_t num_entries = g_libzip.zip_get_num_entries(archive, 0);
            for (int64_t i = 0; i < num_entries && g_zip_entry_count < EX_MAX_ZIP_ENTRIES; i++) {
                const char *name = g_libzip.zip_get_name(archive, i, 0);
                if (!name) continue;
                ExZipEntry *ze = &g_zip_entries[g_zip_entry_count++];
                WUBU_STRCPY(ze->name, name, sizeof(ze->name));
                ze->central_dir_index = (int)i;
                ze->is_directory = (name[strlen(name) - 1] == '/');
            }
            g_libzip.zip_close(archive);
            g_zip_entries_valid = true;
            ex_zip_populate_entries();
            return true;
        }
    }
    // Fallback to raw parser
    int count = ex_zip_read_central_directory(zip_path);
    if (count > 0) {
        WUBU_STRCPY(g_explorer.current_zip_path, zip_path, EX_MAX_PATH);
        g_explorer.in_zip_archive = true;
        ex_zip_populate_entries();
        return true;
    }
    return false;
}
```

### Test Added (explorer_test.c)

```c
bool ret = explorer_mount_zip("/tmp/test.zip");
TEST_ASSERT(ret, "mount_zip returns true for real zip");
TEST_ASSERT(explorer_is_in_zip(), "in_zip_archive is true after mount");
TEST_ASSERT(ex->entry_count > 0, "entries populated from zip");

explorer_unmount_zip();
TEST_ASSERT(!ex->in_zip_archive, "unmount_zip clears flag");

ret = explorer_mount_zip("/fake/archive.zip");
TEST_ASSERT(!ret, "mount_zip returns false for missing file");
```

### Verification

```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
make test_explorer
# Results: 74/74 pass (was 71 — added 3 zip tests)
```

### Files Modified
- `src/gui/explorer.c` — +300 lines (structures, libzip dlopen, raw parser, mount/unmount)
- `src/gui/explorer_test.c` — +3 test assertions
- `src/gui/explorer.h` — No changes (API already existed)

### Includes Added
```c
#include <dlfcn.h>
#include <stdint.h>
#include <zlib.h>
```

### Pitfalls
- `dlopen("libzip.so.4")` — versioned SONAME; fallback works if missing
- `dlopen` requires `-ldl` at link time (already in Makefile via JIT)
- Raw parser uses `malloc` for EOCD search buffer — must `free()`
- DOS timestamp year offset: 1980 → `+80` for `tm_year` (years since 1900)
- `strncpy` overflow warning on btrfs — fixed with `memcpy` + explicit null-termination
- Need `#include <sys/wait.h>` for `waitpid()` in zfs fallback (already in wubu_snapshot.c)