# OCI Runtime — Registry & Blob Operations

## What This Covers
`src/runtime/wubu_oci.c` — OCI (Open Container Initiative) distribution spec implementation:
registry auth, manifest push/pull, blob push/pull, tag listing, blob store management,
cleanup/GC, mount blob.

## Key Functions & Fixes (Phase 12)

### sha256_file() — Infinite Recursion Fix
**Bug:** The function declared an `extern` with the same signature and called itself → infinite recursion.
**Fix:** Real implementation: `open()` → `fstat()` → `malloc()` → `read()` → `sha256_digest()` → `free()`.
Always check `read()` return value against `st.st_size`.

### oci_registry_get_blob() — File Handle Fix
**Bug:** Opened `FILE*` for writing (`"wb"`), then tried to `fread()` from it. The curl `-o` flag
writes to the path directly, not through the FILE*.
**Fix:** Let curl write to a temp file path, then `open()` + `read()` from that path separately.

### oci_registry_put_blob() — Real Upload
**Before:** POSTed to `/v2/<repo>/blobs/uploads/` but never sent actual blob data.
**After:** Monolithic upload via `POST /v2/<repo>/blobs/uploads/?digest=<digest>` with
`--data-binary @<tempfile>`. Writes data to temp file first, then uploads.

### oci_registry_list_tags() — New Implementation
**Before:** Declared in header, never implemented (linker error if called).
**After:** `GET /v2/<repo>/tags/list`, writes response to temp file, parses JSON `tags` array.
Returns count of tags found, fills `tags[][128]` array.

### oci_cleanup_old_layers() — Real Implementation
**Before:** `(void)params; return 0;` — full stub.
**After:** `opendir()` on `<root>/blobs/sha256`, `stat()` each file, compare `st_mtime` against
`now - max_age_days*86400`, `unlink()` if too old. Returns count removed.
**Edge case:** Returns 0 (not -1) when blob dir doesn't exist (`ENOENT`) — nothing to clean.

### oci_gc_unreferenced_blobs() — Real Implementation
**Before:** `(void)params; return 0;` — full stub.
**After:** Two-phase GC:
1. **Collect:** Walk `<root>/blobs/sha256`, store all blob names in array.
2. **Mark:** Scan `index.json` for `sha256:` digests, scan manifest blobs for nested `sha256:` refs.
3. **Sweep:** `unlink()` unreferenced blobs. Returns count removed.

### oci_blob_store_init() — Layout File
**Before:** Created directory chain only.
**After:** Also writes `oci-layout` file (`{"imageLayoutVersion":"1.0.0"}`) to mark valid OCI layout.

### oci_registry_mount_blob() — URL Format Fix
**Before:** `GET /v2/<repo>/blobs/<digest>/mount?from=<source>` (wrong — digest in path).
**After:** `POST /v2/<repo>/blobs/uploads/?mount=<digest>&from=<source>` (correct OCI spec).

## Native HTTP Client — Removed curl CLI Dependency (Phase 1 — 2026-06-28)

### Motivation
The "hosted binary IS the product" (Inferno emu pattern) requires the WuBuOS binary to be
self-contained. The previous implementation shelling out to `curl` via `system()` was:
- **Not portable** — requires `curl` binary on host
- **Slow** — process spawn overhead per request
- **Brittle** — command injection risks, temp file management
- **No TLS control** — opaque dependency on system curl build

### Implementation: `OciHttpClient` (Pure POSIX Sockets)

#### Types
```c
typedef struct {
    int sockfd;
    char host[256];
    int port;
    bool use_tls;
} OciHttpClient;
```

#### Core Functions
| Function | Purpose |
|----------|---------|
| `oci_http_connect(host, port, use_tls)` | Resolve via `getaddrinfo`, connect with 10s timeout, set `SO_RCVTIMEO`/`SO_SNDTIMEO` |
| `oci_http_send(data, len)` | Full write loop, handles partial sends |
| `oci_http_recv(buf, size, out_recv)` | Read loop with `Content-Length` heuristic for body completion |
| `oci_http_request(method, path, headers, body, body_len, resp, resp_size)` | Builds full HTTP/1.1 request, sends, parses response, extracts body |
| `oci_parse_auth_header(headers, realm, service, scope)` | Extracts Bearer token params from `WWW-Authenticate` |
| `oci_base64_encode(input, output, size)` | For Basic Auth credentials |

#### Registry Transport Wrapper
```c
static int oci_registry_do_request(client, method, path, extra_headers,
                                    body, body_len, response, resp_size, out_status)
```
- Parses `client->registry` (handles `https://host:port`, `http://host:port`, bare `host:port`)
- Falls back from HTTPS (443) → HTTP (80) for local registries
- Builds auth headers:
  - **Basic Auth**: `Authorization: Basic <base64(username:password)>`
  - **Bearer**: `Authorization: Bearer *** (from `client->auth_token`)
- Calls `oci_http_request()` with combined headers

#### All Registry Operations Now Use Native HTTP
| Operation | Method | Path |
|-----------|--------|------|
| `oci_registry_ping` | GET | `/v2/` |
| `oci_registry_get_manifest` | GET | `/v2/<repo>/manifests/<tag_or_digest>` (with `Accept` header) |
| `oci_registry_put_manifest` | PUT | `/v2/<repo>/manifests/<tag>` (with `Content-Type`) |
| `oci_registry_get_blob` | GET | `/v2/<repo>/blobs/<digest>` |
| `oci_registry_put_blob` | POST | `/v2/<repo>/blobs/uploads/?digest=<digest>` (body = blob data) |
| `oci_registry_mount_blob` | POST | `/v2/<repo>/blobs/uploads/?mount=<digest>&from=<source>` |
| `oci_registry_delete_manifest` | DELETE | `/v2/<repo>/manifests/<digest>` |
| `oci_registry_list_tags` | GET | `/v2/<repo>/tags/list` |

### TLS Note
HTTPS/TLS is **not implemented** — would require OpenSSL/mbedTLS integration.
Current behavior: attempts TLS (port 443), falls back to plain HTTP (port 80) on failure.
For production HTTPS registries, link against a TLS library.

## OCI Distribution Spec Reference

### Registry API Endpoints
| Operation | Method | Endpoint |
|-----------|--------|----------|
| Ping | GET | `/v2/` |
| List tags | GET | `/v2/<name>/tags/list` |
| Get manifest | GET | `/v2/<name>/manifests/<tag_or_digest>` |
| Put manifest | PUT | `/v2/<name>/manifests/<tag>` |
| Get blob | GET | `/v2/<name>/blobs/<digest>` |
| Start upload | POST | `/v2/<name>/blobs/uploads/` |
| Monolithic upload | POST | `/v2/<name>/blobs/uploads/?digest_version": 2,
  "mediaType": "application/vnd.oci.image.manifest.v2+json",
  "config": {
    "mediaType": "application/vnd.oci.image.config.v1+json",
    "size": <int>,
    "digest": "sha256:<hex>"
  },
  "layers": [
    {
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
      "size": <int>,
      "digest": "sha256:<hex>"
    }
  ]
}
```

### Config JSON Schema
```json
{
  "created": "<timestamp>",
  "architecture": "x86_64",
  "os": "linux",
  "config": {
    "Entrypoint": ["/bin/sh"],
    "Cmd": ["run"],
    "WorkingDir": "/app",
    "User": "root",
    "Env": ["KEY=VAL"],
    "ExposedPorts": {"8080/tcp": {}}
  },
  "rootfs": {
    "type": "layers",
    "diff_ids": ["sha256:<hex>"]
  }
}
```

## Build & Test
```bash
make all          # Full build
make test_oci     # OCI-specific tests (10 tests)
make test         # Full suite (1000+ tests)
```

## Test Coverage (wubu_oci_test.c)
- Media type strings
- Descriptor create
- Config roundtrip (create → JSON → parse)
- Manifest roundtrip (create → JSON → parse)
- Blob store (put/get/exists)
- Index (create/add/to_json)
- Runtime spec (create/to/from/validate)
- Hook create
- Registry client lifecycle
- Cleanup/GC (real execution, not stub)

## Common Pitfalls
1. **`snprintf` return value:** Check `n >= 0` before `p += n; rem -= n;` — negative return means error.
2. **`strncpy` truncation:** GCC warns when source length equals destination size. Use `sizeof(dst)-1` and ensure null termination.
3. **`typedef` inside function:** C allows `typedef` at block scope, but `patch` tool can accidentally remove it if the old_string boundary cuts through it. Always verify typedefs survive patching.
4. **`opendir` on missing dir:** Return 0 (not -1) for `ENOENT` when the operation is "clean up" — nothing to do is success.
5. **curl temp files:** Use `getpid()` in temp filenames to avoid collisions. Always `unlink()` in error paths.
6. **JSON parsing:** The simple `strstr`-based parser doesn't handle nested objects or escaped quotes. Good enough for OCI manifests but not general JSON.