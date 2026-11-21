# Stage System

## Grammar

```
STAGE {name}:
  ON:
    - condition
  DO:
    - action
  YIELD:
    - artifact
  UNTIL:
    - terminal condition
```

## Multi-stage direction

A direction is a list of STAGE blocks in order.

### Inter-stage signals

- `CONTINUE` — move to next stage in same phase.
- `LOOP` — restart current phase.
- `BRANCH {id}` — move to named branch.
- `TERMINATE` — exit loop.

### Example

```
STAGE overture:
  DO: emit intro
  YIELD: intent.md
  UNTIL: intent.md exists

STAGE indexing:
  DO: scan project
  YIELD: project-index.md
  UNTIL: project-index.md current

STAGE devils-advocate:
  DO: launch 4-phase loop
  UNTIL: loop complete
```

## Stage state files

Each stage writes a state file under `.hermes/mindpalace/sessions/`.
State file naming: `{stage-slug}.state`.

## Size constraints

- Stage name: max 64 chars.
- Direction: max 1024 stages.
- Single stage body: max 4096 tokens.
