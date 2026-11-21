# Slate schema

Required top-level keys:

```
slate_id: string
created_at: ISO-8601
updated_at: ISO-8601
branch: string | null
status: active | archived | failed
stages_run: array[stage_slug]
max_passes: non-negative integer
pass_count: non-negative integer
loop_state: locate | against | for | decide | done
subject: string
summary: string | null
```

Required fields: `slate_id`, `status`, `loop_state`, `pass_count`.
Optional: `branch`, `summary`.

Round-trip: written on LAYER_END, read on LOAD, updated each pass. Failure is a
hard error. Anti-patterns: rewriting the whole slate to update one field;
treating `null` as missing; fields outside the schema; empty string as title.

The slate is "what is being worked on RIGHT NOW" — a specific step, not a vibe.
