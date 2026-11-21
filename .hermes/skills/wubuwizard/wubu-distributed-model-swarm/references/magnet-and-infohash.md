# Magnet URIs and info-hashes

Depth for the addressing leg. The module's own header is the contract; this
file is the domain note behind it.

## BEP 9 magnet format

```
magnet:?xt=urn:btih:<40 hex>&dn=<display name>&tr=<tracker>&xl=<bytes>
```

| param | meaning | notes |
|---|---|---|
| `xt` | exact topic | `urn:btih:` = v1 SHA-1 info-hash; `urn:btmh:` = v2 multihash. REQUIRED -- a magnet with no `xt` names nothing. |
| `dn` | display name | human only; percent-encode it, it is not a filename |
| `tr` | tracker | repeatable; a URL, not the model's location |
| `xl` | exact length | bytes; 0 or absent means unstated |

Unknown parameters are IGNORED on parse (BEP 9 lets senders add them). Do not
refuse a magnet because it carries a parameter you do not know.

## The build/parse contract the module implements

- Build: `magnet:?xt=urn:btih:` + the 40 hex chars, then `&dn=` (only if a name
  is present), then one `&tr=` per tracker, then `&xl=` if a length is stated.
  Every component after `dn` is percent-encoded on the way out.
- Parse: split on `&`, then on the FIRST `=`. A parameter with no `=` is a
  failure. Percent-decode each key and value; a truncated or non-hex escape is
  a failure.
- Names are compared as fixed-width, space-padded fields on the wire and
  trimmed on decode, so a peer sees the name, not the padding.

## Info-hash rules (for the SHA-1 leg)

- The btih is `SHA-1(bencode(info dict))` over the `.torrent`'s info dict,
  canonically re-encoded. It is NOT a hash of the files, the file names, a
  directory listing, or an HF `index.json`.
- v1 = 20 raw bytes = 40 lowercase hex. v2 = multihash, longer, base32 or hex
  depending on the client. Keep them in separate fields.
- A torrent with no `info` dict has no info-hash. Refuse rather than emit an
  empty one.

## Percent-encoding set

Encode every byte outside the RFC 3986 unreserved set
(`A-Z a-z 0-9 - _ . ~`) as `%XX` uppercase hex. In particular a space becomes
`%20` and `/` becomes `%2F` -- without this a display name containing either
splits the URI into extra parameters and the address changes meaning.

## What to assert in the test

1. A bare magnet is exactly the BEP 9 form (no trailing `&`, no extra `?`).
2. A round trip: build then parse returns the same hash, name, trackers, length.
3. A name with a space and a slash is escaped on the way out and restored on
   the way in; no raw space survives in the URI.
4. Every refusal: non-magnet, no `xt`, unknown topic, short hash, non-hex hash,
   bad percent escape, parameter with no value, over-long name.
5. A refused parse leaves the caller's struct byte-identical (fill it with a
   sentinel and compare).
6. Unknown parameters do not break the parse.
