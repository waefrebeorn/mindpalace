# Tailslayer DRAM-refresh hedge — compiler port (2026-08-13)

## What Tailslayer is (and isn't)
github.com/LaurieWired/tailslayer is a **memory-subsystem shim**, not a JIT
technique. DRAM refresh (tREFI ~7.8µs) periodically stalls a channel for
~150-750ns. Tailslayer eliminates this tail latency by:
1. Replicating data across independent DRAM channels (256-byte channel
   stride, `channel_offset=256`, `channel_bit=8`).
2. Issuing hedged concurrent reads from all replicas; the first to complete
   wins (channel refresh schedules are uncorrelated).
3. Core-pinned worker threads spinning on an atomic signal.

## The compiler-level "implicit for all code" form
You don't need thread replication to get most of the win in a JIT. Emit a
software prefetch (`prefetchnta`, `0F 18 /0`) immediately before EVERY memory
load the codegen produces. The prefetch primes the DRAM read so the actual
load overlaps refresh. Zero source changes → "all code magically."

## Encodings (all `0F 18 /0` = prefetchnta)
| form | bytes |
|------|-------|
| `prefetchnta [rax]`        | `0F 18 00` |
| `prefetchnta [rax+disp32]` | `0F 18 80 disp32` |
| `prefetchnta [rdi]`        | `0F 18 07` |
| `prefetchnta [rbp-disp32]` | `0F 18 85 disp32` |
| `prefetchnta [rip+disp32]` | `0F 18 05 disp32` |

All are 7-byte RIP-relative except the no-displacement `[rax]`/`[rdi]` (3
bytes). The RIP forms reuse the shared global patch formula
`disp32 = code_size + global_offset - patch_pos - 4`.

## The one real bug (patch_pos ordering)
`emit_prefetch_rip` records a global_patch at `patch_pos = code_size + 3`.
If you compute that `patch_pos` BEFORE emitting the 7-byte prefetch, it points
into the prefetch's middle → the following load's disp32 gets the wrong fixup
→ garbage result. **Emit the prefetch first, THEN compute `patch_pos`.**

## Where to wire it (holyc_codegen_expr.c)
Every load path needs the hedge, not just the obvious ones:
- global IDENT read — INLINE `48 8B 05` (~line 482), NOT via
  `emit_global_load_rax`. This is the easy-to-miss one.
- stack local IDENT read — `48 8B 85`
- sized member/element — `emit_sized_load_rax_off`
- array INDEX — base in rdi, `48 0F B6/B7 07` or `8B 07` / `48 8B 07`
- pointer DEREF — `48 8B 00`
- PRE/POST inc-dec + ASSIGN/compound use `emit_global_load_rax` /
  `emit_var_load` which call the prefetch internally once you add it there.

## Verification (permanent gate `make test_hedge`)
`hc_eval` returns only the VALUE — you can't scan `gen.code` for loads inside
FUNC_DECL bodies (separate exec buffer). Use a diagnostic counter
`wubu_hedge_prefetch_count` in the emitter, incremented per prefetch. The
probe (`tools/probe/hedge_verify.c`) asserts each load class bumps it >0 and
pure constants emit 0.

## Kernel half — DONE (2026-08-13): `src/kernel/wubu_dram_hedge.{c,h}`
Channel-replicated hedged memory, tested via `make test_dram_hedge` (288/288):
- allocates a pinned region (1 GB hugepage + mlock on host; page-allocator
  placement on metal), places N replicas at 256-byte channel strides
  (`channel_bit=8`) so each lands on a different DRAM channel with an
  uncorrelated refresh schedule.
- `wdh_put` writes every replica; `wdh_get` races them (first channel wins).
- Channel-stride addressing: `per_chunk = 256/elem_size`, `stride =
  num_replicas*256`, `offset(i) = (i/per_chunk)*stride + (i%per_chunk)*elem`,
  `replica[k] = region + k*256`. Selftest proves replicas exactly 256B apart
  and both hold identical bytes after one put.
- `wdh_probe_trefi`: clflush+reload DRAM-refresh periodicity probe (host
  x86-64 only, guarded by `WDH_HOST_PROBE`; kernel metal build gets a
  freestanding-safe stub returning 0).

**Build gotcha: do NOT add `wubu_dram_hedge.o` to `KERNEL_OBJS`** — that list
compiles `-ffreestanding -nostdlib -mcmodel=kernel`, and this module uses
libc (`mmap`/`mlock`/`malloc`). It is a HOSTED subsystem: wire it into
`mk/tests.mk` (`test_dram_hedge`) + the `test_critical_kernel` tier, NOT the
freestanding kernel object list. The probe's inline asm/rdtsc also must not
compile under `-ffreestanding` — the `WDH_HOST_PROBE` guard handles this.

## Worker-pool race — DONE (2026-08-13): `wdh_reader_*` (289/289)
The Tailslayer race-to-completion is now real, not in-call:
- `wdh_reader_create/read/destroy`: N pthreads, each pinned to a dedicated
  core (`sched_setaffinity`), spinning on a generation signal. Publishing a
  read index wakes them to load their OWN channel replica; the reader
  completes when every current-generation replica has loaded. All replicas
  hold identical bytes, so any slot is correct.
- Guarded by `WDH_READER_THREADS` (host builds with pthread); kernel-metal
  build gets a no-pthread fallback stub returning NULL/-1.
- `sched_setaffinity`/`CPU_ZERO` need `_GNU_SOURCE` before includes.
- `make test_dram_hedge` is now 289/289 (was 288/288).

### THE LOCK-FREE SPIN HANDSHAKE DEADLOCK (5 iterations to solve — reuse this)
Do NOT build the worker pool as a shared-claim CAS (`winner` slot that the
first worker to complete sets). It deadlocks/flakes intermittently on
sequential reads because a SLOW worker from a previous generation can
CAS-claim after the reader clears the slot but before it publishes the new
ticket, satisfying the reader's wait with a STALE value — or can block a
current worker's CAS forever. Every "claim with re-validate" variant (plain
store, CAS 0→gen, CAS-back release, generation-token, per-slot buffers)
still flaked under stress (0/40 would show 1-4 failures).

**The provably-correct design for SEQUENTIAL reads is a done-counter, NOT a
claim:** reader sets `cur_idx`, resets `done=0`, publishes `ticket++`; each
worker copies into its OWN `winner_val[k]` then does
`if (ticket==last) __sync_fetch_and_add(&done,1)`; reader spins until
`done >= n_workers`, then reads `winner_val[0]`. Per-worker buffers (no torn
copy) + the `ticket==last` guard on the increment (a stale worker can't
inflate done for the current gen) + fully-sequential reads = deadlock-free
and stale-free. Stress-tested 40/40 and 0/40, 0.37s, 289/289.

Honest remainder: the kernel-metal build needs the page allocator to
*guarantee* physical channel placement; the 256-B virtual stride is a strong
heuristic, not a hardware guarantee. Documented, not claimed.

Full port writeup + kernel design + 7-hop Kevin-Bacon trace:
repo `tools/research/notes_tailslayer.md` + `docs/compendium/02-architecture/wubu-dram-hedge.md`.

## /n/dram Styx-9P export — DONE (2026-08-13, 11/11)
`src/runtime/wubu_ns_dram.{c,h}` + `wubu_ns_dram_test.c`, gate
`make test_ns_dram` (wired into test_medium_other). Exposes the hedge over
the namespace, SAME pattern as /n/ec and /n/steaminput:
- `ns_mkdir`/`ns_write` from `wubu_ns_fs.c` wrap the REAL `wdh_*` API, no
  new daemon, no reimplementation.
- `/n/dram/{state,slots,replicas,elem,trefi,ctrl,status}`. `echo 3:42 >
  /n/dram/ctrl` stores 42 in slot 3 (all replicas).
- Test pattern (mirror `wubu_ns_ec_test.c`): set `g_ns_root` DIRECTLY to a
  tmpdir, link `wubu_ns_fs.o` + the module + the hedge — do NOT link
  `wubu_ns_bridge.o` (memory-constrained-linker rule). Expose the backing
  hedge via a getter (`wubu_ns_dram_hedge()`) so the test can read the
  value back through the real API, not just the file.
- The module header must `#include "wubu_dram_hedge.h"` to get
  `wdh_hedge_t*` in the getter.

## HONEST BENCHMARK FINDING (2026-08-13, `make bench_dram_hedge`)
`tools/bench_dram_hedge.c` compares cold clflush reads (UNHEDGED) vs the
reader-pool (HEDGED) on THIS WSL host: unhedged median ~320cyc / p99.9
~832, hedged median ~832-990cyc / p99.9 ~2240-2600. **The hedged worker
pool is SLOWER per-read here.** Reason: the two-thread spin handshake
(__sync barriers + cache-line bouncing on shared ticket/done/winner) costs
~500+ cycles per read, while the unhedged clflush path rarely hits a real
refresh stall in a microbenchmark (no real DRAM pressure). The tail-latency
win only shows on hardware where a channel is actually mid-refresh often.

LESSON — record honestly, do not claim a speedup a benchmark doesn't show:
- The COMPILER half (prefetchnta, ~1 cycle, no sync) is the zero-cost "for
  all code" win.
- The kernel worker-pool is the faithful but high-overhead form that pays
  off only on real DRAM-contended hardware (where the unhedged tail is
  ~150-750ns worse).
- If you benchmark a new latency-hiding mechanism and it's slower on your
  test host, say so in the notes/docs rather than hiding the number. The
  mechanism is not invalidated — its win is hardware-dependent.

## Repo research artifacts (persistent, not /tmp)
- `tools/research/notes_tailslayer.md` — the deep-dive + port strategy
- `tools/research/tailslayer_hedge.h` — C shim (init/insert/read/probe)
- `tools/research/trefi_probe.c` — DRAM refresh periodicity probe
- `tools/research/x86_speedup_cheatsheet.md` — Agner Fog + uops.info tables
- `tools/probe/hedge_verify.c` — the permanent compiler test gate
- `tools/bench_dram_hedge.c` — the benchmark (`make bench_dram_hedge`)
- `src/runtime/wubu_ns_dram.{c,h,test}` — the /n/dram 9P export
