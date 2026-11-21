# MEGA-OS operator build — fail-closed external contract (verified 2026-07-25)

## The pattern
When you build the operator-side of a subsystem whose kernel/infra half is
owned by ANOTHER project (here: **wubuwizard** owns the kernel; WuBuOS
operators own desktop + agent + EDR), build the operator layer FIRST and
wire the external half as a **fail-closed stub** — never assert success
on a schema the external side hasn't signed off on.

## Operator-side build order that went green
1. `src/runtime/wubu_trace.{h,c}` — immutable, versioned, user-owned
   trace store; grepable plain-text mirror (the N9 rule: `file` →
   ASCII, not a journald blob).
2. `src/runtime/wubu_realm.{h,c}` — realm abstraction over the
   supervisor (8 personalities × 3 backends); `wubu_realm_set_kernel_schema()`
   + `wubu_realm_kernel_schema_ok()` — a mismatched kernel schema is
   **REFUSED** (fail-closed).
3. `src/runtime/wubu_selfimprove.{h,c}` — trace→eval→promotion loop:
   INDEPENDENT verifier fn pointer, human/overseer promotion gate,
   failure-weighted ingest (3×), user freeze.
4. `wubu_ns_publish_realm_trace()` in `wubu_ns_bridge.c` — publishes
   a realm's grepable trace to `/n/realms/<name>/trace` on the Styx9P bus.
5. Verify each phase with a REAL assertion (test_mega_os_loop in test_archd,
   test_realm_trace_publish in test_ns_bridge). Never "for later".

## Fail-closed external contract — the reusable lesson
- The operator sets `wubu_realm_set_kernel_schema(sup, EXPECTED_MAJOR)`
  up front. A realm whose kernel schema != expected **refuses to start**
  (`wubu_realm_kernel_schema_ok()` returns false → add/start returns -1).
- This means: if wubuwizard changes the `/n/trace` span schema without
  bumping the major, the operator layer STOPS — no silent telemetry gap,
  no phantom "green" that hides a contract break.
- Verify the fail-closed path in the SAME test that verifies the happy
  path: assert `kernel_schema_ok == true` on match AND `== false` on a
  deliberately-wrong major. A test that only checks the happy path is a
  false-green for a contract boundary.

## Research-grounded synthesis — cite, do NOT invent
The Mega-OS design pulls load-bearing facts from 2025–2026:
- EDR internals + HookChain (DEF CON 32, arxiv 2404.16856): ~88% of 26
  EDRs bypassed via the NTDLL-subsystem blind spot → the realm boundary
  (microVM/gVisor) MUST be the EDR, not an in-realm hookable agent.
- Agent observability (OpenTelemetry/OpenInference trace trees → eval
  dataset → CI regression): the proven flywheel. UC Berkeley 1600-trace
  study: multi-agent failure rates up to 86.7% → the self-improve loop
  must weight FAILURES (3×), not just successes.
- Recursive self-improvement (Anthropic "When AI builds itself"; CSA 2026
  report): loss-of-control via RSI is a top national-security risk → the
  verifier MUST be independent of the generator, with a human/overseer
  promotion gate.
- Scalable oversight (Anthropic 2025; arxiv 2504.18530): weak-to-strong,
  debate, embedded-agency / reward-tampering hazard.
Encode these as the *why* behind each architectural choice; never substitute
plausible-sounding invention for a cited source.

## Triple Devil's-Advocate — answered by architecture
- **DA-1 (privacy):** traces user-owned, on-device, deletable by
  default; never exfiltrated without explicit, revocable consent.
- **DA-2 (feasibility):** the realm boundary (microVM/gVisor) IS the
  EDR — observation outside the observed realm; wubuwizard kernel schema
  checked **fail-closed** (mismatch refused).
- **DA-3 (alignment):** the self-improvement loop has an INDEPENDENT
  verifier (never the self-improving agent), a human/overseer promotion
  gate, failure-weighted ingest (3×), and a user freeze switch.
The three DAs converge on ONE requirement: independence + user-ownership
+ a human (or independent overseer) in the room. Build that in and the
"borg-OS" is a defensible, privacy-respecting self-improving substrate;
skip it and it's a surveillance appliance that drifts.
