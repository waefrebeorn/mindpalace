# wubuwizard C11 correctness — bug transcripts

Exact before→after diffs for pitfalls P1–P8, drawn from the gap-closing cycles
in the 2026-08-01 session (commits 78e06d3, d9944cb, b0f71f7 and prior).

## P1 — prefix-cache token truncation (D02, doc 010)
File: `src/wubu_prefix_cache.c`. The trie child index used `tok & 0xFF`,
colliding token 1 and 257. Hash the full 32-bit id instead.

```c
/* BEFORE (buggy) */
for (int i = 0; i < n_tokens; i++) {
    int tok = token_ids[i] & 0xFF;
    if (cache->nodes[node].children[tok] == -1) { ... }
    node = cache->nodes[node].children[tok];
}

/* AFTER (fixed) — add helper, use it in register/match/release */
static inline int tok_slot(int tok) {
    uint32_t x = (uint32_t)tok;
    x ^= x >> 16; x *= 0x45d9f3bU; x ^= x >> 16;
    return (int)(x & 0xFF);
}
```
Test upgraded to real ids (1000+, 5000+) — `test_prefix_reuse` then passed.

## P2 — delta-net chunk WY-form (E03, doc 008)
File: `src/wubu_delta_net.c`. `wubu_delta_net_chunk_prefill` used a WY form
that is only exact for C=1; for C>1 error ≈ 1.0. Replace with chunk-bounded
serial recurrence (bit-for-bit 0.00e+00 vs reference).

```c
/* AFTER (fixed) */
for (int t0 = 0; t0 < n; t0 += chunk) {
    int C = (t0 + chunk <= n) ? chunk : (n - t0);
    wubu_delta_net_recurrence(q + t0*d, k + t0*d, v + t0*d,
                              beta + t0, C, d, S);
}
```

## P3 — KV tier recursive alloc (A06, doc 002)
File: `src/wubu_kv_tier.c`. `wubu_kv_tier_alloc_block` called itself
recursively after demoting a victim. Fix: allocate the freed hot slot directly.

```c
/* AFTER (fixed) — iterative, no recursion */
t->hot_blocks[victim] = t->hot_blocks[t->hot_used - 1];
t->hot_used--;
wubu_kv_block_t *nb = hot_alloc(t);
if (nb) {
    nb->data = calloc(1, block_bytes);
    if (nb->data) { nb->block_bytes = block_bytes; nb->is_dirty = 1; return nb; }
    t->hot_used--;
}
```

## P4 — KV tier promote NULL data (A06, doc 002)
`wubu_kv_tier_write_block` did `memcpy(b, hot, sizeof(*b))` where `hot->data`
was NULL. Fix: copy file bytes into `b->data`, reset file fields.

```c
/* AFTER (fixed) */
if (!b->data) { b->data = calloc(1, b->block_bytes); if (!b->data) {...} }
memcpy(b->data, tmp, b->block_bytes); free(tmp);
b->tier = WUBU_KV_TIER_HOT; b->is_dirty = 1;
b->offset_in_file = 0; b->file_fd = -1; b->mmap_addr = NULL; b->mmap_size = 0;
```

## P5 — aligned_alloc → posix_memalign
Files: `src/wubu_model.c`, `src/wubu_model_safetensors_bridge.c`,
`src/wubu_kv_runtime.c`. `aligned_alloc(64, sz)` fails when `sz % 64 != 0`.
Replace with `posix_memalign(&ptr, 64, sz)`.

## P6 — Makefile shadowed test target (D01/D04, doc 007)
Two `test_continuous_batching:` rules existed; the later (at line ~554) won,
referencing `tools/test_kv_tier.c` (old block API). Fix: keep the version at
line ~276 that points at `tests/`, and ensure `.o` deps include
`src/wubu_continuous_batching.o` (not just `src/wubu_scheduler.o`):

```make
test_continuous_batching: tools/test_continuous_batching.c \
    src/wubu_scheduler.o src/wubu_continuous_batching.o $(CPU_OBJ)
	$(CC) $(CFLAGS) -I include -o $@ $^ -lm -fopenmp
	./$@
```

## P7 — size_t / duplicate typedef (D01/D04)
`include/wubu_continuous_batching.h` used `size_t` without `<stddef.h>` and
redefined `wubu_sched_item_t` (already in the .c). Fix: add `#include <stddef.h>`
and delete the .c's local `typedef struct {...} wubu_sched_item_t;`.

## P8 — static before definition (D01/D04)
`run_overlap()` called from `main()` above its `static` definition. Fix: add
forward decl `static int run_overlap(void);` near the top.

All fixes verified green via `make test_all` (=== ALL TESTS PASSED ===).
