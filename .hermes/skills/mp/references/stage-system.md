# Stage system — multi-stage direction

## Grammar

```
STAGE {name}:
  ON:    - condition
  DO:    - action
  YIELD: - artifact
  UNTIL: - terminal condition
```

A direction is an ordered list of STAGE blocks, selected by project need.

## Inter-stage signals

- `CONTINUE` — next stage in same phase.
- `LOOP` — restart current phase.
- `BRANCH {id}` — move to named branch.
- `TERMINATE` — exit loop.

Each stage writes a state file under `sessions/` named `{stage-slug}.state`.
Constraints: stage name <=64 chars; direction <=1024 stages; body <=4096 tokens.
