# Netlink rtnetlink + mbedTLS Integration Patterns

## Netlink rtnetlink Socket Implementation (wubu_network.c)

### Core Infrastructure
```c
// Socket state
static int g_nl_sock = -1;

// Open netlink socket
static int nl_socket_open(void) {
    if (g_nl_sock >= 0) return g_nl_sock;
    g_nl_sock = socket(AF_NETLINK, SOCK_RAW, NETLINK_ROUTE);
    struct sockaddr_nl sa = { .nl_family = AF_NETLINK,
                              .nl_groups = RTMGRP_LINK | RTMGRP_IPV4_IFADDR };
    bind(g_nl_sock, (struct sockaddr *)&sa, sizeof(sa));
    return g_nl_sock;
}

// Send message and parse ACK
static int nl_send_recv(struct nlmsghdr *nh) {
    int sock = nl_socket_open();
    struct sockaddr_nl sa = { .nl_family = AF_NETLINK };
    struct iovec iov = { nh, nh->nlmsg_len };
    struct msghdr msg = { &sa, sizeof(sa), &iov, 1, NULL, 0, 0 };
    sendmsg(sock, &msg, 0);
    
    // Receive and parse ACK
    char buf[4096];
    iov.iov_base = buf; iov.iov_len = sizeof(buf);
    ssize_t len = recvmsg(sock, &msg, 0);
    for (struct nlmsghdr *rnh = (struct nlmsghdr *)buf; NLMSG_OK(rnh, len); rnh = NLMSG_NEXT(rnh, len)) {
        if (rnh->nlmsg_type == NLMSG_ERROR) {
            struct nlmsgerr *err = (struct nlmsgerr *)NLMSG_DATA(rnh);
            if (err->error < 0) { errno = -err->error; return -1; }
        }
        if (rnh->nlmsg_type == NLMSG_DONE) break;
    }
    return 0;
}

// Add attribute helper
static void nl_addattr(struct nlmsghdr *nh, int maxlen, int type, const void *data, int alen) {
    int len = RTA_LENGTH(alen);
    struct rtattr *rta = (struct rtattr *)(((char *)nh) + NLMSG_ALIGN(nh->nlmsg_len));
    rta->rta_type = type; rta->rta_len = len;
    memcpy(RTA_DATA(rta), data, alen);
    nh->nlmsg_len = NLMSG_ALIGN(nh->nlmsg_len) + len;
}
```

### Interface Creation (RTM_NEWLINK)
```c
static int netlink_link_create(const char *name, const char *kind,
                               const char *parent, int vlan_id,
                               const char *vxlan_id, int vxlan_port,
                               const char *vxlan_remote, bool vxlan_encrypt) {
    struct { struct nlmsghdr nh; struct ifinfomsg ifi; char attrs[4096]; } req = {0};
    req.nh.nlmsg_len = NLMSG_LENGTH(sizeof(struct ifinfomsg));
    req.nh.nlmsg_flags = NLM_F_REQUEST | NLM_F_CREATE | NLM_F_EXCL | NLM_F_ACK;
    req.nh.nlmsg_type = RTM_NEWLINK;
    req.ifi.ifi_family = AF_UNSPEC;
    
    nl_addattr(&req.nh, sizeof(req), IFLA_IFNAME, name, strlen(name) + 1);
    nl_addattr(&req.nh, sizeof(req), IFLA_INFO_KIND, kind, strlen(kind) + 1);
    
    if (parent) {
        int parent_idx = if_nametoindex(parent);
        if (parent_idx > 0) nl_addattr(&req.nh, sizeof(req), IFLA_LINK, &parent_idx, sizeof(parent_idx));
    }
    
    // Kind-specific attributes
    if (strcmp(kind, "vlan") == 0 && vlan_id > 0) {
        struct ifla_vlan_flags vf = {0};
        nl_addattr(&req.nh, sizeof(req), IFLA_VLAN_FLAGS, &vf, sizeof(vf));
        nl_addattr(&req.nh, sizeof(req), IFLA_VLAN_ID, &vlan_id, sizeof(vlan_id));
    }
    if (strcmp(kind, "vxlan") == 0) {
        if (vxlan_id) { uint32_t vni = strtoul(vxlan_id, NULL, 10);
            nl_addattr(&req.nh, sizeof(req), IFLA_VXLAN_ID, &vni, sizeof(vni)); }
        if (vxlan_port > 0) {
            nl_addattr(&req.nh, sizeof(req), IFLA_VXLAN_PORT, &vxlan_port, sizeof(vxlan_port));
            struct ifla_vxlan_port_range vpr = {vxlan_port, vxlan_port};
            nl_addattr(&req.nh, sizeof(req), IFLA_VXLAN_PORT_RANGE, &vpr, sizeof(vpr));
        }
        if (vxlan_remote) {
            struct in_addr addr; if (inet_pton(AF_INET, vxlan_remote, &addr) == 1)
                nl_addattr(&req.nh, sizeof(req), IFLA_VXLAN_GROUP, &addr, sizeof(addr));
        }
    }
    return nl_send_recv(&req.nh);
}
```

### Interface Deletion (RTM_DELLINK)
```c
static int netlink_link_delete(const char *name) {
    int ifindex = if_nametoindex(name);
    if (ifindex == 0) return 0;
    struct { struct nlmsghdr nh; struct ifinfomsg ifi; char attrs[4096]; } req = {0};
    req.nh.nlmsg_len = NLMSG_LENGTH(sizeof(struct ifinfomsg));
    req.nh.nlmsg_flags = NLM_F_REQUEST | NLM_F_ACK;
    req.nh.nlmsg_type = RTM_DELLINK;
    req.ifi.ifi_family = AF_UNSPEC;
    req.ifi.ifi_index = ifindex;
    return nl_send_recv(&req.nh);
}
```

### Link Up/Down (RTM_NEWLINK with IFF_UP)
```c
static int netlink_link_set_up(const char *name, bool up) {
    int ifindex = if_nametoindex(name);
    if (ifindex == 0) return -1;
    struct { struct nlmsghdr nh; struct ifinfomsg ifi; char attrs[4096]; } req = {0};
    req.nh.nlmsg_len = NLMSG_LENGTH(sizeof(struct ifinfomsg));
    req.nh.nlmsg_flags = NLM_F_REQUEST | NLM_F_ACK;
    req.nh.nlmsg_type = RTM_NEWLINK;
    req.ifi.ifi_family = AF_UNSPEC;
    req.ifi.ifi_index = ifindex;
    req.ifi.ifi_change = up ? IFF_UP : 0;
    req.ifi.ifi_flags = up ? IFF_UP : 0;
    return nl_send_recv(&req.nh);
}
```

### IP Address Addition (RTM_NEWADDR)
```c
static int netlink_addr_add(const char *iface, const char *ip_with_cidr) {
    // Parse IP/prefix
    char ip_copy[128]; strncpy(ip_copy, ip_with_cidr, sizeof(ip_copy)-1);
    char *slash = strchr(ip_copy, '/'); if (!slash) return -1;
    *slash = '\0'; int prefixlen = atoi(slash + 1);
    struct in_addr addr; if (inet_pton(AF_INET, ip_copy, &addr) != 1) return -1;
    int ifindex = if_nametoindex(iface); if (ifindex == 0) return -1;
    
    struct { struct nlmsghdr nh; struct ifaddrmsg ifa; char attrs[4096]; } req = {0};
    req.nh.nlmsg_len = NLMSG_LENGTH(sizeof(struct ifaddrmsg));
    req.nh.nlmsg_flags = NLM_F_REQUEST | NLM_F_CREATE | NLM_F_EXCL | NLM_F_ACK;
    req.nh.nlmsg_type = RTM_NEWADDR;
    req.ifa.ifa_family = AF_INET; req.ifa.ifa_prefixlen = prefixlen;
    req.ifa.ifa_flags = IFA_F_PERMANENT; req.ifa.ifa_scope = RT_SCOPE_UNIVERSE;
    req.ifa.ifa_index = ifindex;
    nl_addattr(&req.nh, sizeof(req), IFA_LOCAL, &addr, sizeof(addr));
    nl_addattr(&req.nh, sizeof(req), IFA_ADDRESS, &addr, sizeof(addr));
    return nl_send_recv(&req.nh);
}
```

### Key Constants (from linux/if_link.h)
- `IFLA_INFO_KIND` — link kind (bridge, macvlan, ipvlan, vxlan, dummy, vlan)
- `IFLA_LINK` — parent interface index
- `IFLA_VLAN_ID`, `IFLA_VLAN_FLAGS` — VLAN attributes
- `IFLA_VXLAN_ID`, `IFLA_VXLAN_PORT`, `IFLA_VXLAN_PORT_RANGE`, `IFLA_VXLAN_GROUP` — VXLAN attributes

---

## mbedTLS TLS Integration (wubu_oci.c)

### Conditional Compilation
```c
#ifdef MBEDTLS_SSL_H
#include <mbedtls/ssl.h>
#include <mbedtls/entropy.h>
#include <mbedtls/ctr_drbg.h>
#include <mbedtls/error.h>
#include <mbedtls/net_sockets.h>
#include <mbedtls/x509_crt.h>
#endif
```

### Extended HTTP Client Struct
```c
typedef struct {
    int sockfd;
    char host[256]; int port; bool use_tls;
#ifdef MBEDTLS_SSL_H
    mbedtls_ssl_context ssl;
    mbedtls_ssl_config conf;
    mbedtls_entropy_context entropy;
    mbedtls_ctr_drbg_context ctr_drbg;
    mbedtls_x509_crt cacert;
    bool tls_initialized;
#endif
} OciHttpClient;
```

### TLS Connection Setup
```c
// In oci_http_connect()
#ifdef MBEDTLS_SSL_H
if (use_tls) {
    mbedtls_ssl_init(&client->ssl);
    mbedtls_ssl_config_init(&client->conf);
    mbedtls_entropy_init(&client->entropy);
    mbedtls_ctr_drbg_init(&client->ctr_drbg);
    mbedtls_x509_crt_init(&client->cacert);
    
    // Seed RNG
    rc = mbedtls_ctr_drbg_seed(&client->ctr_drbg, mbedtls_entropy_func, &client->entropy, NULL, 0);
    if (rc != 0) goto tls_fail;
    
    // Skip cert verification (insecure but functional)
    mbedtls_ssl_conf_authmode(&client->conf, MBEDTLS_SSL_VERIFY_NONE);
    
    // SSL config
    rc = mbedtls_ssl_config_defaults(&client->conf, MBEDTLS_SSL_IS_CLIENT,
                                     MBEDTLS_SSL_TRANSPORT_STREAM, MBEDTLS_SSL_PRESET_DEFAULT);
    mbedtls_ssl_conf_rng(&client->conf, mbedtls_ctr_drbg_random, &client->ctr_drbg);
    mbedtls_ssl_conf_ca_chain(&client->conf, &client->cacert, NULL);
    
    // SNI
    mbedtls_ssl_set_hostname(&client->ssl, host);
    mbedtls_ssl_setup(&client->ssl, &client->conf);
    mbedtls_ssl_set_bio(&client->ssl, &client->sockfd, mbedtls_net_send, mbedtls_net_recv, NULL);
    
    // Handshake
    while ((rc = mbedtls_ssl_handshake(&client->ssl)) != 0) {
        if (rc != MBEDTLS_ERR_SSL_WANT_READ && rc != MBEDTLS_ERR_SSL_WANT_WRITE) goto tls_fail;
    }
    client->tls_initialized = true;
}
#endif
```

### TLS Send/Receive
```c
// oci_http_send()
#ifdef MBEDTLS_SSL_H
if (client->use_tls && client->tls_initialized) {
    while (sent < len) {
        int n = mbedtls_ssl_write(&client->ssl, (const unsigned char*)(p+sent), len-sent);
        if (n <= 0) {
            if (n != MBEDTLS_ERR_SSL_WANT_READ && n != MBEDTLS_ERR_SSL_WANT_WRITE) return -1;
            continue;
        }
        sent += n;
    }
    return 0;
}
#endif

// oci_http_recv()
#ifdef MBEDTLS_SSL_H
if (client->use_tls && client->tls_initialized) {
    while (total < buf_size - 1) {
        int n = mbedtls_ssl_read(&client->ssl, (unsigned char*)(p+total), buf_size-1-total);
        if (n <= 0) {
            if (n == MBEDTLS_ERR_SSL_WANT_READ || n == MBEDTLS_ERR_SSL_WANT_WRITE) continue;
            if (n == MBEDTLS_ERR_SSL_PEER_CLOSE_NOTIFY) break;
            return -1;
        }
        total += n;
        // ... Content-Length parsing same as non-TLS
    }
}
#endif
```

### TLS Cleanup
```c
// oci_http_close()
#ifdef MBEDTLS_SSL_H
if (client->use_tls && client->tls_initialized) {
    mbedtls_ssl_close_notify(&client->ssl);
    mbedtls_ssl_free(&client->ssl);
    mbedtls_ssl_config_free(&client->conf);
    mbedtls_entropy_free(&client->entropy);
    mbedtls_ctr_drbg_free(&client->ctr_drbg);
    mbedtls_x509_crt_free(&client->cacert);
    client->tls_initialized = false;
}
#endif
```

### Build with mbedTLS
```bash
# Install on Debian/Ubuntu
sudo apt-get install libmbedtls-dev

# Link flags
-lmbedtls -lmbedx509 -lmbedcrypto
```

---

## Usage Pattern

For HTTPS registry calls:
```bash
# Compile with mbedTLS support
make test_oci  # Works without mbedTLS (HTTP only)
# With mbedTLS dev package installed, HTTPS registries work
```