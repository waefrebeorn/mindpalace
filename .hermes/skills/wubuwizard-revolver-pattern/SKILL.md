---
name: wubuwizard-revolver-pattern
description: "Replace hardcoded limits with configurable revolvers."
version: 1.0.0
author: Hermes Agent
license: MIT
tags:
  - wubuwizard
  - revolver
  - resource-governance
  - configurable-limits
related_skills:
  - wubuwizard-inference-debugging
  - wubuwizard-weight-pipeline
---

# wubuwizard Revolver Pattern

Use when replacing any hardcoded value that controls resource usage:
timeouts, buffer sizes, slot counts, thread counts, context lengths,
memory ceilings, or similar limits.

## Why Revolver

Hardcoded values like `timeout 120`, `max_ctx 524288`, `n_slots 512`,
or `thread_handles[64]` cause OOM, hangs, and inflexible deployments.
A revolver wraps any resource parameter, allowing it to be set to
*whatever we want*, while clamping it to a hard memory-safe ceiling.
The total of all limits is the "declared memory budget" — the maximum
total memory the system will ever request.

## The Revolver Contract

Every revolver follows this shape:

```c
static wubu_revolver_t revolver_<name>;

void configure_revolver_<name>(void) {
    wubu_revolver_init(&revolver_<name>, "<name>",
                       <DEFAULT>, <LIMIT>, <SCALE>);
    wubu_revolver_set_from_env(&revolver_<name>, "<ENV_VAR>");
    wubu_revolver_register(&revolver_<name>);
}

/* Use */
int value = (int)wubu_revolver_get(&revolver_<name>);
```

Parameters:
- `name` — label for debugging/audit
- `DEFAULT` — value used when caller omits a setting
- `LIMIT` — hard memory-safe ceiling (current never exceeds this)
- `SCALE` — unit multiplier (1 for counts, 1024 for KB, 1024*1024 for MB)
- `ENV_VAR` — environment variable for runtime override

## Procedure: Revolverize a Hardcoded Value

### Step 1: Identify all hardcoded instances

Grep the codebase for the literal value. Common targets:
- Timeouts: `120`, `600`, `timeout`
- Buffer sizes: `512 * 1024`, `1024 * 1024`, `256 * 1024`
- Slot counts: `n_slots > 512`, `16`, `256`
- Thread arrays: `thread_handles[64]`
- Context limits: `GQA_MAX_CTX`, `524288`, `262144`

### Step 2: Define defaults and limits in the header

Add to the owning header (e.g. `include/wubu_stager.h`):

```c
#include "wubu_revolver.h"

#define WUBU_REVOLVER_<NAME>_ENV  "WUBU_<NAME>"
#define WUBU_<NAME>_DEFAULT  <default_value>
#define WUBU_<NAME>_LIMIT    <safe_ceiling>
```

### Step 3: Add configure function to the .c file

In the implementation file, add:

```c
static wubu_revolver_t revolver_<name>;
static int revolver_<name>_ready = 0;

void wubu_<module>_configure_revolver_<name>(void) {
    if (revolver_<name>_ready) return;
    revolver_<name>_ready = 1;
    wubu_revolver_init(&revolver_<name>, "<name>",
                       WUBU_<NAME>_DEFAULT, WUBU_<NAME>_LIMIT, <scale>);
    wubu_revolver_set_from_env(&revolver_<name>, WUBU_REVOLVER_<NAME>_ENV);
    wubu_revolver_register(&revolver_<name>);
}
```

Call this at the top of any create/init function.

### Step 4: Replace hardcoded values

Replace every hardcoded literal with the revolver getter:

```c
/* Before */
if (n_slots > 512) n_slots = 512;
size_t buf_bytes = 512 * 1024;
void* thread_handles[64];

/* After */
size_t slot_limit = wubu_revolver_get_limit(&revolver_stager_slots);
if ((size_t)n_slots > slot_limit) n_slots = (int)slot_limit;
size_t buf_kb = wubu_revolver_get(&revolver_stager_slot_kb);
size_t buf_bytes = buf_kb * 1024;
void** thread_handles = calloc(n_threads, sizeof(void*));
```

### Step 5: Dynamic allocation for fixed-size arrays

When a hardcoded array like `thread_handles[64]` is replaced,
allocate it dynamically in the create function:

```c
s->n_threads = (int)wubu_revolver_get(&revolver_max_threads);
s->thread_handles = (void**)calloc(s->n_threads, sizeof(void*));
```

And free it in destroy:
```c
free(s->thread_handles);
```

### Step 6: Update Makefile

1. Add `src/wubu_revolver.o` to `EXTRA_OBJ`
2. Add `src/wubu_revolver.o` to any test target that uses a revolversified module
3. Add a `test_revolver` target if one does not exist

### Step 7: Verify

```bash
make test_revolver   # unit tests for the revolver itself
make test_<module>   # verify the revolversified module still passes
```

## Revolver API Reference

See `include/wubu_revolver.h` and `src/wubu_revolver.c` for the full API.
Key functions:

- `wubu_revolver_init(r, name, default, limit, scale)` — initialize
- `wubu_revolver_set(r, requested)` — set current value (clamped to limit)
- `wubu_revolver_set_from_env(r, env_var)` — override from env var
- `wubu_revolver_get(r)` — get current (clamped) value
- `wubu_revolver_get_limit(r)` — get hard ceiling
- `wubu_revolver_register(r)` — add to global registry
- `wubu_revolver_declared_memory()` — sum of all registered limits
- `wubu_revolver_dump(out)` — print registry for debugging

Env var suffixes supported: `120`, `120s`, `512K`, `16M`, `2G`.
Parsed value is divided by `scale` then clamped to limit.

## Pitfalls

- **Makefile backslash corruption**: when editing `EXTRA_OBJ` or any
  multi-line Makefile rule, the `patch` tool doubles backslashes in line
  continuations (`\\` instead of `\`). Use `execute_code` Python with
  exact line-index surgery for Makefile edits, or verify the result with
  `grep '\\\\' Makefile` after patching.
- **`FILE` type requires `stdio.h`**: any revolver function that takes
  `FILE*` must include `<stdio.h>` in the header, not just the .c file.
  The header is included by test files that do not otherwise pull in stdio.
- **`free(s->thread_handles)` in destroy**: when converting a fixed-size
  array (`void* thread_handles[64]`) to a dynamic pointer (`void**
  thread_handles`), remember to add `free(s->thread_handles)` in the
  destroy function. Forgetting this leaks memory on every create/destroy
  cycle.
- **Revolver defaults should be conservative**: choose defaults that work
  on the smallest target hardware (RTX 4050 / 6GB VRAM). The limit can
  be higher for larger machines, but defaults must not OOM the minimum
  config.
- **Scale must match the unit**: if the parameter is "KB", set scale=1024
  so that `wubu_revolver_set_from_env` correctly parses `512K` → 512.
  Mismatched scale produces silent wrong values.
- **Registry overflow**: `WUBU_REVOLVER_MAX` is 32. If you need more
  revolvers than this, increase the constant in `wubu_revolver.c`.

## Existing Revolverified Modules

| Module | Revolver name | Default | Limit | Env var |
|--------|--------------|---------|-------|---------|
| wubu_stager | stager_slots | 128 | 1024 | WUBU_STAGER_SLOTS |
| wubu_stager | stager_slot_kb | 512 | 4096 | WUBU_STAGER_SLOT_KB |
| wubu_stager | max_threads | 4 | 64 | WUBU_MAX_THREADS |
| wubu_model | kv_ctx | 262144 | 524288 | WUBU_MAX_CTX |
| wubu_safekern | oom_ceiling | 524288 | 1048576 | WUBU_OOM_CEILING |

## Testing

Every revolversified module should have:
1. Its own existing test target (e.g. `test_maya_stager`)
2. The revolver unit tests (`test_revolver`) passing

Run both before committing:
```bash
make test_revolver && make test_<module>
```

Declared memory audit at startup:
```c
wubu_stager_configure_revolvers();
wubu_revolver_dump(stderr);
```
