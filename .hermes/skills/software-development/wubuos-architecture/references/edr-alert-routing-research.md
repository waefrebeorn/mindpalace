# WuBuOS EDR Alert Routing & Pins Research

**Date**: 2026-07-03
**Source**: heavener reference, wubu_edr.c/.h audit, wubu_notify.c audit, Wazuh alert management study

---

## Current State (wubu_edr.c, 566 lines, 7/9 tests passing)

The EDR engine has working core but **zero routing infrastructure**:

| Component | Status | Notes |
|-----------|--------|-------|
| Event pipeline (fanotify, inotify) | ✅ Working | Lock-free MPSC queue, worker thread |
| Process model (procfs enrichment) | ✅ Working | 8192 max, ancestry chain, creators, injection tracking |
| YARA module shell | ⚠️ Stub | `yara_module_on_event` has 4x (void) — empty handler |
| Behavioral module | ✅ Working | PPID spoof, lsass handle read, file burst rules |
| FNV-1a alert hashing | ✅ Working | Deterministic ID for idempotent replay |
| 9P/Styx path declarations | ⚠️ Unmounted | `/edr/alerts/`, `/edr/config/`, `/edr/rules/` declared but never mounted |
| Alert buffer | ⚠️ Static array | `g_alerts[1024]` — FIFO overwrite, **no pinning, no persistence** |
| Alert forwarding | ❌ Missing | No syslog, webhook, SMTP, desktop notify wiring |
| Severity routing | ❌ Missing | All alerts go to same flat buffer |
| Desktop notification integration | ❌ Missing | `wubu_notify_system()` exists but never called from EDR |
| GC pinning | ❌ Missing | Alerts are raw arrays, not GC-managed objects |

## The "Pins" Problem

"Most people will need to route to pins" = **two distinct needs**:

### 1. Pinned alerts (survive GC / don't rotate out)
- Critical alerts (severity=malicious) must NOT be lost to ring-buffer overwrite
- WuBuOS GC (`wubu_gc.c`) has `.pinned` field on GC objects — but EDR alerts are raw C arrays, not GC-managed
- Need: separate persistent alert store with configurable max (StyxFS-backed), or wire alerts into GC allocator

### 2. Pin routing (severity→destination mapping)
- Each alert severity routes to zero or more destination "pins"
- Route table: `EdrRouteEntry[severity][EDR_MAX_ROUTE_TARGETS]`

## Production EDR Alert Routing (What Users Actually Need)

From Wazuh, CrowdStrike, SentinelOne patterns:

| Destination | Protocol | WuBuOS Feasibility | Priority |
|-------------|----------|-------------------|----------|
| **Syslog** (RFC 5424/3164) | UDP/TCP :514 | High — raw sockets, no libs needed | **Critical** |
| **Webhook** (HTTP POST) | JSON over HTTP | High — reuse wubu_oci.c HTTP client patterns | **Critical** |
| **Desktop toast** | wubu_notify_system() | Trivial — API already exists | **High** |
| **SMTP** email | RFC 5321 SMTP | Medium — raw socket, needs base64 auth | Medium |
| **StyxFS/9P** persist | 9P namespace | Medium — mount `/edr/alerts/` as 9P dir | Medium |

### Wazuh's Approach (Reference Implementation)

From wazuh.com alert management docs:

- **Log alert level**: minimum severity for file logging (default 3/16)
- **Email alert level**: minimum severity for email (default 12/16)
- **Syslog output**: per-server config with minimum level filter, UDP 514
- **Multiple syslog targets**: define multiple `<syslog_output>` blocks
- **Email format**: structured notification with rule ID, level, file attributes, hashes

### heavener's Approach (WuBuOS Reference)

From reference/heavener.html:

- Alert IDs: deterministic FNV-1a hashes for idempotent replay
- Outbox directory: alerts written as JSONL
- Forwarder: separate process (Go binary in heavener, should be in-process C for WuBuOS)
- Console stack: ClickHouse + Postgres + Redis + REST API + React SPA

## Proposed Routing Architecture

```
                 ┌──────────────────┐
                 │  EdrEventQueue   │
                 │  (lock-free MPSC) │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │  EventPipeline   │
                 │  (worker thread) │
                 └────────┬─────────┘
                          │ batch drain
                          ▼
                 ┌──────────────────┐
                 │  ProcessModel    │
                 │  + ModifierEng.  │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │  IEdrModule     │
                 │  (yara/behavioral)│
                 └────────┬─────────┘
                          │ alerts
                          ▼
     ┌──────────────────────────────┐
     │   AlertSink + Router         │
     │                              │
     │  severity → [destinations]   │
     │                              │
     │  ┌──────────────────────┐    │
     │  │ Pinned Alert Store   │    │
     │  │ (StyxFS /edr/alerts/)│    │
     │  │ (GC pinned objects)  │    │
     │  └──────────────────────┘    │
     │                              │
     │  ┌──────────────────────┐    │
     │  │ Syslog Forwarder     │◄───│── UDP/TCP :514
     │  └──────────────────────┘    │
     │                              │
     │  ┌──────────────────────┐    │
     │  │ Webhook Forwarder    │◄───│── HTTP POST
     │  └──────────────────────┘    │
     │                              │
     │  ┌──────────────────────┐    │
     │  │ SMTP Forwarder       │◄───│── SMTP relay
     │  └──────────────────────┘    │
     │                              │
     │  ┌──────────────────────┐    │
     │  │ Desktop Notify       │◄───│── wubu_notify_system()
     │  └──────────────────────┘    │
     └──────────────────────────────┘
```

## REAL_GAPs Identified

| # | Component | Est. LOC | Key File | Priority |
|---|-----------|----------|----------|----------|
| 1 | `edr_route_table()` — severity→destination router | ~120 | `wubu_edr.c` | Critical |
| 2 | `edr_pin_alert()` — GC-pinned persistent alert store | ~150 | `wubu_edr.c` + `wubu_gc.h` | Critical |
| 3 | `edr_forwarder_syslog()` — RFC 5424 UDP/TCP | ~200 | `wubu_edr.c` | High |
| 4 | `edr_forwarder_webhook()` — HTTP POST JSON | ~200 | `wubu_edr.c` (reuse `wubu_oci.c` HTTP) | High |
| 5 | `edr_wire_notify()` — desktop toast integration | ~80 | `wubu_edr.c` + `wubu_notify.h` | High |
| 6 | `edr_forwarder_smtp()` — raw socket SMTP | ~250 | `wubu_edr.c` | Medium |
| 7 | `edr_persist_styx()` — 9P namespace mount | ~150 | `wubu_edr.c` + `styxfs.h` | Medium |
| 8 | Update `wubu_edr.h` API (route config, pin API, severity defs) | ~50 | `wubu_edr.h` | High |

**Total new**: ~8 REAL_GAPs, ~1,200 LOC real C

## Key API Decisions

```c
// Route target flags
typedef uint32_t EdrRouteTarget;
enum {
    EDR_ROUTE_NONE    = 0,
    EDR_ROUTE_SYSLOG  = 1 << 0,
    EDR_ROUTE_WEBHOOK = 1 << 1,
    EDR_ROUTE_SMTP    = 1 << 2,
    EDR_ROUTE_NOTIFY  = 1 << 3,
    EDR_ROUTE_STYX    = 1 << 4,
};

// Route configuration
typedef struct {
    EdrRouteTarget route_mask;          // bitmask of destinations
    const char *syslog_host;            // "192.168.1.241"
    int syslog_port;                    // 514
    const char *webhook_url;            // "https://hooks.example.com/alerts"
    const char *smtp_to;               // "soc@example.com"
    bool sticky;                        // if true, pinned (survives GC/rotation)
} EdrRouteConfig;

// API additions to wubu_edr.h
int edr_set_route(EdrRouteConfig *cfg);           // Set route config
int edr_get_route(EdrRouteConfig *cfg);            // Get current route config
int edr_pin_alert(uint32_t alert_index);           // Pin an alert (survives rotation)
int edr_forward_syslog(const EdrAlert *a);         // Send alert to syslog target
int edr_forward_webhook(const EdrAlert *a);        // HTTP POST alert to webhook
int edr_forward_notify(const EdrAlert *a);         // Desktop toast via wubu_notify
```

## Implementation Strategy

1. **Core route table** — Add `EdrRouteConfig` to `wubu_edr.c`, wire into `edr_alert_push()` so each alert hits the route table after the module pipeline
2. **Syslog first** — Most users have a SIEM, raw UDP syslog needs no dependencies
3. **Desktop notify** — Trivial wire, high visibility for local operators
4. **Webhook** — Reuse `wubu_oci.c` HTTP client (socket + TLS if needed)
5. **Pinned store** — Separate ring buffer for pinned alerts, or expand `g_alerts` with a `pinned` flag and exempt from overwrite
6. **SMTP** — Lowest priority, complex (auth, MIME, attachments)

## heavener Reference (reference/heavener.html)

Key design decisions from heavener that WuBuOS should adopt:
- Deterministic FNV-1a alert IDs for idempotent replay
- JSONL outbox format (human-readable, grepable)
- Lock-free MPSC queue for event ingestion
- Single worker thread for ordered event processing
- Hot-swappable modules (already implemented in `edr_switch_module`)