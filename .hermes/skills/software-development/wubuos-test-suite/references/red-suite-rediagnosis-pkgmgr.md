# Red-Suite Re-Diagnosis: test_pkgmgr 8/11 → 11/11 (commit b4d9b2d, 2026-07-07)

## Lesson
A prestige update / Next Session Prompt summarized the 3 `test_pkgmgr` failures
as "the payload-extraction TODO in wubu_pkgmgr_install.c". That was only ONE of
SIX root causes. Trusting the summary would have under-fixed. Always run the
target and read the FAIL lines first.

## The six real root causes (file:line at fix time)

| # | Symptom (FAIL line) | Root cause | Location | Fix |
|---|---------------------|-----------|----------|-----|
| 1 | `install pkg` (install_remove_db, autoremove) | `wubu_pkgmgr_extract_package()` was a stub — only `mkdir`, the `.tar.zst` payload was never unpacked | `wubu_pkgmgr_pkg.c:273` | Implemented real `zstd -d \| tar -xf` unpack via fork+exec, reading payload from `sizeof(header)+manifest_size` offset |
| 2 | `install pkg` → no files installed | `extract_pkg_manifest()` only filled scalar fields (id/name/version/arch); `files[]/n_files`, `depends[]`, `entrypoints[]` stayed empty → `install_package_files()` iterated `n_files==0` (no-op) | `wubu_pkgmgr_pkg.c:210` | Added JSON-array parsers (`json_find_array`, `json_array_count`, `json_array_str_at`) for `files`/`deps`/`entries` |
| 3 | `install pkg` → "[pkgmgr] Package conflicts with installed packages" | `wubu_pkgmgr_check_conflicts()` returned `false` **unconditionally** | `wubu_pkgmgr.c:302` | Now returns true unless the same id is already installed |
| 4 | `install pkg` → empty install / `SQLite error` | `manifest_to_json()` emitted `"arch":"%s"` against an `int` enum (**UB**) and **dropped the `files[]` array entirely** from the serialized manifest | `wubu_pkgmgr.c:266` | Emit `"arch":%d`; serialize `files[]` as `"src|dst|mode"`; growable buffer (realloc on truncation) |
| 5 | `list installed count` (install_remove_db, autoremove) → "SQLite error: table packages has no column named description" | `packages` table schema was missing columns the INSERT referenced (`description`, `maintainer`, `homepage`, `license`, `manifest_json`, `install_path`, `auto_installed`, `payload_type`, `sandbox_profile`) | `wubu_pkgmgr.c:91` (SCHEMA_SQL) | Added all referenced columns; relaxed `install_date` to nullable |
| 6 | `desktop file exists` (test_desktop_entry_generation) | `ensure_dir()` was **non-recursive** — `share/applications/` never got created, so `write_file` of the `.desktop` failed. NOTE: this failure is unrelated to payload extraction; the test builds its manifest inline and never installs | `wubu_pkgmgr_internal.h:58` | Made `ensure_dir` recursive (mkdir each parent segment) |

## Verification
- `make clean && make runtime && make hosted` green (from scratch)
- `make test_pkgmgr` → 11 passed, 0 failed
- Full gate `make test`: only `test_network` 114/139 fails, identical to the
  pre-existing environmental root/netlink "Operation not permitted" — no
  regression from the pkgmgr changes.

## Gotcha: stale SQLite DB
Test DBs persist under `/tmp/wubu_pkgmgr_test*`. After a schema change, an old
DB missing the new columns produces "no such column" errors that look like code
bugs. Always `rm -rf /tmp/wubu_pkgmgr_test*` before a clean `make test_pkgmgr`
run when schema changed.
