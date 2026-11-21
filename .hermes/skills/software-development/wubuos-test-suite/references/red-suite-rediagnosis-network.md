# Red-Suite Re-Diagnosis: test_network 114/139 → 139/139 (2026-07-07)

## Lesson
The prestige update / Next Session Prompt labeled `test_network` 114/139 as a
**pre-existing environmental failure** ("root/netlink `Operation not permitted`").
That label was WRONG. The 25 failures were all one real code bug cascading
through the endpoint path — no root/netlink/permissions involved at all.

## The actual root cause (single bug, 25 failures)

`wubu_network_create_bridge()` and `wubu_network_create_host()` in
`src/runtime/wubu_network.c` call `profile_default()` which sets
`p->enabled = false`, then never re-set it to `true`. (Compare
`wubu_network_create()` at the same file, which DOES set `p->enabled = true`.)

`wubu_endpoint_connect()` early-returns `-1` when `!net->enabled`
(`if (!net->enabled) return -1;`). So every endpoint test failed at the very
first `wubu_endpoint_connect(...)` call, cascading:

- "network enabled by default" (the created bridge's `enabled==false`)
- ALL endpoint CRUD tests (connect → -1)
- inspect / disconnect / port-map / alias / list / stats (all depend on a
  successful connect)

## Fix (one line each, in `src/runtime/wubu_network.c`)
- In `wubu_network_create_bridge()`: after the `if (!gateway) strncpy(...)`
  line, add `p->enabled = true;` (a created bridge is enabled by default,
  matching `wubu_network_create`).
- In `wubu_network_create_host()`: after `p->created = true;`, add
  `p->enabled = true;`.

Result: 139/139 (was 114/139). QoS / WireGuard / Tailscale / CNI / string-helper
sections were already passing — the bug was isolated to the enable flag.

## How it was caught
Ran `make test_network 2>&1 | grep ❌` → all 25 FAILs were in `[Endpoint CRUD]` /
port-maps / stats. Read the test at line 226 (`mgr->networks[0].enabled == true`)
→ opened `wubu_network_create_bridge` → saw `enabled` left false → confirmed
`wubu_endpoint_connect` rejects disabled networks.

## Meta-lesson (applies to ALL red suites)
Do NOT trust a handoff's "environmental" verdict. Reproduce and read the FAIL
lines. The "root/netlink Operation not permitted" text belongs to a DIFFERENT,
genuinely-environmental path in the runtime (host netlink bridge creation, which
prints `[wubu_net] bridge ... host setup failed (non-fatal)` and is tolerated) —
it is NOT what failed these 25 tests.
