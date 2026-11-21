# The federation agent surface (AID identity + the WorldSpace bridge)

The OS-side identity contract. The authoritative spec lives OUTSIDE the tree:
`Waefrebeorn/WuBuFederation/agent-protocol.json` + `JOINING.md` (raw:
`https://raw.githubusercontent.com/waefrebeorn/WuBuFederation/main/agent-protocol.json`).
Fetch the spec; do not invent fields.

## AID format

`AID-<CLASS>-<YY>-<NNNN>-<C>`
- CLASS: two uppercase letters (IN = individual).
- YY: two-digit enrolment year. NNNN: zero-padded sequence within the year.
- C: mod-11 check digit over the YYNNNN digits, weights 7,6,5,4,3,2 left to
  right; remainder 10 renders as `X`.

Worked example from the spec: `AID-IN-26-0001-8`.

**Validate against the spec's FIELD WIDTHS, not against one example string.**
A validator written from a single example passes that example and rejects every
real value (the classic form: a check that counts 9 tail characters while the
format specifies 11).

## Card + persistence

`~/.config/wubu/agent-card.txt` — JSON, `wubu-agent-card-v1`. The loader
re-derives the AID from class/year/seq, so a tampered row is rejected rather
than trusted. The seal is a SHA-256 over the canonical card;
`wubu_agent_seal()` is its single owner, and `seal` + `card` are published
together at `/n/agent/`. Enrolment refuses a card with no sponsor, an unknown
class, or a field containing the record separator.

## `/n/agent/` and `/n/worldspace/`

The `/n` root is `~/.wubu/n` (NOT `~/.wubu`). Publishers:
- `src/runtime/wubu_agent.c` -> `/n/agent/{aid,class,sponsor,model,endpoint,capabilities,note,seal,card}`
- `src/runtime/wubu_ns_worldspace.c` -> `/n/worldspace/{state,agent,portal,transport,capabilities}`

The portal file is `~/.config/wubu/worldspace.conf` (`portal=a2a://host:port`).

## The space bridge is a REACH, not an embed

`make worldspace` builds the WWW engine (`src/lua/www/~WuBu~`, its own gates).
Embedding it would drag MuJoCo, Lua and a second renderer into the OS process.
The body builds it and publishes the entry point; `transport` names the SDR
fail-closed relay + the swarm aggregation ledger so a client knows what exists.

## Rules

- **Publish the HONEST unconfigured state** (`portal=unconfigured`,
  `agent=not enroled`) rather than inventing a card or a portal. A surface that
  lies about being configured is worse than one that says it is not.
- **The world state comes from the hardware backend** (`wubu_hosted_hw.c` on
  the hosted path); never synthesize plausible values.
- A publisher must not claim a capability the tree does not have — name the
  relay/ledger in `transport` only if it is really there.
