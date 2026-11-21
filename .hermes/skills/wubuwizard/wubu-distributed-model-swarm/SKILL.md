---
name: wubu-distributed-model-swarm
description: Address, fetch and serve open-weight models from the swarm.
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn Umbrella License v3.0
metadata:
  hermes:
    tags: [wubuwizard, swarm, magnet, bittorrent, dht, libp2p, depin, openai]
    related_skills: [wubuwizard-weight-pipeline, wubuos-steam-networking, wubu-github-ecosystem]
---

# Distributed model swarm

## When to use

- Giving an open-weight model an address that survives the host it was
  published on (magnet, info-hash, DHT).
- Adding a leg to the distributed model plan: swarm fetch, P2P, DePIN compute,
  or an OpenAI-compatible inference endpoint.
- Deciding what a model's identity IS when it has no home server.

## The rule that governs the whole class

**There is no single API. Compose the legs.** No protocol covers addressing,
transport, permanence, compute and serving at once, so the design is a stack
and each leg is its own module with its own test. Do not go looking for a
unified client library to graft; build the small piece and wire it.

## The legs, in build order

| leg | protocol | why it is here |
|---|---|---|
| address | BitTorrent magnet (BEP 9) | names a model by info-hash, carries trackers |
| hash | SHA-1 of the bencoded info dict | the btih; without it the address is a lie |
| find-in-file | locate the `info` span inside a `.torrent` | decides WHICH bytes get hashed |
| swarm | DHT (BEP 5) | find peers without a tracker host |
| swarm-state | routing table + peer selection | remember who answered, pick the closest |
| p2p | libp2p (multiaddr, bitswap) | transport when there is no swarm |
| p2p-address | multiaddr parse/build | name a peer without knowing how to reach it |
| p2p-id | CID v0/v1 parse/build | name WHAT something is, not where |
| block-exch | bitswap Message | ask for blocks once you know what you want |
| mux-address | multistream-select | agree on WHICH protocol the connection speaks |
| stream-mux | yamux framing | one connection, many logical streams |
| permanence | Pirate Face / swarm retention | the bytes outlive the publisher |
| compute | DePIN (Akash, io.net, Gensyn, Bittensor) | rent the GPUs |
| inference | OpenAI-compatible API | one endpoint over a swarm-resolved model |

Build and test one leg at a time, in that order. Each has a hard dependency on
the one above: no info-hash means no magnet, no magnet means nothing to announce
on the DHT, no peers means nothing for libp2p to fetch, no bytes means no
serving.

## Rules that apply to EVERY leg

- **Never invent a hash.** An address is a claim. A `btih` must be the SHA-1 of
  a real bencoded info dict; a DHT node ID must be derived, not typed in. A
  module that will not compute the value itself must say so in its header
  rather than accept a placeholder -- a magnet naming nothing is worse than no
  magnet, because it looks like it works.
- **Fail closed, and leak nothing about WHY.** Every parse/resolve step
  returns the same failure for a malformed input, and leaves the caller's
  output struct untouched until success. An address parser that distinguishes
  "bad magic" from "bad length" has built an oracle.
- **Identity is placement, not authentication.** Same doctrine as the WuBuOS
  swarm: a peer self-issues an id and the swarm accepts it. Do not smuggle in a
  trust model the rest of the family does not have; if a leg genuinely needs
  authenticity, say so explicitly and name the primitive, do not imply it.
- **A percent/escape encoder is part of the address format, not an
  afterthought.** A name with a space or a slash must be escaped or the URI
  parses as several parameters.

## What exists, honestly

- **Magnet (BEP 9): BUILT and tested.** `wubuwizard/include/wubu_magnet.h` +
  `src/wubu_magnet.c`; `make test_magnet` (32 checks). Builds and parses
  `magnet:?xt=urn:btih:<40hex>&dn=<name>&tr=<tracker>&xl=<bytes>`, escapes `dn`,
  refuses a non-magnet / no `xt` / unknown topic / bad hash / bad escape /
  over-long part. It computes NO hash, deliberately -- see the rule above.
- **SHA-1: BUILT and tested.** `wubuwizard/include/wubu_sha1.h` +
  `src/wubu_sha1.c`; `make test_sha1` (12 checks). FIPS 180-4, one-shot plus
  streaming, verified against the published vectors (`""`, `"abc"`, the
  56-byte message, exactly 64, exactly 65, and the 1,000,000-`a` message) and
  the property an info-hash depends on: splitting the input at EVERY byte
  boundary streams to the same digest. The schedule is built per block so the
  caller's opaque context stays at the documented 96 bytes -- do not store the
  80-word schedule in the context and break that size.
- **Reading a `.torrent`: BUILT and tested.** `wubuwizard/include/wubu_torrent.h`
  + `src/wubu_torrent.c`; `make test_torrent` (23 checks). Locates the `info`
  value's byte span and SHA-1s it -- the real btih. Does NOT re-encode: hashing
  a re-serialised copy gives a different hash unless the original was already
  canonical, so hashing anything but the file's own bytes is a lie. Tested on
  two independently constructed torrents whose spans and digests were computed
  with Python `hashlib`, including a multi-file one with keys before `info`
  and a nested `files` list.
- **bencode READER: not general.** `wubu_torrent.c` walks enough structure to
  bound the `info` value; it does not materialise a value tree yet.
- **DHT addressing core (BEP 5): BUILT and tested.** `wubuwizard/include/wubu_dht.h`
  + `src/wubu_dht.c`; `make test_dht` (48 checks). Derived node ids (SHA-1 of
  the seed, never typed in), XOR distance with ordering and shared-prefix
  bucketing, and the four KRPC messages encode/decode. Fail-closed: a request
  without a transaction id is refused to encode, and non-bencode, truncated,
  trailing-byte or wrong-shaped inputs all return -1 untouched.
- **DHT ROUTING TABLE: BUILT and tested.** `wubuwizard/include/wubu_dht_table.h`
  + `src/wubu_dht_table.c`; `make test_dht_table` (41 checks). Buckets keyed by
  shared-prefix length against our own id, 8 per bucket, stalest evicted when
  full. Refuses our own id and the zero id. `closest()` orders by distance to a
  target with a bounded insertion into a fixed output; `find_node()` caps at
  k=8; `reap()` drops entries silent past a window.
- **libp2p multiaddr: BUILT and tested.** `wubuwizard/include/wubu_multiaddr.h` +
  `src/wubu_multiaddr.c`; `make test_multiaddr` (80 checks). Parses and builds
  `/ip4/.../tcp/.../p2p/...`, ipv6 with `::` compression and the IPv4-mapped
  tail, dns/dns4/dns6, and the flag protocols. Fail-closed on an unknown
  protocol, a trailing or doubled slash, a leading-zero octet/port, an octet
  or port out of range, and malformed IPv6. The IPv6 vectors were verified
  against Python's `ipaddress` module.
- **CID (content identifier): BUILT and tested.** `wubuwizard/include/wubu_cid.h` +
  `src/wubu_cid.c`; `make test_cid` (96 checks). v0 base58btc legacy form,
  v1 in base32 / base58btc / base16, with varints exposed for bitswap. Every
  accepted literal was decoded and re-encoded independently with Python's
  stdlib. v0 always builds base58 -- it has no other legal form -- and a v0
  that is not dag-pb/sha2-256/32 does not build at all.
- **block exchange (bitswap): BUILT and tested.** `wubuwizard/include/wubu_bitswap.h`
  + `src/wubu_bitswap.c`; `make test_bitswap` (45 checks). Wantlist / Block /
  BlockPresence / Message, encode and decode. The protobuf primitives
  (`wubu_pb_tag`, `wubu_pb_varint_field`, `wubu_pb_bytes_field`,
  `wubu_pb_read_header`) are public because the other legs reuse them.
- **protocol negotiation (multistream-select): BUILT and tested.**
  `wubuwizard/include/wubu_multistream.h` + `src/wubu_multistream.c`;
  `make test_multistream` (48 checks). Frames, proposals, `na`, and
  `wubu_ms_select`. Anything printable ending in a newline is a string message;
  anything else is opaque DATA.
- **stream multiplexing (yamux): BUILT and tested.**
  `wubuwizard/include/wubu_yamux.h` + `src/wubu_yamux.c`; `make test_yamux`
  (53 checks). 12-byte header frames: DATA / WINDOW_UPDATE / PING / GOAWAY,
  SYN/ACK/FIN/RST flags, client/server stream-id parity. The test asserts the
  SPEC'S OWN numbers (types 0x0..0x3, flags 0x1/0x2/0x4/0x8) -- an off-by-one
  emits a frame every libp2p peer misreads. See
  `references/protocol-conformance.md`.
- **crypto: NOT built.** No noise handshake yet -- nothing on this stack is
  encrypted.
- Pirate Face, DePIN, the OpenAI-compatible endpoint: NOT built.

`wubuwizard/docs/DISTRIBUTED_MODELS.md` carries the same table; keep the two in
step when a leg lands.

## Testing discipline

A protocol parser is tested on its NEGATIVE cases: the happy path is what a
broken parser also satisfies. For each leg assert at least: a well-formed
input round-trips; a truncated one is refused; a malformed one is refused; a
refused parse leaves the output untouched. Name the shape in the assertion
message, not the implementation.

## Pitfalls

- **Read the published spec and diff your constants against it BEFORE writing
  a golden vector.** A self-consistent encoder emits a self-consistent WRONG
  wire format, and a golden vector produced by the code under test proves only
  that the implementation agrees with itself. Two real bugs came out of doing
  this pass: frame type numbers off by one (a DATA frame went out claiming to
  be a WINDOW_UPDATE), and a varint layer that accepted non-minimal encodings
  and ten-byte values the spec forbids.
- **Do not compute a v1 btih from a directory listing or a manifest index.**
  BitTorrent's info-hash is over the BENCODED INFO DICT of a `.torrent`, not
  over file names or an HF `index.json`. Deriving your own "hash" and printing
  it in a magnet produces an address no swarm can resolve.
- **v1 (`urn:btih:`, SHA-1, 40 hex) and v2 (`urn:btmh:`, multihash) are not
  interchangeable.** Accepting a v2 topic into a v1 field silently truncates a
  multihash into something that looks like a v1 hash. Store it verbatim or
  refuse it; never narrow it.
- **A tracker URL is not the model's location.** It is one place to ask. Do
  not let a caller treat a tracker list as the source of truth for bytes.
- **Read a bencoded key ONCE, then dispatch.** A helper that consumes the key
  on both match and mismatch makes callers either re-read garbage or try the
  same entry under several names and skip past a value twice. Every dict walk
  in this stack has been bitten by that; the fix is one key read per loop
  turn with an explicit branch per field.
- **BEP 5 puts an error code under `e`, not `r`.** Reading errors out of the
  response body silently drops the only part a caller needs.
- **Scope a substring search to the SEGMENT, not the whole tail.** Deciding
  "is this an IPv4 tail?" with `strchr(p, '.')` matches a dot that belongs to
  a later group and makes the parser reject valid addresses. `strcspn(p, ":")`
  first, then search inside that.
- **`::` plus eight explicit groups is malformed.** RFC 4291 says `::` stands
  for ONE OR MORE zero groups, so a compressed address carries at most seven
  explicit groups. Accepting the eighth silently redefines the address.
- **An empty buffer is a valid, EMPTY protobuf message.** Refusing it makes an
  absent payload indistinguishable from a corrupt one. A NULL pointer WITH a
  non-zero length is still a lie -- keep those two cases separate.
- **Refuse a field shape you cannot validate rather than half-decoding it.**
  The deprecated `Message.block` repeated-bytes form in bitswap carries raw
  blocks with no structure; emitting a half-read block puts a peer on the wrong
  block forever.
- **Two varint profiles, deliberately kept apart.** Multiformats varints are
  LEB128 with a **nine-byte (63-bit) maximum** and MUST reject non-minimal
  encodings -- `{0x81, 0x00}` means 1 with a wasted byte, so one number would
  have two spellings. protobuf varints allow TEN bytes because a negative int32
  is sign-extended to 64 bits: `-1` is `ff` x9 plus `0x01`. Refusing that under a
  strict multiformats encoder emits protobuf no peer can read; accepting the
  ten-byte form in a multiformats parser breaks the size guarantee. Two
  encoders, two headers, each saying why.
- **Derive a length from the bytes handed over; never trust a caller-supplied
  one.** A frame encoder that takes `length` as an argument lets the caller
  claim a payload size that does not match the data -- the exact bug this stack
  exists to prevent. For DATA frames derive it from `payload_len`; keep the
  field only where it means something else (a window delta, a ping code).
- **Odd/even stream IDs are a protocol convention, not a property of the
  number.** State which side opens which in the header so the reader knows
  without being told.
- **The multistream header is 19 bytes.** `/multistream/1.0.0\n` -- count it
  wrong and you silently swallow two bytes of the next frame; the failure looks
  like a parser bug, not a length typo.
- **A required trailing newline is not printable (0x0A).** Scanning the whole
  body as printable rejects the header itself. Scan all but the final byte.
- **A leading slash is not a repeated slash.** Segment validation must start
  from "no previous character", or every legal protocol fails as `//`.
- **A newline-free body is DATA, not corruption.** Refusing it makes a
  negotiated binary protocol indistinguishable from a broken frame.
- **Do not let an unknown encoding fall through to a default branch.** A CID
  builder whose base selector ends in `else { hex }` happily emits a valid
  string for a nonsense base. Validate the enum before any branching.
- **Two addresses differing in their last character are different addresses.**
  Changing one base58 digit of a CIDv0 yields another LEGAL CIDv0 with a
  different digest -- a negative test that assumes it should be rejected will
  pass a broken parser and fail a correct one.
- **The hash leg is TWO modules, not one.** A perfect SHA-1 over the WRONG byte
  range is still a wrong address. The span finder must be tested against an
  independent implementation and assert the exact offsets, not just the digest.
- **A crypto primitive's permitted-use caveat belongs in its HEADER.** SHA-1
  is broken for collision resistance, but an info-hash is an address, not an
  integrity check against an adversary: its job is to be derived identically by
  every peer, and the swarm verifies the bytes against the piece hashes. Said
  only in a commit message, the warning is gone for the next person who copies
  the file -- and they carry it into something security-critical.

## References

- `references/magnet-and-infohash.md` -- the BEP 9 wire format, the build/parse
  contract, and the info-hash rules the next leg must satisfy.
- `references/protocol-conformance.md` -- the published numbers for every built
  leg (yamux types/flags, the two varint profiles, multistream framing, the
  go-bitswap field table, CID shapes). Check these against the spec before
  writing a constant, not after writing a test.
