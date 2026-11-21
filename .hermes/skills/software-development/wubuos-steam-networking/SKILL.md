---
name: wubuos-steam-networking
description: Use when porting Steam Networking (SDR) into WuBuOS.
category: software-development
version: 1.0.0
author: WaefreBeorn
license: MIT
metadata:
  hermes:
    tags: [wubuos, steam, sdr, networking, relay, security]
    related_skills: [wubuos-test-suite, d3d12-vulkan-translation]
---

# Steam Networking (SDR) onto WuBuOS

Steam's networking stack -- SDR (Steam Datagram Relay), the POP relay fabric,
NAT traversal -- is the graft target. The model is NOT peer-to-peer: every user
gets a VIRTUAL IP, and a client never learns its peer's real address, only a
virtual one. A ROUTING TICKET authorizes a connection, and a POP forwards
packets between virtual addresses.

## When to Use

Load this when:
- building or extending the `wubu_sdr*` module family (tickets, routes, relay,
  sessions);
- designing any relay, ticket, capability or session-lifetime rule;
- reviewing a module where a wrong decision means one peer reading another's
  traffic.

## The layers, in dependency order

1. **Tickets** (`wubu_sdr`) -- a signed, expiring authorization for ONE
   connection.
2. **Route table** (`wubu_sdr`) -- virtual address -> POP + peer.
3. **Relay decision** (`wubu_sdr_relay`) -- the per-packet allow/deny.
4. **Session layer** (`wubu_sdr_session`) -- virtual address assignment,
   keepalive, teardown.

Build them in that order. Each is pure C11 with no socket, no libc beyond
`<string.h>`/`<stdlib.h>`/`<stdio.h>`, and each is unit-testable on any host.

## Rules that are security-relevant, not stylistic

**Tickets.**
- A ticket is for ONE connection: it names BOTH a source and a destination
  virtual address. A ticket that names only a destination can be replayed
  against another source.
- A ticket EXPIRES, and the window is CAPPED (a day). A ticket that never
  expires is a permanent authorization, which a relay must never hand out.
- The window is HALF-OPEN: valid at `issued_at`, invalid AT `expires_at`. An
  expiry check written `now <= expires_at` hands out one extra second of
  authorization on every ticket.
- A ticket is TAMPER-EVIDENT (checksum over the canonical fields). A malformed
  string, a bad checksum and a structurally invalid ticket must be
  INDISTINGUISHABLE to the caller -- none of them may leak WHY, or the
  difference becomes an oracle for an attacker.
- `issued_at == expires_at` (zero window) is either rejected or immediately
  expired; decide and test it, do not leave it to unsigned arithmetic.

**Route table.**
- A virtual address may be claimed ONCE. A duplicate is a HIJACK ATTEMPT, not
  an update -- an update goes through a separate `set_ready`. Returning success
  for a duplicate silently overwrites the victim's route.
- A route must be READY before packets are forwarded to it. Forwarding into a
  not-ready route BLACK-HOLES the packet, which is a denial of service on the
  SENDER, not just the recipient.

**Relay decision.**
- FAIL CLOSED: every check must pass, and the FIRST failure decides. There is
  no "allow by default" and no "skip this check if the ticket looks fine".
- Order the checks so the CHEAPEST and most diagnostic come first: route
  exists -> route ready -> ticket present -> ticket valid -> ticket matches ->
  not loopback -> rate allowed. A destination with no route is refused before
  the ticket is even read, and the caller learns WHICH check failed.
- Never loop a packet back to its sender.
- Every decision has a NAME, not just an enum value -- an operator reading a log
  needs "deny: ticket expired", not "deny 5".

**Session layer.**
- **PORT REASSIGNMENT IS THE ONE RULE THAT MATTERS MOST.** A virtual port must
  NEVER be handed to a new session while the old one could still receive
  traffic. Otherwise packets for the previous peer are delivered to the new
  one -- a session hijack indistinguishable from a legitimate handover. A port
  becomes reusable only when its session is REAPED (expired past keepalive),
  never merely closed.
- A session is ALIVE only while not closed AND within its keepalive window.
  Silence means gone.
- Opening for a peer that already has a session is IDEMPOTENT and returns the
  SAME virtual address -- a client retrying a connect must not be handed a
  second one.
- A peer already on a DIFFERENT POP is refused.
- Touching or closing an unknown session is an ERROR, not a no-op. A POP that
  silently accepted those would mask a client bug or an attack.
- Keepalive 0 means "lives until closed"; do not treat 0 as "already dead".

**Allocator.**
- A MONOTONIC COUNTER IS NOT AN ALLOCATOR. It never reuses a freed port and
  exhausts the 16-bit space. Recycle freed ports through a FREE LIST that a
  reap fills and an open drains -- O(1), no collision, bounded reuse.
- Never hand out a port that is still in use, even if the previous owner was
  closed moments ago. Reuse only after the reap.

## Publishing a payload over SDR: there is no socket

The `wubu_sdr*` family is a DECISION layer, not a transport. Nothing in it
sends a byte: tickets, routes and `wubu_sdr_relay()` answer "may this packet
go", and `wubu_sdr_session` answers "who holds this virtual port". So when a
new payload must ride SDR -- a boot report, a ledger frame, anything -- do NOT
go looking for a send call. The shape is:

1. Take the payload as opaque bytes (a fixed frame, shape-fail-closed).
2. Walk the route table. For EACH route, take `wubu_sdr_relay()` with the
   packet's addresses and ticket.
3. Hand the bytes to a transmit CALLBACK only where the decision is FORWARD.

Two rules follow. **Who may receive it is the relay's call** -- a payload
never bypasses a check (no route, not ready, no ticket, expired, mismatched,
loopback, rate-limited) by being special. And **"to everyone" means every
route in the table**, not one broadcast address: the table is the peer set.

`wubu_boot_attest_relay.c` is the reference implementation (a sealed boot
report offered to every ready, ticketed peer). Read it before writing a second
publisher -- the callback seam is the part that stays the same.

## Pitfalls

- **Never checksum a struct by hashing its RAW BYTES.** C struct padding is
  unspecified, so a `memcpy` of the struct into a checksum buffer carries
  uninitialized bytes and encode/decode can disagree for an IDENTICAL value.
  Zero a copy, then assign the FIELDS explicitly (never `memcpy` the whole
  struct), then hash. The same rule applies to any hash key over a struct.
- **Derive every constant; never write a unit factor from memory.** A
  milli-token bucket refills at `rate_per_sec` per MILLISECOND, not divided by
  1000. The test's own timings (expect one packet per 100ms at 10/sec) are what
  expose the error -- write the timings into the test rather than asserting
  only "eventually allowed".
- **A test that asserts the right-sounding decision for the wrong state is its
  own bug.** Asserting a ticket mismatch for a destination that has no ROUTE
  will always fail, because the route check fires first. When a test of a late
  check fails, verify the earlier checks are satisfied in the fixture before
  blaming the check under test.
- **Bound every table and state the bound in the test.** A silent overwrite at
  capacity is a memory-safety bug; a refusal at capacity with a reason is a
  working allocator.
- **Encode/decode lengths are derived, not assumed.** 36 bytes is a multiple of
  3 so base64 needs no padding and the text is exactly 48 chars -- but assert
  the length comes from the byte count, or a future field addition silently
  produces a wrong-length ticket.

## Testing discipline

Every rule above is testable with no network and no privileges. Prefer tests
that assert the NEGATIVE case (a duplicate address refused, a cancelled-again
refused, a port NOT reused before a reap) -- the happy path is what a
wrong implementation also satisfies.

Add each new target to `test_medium_other` and anchor new recipes on the
PREVIOUS target's last recipe line, never its prerequisite line (see
`wubuos-test-suite`).
