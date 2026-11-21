# Slate

## Schema

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

## Required fields

- `slate_id` — unique id, human-friendly slug.
- `status` — current status of the slate.
- `loop_state` — current 4-phase loop position.
- `pass_count` — number of completed devils passes.

## Optional fields

- `branch` — associated branch if the slate is branch-scoped.
- `summary` — free-text digest written at the end of each pass.

## YAML round-trip

The slate is:
- written on LAYER_END,
- read on LOAD,
- updated on each pass.

Round-trip failure is reported as a hard error.

## Anti-patterns

- Re-writing the entire slate to update a single field.
- Treating `null` as missing.
- Using slate fields outside the schema, even if “convenient”.
- Materializing the empty string as a valid title.
