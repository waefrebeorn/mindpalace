# TLS Migration: mbedTLS → OpenSSL in OCI HTTP Client (2026-07-24)

## Context
The OCI HTTP client (`src/runtime/oci/oci_http_client.c`) was written with conditional mbedTLS support (`#ifdef MBEDTLS_SSL_H`). However, mbedTLS was not available on the build system (no `libmbedtls-dev` installable without root). OpenSSL (`libssl-dev`) IS available via system package manager.

## Migration Pattern

### 1. Replace mbedTLS headers with OpenSSL in internal header
```c
/* oci_internal.h - BEFORE */
#ifdef MBEDTLS_SSL_H
#include <mbedtls/ssl.h>
#include <mbedtls/entropy.h>
#include <mbedtls/ctr_drbg.h>
#include <mbedtls/error.h>
#include <mbedtls/net_sockets.h>
#include <mbedtls/x509_crt.h>
#endif

/* oci_internal.h - AFTER */
#include <openssl/ssl.h>
#include <openssl/err.h>
```

### 2. Update opaque struct definition
```c
/* BEFORE */
typedef struct OciHttpClient {
    int sockfd;
    char host[256];
    int port;
    bool use_tls;
#ifdef MBEDTLS_SSL_H
    mbedtls_ssl_context ssl;
    mbedtls_ssl_config conf;
    mbedtls_entropy_context entropy;
    mbedtls_ctr_drbg_context ctr_drbg;
    mbedtls_x509_crt cacert;
    bool tls_initialized;
#endif
} OciHttpClient;

/* AFTER */
typedef struct OciHttpClient {
    int sockfd;
    char host[256];
    int port;
    bool use_tls;
    SSL *ssl;
} OciHttpClient;
```

### 3. Implement TLS lifecycle with shared SSL_CTX
```c
/* Static shared context - created once, reused across connections */
static SSL_CTX *g_ssl_ctx = NULL;
static bool g_ssl_init_done = false;

static void oci_http_ssl_init(void) {
    if (g_ssl_init_done) return;
    SSL_library_init();
    SSL_load_error_strings();
    OpenSSL_add_all_algorithms();
    g_ssl_ctx = SSL_CTX_new(TLS_client_method());
    if (!g_ssl_ctx) {
        fprintf(stderr, "[wubu_oci] SSL_CTX_new failed\n");
        return;
    }
    SSL_CTX_set_verify(g_ssl_ctx, SSL_VERIFY_NONE, NULL);  // Insecure but functional
    g_ssl_init_done = true;
}

static void oci_http_ssl_cleanup(void) {
    if (g_ssl_ctx) {
        SSL_CTX_free(g_ssl_ctx);
        g_ssl_ctx = NULL;
    }
    EVP_cleanup();
    g_ssl_init_done = false;
}
```

### 4. Connection with TLS
```c
int oci_http_connect(OciHttpClient *client, const char *host, int port, bool use_tls) {
    /* ... socket setup ... */
    client->ssl = NULL;
    
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

### 5. Send/Receive with proper error handling
```c
/* Send */
if (client->use_tls && client->ssl) {
    while (sent < len) {
        int n = SSL_write(client->ssl, p + sent, len - sent);
        if (n <= 0) {
            int err = SSL_get_error(client->ssl, n);
            if (err == SSL_ERROR_WANT_READ || err == SSL_ERROR_WANT_WRITE)
                continue;
            return -1;
        }
        sent += n;
    }
    return 0;
}

/* Receive */
if (client->use_tls && client->ssl) {
    while (total < buf_size - 1) {
        int n = SSL_read(client->ssl, p + total, buf_size - 1 - total);
        if (n <= 0) {
            int err = SSL_get_error(client->ssl, n);
            if (err == SSL_ERROR_WANT_READ || err == SSL_ERROR_WANT_WRITE)
                continue;
            if (err == SSL_ERROR_ZERO_RETURN)
                break;
            return -1;
        }
        total += n;
        /* ... content-length check ... */
    }
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

## Makefile Changes
Add `-lssl -lcrypto` to any test target that links `oci_http_client.c`:

```makefile
test_oci:
	$(CC) ... $(RT)/oci/oci_http_client.c ... -o $(RT)/wubu_oci_test -lm -lssl -lcrypto

test_pkgmgr:
	$(CC) ... $(RT)/oci/oci_http_client.c ... -o $(GUI)/wubu_pkgmgr_test -lsqlite3 -lzstd -lssl -lcrypto
```

## Verification
```bash
# Test OCI suite (includes HTTPS index fetch)
make test_oci
# → 10/10 passed

# Test pkgmgr (includes repo_update over HTTPS)
make test_pkgmgr
# → 12/12 passed (test_repo_update_fetch connects to local HTTP server)
```

## Pitfalls
1. **SSL_VERIFY_NONE** - This disables cert verification (insecure). In production, load system CA certs:
   ```c
   SSL_CTX_load_verify_locations(g_ssl_ctx, "/etc/ssl/certs/ca-certificates.crt", NULL);
   SSL_CTX_set_verify(g_ssl_ctx, SSL_VERIFY_PEER, NULL);
   ```
2. **EVP_cleanup()** - Deprecated in OpenSSL 3.0+. Use `OPENSSL_cleanup()` if available.
3. **Thread safety** - The shared `g_ssl_ctx` is not thread-safe for concurrent modification. If multi-threaded TLS is needed, add mutex or use per-thread contexts.
4. **Memory leaks** - Ensure `SSL_free()` is called on every error path in `oci_http_connect()`.

## Files Modified
- `src/runtime/oci/oci_http_client.c` — Full rewrite of TLS logic
- `src/runtime/oci/oci_internal.h` — Header updates
- `Makefile` — Link flags for test targets

## Related Patterns
See `references/mbedtls-tls-integration-2026-06-28.md` for the original mbedTLS approach (kept for reference).