---
name: wubu-revolver-pattern
description: Replace hardcoded constants with configurable revolvers.
version: 1.0
author: wubu
license: MIT
hermes:
  tags:
    - revolver
    - configuration
    - memory-safety
  related_skills:
    - gguf-revolver-block-sizes
---

# Revolver Pattern

## When to Use
Replace hardcoded constants (sizes, timeouts, counts) with runtime-configurable revolver values that can be overridden via environment variables, clamped to memory-safe ceilings.

## Static revolver pattern
```c
static wubu_revolver_t rev;
static int rev_ready = 0;
if (!rev_ready) {
    wubu_revolver_init(&rev, "name", DEFAULT, LIMIT, SCALE);
    /* NULL is acceptable; it prints the warning on stderr. */
    wubu_revolver_set_from_env(&rev, "ENV_VAR", NULL);
    rev_ready = 1;
}
TYPE get_name(void) { return (TYPE)wubu_revolver_get(&rev); }
```
Cache the result with the `rev_ready` guard: re-reading the environment on every
lookup hides the fact that a runtime bound is fixed for the life of the process.

## One-shot form: do NOT put it behind a single static slot

A convenience function like `wubu_revolver_get_static("name", default, limit,
"ENV_VAR")` looks harmless and is a trap when its state is ONE static
instance. A second caller with a different name silently RE-INITIALISES the
first caller's knob -- two subsystems sharing one slot, last writer wins, and
the first one's configured value vanishes with no error. Ship it only if every
caller passes the same name AND calls it at most once per process.

The surface that cannot surprise anyone:

```c
static wubu_revolver_t rev;
static int rev_ready = 0;
if (!rev_ready) {
    wubu_revolver_init(&rev, "name", DEFAULT, LIMIT, SCALE);
    wubu_revolver_set_from_env(&rev, "ENV_VAR", warn_cb_or_NULL);
    rev_ready = 1;
}
TYPE get_name(void) { return (TYPE)wubu_revolver_get(&rev); }
```

## Refusal semantics -- the clamp is not the interesting half

Environment variables are USER INPUT. An unbounded override turns configuration
into an allocation primitive: `WUBU_FS_FILES=999999999` becomes a request to size a
table with it. So the effective range is **[1, limit]**, and:

- **Refuse anything that is not a clean decimal integer.** Require full
  consumption by `strtol`. A typo like `6O4` yields partial parse 6; a unit
  suffix like `64K` yields 64. Both silently hand back a smaller limit than
  anyone asked for, which is the worst failure mode available here.
- **Refuse values below 1.** Zero can never be a bound.
- **Clamping is ALWAYS reported** through a warn callback. A silent fallback
  reads as acceptance, so the user believes their override took effect while
the code is running the ceiling.
- Lowering below the default is usually the POINT (shrinking buffers on bare
  metal), so the floor is 1, not the default.

### Arrays keep a compile-time extent
C requires compile-time sizes for arrays. Define `#define NAME_LIMIT <ceiling>`
at the revolver's limit, then `#define NAME NAME_LIMIT` as the alias existing
callers use. Callers that SIZE ARRAYS may use the alias; every BOUNDS CHECK must
use the runtime accessor. Mixing them lets a configuration change resize the
checks while the array stays put.

### A ceiling equal to the array's INLINE extent can only SHRINK
When the payload lives inline in the table entry (`data[8192]` inside the struct),
the ceiling is that array's size and no environment variable can raise it -- growing
means changing the storage layout, which is a design decision, not configuration.
Write the ceiling as the array extent and say so in a comment, so nobody "fixes"
it by raising the limit into an overflow.

### Convert EVERY bounds check, including copies in other modules
A module that owns a table often has a sibling (persistence, sync, a second
namespace) carrying its OWN copy of the same limit. Convert all of them in one
pass, or the sibling keeps admitting entries into a table that now believes it may
hold more.

### CPU-GPU Makefile split requires filter-out for stub objects
When a CPU-only tool target links `$(CORE_OBJ)` but the core includes a
`.o` whose real implementation calls into CUDA at runtime (e.g.
`wubu_dims_gpu.o` → `wubu_dims_sync_gpu()` → `cudaMemcpyToSymbol` with no
CUDA context), the CPU binary segfaults silently. Fix: in the CPU target,
`filter-out` the GPU object and substitute the stub:

```makefile
gen_text_cpu: ... $(filter-out src/wubu_dims_gpu.o,$(CORE_OBJ)) src/wubu_dims_gpu_stub.o ...
```

### More revolvers: allocation limits, not just scalar constants
Every allocation or loop bound that depends on model/data dimensions
should be revolver-controlled. KV cache sizing, thread counts, stack
buffer sizes, prefetch distance, and column strides are all candidates —
not just feature constants like block sizes or max context. When the
GPU/CPU fallback path takes a different allocation path, the bound must
come from the same revolver that the GPU build uses, or the two diverge
silently.

**Concrete allocation-limit revolvers:**

| Revolver name | Env var | Default | Ceiling | What it controls |
|---|---|---|---|---|
| `kv_cache_size` | `WUBU_MAX_CTX` | 2048 | 1,048,576 | GQA/MHA KV cache token slots; each slot = `n_layers * kv_heads * head_dim * 2 bytes` |
| `q8_k_alloc` | `WUBU_Q8K_BLOCKS` | `ceil(D_MODEL/256)` | `ceil(MAX_CTX/256)` | Per-token Q8_K activation buffer count in quantized matmul |
| `thread_count` | `WUBU_THREADS` | `omp_get_max_threads()` | 64 | OpenMP thread pool size for matmul/attention loops |
| `gpu_chunk` | `GPU_CHUNK` | 256 | 4096 | Token batch size for GPU strided-batched attention |
| `gpu_max_ctx` | `MAX_CTX` | 262144 | 1048576 | GPU KV cache max context |
| `persist_max_tokens` | `WUBU_PERSIST_MAX_TOKENS` | 4096 | 65536 | Max output tokens in persistent mode |

**Rule**: any `malloc`/`calloc` whose size is a function of `n_rows`,
`n_cols`, `max_ctx`, or model dimension MUST be driven by a revolver.
Hardcoding these for the CPU path while the GPU path uses a revolver
creates a silent divergence — the CPU path will OOM or hang at a
different threshold, masking the real allocation that needs fixing.

## Pitfalls

### Linking a new revolver source
When a tool target calls `wubu_revolver_get_static()` it needs
`src/wubu_revolver.o` on the link line. In wubuwizard, `gen_text_gpu`
links `$(CORE_OBJ)` but `wubu_revolver.o` is in `$(EXTRA_OBJ)`, not
`CORE_OBJ` — adding it to `CORE_OBJ` is the fix. A missing `.o` produces
`undefined reference` that looks like a missing symbol.
See also the code-quality skill's Makefile link debugging section.

### The dependency lands in every recipe that LINKS the .c, not just the product
Giving an existing `.c` a new call into the revolver breaks each test recipe
that compiles that `.c` directly -- six recipes in the WuBuOS tree linked
`hosted_styxfs.c`, so all six went red one at a time. Enumerate them BEFORE
patching: `grep -n '<module>\.c' mk/tests.mk` is the complete affected-target
list. Fixing them one failed build at a time leaves a different gate red on each
successive commit.

### Validate BEFORE consuming a slot or writing output
A guard placed after `&table[n++]` (or after the name has been copied) leaves a
partial record behind when it refuses. Refuse first, then claim the resource.

### Source files must be added to CORE_OBJ, not just compiled
Adding a new `.c` file to wubuwizard requires both a Makefile compilation
rule AND a `CORE_OBJ` entry. Without the `CORE_OBJ` entry the object is
never linked into `gen_text_gpu`/`gen_text_cpu`, producing `undefined
reference` at link time. With the rule but no `CORE_OBJ` entry, the object
is compiled but discarded.

### Skill YAML frontmatter
Description must be under 60 chars, ASCII only (no unicode dashes/arrows).
Must include a `name:` field. Missing metadata produces lint warnings.

### GQA_MAX_CTX backward compat
Keep a `#define GQA_MAX_CTX GQA_MAX_CTX_LIMIT` alias so callers compile.
Tests comparing `GQA_MAX_CTX >= GQA_MAX_CTX / 8` are scale-invariant.

## Q4_K_XL env vars
```bash
export WUBU_QK_K=512 WUBU_Q4_K_BLOCK_SIZE=272
```

## Test
`make test_revolver` and `make test_maya_stager`. A new revolver's gate must cover
the NEGATIVE cases specifically -- garbage input refused with the value unchanged,
clamping reported, and an absent variable leaving the value alone. A gate that only
checks the happy path proves nothing about the property that matters.