# Router-slot plumbing bugs (2026-08-08) — P44/P45/P46 transcripts

Three real bugs found while building the ROUTER SLOT (wubu_router.h/.c +
wubu_router_physics.c + the MoE engine wiring). Each was found via gdb or
ASan, not by reading.

## 1. Anonymous struct type-punning in wubu_hive.c (P44)

Header:
```c
struct { wubu_hive_block_t *block; size_t slot; } *free_entries;
```
wubu_hive.c free_entries_push:
```c
struct { wubu_hive_block_t *block; size_t slot; } *nf = realloc(...);
h->free_entries = nf;   // -Wincompatible-pointer-types
```
C11: every anonymous struct declaration is a DISTINCT type, even with
identical bodies. The compiler warned; the assignment was UB. Fix: tag it —
`struct wubu_hive_free_entry { ... };` in the header, use the tag in the .c.

## 2. Poincaré router native-dim heap overflow (adapter)

`wubu_poincare_router_init_random(centroids_out, seed)` writes
`N_EXPERTS * D_MODEL` floats (256 × 2048 = 524288) — regardless of the
probe dim. The adapter allocated `N_EXPERTS * probe_dim` (256 × 32) →
heap overflow → SIGSEGV in `wubu_poincare_router_init_random`.
Fix: allocate the FULL native space and zero-pad route inputs to D_MODEL.

## 3. MoE forward stack over-read (P45)

Probe passed `float x[DIM]` (32 floats) to `wubu_moe_forward` which reads
D_MODEL-wide tokens. Segfault inside the omp parallel region:
```
#0 wubu_moe_forward._omp_fn.0 at src/wubu_moe.c:609
#1 GOMP_parallel
```
gdb: `p w->ffn_gate_shexp` → valid heap ptr; `p x_s` → stack address;
`p k` → 968 (past the 32-float array). Fix: zero-pad input to D_MODEL.

## 4. Weightless MoE probe (P46) — the clip guard trap

To run `wubu_moe_forward` with only a router installed (no checkpoint):
- `n_experts_loaded = 1` — the clip guard is `n_experts_loaded > 0`, so
  setting 0 does NOT clip and the F32 expert path derefs NULL
  `ffn_gate_exps` (crash in the routed-expert task).
- Expert 0 must not clip → give it one real zeroed F32 blob with
  `ffn_*_exps_q_type = GGML_TYPE_F32`.
- Shared expert needs its three F32 buffers (gate/up/down).
- Link `wubu_moe.o` + `quantized_matmul.o` + `quantized_dot_generic.o` +
  `dequant_iq2_xxs.o` + `-fopenmp` (GOMP).

## Debugging path that worked
1. `make test_router` → "Segmentation fault (core dumped)".
2. Build a `-O0 -g` variant linking the same objects; run under gdb
   `-batch -ex run -ex bt` → crash frame in `wubu_moe_forward._omp_fn`.
3. First build had no line info in wubu_moe.o (Makefile CFLAGS) — rebuilt
   that ONE object with `-O0 -g` so `bt` showed `src/wubu_moe.c:609`.
4. `frame 0` + `p w->ffn_gate_shexp` / `p x_s` / `p k` disambiguated:
   weights valid, input pointer walked off → zero-pad the input.
5. ASan (`-fsanitize=address -fopenmp`) on the final gate → clean.
