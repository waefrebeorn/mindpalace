# TLS Migration: mbedTLS → OpenSSL in OCI HTTP Client (2026-07-24)

## Overview
The OCI HTTP client (`src/runtime/oci/oci_http_client.c`) originally used mbedTLS for HTTPS support, but the build system lacked `libmbedtls-dev`. Migrated to OpenSSL (system `libssl-dev` available).

## The Problem
- mbedTLS headers not installed on build system
- `oci_http_client.c` had `#ifdef MBEDTLS_SSL_H` guards but no mbedTLS
- TLS connections returned `-1` with "compile with -DMBEDTLS_SSL_H" error

## Solution: OpenSSL Migration

### 1. Header Updates (`oci_internal.h`)
```c
/* -- OpenSSL TLS Support --------------------------------------------- */
#include <openssl/ssl.h>
#include <openssl/err.h>
```

### 2. Opaque TLS Context in Struct
```c
typedef struct OciHttpClient {
    int sockfd;
    char host[256];
    int port;
    bool use_tls;
    SSL *ssl;  // OpenSSL connection handle
} OciHttpClient;
```

### 3. Shared SSL_CTX (Process-wide, initialized once)
```c
static SSL_CTX *g_ssl_ctx = NULL;
static bool g_ssl_init_done = false;

static void oci_http_ssl_init(void) {
    if (g_ssl_init_done) return;
    SSL_library_init();
    SSL_load_error_strings();
    OpenSSL_add_all_algorithms();
    g_ssl_ctx = SSL_CTX_new(TLS_client_method());
    if (!g_ssl_ctx) { fprintf(stderr, "[wubu_oci] SSL_CTX_new failed\n"); return; }
    // For now: disable cert verification (insecure but functional)
    SSL_CTX_set_verify(g_ssl_ctx, SSL_VERIFY_NONE, NULL);
    g_ssl_init_done = true;
}
```

### 4. Connection with TLS
```c
int oci_http_connect(OciHttpClient *client, const char *host, int port, bool use_tls) {
    // ... socket setup (getaddrinfo, connect) ...
    
    if (use_tls) {
        oci_http_ssl_init();
        if (!g_ssl_ctx) { close(sockfd); return -1; }
        
        client->ssl = SSL_new(g_ssl_ctx);
        if (!client->ssl) { close(sockfd); return -1; }
        
        SSL_set_fd(client->ssl, sockfd);
        SSL_set_tlsext_host_name(client->ssl, host);  // SNI
        
        int ssl_rc = SSL_connect(client->ssl);
        if (ssl_rc != 1) {
            int err = SSL_get_error(client->ssl, ssl_rc);
            fprintf(stderr, "[wubu_oci] SSL_connect failed: %d\n", err);
            ERR_print_errors_fp(stderr);
            SSL_free(client->ssl);
            client->ssl = NULL;
            close(sockfd);
            return -1;
        }
    }
    return 0;
}
```

### 5. Send/Receive with Proper Error Handling
```c
int oci_http_send(OciHttpClient *client, const void *data, size_t len) {
    if (client->use_tls && client->ssl) {
        while (sent < len) {
            int n = SSL_write(client->ssl, p + sent, len - sent);
            if (n <= 0) {
                int err = SSL_get_error(client->ssl, n);
                if (err == SSL_ERROR_WANT_READ || err == SSL_ERROR_WANT_WRITE) continue;
                return -1;
            }
            sent += n;
        }
        return 0;
    }
    // ... plain send() ...
}

int oci_http_recv(OciHttpClient *client, void *buf, size_t buf_size, size_t *out_recv) {
    if (client->use_tls && client->ssl) {
        while (total < buf_size - 1) {
            int n = SSL_read(client->ssl, p + total, buf_size - 1 - total);
            if (n <= 0) {
                int err = SSL_get_error(client->ssl, n);
                if (err == SSL_ERROR_WANT_READ || err == SSL_ERROR_WANT_WRITE) continue;
                if (err == SSL_ERROR_ZERO_RETURN) break;  // Clean shutdown
                return -1;
            }
            total += n;
            // ... Content-Length parsing ...
        }
        return total > 0 ? 0 : -1;
    }
    // ... plain recv() ...
}
```

### 6. Cleanup
```c
void oci_http_close(OciHttpClient *client) {
    if (client->sockfd >= 0) {
        if (client->use_tls && client->ssl) {
            SSL_shutdown(client->ssl);
            SSL_free(client->ssl);
            client->ssl = NULL;
        }
        close(client->sockfd);
        client->sockfd = -1;
    }
}
```

### 7. Makefile Link Flags
```makefile
# test_oci target
-o $(RT)/wubu_oci_test -lm -lssl -lcrypto

# test_pkgmgr target (uses oci_http_client.c)
-o $(GUI)/wubu_pkgmgr_test -lsqlite3 -lzstd -lssl -lcrypto
```

## Verification
```bash
cd /home/wubu/wubuos
make clean && make test_oci test_pkgmgr
# Both pass: 10/10 OCI tests, 12/12 pkgmgr tests (including test_repo_update_fetch which hits HTTPS)
```

## Key Differences from mbedTLS

| Aspect | mbedTLS | OpenSSL |
|--------|---------|---------|
| Context init | Per-connection `mbedtls_ssl_init` | Shared `SSL_CTX`, per-connection `SSL_new` |
| RNG seeding | `mbedtls_ctr_drbg_seed` | Automatic via `SSL_library_init` |
| Cert verification | `MBEDTLS_SSL_VERIFY_NONE` | `SSL_CTX_set_verify(ctx, SSL_VERIFY_NONE, NULL)` |
| SNI | `mbedtls_ssl_set_hostname` | `SSL_set_tlsext_host_name` |
| BIO | `mbedtls_ssl_set_bio` + `mbedtls_net_send/recv` | `SSL_set_fd` |
| Handshake | `mbedtls_ssl_handshake` loop | `SSL_connect` (blocking) |
| Read/Write | `mbedtls_ssl_read/write` | `SSL_read/write` |
| Error codes | `MBEDTLS_ERR_SSL_WANT_READ/WRITE` | `SSL_ERROR_WANT_READ/WRITE` |
| Cleanup | `mbedtls_ssl_free` + config/entropy/cert free | `SSL_shutdown` + `SSL_free` |

## Notes
- **Certificate verification disabled** (`SSL_VERIFY_NONE`) — matches original mbedTLS behavior. Production should load system CA bundle.
- Shared `SSL_CTX` avoids per-connection overhead
- `SSL_ERROR_WANT_READ/WRITE` handling required for non-blocking sockets (current code uses blocking with timeout, but pattern is correct)
- `ERR_print_errors_fp(stderr)` provides detailed OpenSSL error output on failure

## Related Patterns
- `references/mbedtls-tls-integration-2026-06-28.md` — Original mbedTLS approach (kept for reference)
- `references/cudnn-cpu-fallback-patterns.md` — Another "unavailable hardware → CPU fallback" pattern