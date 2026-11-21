---
name: slermes-omarchy-integration
description: Slermes agent stack; native Hermes usage JSON for omarchy.
---
# slermes-omarchy agent-integration stack

## The contract
omarchy's shell agents panel shows a usage record per coding agent by reading the
agent's local state. Its `bin/omarchy-agent-usage-hermes` reads Hermes' state.db
and emits a JSON record. Slermes (the C11 Hermes port) reproduces that record
natively via `src/agent/omarchy_usage.c` so the panel sees Slermes exactly where
it sees Hermes. Both read the SAME schema (hermes_state_open.c):
`sessions(id,started_at,model,billing_provider,billing_base_url)`,
`session_model_usage(session_id,model,billing_provider,input/output_tokens,
cache_read/write_tokens)`, `messages(session_id,role,timestamp)`.

## The record (must match omarchy exactly)
Top-level: `schemaVersion:1, id:"hermes", name:"Hermes", ready, hasLocalStats,
hasPromptStats`. Stats block: `todayPrompts, todaySessions, todayTotalTokens,
todayTokensByModel {model: todayTotal}`, `recentDays` = last 7 LOCAL days oldest
first each `{"date":y-m-d,"messageCount":N}`, `totalPrompts, totalSessions,
activeDays, activeDates(sorted)`, and `modelUsage {model: {inputTokens,
outputTokens, cacheReadInputTokens, cacheCreationInputTokens}}` (NESTED).

## Ownership rule (the real semantics)
A session is count-as-ours only when **unrouted (no provider AND no url)** OR
billed by empty/`nous`. A recorded non-nous provider (deepseek, stepfun, ...)
routes it elsewhere and it is excluded from sessions AND prompts AND tokens.
Prompts need owner filtering too: `messages JOIN sessions` and keep only
sessions whose billing_provider is NULL/''/nous.

## Pitfalls (each cost a debug pass)
- The local date variable must NOT be named `day` -- it shadows the `day`
  typedef, so `day *d = ...` misparses. Name it `dstr`.
- omarchy ALWAYS scans the native `~/.hermes` regardless of HERMES_HOME, so an
  A/B test on your synthetic db must set `HOME` to an isolated fake home, not
  HERMES_HOME, or you'll compare against your real sessions.
- Trusted-token guard: negative/non-numeric/absurd(>=1e12) token counts = 0.
- `sqlite3_open_v2` with `file:path?mode=ro` URI for read-only scanning.

## Gate
`python3 scripts/test_omarchy_usage.py [path/to/omarchy]` builds a synthetic
state.db with a deepseek session that must be excluded, runs the C collector
AND omarchy's own python collector on the same db, asserts all stat fields
agree. Needs `gcc -lsqlite3` (sqlite3 is a core slermes dep).

## Where it lives
`src/agent/omarchy_usage.{c,h}`, `src/agent/test_omarchy_usage_main.c`,
`scripts/test_omarchy_usage.py`; registered in `build/objects.mk` after
`src/agent/account_usage.o`. Full slermes build is heavy (openssl/wayland); the
collector is standalone-verifiable with gcc alone.
