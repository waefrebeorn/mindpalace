---
name: wubuwizard-c11-correctness
description: C11 pitfalls + Triple-DA oracles for wubuwizard engine work.
---

# wubuwizard C11 correctness — recurring traps + verification

Companion to `wubuwizard-c11-engineering` (wiring) and `research-loop` (gaps).
Memory holds the standing rules (Triple-DA, opaque structs, no god headers,
-ffinite-math-only guards). This skill is the C11 trap + oracle list.
CV/geometry numerics (DLT, RQ, pose, distortion identifiability) live in
`references/geometric-vision-pitfalls.md`.

## Opaque handles with external adapters

- **Never bind an opaque handle's vtable/adapter to a stack compound literal**
  (`&(const T){...}`) — the address dangles the moment the enclosing function
  returns, and the first dispatch through the saved handle is use-after-free.
  Keep adapters as file-scope `static const` structs, or resolve them from a
  registry by key at every dispatch instead of storing the pointer in the
  handle (a key lookup cannot dangle across close/re-registration; a saved
  pointer can).
- **When an API is an opaque handle meant to accept external adapters or
  backends, expose `handle_new(kind, backend, &out)` and `backend(c)`
  helpers.** Third-party adapter writers cannot see the struct fields of an
  opaque type, so the module must provide the way to build the handle and to
  recover the private state — keeping the handle opaque even to its own
  backend. A module that builds a hidden vtable from a parameter also typically
  means it should resolve from a registry by that parameter's key.

## Trigger
- Implementing a wubuwizard `src/wubu_*.c` module or flipping a
  `research/INDEX.md` `open` → `wired` gap.
- Reviewing KV-cache / prefix-cache / paged-KV / trie / scheduler code.
- Wiring a new test into the Makefile (link errors, shadowed targets).
- Adding a CV / geometry / numeric module (`wubu_cv`, `wubu_flow`, `wubu_calib`)
  or any code whose output is a number rather than a flag.

## Numeric modules: prove the answer, not the shape

- Assert **recovery of a known answer** (exact shift, exact pose, exact K), not
  `isfinite` / `!= 0`. Print the measured error so the number is auditable.
- Never ship a function whose name promises more than the math delivers. An
  integer-returning centroid is "centroid refinement", not sub-pixel; rename the
  claim (header + docs) rather than inflate it.
- Guard against **false greens**: a loop over a negative count passes vacuously,
  and a fixture freed by an earlier test block silently yields zero samples.
  Assert the count first, then iterate; rebuild fixtures per block.
- Recompute the expected value by hand before "fixing" code that failed a test —
  the test is as likely to be wrong as the implementation.
- Recipes (flow ladder, DLT denormalisation, RQ orientation, Rodrigues updates,
  marker decode) live in `references/cv-geometry-reimplementation.md`.

## HolyD MIR codegen debugging (wubunos gauntlet)

When a gcc_torture/gauntlet test fails on x86-64 but passes on riscv, the MIR is
usually right and the bug is a codegen path that degrades silently. Diagnose in
this order — each step is cheap and localizes fast:

1. **Minimize with `gauntlet_runner --dump-asm <target> "$SRC"`.** Pipe a
   multi-line source via `SRC=$(cat /tmp/t.c)`. Bisect the C program down to
   the failing primitive (drop struct members, replace pointer chains with
   direct access) BEFORE reading compiler code. Two-minute bisects beat
   twenty-minute code reads.
2. **`WUBU_DEBUG_MIR_BEFORE=1` / `WUBU_DEBUG_MIR_AFTER=1`** dump the MIR
   around `wubu_mir_optimize`. If BEFORE is right and AFTER is wrong, the
   optimizer pass is at fault; if BEFORE is already wrong, it's codegen.
   NOTE: a truncated AFTER dump can be a stdio artifact — always check the
   full log, not a `head` window.
3. **Silent-degradation signature:** a store to `mem[v0]` (the return
   register) means an address-computation function returned 0 and the
   caller fell back to a default vr. Grep the emitted MIR for `mov vN = v0`
   followed by `store mem[vN]` — that is the smoking gun for a failed
   `mir_address_of` / `mir_lvalue_addr`.
4. **Address helpers:** `mir_address_of()` (value context) and
   `mir_lvalue_addr()` (store context) are SEPARATE functions with
   overlapping but NOT identical case coverage. A node kind handled in one
   and missing in the other (e.g. ARROW) compiles reads but silently breaks
   stores — or vice versa. When fixing one, audit the other.
5. **Struct member metadata** (`mir_struct_t.member_is_ptr` etc.) is
   populated at THREE registration sites: file-scope named types in
   `hd_build_mir` (the parser's named_types table), the `HD_AST_STRUCT_DECL`
   statement handler, and the anonymous-struct fallback inside
   `HD_AST_VAR_DECL`. Adding a member field means updating all three, or
   file-scope structs (the common case) silently miss it.
6. **Static-local initializers:** the scalar static path and the
   brace-init (array/struct) path are different branches. A static local
   with `= {…}` must take the brace path WITH the init-once guard wrapped
   around the per-element stores; falling into the scalar path evaluates
   the brace list as one expression and stores 0.

Pitfall: pointer MEMBER indexing (`s.sp[2]`, `ps->sp[2]`) — the member's
cell holds a pointer VALUE; `mir_address_of` returns the member's ADDRESS.
The INDEX codegen must LOAD the pointer first when the base is a
DOT/MEMBER/ARROW naming a pointer-typed member. Without the load, the
index offsets the member's own slot (reading a sibling member instead).

## Pitfalls (each has burned us)

### P1 — Token-ID truncation in trie/lookup keys
`int tok = token_ids[i] & 0xFF;` collides token 1 and 257 (and N, N+256...).
For a 128K vocab this **silently returns the WRONG prefix KV** — a correctness
disaster, not a perf issue. Fix: spread the full 32-bit id with a multiplicative
hash before indexing the 256-wide child array:
```c
static inline int tok_slot(int tok) {
    uint32_t x = (uint32_t)tok;
    x ^= x >> 16; x *= 0x45d9f3bU; x ^= x >> 16;
    return (int)(x & 0xFF);
}
```
Verify: test with REAL token ids (1000+, 5000+), assert hit/miss/partial-match
correct AND `hash(prefixA) != hash(prefixB)` for different prompts.

### P2 — Chunked-prefill WY-form is only correct for C=1
The delta-net / linear-attn WY representation
`S = S*(I - Y W^T) + Y V^T` drops the cross-token right-multiplication for
chunk size C>1 (observed error ≈ 1.0). Fix: apply the EXACT serial recurrence
per token, just bounded in chunks of `chunk` to cap working set:
```c
for (int t0 = 0; t0 < n; t0 += chunk)
    wubu_delta_net_recurrence(q+t0*d, k+t0*d, v+t0*d, beta+t0, C, d, S);
```
Verify: `maxdiff(chunk_prefill_state, serial_recurrence_state) < 1e-4f`
(target 0.00e+00).

### P3 — Recursive alloc inside eviction/demote loops
`return wubu_kv_tier_alloc_block(...)` from inside the demote branch re-enters
and can recurse until stack overflow or double-free. Fix: after demoting the
victim, allocate the freed hot slot directly (iterative, no recursion).

### P4 — NULL data on promote cold/warm → hot
When promoting a block, `memcpy(b, hot, sizeof(*b))` copies a freshly calloc'd
`hot` whose `data` is NULL into the caller's block; the next
`memcpy(b->data + off, ...)` segfaults. Fix: allocate `b->data` on promote (or
copy the file bytes into `b->data`), never swap the whole struct. Reset
`offset_in_file/file_fd/mmap_*` after promotion.

### P5 — `aligned_alloc` vs `posix_memalign`
`aligned_alloc(64, sz)` requires `sz % 64 == 0`. KV-cache byte sizes usually
aren't. Use `posix_memalign(&ptr, 64, sz)` (no size-alignment constraint).
Same for `wubu_kv_runtime.c` and the bridge KV alloc.

### P6 — Makefile duplicate test targets shadow each other
Two `test_X:` rules in the Makefile → the LAST one wins; the earlier (often
correct) one is dead. `make test_X` builds the shadowed target. Always grep the
Makefile for the target name before adding; if a duplicate exists, extend the
existing rule or delete the stale one. Also ensure the test's `.o` deps include
every module it calls (e.g. a `wubu_cont_batch_overlap` test needs
`src/wubu_continuous_batching.o`, not just `src/wubu_scheduler.o`).

### P7 — `size_t` / duplicate typedef in headers
A header using `size_t` without `<stddef.h>` fails under `-Wall -Wextra`.
Also: defining a `typedef struct {...} foo_t;` in BOTH the .h and the .c causes
`conflicting types`. The .c must NOT redefine a type already in its header.

### P8 — Statics used before definition
A `static int helper(void)` called from `main()` above its definition, with no
forward decl, is implicitly declared non-static, then the later static definition
conflicts (`static declaration follows non-static`). Fix: add a forward
declaration at the top of the file.

### P9 — Cholesky / LinSolve backward-substitution direction (CRITICAL, burned pass 44)
Solving `L^T * alpha = tmp` (back-substitution of a Cholesky factor) MUST iterate
`i` in DESCENDING order. The equation for row `i` is
`L[i][i]*alpha[i] + Σ_{k>i} L[k][i]*alpha[k] = tmp[i]`, so it reads `alpha[k]` for
`k>i` — those MUST already be solved. Iterating `i=0..n-1` (ascending) reads
UNCOMPUTED values → corrupt `alpha` → GP predictions are completely wrong even
though variance is ~0 (the tell-tale sign: pred=45.46 at a training point where
true=25.0, var≈0).
```c
/* WRONG: ascending reads alpha[k] (k>i) before it's computed */
for (int i = 0; i < n; i++) {
    double s = tmp[i];
    for (int k = i + 1; k < n; k++) s -= L[k][i] * alpha[k];
    alpha[i] = s / L[i][i];
}
/* RIGHT: descending so alpha[k] for k>i is already solved */
for (int i = n - 1; i >= 0; i--) {
    double s = tmp[i];
    for (int k = i + 1; k < n; k++) s -= L[k][i] * alpha[k];
    alpha[i] = s / L[i][i];
}
```
Verify: predict at an OBSERVED training point → `mean ≈ y` (GP interpolates).
If off by >1e-3 with var≈0, the backsolve direction is wrong. Applies to ANY
Cholesky/LDL^T/LU backward solve, not just GP.

### P10 — Header forward-include miss (unknown type / undeclared macro)
A header that references a struct/enum/macro defined in ANOTHER header MUST
`#include` it. Relying on the includer's include-order is a latent bug:
`wubu_bo.h` used `wubu_gp_t` + `WUBU_GP_MAX_DIM` (defined in `wubu_gp.h`) but
didn't include it → `unknown type name 'wubu_gp_t'` / `'WUBU_GP_MAX_DIM'
undeclared`. Fix: add `#include "wubu_gp.h"` (and any other needed headers) at
the TOP of `wubu_bo.h`. Rule: every header is self-contained — it includes every
header whose symbols it names. Don't depend on transitive includes.

### P11 — `static` helper same name across TUs, called from a third (link error)
`static` = internal linkage: a `static double rng_f(unsigned*)` in `wubu_bandit.c`
and another in `wubu_symreg.c` coexist fine (each invisible outside its own TU).
But a THIRD TU (e.g. `test_ff.c`) that calls `rng_f(&seed)` fails with
`undefined reference to rng_f` — the static is not visible there. Fix: never call
a module-private `static` from a test or another module; either expose a public
`wubu_X_rand` helper or use a local RNG inside the test. (Contrast with P8: that's
visibility issue.)) 

### P12 — `min(1, a/b)` reject-probability trap (speculative decoding / rejection sampling)
Rejection sampling must accept a draft token with probability `min(1, p_target/q_draft)`.
The naive ternary `float accept_p = (pt < pq) ? 1.0f : (pt / pq);` is WRONG: when
`pt == 0` (target gives ZERO prob to the draft token), `pt < pq` is TRUE so it returns
`1.0` — ACCEPTING an IMPOSSIBLE token. That breaks speculative decoding's core
guarantee (output distribution must equal the target's). Correct form computes the
ratio first, then clamps:
```c
float ratio = pt / pq;
float accept_p = (ratio > 1.0f) ? 1.0f : ratio;   /* true min(1, p/q) */
```
Verify: set target prob = 0 on the draft token → `n_accepted == 0` (guaranteed
reject). Applies to ANY `min(1, a/b)` where `a` may be 0: use ratio+clamp, never a
`a < b ? 1 : a/b` ternary. Burned in wubu_specdec.c (HH axis, 2026-08-01): a
target prob of 0 on the draft token produced accept_p=1.0 and silently accepted
wrong tokens until fixed.

### P13 — Large struct/array on the stack → segfault under production CFLAGS
A struct embedding huge fixed-size arrays, instantiated BY VALUE on the stack
(in a test `main` or any function), overflows the thread stack and segfaults at
runtime. In wubu_specdec.h, `WUBU_SPECDEC_VOCAB = 32000` made `wubu_specdec_t`
hold `draft_probs[16][32000]` + `target_probs[16][32000]` ≈ 4 MB of locals; a test
declaring `wubu_specdec_t sd;` segfaulted under the engine's production flags
(`-O3 -march=native -ffast-math -fopenmp`). Root cause: a ~4 MB stack frame
exceeds the (OMP-reduced) thread stack. Fix: shrink the constant (VOCAB 1024 →
struct ~128 KB) or `malloc` the big arrays. Rule: cap per-call stack use well under
~256 KB; never embed enormous fixed arrays in a by-value struct. This is the
by-value-struct variant of the OMP-parallel-local-array trap in
`wubuwizard-c11-engineering` — both mean: keep stack frames small.

### P14 — EMA / running-average threshold tests need enough samples
A test asserted a Medusa draft-head's EMA acceptance dropped below 0.5 after ONE
`wubu_medusa_update(&m, 3, 1, 10)` (10% acceptance, α=0.1). But
`EMA = 0.9*init + 0.1*rate`; from init 0.8 with rate 0.1 that's 0.73 — still > 0.5,
so the head was NOT dropped and the assertion failed. It took ~20 low updates to
push EMA below 0.5. Lesson: when a test asserts a running statistic crosses a
threshold, compute the convergence `EMA_k = (1-α)^k*init + α*Σ` — one update barely
moves it. Either drive enough updates or assert the DIRECTION (EMA decreased)
rather than the threshold. Same class as the symreg coef-range and
"verifier correctness beats test-passing" traps.

### P15 — Per-token write stride must match the allocated token buffer dim
A module that writes N tokens into a caller-allocated buffer has TWO dims in
play: the token buffer's dimension (what `malloc` sized) and the encoder's
per-token stride. If they diverge, the writes walk off the buffer. Real bug
(moondream_cli, 2026-08-02): `wubu_md3_encode` computed
`tok_dim = img->channels * 2 * 2` (= 12 for RGB) and wrote
`tokens[tid * tok_dim + d]`, but `wubu_md3_infer` allocated
`max_tokens * 4` floats (the model dim is 4 — MoE + detect both read 4 per
token). 192 tokens × stride 12 = writes up to `191*12+3` → heap overflow.
The plain `-O2` build ran and the unit test PASSED (small stack arrays masked
it); only the CLI with a real 32×24 image crashed with
`malloc(): corrupted top size`. Fix: `const int tok_dim = 4;` — the stride is
the MODEL dim, not the input-channel-derived patch dim. General rule: define
ONE token-dim constant, size the buffer AND the encode stride from it, and
ASan-verify the CLI/runner path (host tests with tiny arrays miss OOB writes
that real-sized inputs hit).

### P16 — `fscanf` PPM header parsing: type byte vs unused-partition check
When parsing MBR partition entries in tests, remember the layout: byte 0 =
boot flag (0x80), byte 4 = partition TYPE (0x0B = FAT32), bytes 8-11 = LBA
start (LE). A test that sets only the boot flag and expects the entry to be
"used" fails because the reader checks `type == 0` → "unused". The MBR offset
is `446 + part_no * 16` — partition 1 is at 446, NOT 446+16 (that's partition
2). Same class as the FAT BPB test: `root_entries = bpb[17] | bpb[18]<<8`
with 32 entries means `bpb[17]=0x20, bpb[18]=0x00` — the 32 goes in the LOW
byte, not the high.

### P17 — POSIX functions under `-std=c11`: implicit declaration returns int garbage (BURNED TWICE, 2026-08-02)
`strdup` and `getline` are POSIX, NOT C11. Under `-std=c11` without
`_POSIX_C_SOURCE` they are IMPLICITLY declared (`int strdup(...)`), the call
returns a truncated int, and the caller treats it as a pointer → NULL/garbage
→ SEGV in `strlen`/`memcpy` at the WRONG line. Hit twice this session:
- `wubu_tokenizer_hf.c` used `strdup` for every BPE symbol — every `syms[i]`
  was garbage; ASan showed `SEGV in internal_strlen` deep in encode.
- `wubu_save.c` used `strdup` for tensor names — same crash in the writer.
FIX (the no-third-party doctrine): provide a local implementation, never
rely on the implicit decl:
```c
static char *local_strdup(const char *s) {
    if (!s) return NULL;
    size_t n = strlen(s) + 1;
    char *out = malloc(n);
    if (!out) return NULL;
    memcpy(out, s, n);
    return out;
}
```
For `getline`: `#define _POSIX_C_SOURCE 200809L` as the FIRST line of the .c,
before EVERY include (defining it after a system header is a no-op → the
implicit-decl bug returns; `wubu_tokenc.c` tokenized a 640MB corpus to 30KB
of garbage before this fix). Rule: any libc function not in C11
(strdup/getline/strndup/strtok_r/realpath...) needs EITHER a local
implementation OR the feature macro at the very top.

Same family, two more macros that bite tests: **`O_CLOEXEC` is not exposed by
strict `-std=c11`** — `open(path, O_CREAT|O_RDWR|O_CLOEXEC, 0600)` fails with
`'O_CLOEXEC' undeclared`. Open plainly, then `(void)fcntl(fd, F_SETFD,
FD_CLOEXEC);`. And **`usleep` needs `_DEFAULT_SOURCE`**; use `nanosleep` with
`#define _POSIX_C_SOURCE 200809L` as the first line instead. Both produce only
a warning at first (`implicit declaration of function 'nanosleep'`) and then a
truncated argument at runtime — compile with `-Werror=implicit-function-declaration`
in new test targets so the warning cannot pass silently.

### P18 — `M_PI` undeclared under strict C11
`M_PI` is POSIX, not C11. `-std=c11` + `-Wall` → `'M_PI' undeclared`. Fix:
`acosf(-1.0f)` (or define your own `#define WUBU_PI 3.141592653589793f`).
**The GNU-free doctrine (2026-08-04 — the user's standing directive):** we keep
having to add `_GNU_SOURCE` for M_PI/strdup — a GNU feature-test macro that
imports a dependency surface (and its license framing) we don't want; the
endgame is our own compiler (wubuos HolyC, ring-0) where WE define the feature
surface. The permanent fix is `include/wubu_std.h` (M_PI/M_PI_2/M_E as plain
constants + `wubu_strdup`, 4 lines) — NO feature macro needed. See the
"GNU-free C11 surface" section in `wubuwizard-c11-engineering` for the full
doctrine: wubu_std.h for M_PI/strdup; `_GNU_SOURCE` ONLY for kernel APIs
(CPU_ZERO/CLONE_NEW*/FTW_DEPTH/DT_DIR/st_atime — scheduling features, kept
localized with a comment); strict `-std=c11` build as the gate; cargo-cult
`_GNU_SOURCE` at file top with no gated symbol is dead weight — strip it.

### P29 — Grow/realloc invalidates the captured parent pointer (heap-use-after-free, 2026-08-04)
A grow function that (a) captures `parent = &g->cells[id]`, then (b) REALLOCS
the cell array to make room for a daughter, then (c) writes through `parent` →
the realloc FREED the old array, so `parent` dangles → heap-use-after-free.
ASan caught it in `wubu_gravity_grow`: `d1->r = clamp_r(g, d1->r + dr*0.5)`
read the freed slot. Fix (the general pattern): SNAPSHOT the fields you need
(`double pr = parent->r; double ptheta = parent->theta;`) BEFORE the realloc,
then RE-DERIVE the pointer from the NEW array after it
(`wubu_gravity_cell_t *d1 = &g->cells[cell_id];`). Rule: after any
`realloc`/`free` of a container, every pointer into the old container is dead —
re-derive by index, never reuse the old pointer. Same trap class as P28's
struct-copy aliasing (both are "two names for one region"); the realloc variant
is caught by ASan immediately, the struct-copy variant by a teardown double-free.

### P30 — Freeing a struct-FIELD address as if it were a heap wrapper (double-free)
When a container slot embeds a sub-struct by value
(`orbit_slot_t { wubu_orbit_addr_t addr; }`), calling the heap-wrapper free
(`wubu_orbits_addr_free(&slot->addr)` which does `free(a)` on the pointer) is
`free(&slot->addr)` — freeing INSIDE the slot object, then `free(slot)`
double-frees the slot. ASan: "attempting double-free" with the first free in
`wubu_orbits_addr_free`. Fix: the slot's sub-struct is a FIELD, not a heap
object — free ONLY the arrays it owns (`slot_addr_free(&slot->addr) { free(a->r);
free(a->theta); }`), never the field address itself. Rule: know whether a struct
is heap-owned (free the whole thing) or field-owned (free only its internal
pointers); a single `free()` on a field address is always wrong. Also: when
TRANSFERRING a heap address into a slot (`s->addr.r = a->r; s->addr.theta =
a->theta; s->addr.n_levels = a->n_levels; free(a);`) — move the arrays, not the
wrapper struct (a struct copy `s->addr = *a` aliases the arrays with a second
owner).

### P31 — `const char *` struct member written via strncpy (SEGV in strncpy-evex)
A writer struct declared `const char *name;` (a POINTER) but the caller did
`strncpy(out[i].name, e->name, sizeof(out[i].name)-1)` — writing through a NULL
pointer → immediate SEGV at `__strncpy_evex` (gdb: frame in strncpy, not your
code). Fix: check the struct member's type — if `name` is a `const char *`,
ASSIGN the pointer to a stable owner (`out[i].name = e->name;` — the catalog
stays open until after the write), never strncpy into it. General rule: before
writing into a struct member, verify it's an ARRAY (`char name[192]`) not a
POINTER (`const char *name`); the two look identical in a header skim and
compile cleanly, then crash at runtime.

### P32 — Bulk-rewrite scripts MUST refuse to empty a file (the n=0 loop bug, 2026-08-04)
A Python bulk-edit script that rewrites every matching .c file had
`out, i, n = [], len(lines), 0` — `n = 0` instead of `n = len(lines)`, so the
rewrite loop never ran and EVERY file was written EMPTY (20+ files; `git diff`
showed `e69de29` = empty blob). The build failed with a cascade of `undefined
reference` (each file's functions vanished). Damage control: restore every
emptied file from git:
```bash
git status --short | awk '$1=="M"{print $2}' | while read f; do
  if [ ! -s "$f" ]; then git checkout -- "$f"; fi
done
```
PREVENTION (the permanent rule): any script that rewrites many files must (1)
assert the output is non-empty when the input was non-empty (`if not new.strip()
and src.strip(): refuse`), (2) after the run verify no tracked file is 0 bytes,
(3) build + test BEFORE committing. Also: when stripping `#ifndef X / #define X
/ #endif` guard pairs, handle the NON-adjacent case (blank line / comment
between them) or you leave a dangling `#endif` that breaks the next compile —
grep for a leading `#endif` after the strip.

### P21 — Fresh block skipfield init: calloc zeroes skip, but foreach treats skip=0 as "live"
A new `wubu_hive_block_t` is `calloc`'d, which zeroes `skip[]` to all 0s. The
`wubu_hive_foreach` iterator skips entries where `skip[s] == 1` (erased) and
visits everything else — so a fresh 64-slot block with 5 live entries reports
64 "live" to the caller. The DA test caught this: 123 visited for 65 live.
Fix: `memset(blk->skip, 1, BLOCK_CAP)` in `block_alloc()` so fresh blocks start
with ALL slots marked erased; `wubu_hive_insert` sets `skip[s] = 0` for the
slot it writes. Verify: `wubu_hive_live()` matches the count returned by
`wubu_hive_foreach` after inserting N entries into a fresh block.

### P22 — AGI model disclosure: the README must state plainly that this is an AGI project
When publishing an AGI model on HuggingFace, the README must contain a
mandatory disclosure section that states: (1) it is an AI, (2) it is being
built to be general, (3) it is human-centric (the human always keeps the
mouse/keyboard), (4) it is accountable (prestige ledger, no black boxes),
(5) it is not ready for autonomy. This is not optional — the user's
directive is "disclose that you are an AGI." The disclosure goes in the
model card README on HF AND in the local `docs/wubu-model-card.md`.

### P23 — HuggingFace token hygiene: never commit tokens to git
Both read and write tokens must be stored in `~/.cache/huggingface/token`
(0600) and `~/.hermes/profiles/mind-palace/secrets/hf.env` (0600), NEVER
in the repo or any committed file. The `secrets/hf.env` is gitignored.
Verify by checking that `git log --all --oneline` never shows a commit
containing a token string.

### P20 — cuBLAS SGEMM orientation for row-major [out,in] weights (the transposed-weight trap)
The engine's CPU matmul is `out[s,o] = Σ_i w[o,i]·x[s,i]` where w is stored
row-major `w[o*in + i]` ([out,in]) — that is `out = x @ w^T`, NOT `x @ w`.
A cuBLAS call `cublasSgemm(OP_N, OP_N, N, M, K, ...)` computes `x @ w`
(no transpose) and silently produces wrong values — the training loss
DIVERGED instead of converging, and a naive correctness check passed the
wrong orientation. Fix:
```c
cublasSgemm(g_cublas, CUBLAS_OP_T, CUBLAS_OP_N, N, M, K,
            &alpha, d_w, K, d_x, K, &beta, d_y, N);
```
(OP_T on the weight, lda=K — the weight is transposed by cuBLAS). ALWAYS
verify a new GPU matmul path against the CPU loop numerically
(max_diff < 1e-4) BEFORE wiring it into training; orientation bugs are
silent until the loss diverges.

### P24 — Buffer aliasing in a forward pass: reuse = latent corruption (5 bugs in one forward, 2026-08-03)
A forward pass that REUSES buffers (scratch aliasing) is a class of silent
corruption. The backprop parity test (recording forward vs released forward)
caught FIVE separate aliasing bugs in `wubu.c` in one session:
1. **In-place matmul**: `matmul(b->gate, g_proj, b->gate)` — the output row
   overwrites the input row while the inner loop is still reading it; every
   output element i uses the clobbered input for indices < i. Fix: NEVER let a
   matmul's output alias its input; give the gate its own `g_out` buffer.
2. **Checkpoint aliased with a hot scratch**: `checkpoint = b->x2` — but the
   o_proj matmul writes `b->x2` EVERY layer, so the residual-selector
   checkpoint was garbage from layer 1 on. Fix: a dedicated `b->checkpoint`
   (the buffer existed; the released path just didn't use it).
3. **Unzeroed scratch accumulation**: the attention `osum` scratch (`b->x2`)
   was never zeroed per position, so every head's output included the previous
   layer's stale o_proj output. Fix: `memset` the scratch at the top of each
   position.
4. **Buffer sized below the tensor width** → OOB read: `b->ffn_gate` was
   allocated `[seq, FF]` but the gate_up tensor is `[seq, 2*FF]`; the SwiGLU
   read the up half out of bounds (fresh calloc pages masked it as zeros, so
   the FFN up-branch was silently DEAD). Fix: allocate the full tensor width.
5. **Row stride ≠ tensor width**: the SwiGLU loop indexed `ffn_gate + s*FF`
   when the rows are `2*FF` wide — the gate/up halves were scrambled (g[d+FF]
   landed in the NEXT row's gate half). Fix: stride = the ACTUAL row width.
Rule: dedicated buffer per tensor in a forward pass (the recording forward
was immune to all five because it allocates one buffer per activation). When
you change a buffer's width, grep EVERY consumer for its row stride.

### P25 — Newton-Schulz 5 diverges in fp32 on spread singular-value spectra
The Muon NS5 polynomial `X ← aX + (b·A + c·A²)·X` with (a,b,c) =
(3.4445, −4.7750, 2.0315) converges only inside a narrow singular-value basin.
After Frobenius normalization, a 448×64 k_proj gradient went
`max|M|: 0.32 → 1157 → inf` across 5 iterations — every k_proj matrix became
NaN after one optimizer step (the tall-matrix transpose path hit it first).
The paper's bf16 rounding masks this in PyTorch; C11 fp32 does not. A
Frobenius rescale keeps the norm bounded — but do NOT apply it unconditionally
every iteration as if it were part of the algorithm. Measured on a 64×64
Gaussian probe: with unit-Frobenius normalization each iteration, ‖M‖_F is
pinned at 1.000000 forever and ‖MᵀM − I‖_F sits at ≈7.9 (= √(n−1)) for 1, 2,
… 8 iterations. The polynomial never reaches its basin, because unit Frobenius
on a dense n×n matrix means a spectral norm near 1/√n, far below the σ≈1 the
coefficients (3.4445, −4.7750, 2.0315) are tuned for.

Use the rescale as a DIVERGENCE GUARD, not a normalizer: after each iteration,
rescale only when ‖M‖_F exceeds a bound (e.g. 2). Then the iterate is
orthogonal up to a scale, and an ABSOLUTE oracle must divide that scale out
first — if the routine normalized to unit Frobenius, multiply by
√min(rows,cols) before asserting ‖MᵀM − I‖ < 1e-3, or the test reports ~√n
however well it converged. Diagnostic: print ‖M‖_F per iteration; a constant
1.000000 is the signature of an unconditional renormalization cancelling the
polynomial's growth.

The Moonlight per-matrix scale should then be the "RMS = 0.2" form
(step = lr · 0.2 · X/RMS(X), so muon_lr ~ adam_lr, e.g. 2e-3 both), NOT the
`0.2·sqrt(max dims)` lr-multiplier form, which oversteps and diverges
training. Verify with a synthetic spread-spectrum matrix (random grads, tall
shape): 5 NS iterations must stay finite, and the post-rescale
‖MᵀM − I‖_F must fall with iteration count rather than sit flat.

**The quintic has no stable fixed point at 1 — so it is a bounded map, not an
orthogonalizer.** Evaluate the scalar map f(σ)=aσ+bσ³+cσ⁵ with
(3.4445, −4.7750, 2.0315): f(1)=0.701, f(0.701)=1.114, f(1.114)=0.722 — a
period-2 oscillation, and f diverges for σ ≳ 1.3. Out of the basin it cannot
reach orthogonality no matter how many iterations you give it, which is why the
training path's bounded output looked plausible while ‖MᵀM − I‖_F sat at ≈7.9.

When the goal is an ACTUAL polar factor, use the quadratic NS map in its own
TU (`src/wubu_muon.c`, `wubu_muon_orthogonalize`): Frobenius-normalize ONCE
(σ_max ≤ 1), then `X ← 0.5·X·(3I − XᵀX)`, transposing first when rows < cols.
Measured on a 64×64 LCG matrix: **5 iterations → 5.05, 25 iterations →
2.35e-07**; wide 32×64 row space → 1.24e-07. Convergence from a small σ is
slow, so expose the iteration count rather than hardcoding 5, and verify BOTH
the tall (`XᵀX`) and wide (`X Xᵀ`) forms. Keeping it in its own `.c` also lets
the test link one small object instead of the 55KB backprop unit.

### P26 — The degenerate-token FD trap: a passing FD suite can verify NOTHING
A "random" token generator that reuses the same RNG state without advancing
it emits the SAME token id every position (`rng_state % 31` in a loop that
never calls the RNG). With all-identical inputs the embedding INPUT-path
gradient is never exercised, and the FD check on a non-input embedding row
passes trivially (the analytic grad and the numeric grad are both ~0). The
suite reports green while a whole gradient path is unverified. Fixes:
(1) advance the RNG per token; (2) FD-check rows that ARE input tokens
(`embedding[tok0]`, `embedding[tok3]`) so the input path is genuinely
covered; (3) widen the one-per-type sampling (a second element, more layers
— a systematic index bug can hide in the unsampled types). The signature:
"15 unique / 24" in the test's token-diversity print is the sanity check —
if it says 1 unique / 24, the input is degenerate.

### P27 — The GPU weight-cache FD masking: stale device copies nullify the check
A GPU weight cache (pointer-keyed, generation-invalidated by the optimizer)
serves STALE device copies for any weight change that is NOT an optimizer
step — exactly what the FD test's perturbations are. If the dirty-mark fires
ONCE before the first forward, the second forward (with `w - h`) reuses the
cached `w + h` and `lp == lm` EXACTLY (the `num = 0.000000` signature). Fix:
mark the cache dirty AFTER EVERY perturbation (both `+h` and `−h`), and bump
the generation at the end of the optimizer step. When a FD check fails with
an EXACT zero difference, suspect a cache/stale-copy layer before suspecting
the math — the gradients may be right and the verifier blind.

### P27b — The head CE gradient is two GEMMs, not 1.9 GFLOP of CPU loops
The tied-head cross-entropy backward is `dh = g @ embedding` (the nt
orientation) and `demb = g^T @ final_h` (the tx orientation), where g is the
softmax error `(p − onehot)/n_pos`. Computing it as per-position CPU loops
over the 29MB embedding cost 1.9 GFLOP/step — the single biggest CPU cost in
the backward (the backward was 88% of fwd+bwd; this one change took it
0.573s → 0.18s). Write the softmax error IN-PLACE over the cached logits
(nothing needs them after the loss is computed), then two GEMMs. General
rule: profile fwd/bwd SEPARATELY before optimizing — the backward was the
winner here, and inside it the head grad was the hotspot; guessing the hot
spot instead of measuring wastes the first optimization pass.

### P28 — Teardown double-free after model growth (`wubu_free` → `free(): invalid pointer`) — CONFIRMED ROOT CAUSE (2026-08-03)
After 7+ growths the model's block weight pointers get freed twice at exit
(`free(): invalid pointer` in `wubu_free` → `__libc_free`). Happens even with
NS5 entirely skipped (`REPRO_SKIP=ns5`) — NOT an NS5 orthogonalization bug.
**Root cause CONFIRMED by ASan + minimal harness — TWO independent bugs:**
1. **Model-side struct-copy aliasing** (`wubu_grow_insert_block`): the shift
   `m->blocks[l] = m->blocks[l-1]` is a BY-VALUE struct copy (pointers copied),
   so the displaced block's weight region gets aliased into the new slot — two
   `blocks[]` entries point at the same malloc'd region. At teardown
   `wubu_free` iterates ALL `WUBU_LAYERS` slots and frees each region twice.
   ALSO: `zero_block()` allocated all weights in ONE `calloc` (offset pointers)
   — `wubu_free`'s per-field `free(k_proj)` etc. then frees sub-pointers that
   were never malloc'd ("free on address which was not malloc()-ed").
2. **CLI off-by-one** (`tools/wubu_train_cli.c`): the grow call passed
   `m.n_layers` AFTER `wubu_grow_insert_block` already incremented it, but
   `wubu_train_grow` expects the PRE-grow count (it frees the displaced
   inactive slot at `[n_layers]` before shifting). Post-increment value freed a
   LIVE slot, then the shift aliased the same pointer → double-free.
**Fix (all three):**
- `wubu_grow.c`: `block_free(&m->blocks[m->n_layers])` BEFORE the shift; after
  each struct copy `memset(&m->blocks[l-1], 0, sizeof)` (ownership transfer so
  `wubu_free` only frees each region once); `zero_block()` now allocates
  per-buffer (matching `wubu_free`'s per-field free).
- `wubu_train_cli.c`: `int pre_layers = m.n_layers - 1;` → pass `pre_layers`.
**Repro/verify:** the crash reproduces minimally at step 100 (ONE grow 2→3).
A minimal ASan harness (`tools/test_grow_free.c`: alloc model+train like the
CLI, grow 2→6, free) crashes in seconds — far faster than the 420-step CLI.
Verify: ASan harness prints ALL CLEAN; full run EXIT=0.
Pitfall: the `ns5_inplace` arg-swap diff (scratch/trans) is a separate
correctness issue that does NOT cause the teardown crash — do not conflate
the two.

### P33 — NVFP4 E2M1 zero code decodes as 0.5 unless special-cased (2026-08-05)
`wubu_nvfp4_to_f32(0)` computed `ldexp(1.0f, exp-1)` with exp=0 → 0.5, so the
quantized zero code round-tripped to 0.5 and EVERY value in a zeroed block
came back 0.5 — a silent bias in every requant/dequant path. Fix: early-return
`if (b == 0) return 0.0f;` BEFORE the sign/exp/mant decode. Rule: E2M1/FP4
decoders must special-case code 0 (and check what the reference packer does —
`wubu_nvfp4_block_quantize` emits 0 for underflow, so decode must return 0).

### P34 — Pack/unpack nibble order must match byte-index math exactly (2026-08-05)
`wubu_nvfp4_block_quantize` writes element `i` at absolute byte
`start/2 + i/2` with even i → LOW nibble, odd i → HIGH. A dequant that reads
`raw_nibbles[bk*16 + byte_idx]` (block offset + absolute idx) DOUBLE-COUNTED
the block offset — it read `bk*32 + i/2` instead of `bk*16 + i/2`. Also
swapping nibble halves (even→high) silently scrambles every pair. Rule: copy
the EXACT byte index + nibble-half convention from the packer into the
unpacker; when in doubt write a debug pair (raw_nibbles hex dump + first 4
dequantized values) and compare against the packer's own source.

### P35 — MXFP4 OCP layout: scale byte at END of block, reuse the packer (2026-08-05)
wubu_mxfp4 pack layout is `[16 nibble bytes][1 E8M0 scale byte]` per 32-element
block (scale at the END), NOT `[scale][nibbles]` at the start (that's the
NVFP4/enc_h3 convention). A hand-rolled "pack experts" wrapper that iterated
experts and called wubu_mxfp4_pack per expert worked, but the SECOND version
that assumed the wrong scale position produced garbage. Rule: when a module
already has `wubu_mxfp4_pack/unpack`, call it ONCE over the whole tensor
(`wubu_mxfp4_pack(experts, n_experts*expert_dim, out)`) — do not reimplement
block layout or per-expert striding by hand. Verify with a pack→unpack
round-trip `max_err < ~0.1` (E2M1 step ≈ 0.058 at scale 1).

### P36 — Sinkhorn: check the FINAL normalization step's invariant, not both (2026-08-05)
Sinkhorn-Knopp alternates row→column normalization per iteration. After N
iterations ending with COLUMN normalization, COLUMNS sum to ~1 but ROWS do
not — asserting `row_sum ≈ 1` fails with err ~1.0 even though the function is
correct. Fix: assert the invariant of the LAST step (even iters → columns,
odd → rows), with tolerance ~1e-1 (5 iters converges to ~1e-7). Rule: for
alternating-balancing algorithms, the test must mirror the implementation's
iteration parity.

### P37 — Rotation (Hadamard/ConvRot) amplifies quantization error: sqrt(P) (2026-08-05)
The H3 ConvRot un-rotation is a normalized Hadamard; a quantization error ε
per element becomes up to `sqrt(P)·ε` after re-rotation (P=64 → 8×). So a
round-trip test over [-0.5, 0.5) weights hits ~0.46 worst-case error — a 0.1
tolerance fails on CORRECT code. Also: the Hadamard can amplify component
magnitudes up to sqrt(P)×, so test data in [-5, 5) overflows NVFP4's ±6 clamp
and clamps to ±6 → giant error. Rule: for rotated-quantization round-trips,
(a) scale test data so post-rotation magnitudes stay inside the quantized
type's clamp range, (b) set tolerance = clamp_step × sqrt(P) ≈ 0.5 for P=64,
(c) document the amplification in the assertion comment.

### P38 — MXFP4/FP4 format pins: always confirm against the in-tree packer
When a port needs "requant to NVFP4" or "pack experts in MXFP4", the format
pins (nibble order, scale position, block size 32, E2M1 levels, E8M0 bias 127)
must be read from the EXISTING `wubu_nvfp4.c` / `wubu_mxfp4.c` source, not
from memory of the reference paper. Two packs in the same repo (nvfp4 vs
mxfp4) have DIFFERENT scale conventions (nvfp4: separate scale array; mxfp4:
scale byte at block end). A port that conflates them round-trips within
tolerance only if its own pack+unpack are consistent — and produces data
incompatible with the engine's other consumers.

### P39 — Terminal grep loops: the search-tool discipline (user-corrected, 2026-08-06)

The agent fell into a repeated-`grep` loop (~30+ identical `grep -n "GGML_TYPE_Q8_0" src/gguf_reader.c` invocations) while hunting a quant-type reference. The user's instruction: *"can we make it so deepseek cant use grep? its always a grep loop."* This is a workflow anti-pattern that wastes context and never converges. The fix is tool-discipline, not a code change:

**Rules (standing directive for this profile):**
- **Never** use `grep`/`rg`/`find` in the `terminal` tool for code search. One `search_files` call does it in a single ripgrep-backed shot with line numbers + context.
- **Batch independent reads.** If you need to inspect N files or N line-ranges, fire them in the same tool-call block — they execute concurrently. Only serialize when a later call genuinely depends on an earlier result (e.g. patching a file you must read first).
- **Use `read_file` with offset/limit for targeted inspection** instead of grepping the same file repeatedly. `read_file(path, offset=1390, limit=20)` is one call; `grep` in a loop is 30.
- **For multi-file pattern hunting, `search_files(pattern, target="content")` returns all matches across the repo in one shot** — never scan file-by-file manually.
- If the SAME grep string appears more than 3 times in a session transcript, STOP and switch to `search_files`.

**Reference:** `references/search-tool-discipline.md`

### P40 — Cap-exit loop leak: `i < n && cnt < max_ids` stops freeing past the cap (OOM crash, 2026-08-08)
The encode loop `for (int i = 0; i < n && cnt < max_ids; i++)` stops iterating
once `cnt` hits `max_ids` — every `syms[i]` past the cap is NEVER freed. On
chunked input the leaked-allocation count is O(n²): **78.9M leaked objects
(169MB) in just 50 encode passes** of a 28KB file → gigabytes → the kernel
OOM-killer SIGKILLed the process (`dmesg`: `oom-kill: task=wubu_pond2tok
total-vm:17.6GB`), which took down the whole gateway. Fix: free
unconditionally, check the cap only for the output write:
```c
for (int i = 0; i < n; i++) {
    if (cnt < max_ids) {
        int id = vocab_find(t, syms[i]);
        if (id >= 0) out_ids[cnt++] = id;
    }
    free(syms[i]);   /* EVERY symbol, regardless of the cap */
}
```
Companion bug in the same crash: passing a NON-NUL-terminated 256-char window
to a `strlen()`-based encoder — `strlen(buf+off)` walks the ENTIRE remaining
buffer, so every chunk re-processes the whole tail (O(n²) work AND the leak
grows with it). Fix: NUL-terminate each window, restore after:
```c
char saved = buf[off + take];
buf[off + take] = '\0';            /* terminate THIS window only */
int cnt = wubu_tok_hf_encode(tok, buf + off, ids, (int)take + 1);
buf[off + take] = saved;           /* restore the stream */
```
Third leak in the same file: `j_skip` called `j_str(j)` (mallocs) and never
freed it — every skipped JSON string leaked. Fix: `char *s = j_str(j);
free(s);`. Rules: (1) any loop with a cap must free resources INDEPENDENT of
the cap condition; (2) any function taking a C string must receive a
NUL-terminated string — chunked callers terminate each window; (3) a JSON
skip/parse helper that mallocs a value must free it. Verify with ASan leak
detection (`-fsanitize=address -O0 -g`, `ASAN_OPTIONS=detect_leaks=1`),
counting leaked allocations before/after: 78.9M → 10 → 0. Also: when a
process dies with **exit 137 (SIGKILL), check `dmesg | grep -i oom` FIRST** —
it names the task and shows total-vm/RSS, instantly distinguishing an
OOM-kill from a segfault. Add a vocab hash (O(1) lookup vs O(16384) linear
scan) to the same tokenizer: encode dropped from ~1s to 7ms per 10KB file.

### P41 — `wubu_kv_embedding_encode_tokens` books the region but does NOT write the payload
The KV-embedding bridge splits namespace bookkeeping (mount + offset record)
from the actual token-float write: `wubu_kv_embedding_encode_tokens` alone
leaves the KV tensor unwritten — the caller must write `tokens[i]` as floats
at the resolved offset (or use the one-call
`wubu_kv_embedding_write_tokens(kv, path, kv_base, tokens, n)` which does
both). A streamer that only calls `encode_tokens` mounts every file but its
`wubu_kv_embedding_region` lookup then returns paths whose data was never
written (the gate test failed exactly there). Fix: use the combined API;
the `kv_base` flat tensor is owned by the CALLER, not the bridge. Also the
slot stride for attention-score compression must come from
`wubu_kvfs_block_size(fs)` — a hardcoded 128 floats/slot when the KVFS block
size is 64 walks off the buffer (the G4 write-back OOB).

### P42 — `-ffast-math` compiles `isnan`/`isinf` AWAY: use IEEE bit checks (2026-08-08)
The engine builds with `-ffast-math`, which implies `-ffinite-math-only` —
the compiler ASSUMES no NaN/Inf exists and optimizes `isnan(x)`/`isinf(x)`
to `false` (dead code). A KV-audit module (`wubu_kv_audit.c`) that used
`isnan`/`isinf` to quarantine poisoned regions PASSED on the standalone
`-O2` build (no fast-math) but silently failed to detect anything under
the production flags. The ONLY NaN/Inf detection that survives fast-math
is IEEE-754 bit inspection:
```c
static int is_nan_bits(float x) {
    uint32_t b; memcpy(&b, &x, 4);
    return (b & 0x7F800000u) == 0x7F800000u && (b & 0x007FFFFFu) != 0;
}
static int is_inf_bits(float x) {
    uint32_t b; memcpy(&b, &x, 4);
    return (b & 0x7FFFFFFFu) == 0x7F800000u;
}
```
(Exponent all-1s: mantissa != 0 → NaN, mantissa == 0 → ±Inf.) `fabsf`
still works fine under fast-math — only the NaN/Inf PREDICATES are
compiled away. Rule: **any code that must DETECT NaN/Inf (audits,
quarantines, sanitizers, FD-check preconditions) uses bit checks;
`isnan`/`isinf` are only safe in code that must NOT detect them.**
Verify: build the test with the SAME `-ffast-math` flags as the engine —
a standalone `-O2`-only pass proves nothing.

### P43 — BPE chunk size changes the token stream: chunking splits merge boundaries (2026-08-08)
A byte-level BPE encoder applied in 512-byte windows produces a DIFFERENT
token stream than one pass over the whole input: a merge pair straddling
the window boundary is never formed, so chunked encode count ≠ single-shot
count. The G3 single-encoder gate (`test_kv_g3`) failed on exactly this —
the standalone `-O2` build passed but the `make` build (with fast-math +
different allocator behavior exposing the boundary) failed the
"multi-chunk count == single-shot count" assertion. Fix: encode content
≤64KB in ONE call (merges stay intact; the trainer depends on exact ids),
chunk at 64KB only above that, and verify the chunked path is
DETERMINISTIC (same bytes → same count) rather than asserting equality
with the single-shot path for >64KB inputs (boundary merges legitimately
differ there). Companion to P40: each window STILL needs NUL-termination
(a bare `content + off` walk is the OOM bug).

### P44 — Anonymous struct in a header is a DISTINCT type per declaration (incompatible-pointer, 2026-08-08)
`struct { wubu_hive_block_t *block; size_t slot; } *free_entries;` in
wubu_hive.h and a local `struct { ... } *nf` in wubu_hive.c are TWO DIFFERENT
types in C11 even with identical bodies — assigning one to the other is an
incompatible-pointer assignment (UB, `-Wincompatible-pointer-types` warning,
and the `realloc` resize silently propagates the wrong type). Symptom:
`warning: assignment to 'struct <anonymous> *' from incompatible pointer
type` at the freelist grow. Fix: give the struct a TAG in the header and use
the tagged form everywhere:
```c
/* header */
struct wubu_hive_free_entry { wubu_hive_block_t *block; size_t slot; };
struct wubu_hive_free_entry *free_entries;
/* .c */
struct wubu_hive_free_entry *nf =
    (struct wubu_hive_free_entry *)realloc(...);
```
Rule: any struct that appears in BOTH a header and a .c (or in two .c files)
must be tagged — anonymous structs are only safe fully local to one TU.

### P45 — Engine forward reads the ENGINE dim: probe inputs must be zero-padded (stack over-read, 2026-08-08)
`wubu_moe_forward` reads `D_MODEL`-wide tokens (`x_s[k]` for k < 2048), but a
test/probe passed a 32-float stack array `float x[DIM]` → stack over-read and
a segfault inside the omp parallel region at `wubu_moe.c:609` (gdb showed a
valid heap `w->ffn_gate_shexp` and a stack `x_s` — the read walked off `x_s`).
Fix: zero-pad probe inputs to the engine's dim before calling a forward that
contracts on D_MODEL:
```c
float *xpad = calloc((size_t)N * D_MODEL, sizeof(float));
memcpy(xpad, x, (size_t)(B * T) * sizeof(float));   /* pad the tail */
wubu_moe_forward(xpad, B, T, &mw, out, NULL);
```
Rule: any wrapper/probe around an engine forward must match the engine's
token width, not the probe's local dim — gdb's `p x_s` + `p k` + `p j` (the
faulting index) pinpoints whether the over-read is input (x_s) or weights.

### P46 — Weightless-MoE forward probe recipe (testing the router hook without a checkpoint)
To prove an engine forward consumes a new hook (e.g. `moe_weights_t.router`)
without a real checkpoint: (1) `n_experts_loaded = 1` — NOT 0: the clip guard
is `n_experts_loaded > 0`, so 0 does NOT clip and the F32 expert path
derefs NULL `ffn_gate_exps`; (2) give expert 0 one real (zeroed) F32 blob
with `ffn_*_exps_q_type = GGML_TYPE_F32` so the complete
router→quantized-matmul→accumulate path runs; (3) allocate shared-expert F32
buffers; (4) zero-pad input to D_MODEL (P45); (5) link the quantized chain
(`wubu_moe.o` needs `quantized_matmul.o`, `quantized_dot_generic.o`,
`dequant_iq2_xxs.o`) plus `-fopenmp` (GOMP symbols). Verify: forward returns
0 and output is finite.

### P47 — `wubu_block_t.gate_up` is `[dim, 2*ffn]` ROW-major: the transposed-FFN trap (2026-08-08)
The engine's FFN layout is NOT column-major. Read it from the header's
dimension comment BEFORE writing any per-element access:
- `gate_up` is `[dim, 2*ffn]` row-major: gate cols `0..ffn-1`, up cols
  `ffn..2*ffn-1` → `gate_up[i * (2*ffn) + j]` (gate), `gate_up[i * (2*ffn) +
  ffn + j]` (up).
- `down` is `[ffn, dim]` row-major → `down[j * dim + i]`.

A prune/shrink written column-major (`gate_up[j * dim + i]`) SILENTLY
corrupts the weights: the AM01 width-shrink's first attempt changed the
forward output 180×, and the "function-preserving" check failed loudly — but
a smaller transpose error can be fully silent (the FFN still runs, just
wrong). Debugging path: a standalone probe that runs the block FFN
before/after the op and prints `max|before-after|` pinpointed the prune as
the corruptor; the fix was matching the header's `/* [448, 2*1228] */`
layout. Rule: **any per-element access to an engine weight matrix starts by
reading the layout comment in the struct definition** — row-major vs
column-major transposes are silent in C.

**The honest function-preservation invariant for shrink:** pruning RANDOM
weights is NOT lossless — a low-norm prune is APPROXIMATELY preserving (the
output change is bounded by the pruned norm mass, and random weights all
have similar norms, so 25% pruning moves the output a lot). Function-
preservation for a shrink op is proven on ZERO columns: a zeroed column
contributes nothing to the output, so pruning it is EXACTLY lossless
(`max|before-after| == 0.000e+00`). Test that invariant; don't assert
losslessness on random weights.

### P48 — The self-describing loader + runtime-dims-everywhere rule (the "training has issues" root cause, 2026-08-09)
A whole pre-existing bug family lived in the load/train path and produced
"the model can't train / the build is broken" symptoms. All five fixed in one
session; each is a standing rule:
1. **wubu_load MUST probe the checkpoint's own geometry and set the runtime dims
   BEFORE reading tensors** (the revolver doctrine). The old design required EVERY
   caller to do the probe dance first and crashed `embedding.weight has N elems,
   expected 0` otherwise (test_wubu_train, wubu_train_cli, wubu_live_learn,
   test_diag oracle 7, test_wubu...). Set dims from the probe's `ckpt_*` fields =
   the file's REAL geometry; no zero-padding, no dual path. New aligned checkpoints
   are born aligned so real == aligned for them; a legacy 448 seed loads at 448
   exactly.
2. **Runtime dims EVERYWHERE in the optimizer, never the old seed's literals**:
   wubu_train.c + wubu_backprop.c hardcoded 448/64/1228/2456/16384 (the old
   geometry) — ANY model with different dims crashed in backprop. Buffer sizes must
   be `WUBU_*` macros: q/k/v/o/g = `dim × (heads·head_dim)` (k/v use kv_heads),
   gate_up = `dim × (2·ffn)` ROW-major, down = `ffn × dim`, emb = `vocab × dim`.
   Includes the grad-norm clip, scale_grad, Muon scratch sizing, and AdamW emb.
3. **q_norm/k_norm are PER-HEAD norms → `WUBU_HEAD_DIM` floats, NOT `WUBU_ROPE_DIM`**
   (rope is the partial-rotation width, a different concept). The rope_dim
   under-allocation corrupted the heap (ASan: free on a 128-byte region 64 bytes
   past — alloc 32 vs free/write 64). Applies in BOTH wubu_train.c (alloc + zero)
   and wubu_backprop.c (norm_slot_weight).
4. **THE DEEP ONE (2026-08-09, SUPERSEDES the include-order workaround below):
   `wubu.h` ITSELF hardcoded the dims.** `include/wubu.h` had `#define WUBU_DIM
   448 / WUBU_FFN_DIM 1228 / WUBU_LAYERS 12` — the compile-time constants
   SHADOWED the runtime `WUBU35_DIMS.*` macros for every TU that included wubu.h
   (i.e. all of them). The agnostic loader set the runtime dims, but the training
   path silently ran 448-era geometry — gdb showed `mm(..., out_n=2456, in_n=448)`
   while the runtime struct read 512/256; the header constants won. THE FIX:
   `wubu.h` now `#include "wubu35_dims.h"` FIRST (its WUBU35_DIMS-backed macros
   redefine WUBU_DIM etc.), the 448/1228 block is wrapped in `#ifndef WUBU35_DIMS_H`
   as a guarded default, and every struct member that used the runtime dims as an
   ARRAY SIZE got a capped constant: `blocks[WUBU_MAX_LAYERS]` (64), `selectors[8]`,
   `is_full[WUBU_MAX_LAYERS]`, and in wubu_train.h `q_proj_g[WUBU_MAX_LAYERS]` +
   `norm_g[WUBU_MAX_NORM_SLOTS]` (pointer arrays hold 8-byte pointers — 64 slots
   = 512B, negligible). `variably modified 'q_proj_g' at file scope` was the
   symptom of an array sized by a runtime macro; a capped constant fixes it.
   ALSO: two `wubu_model_t` types exist (wubu.h's direct-weights training model
   vs wubu_model.h's opaque gguf-loader model) — NEVER include wubu_model.h from
   wubu_train.h or `conflicting types` for wubu_model_init (5-arg vs 2-arg)
   breaks the whole train link. (The OLD guidance below — "wubu35_dims.h must
   come AFTER wubu.h" — was a workaround for the wrong header; after the wubu.h
   fix the runtime macros win everywhere regardless of include order.)
4b. **THE HARDCODED-64 FAMILY in wubu_backprop.c (found by the synthetic
   geometry, 2026-08-09):** the attention/KV path assumed head_dim=64 +
   kv_width=64 EVERYWHERE:
   (a) `wubu_bp_alloc` sized `k_pre/k/s_dk/s_dv` as `max_seq * 64` — with
       kv_heads > 1 or head_dim ≠ 64 the buffers are too small (5 sites → use
       `max_seq * (WUBU_KV_HEADS * WUBU_HEAD_DIM)`);
   (b) the `probs[WUBU_LOCAL_WIN + 2]` VLA in cpu_attn_loop + backward is
       window-sized but a FULL-attention row (is_full=1, lo=0) fills `seq`
       entries → dynamic-stack-buffer-overflow (ASan: `[cb]` redzone at offset
       40). Fix: `float probs[seq + 1];`.
   These were invisible at 448/7-heads/1-kv because 64 happened to be right.
   RULE: the ONLY way to surface geometry-hardcoded code is to build a
   SYNTHETIC model with a different-but-legal geometry (dim=256, heads=4,
   kv=1, hd=64, rope=32, ffn=512) and run the REAL train path on it under
   ASan — the 448 seed's "correctness" masked all of it. A from-scratch
   synthetic model must allocate the FULL block (attn/q/k/ffn norms + q/k/v/o/
   g/gate_up/down matrices) AND the selectors BEFORE wubu_model_init — init
   COPIES the pointer values, so filling selectors AFTER init leaves
   `m->selectors[i]` NULL (the selector path segfaults in bp_forward).
5. **MAKEFILE STALE-LINK FAMILY: every rule linking `src/wubu.o` needs
   `src/wubu35_dims.o` too** — test_wubu_train, wubu_train, wubu_live_learn,
   wubu_boot, wubu_train_gpu, test_wubu, test_backprop, wubu_cli, test_wubu_save,
   test_diag. Signature: `undefined reference to 'WUBU35_DIMS'`. test_diag also
   needs `-fopenmp` (GOMP symbols from wubu.o). After the revolver dims landed,
   every one of these rules silently rotted — grep the Makefile for `src/wubu.o`
   lines missing `wubu35_dims.o` when a training tool fails to link.
6. **Synthetic zeroed-model traps in tests** (building a random-init model without
   a checkpoint): (a) `full_every = 0` → `(i+1) % WUBU_FULL_EVERY` is a MODULO ZERO
   SIGFPE — set full_every ≥ 1; (b) `layers / select_every` integer division must
   be ≥ 1 (8 layers / 2 → 4; 2/4 → 0 selectors → division by zero in
   wubu_model_init); (c) a zeroed synthetic model CANNOT run the real train path —
   wubu_train_microbatch/backprop derefs NULL per-layer weights → guard with a
   `trainable` flag (only real checkpoints train; synthetic models run
   dataset/coherence/grow only). The fs_trainer gate (Phase 8) proved this split.
7. **The tokenizer j_skip leak** (companion to P40's third leak): j_skip called
   j_str (mallocs) and dropped the result — 13×64B leaked per load. Skip quoted
   strings WITHOUT allocating (walk to the closing quote, handle `\\` escapes).

See `references/training-path-bugs-2026-08-09.md` for the full P48 transcript:
the symptom chain (stale-link → expected-0 → heap corruption → hardcoded dims),
the sed sweep for the Makefile family, the gdb/ASan debugging path, and the
verification (448 seed trains again, loss 11.36).

### P49 — Meta-optimizer state-order bugs: compute deltas BEFORE overwriting state (2026-08-09)
The TGT odometer (`wubu_tgt_update` in wubu_optim.c) computed
`t->vel = t->loss_prev - loss` AFTER `t->loss_prev = loss` — so `vel` was
ALWAYS 0 and the "falling into the ravine" branch (r × 0.95) never fired
(the test showed r=2 at step 9 instead of 0.63). Fix: snapshot the old state
first, compute the delta, then store:
```c
float prev = t->loss_prev;
t->vel = (t->loss_prev_ok) ? (prev - loss) : 0.0f;  /* BEFORE the store */
t->loss_prev = loss;
```
Rule: ANY running-statistics update (EMA, velocity, curvature proxy, min/max
trackers) reads the PREVIOUS value to compute a delta — do the read+delta
before the store, or the delta is always 0. Same class as P14 (EMA needs
enough samples): both are "the state machine's own ordering defeats the
assertion."

### P50 — Meta-optimizer null-guard ordering: qlearner/TGT run BEFORE the model check (2026-08-09)
`wubu_optim_step` originally bailed `if (!o || !m || !tr) return` at the TOP —
so a test calling it with `tr=NULL` (to exercise just the qlearner/TGT, which
only need the LOSS) returned before the meta-optimizers ran, and the qlearner
test failed ("lr 0.0001 -> 0.0001"). Fix: run the loss-only meta-optimizers
(qlearner + TGT) FIRST, then the model/tr null-check before the optimizer
switch. Rule: separate what needs the loss (meta-optimizers, LR controllers)
from what needs the model (the actual update) — the guard belongs between
them, not before everything.

See `references/optimizer-dispatch-bringup-2026-08-09.md` for the full
wubu_optim transcript: the geometry-split design (Muon/AdamW/RSGD/qlearner/
TGT), the synthetic-geometry gate that surfaced the hardcoded-64 family
(P48-4b), the wubu.h-dims root cause (P48-4), and the test_optim build path
(which objects link: wubu_optim + wubu + wubu_train + wubu_backprop +
wubu_moe2 + safetensors_reader + wubu_dequant_nf4 + wubu35_dims + qlearner +
rsgd + wubu_mobius + gguf_reader, plus -fopenmp -lm).

### P51 — Probe-array width must match the module's CURRENT kind/slot count (OOB stack read, 2026-08-09)
When a module grows its per-check count (contract kinds, registry slots,
expert lanes), its tests' probe arrays must grow WITH it — a stale width is
an OOB read that NONDETERMINISTICALLY trips. Real case: `wubu_contracts`
grew the default set 5 → 8 kinds (the G38 pack added SKILLS/SPECIALISTS/
TOOLFAILS), but `test_contracts.c` kept `float clean[5]` / `float bad[5]`.
`wubu_contracts_check(ct, probes)` loops `for (i = 0; i < ct->n; i++)` and
reads `probes[i]` — indices 5–7 read STACK GARBAGE. The same binary passed
on one run (`0 violations`) and failed on the next (`1 violation`): the
stack layout differed run to run. The sweep flagged it; 5 reruns showed
0/1 flapping before the fix. FIX: `float clean[8] = {...}` matching the
current `ct->n` (and a comment noting the pack). RULE: whenever a module's
kind/slot array length changes, grep its tests for hardcoded array sizes
that mirrored the OLD count — the probe array width must equal the NEW
count (or the check must take an explicit n). Deterministic-green after the
fix (5/5 reruns). Same family as P14 (test assumptions vs module state) but
this one is memory-unsafe, not just an assertion mismatch.

### P52 — A predicate's return contract is NOT always 0=success (the ==0 skip trap, 2026-10-13)
Many scan/score APIs return a TRI-STATE, not a boolean success flag. `wubu_anomaly_score()` returns `1` = anomalous, `0` = not-anomalous/too-few-samples, `-1` = bad-input. Code that folded it as `if (wubu_anomaly_score(...) == 0) { read z; }` treated `1` (anomalous — the case that CARRIES the z you want) as failure and skipped it, so a 5.6σ spike computed severity 0.0 and never escalated. Fix: read the header/source for the ACTUAL return domain, then gate on the success range (`>= 0`), not on `== 0`. Rule: before writing `if (fn(...) == 0)`, confirm the function returns 0 for success and not for one of several meaningful outcomes — a tri-state predicate inverted this way is silent (no crash, wrong answer).

### P53 — Suffix/wildcard match needs a domain-boundary check (the notexample.com trap)
A `*.example.com` allow/deny rule implemented as a bare case-insensitive suffix compare matches `notexample.com` (it ends in `example.com`) — a false positive that lets a look-alike host through. Two fixes together: (1) skip only `\*.` (2 chars) to get the real suffix `example.com`, then compare; (2) require a boundary — either the host equals the suffix exactly (apex) OR the char immediately before the matched suffix is a `.`. Rule: any prefix/suffix glob over hierarchical names (hosts, paths, dotted keys) must enforce a segment boundary, or look-alikes pass.

### P54 — `snprintf("%s")` into a fixed buffer warns format-truncation → bound the field
`snprintf(dst, N, "%s-%s-%llu", a, b, id)` where `a` is a fixed char[] warns `-Wformat-truncation` because the compiler cannot prove `a` fits. Fix: cap the variable-width field with a precision, `"%.16s-%s-%llu"`, sized to leave room for the fixed parts. Rule: when snprintf-ing a struct member `char name[48]` alongside an unbounded `%s`, precision-bound the `%s` to silence the warning AND guarantee no silent truncation of the id.

### P55 — New-module wiring in this repo: gitignore eats test sources + .o, and the Makefile has no blanket pattern rule (2026-10-13)
Adding a `src/wubu_X.c` + `tools/test_X.c` module requires three non-obvious steps or the work is invisible to git / unbuildable:
1. `.gitignore` has `/tools/test_*` (ignores EVERY tool test source) and `*.o`. `git add tools/test_X.c src/wubu_X.o` is REFUSED. Use `git add -f tools/test_X.c ...` (headers + .c + Makefile add normally; the .o is a build artifact — commit source only). This is the established pattern (`test_anomaly.c` was force-added the same way).
2. There is no blanket `src/%.o: src/%.c` rule for arbitrary modules. Add an EXPLICIT dependency rule `src/wubu_X.o: src/wubu_X.c include/wubu_X.h` after a sibling rule, AND a `test_X: tools/test_X.c src/wubu_X.o [deps]` target that runs `./$@`. Insert both adjacent to a sibling's rules (find the anchor by an existing module's rule text).
3. Some `.o` files are only built ad-hoc by prior runs; if `make test_X` fails with `cannot find src/wubu_X.o`, build it by hand with the engine flags (`gcc -O3 -march=native -mno-avx512f -funroll-loops -fno-fast-math -ffp-contract=fast -ftree-vectorize -I include -c -o src/wubu_X.o src/wubu_X.c`) then re-run.
Rule: a new module is not "done" until its test target exists, builds, and the source is committed (force-add the test source). An orphaned-but-compiling module is the gap-closing failure shape (see the engineering skill's orphaned-module trap).

### P56 — A fix that trades one correctness class for another is a NET REGRESSION: revert, keep the gate green, document the real fix (2026-10-13)
The HolyC/JIT recursion bug (`fib(10)` = -80) has ONE root cause in BOTH backends: a single flat `prog.mem` at fixed offsets with no per-call frame, so a recursive callee reuses the caller's variable slots. The interpreter's `op_ret` was even MISSING the `memcpy(mem, f->mem_save, ...)` restore its own comment promised. Adding that restore fixed fib(10)=55 and simple recursion — but broke 9 struct-return/struct-param tests (MIR battery 112→102): the struct-return buffer is a PERSISTENT static region allocated inside `mem`, and a full-mem restore reverts it, so the caller reads zero. Struct returns are far more common in the suite than recursion, so the "fix" was a net loss and was reverted (gate held at 247/247). Lesson: when a correctness fix moves the failure from one test class to a larger one, it is a regression, not a fix — revert all touched files, keep the gate green, and write the root cause + the REAL architectural fix (frame-relative locals AND params in both backends, with struct-return buffers in a persistent region outside the restored local range) to a scratch plan for a focused session. Do not land a net-negative change to chase one failing test. Same discipline as P48/P28: the gate is the contract.

### P57 — When a state-change assertion fails, decide which side is wrong before editing the implementation (2026-10-13)
Several new-module tests failed on their FIRST run because the ASSERTION encoded a wrong expectation, not because the module was broken: `/n/experts/3` was asserted to be a file but is correctly a directory (the slot node containing per-expert files); a retention-prune was asserted to cap at N but the module correctly NEVER drops the active snapshot (so the count legitimately reaches N+1 while the oldest is active); a NULL security input was asserted to yield the milder of two severities but fail-closed correctly yields the SEVERE one. In each case the right move was to fix the TEST to match the (correct, defensible) semantics — not to distort the module to match a wrong test. Rule: on a failing state-change assertion, first ask "is the observed behavior defensible?" and check the module's stated contract; only edit the implementation when the behavior is genuinely wrong. A test that asserts the wrong invariant is as much a bug as the code it guards.

### P58 — Security/policy modules are written fail-closed by default (2026-10-13)
The AGI-EDR / OMARCHY security modules (`wubu_behavior`, `wubu_inject`, `wubu_egress`, `wubu_trace`, `wubu_escape`, `wubu_landlock`, `wubu_syscall_profile`, `wubu_ns_iso`, `wubu_unit_sandbox`, `wubu_pacman`) all share one shape worth copying for any future policy/security core: DEFAULT-DENY (allow only explicit rules), NULL/garbage/NaN/unknown → the MOST-severe verdict (halt/deny/STOP), a one-way kernel-owned stop the agent cannot clear, deterministic + no hot-path allocation, and an observability counter (denied/checked counts). Rule: for anything that gates, classifies, or contains an agent, the fail-closed default and the un-clearable stop are the invariants — test them explicitly (NULL → severe, steady input → no halt, adversarial input → halt) rather than only the happy path.

### P59 — A "skip"/"seen"/"live" bitfield read as bytes is a heap overflow (caught only under ASAN)
An allocator/registry that tracks per-slot liveness in a BITFIELD (`uint8_t skip[(cap+7)/8]`) but is consumed with `if (blk->skip[i])` reads `skip[i]` for `i < cap` — for cap=64 that is indices 0..63 of an 8-byte array → heap-buffer-overflow. A plain `-O3` build often runs clean (fresh calloc pages read as zeros); ASAN aborts on the first read past the region. Rule: a per-slot bitfield is ALWAYS read `arr[i>>3] & (1u << (i&7))` and written with `|=` / `&= ~(1u<<(i&7))`, never `arr[i]`. When you see a `skip`/`seen`/`live`/`dead` array sized `(cap+7)/8`, every consumer must mask, not index. Verify under ASAN, not just the fast build.

### P60 — `make test` is only a gate if its aggregate target's prerequisites actually exist
The top-level `test:` target aliased a single test (`test: test_ssm`) whose source had been deleted, so `make test` died with "No rule to make target 'test_ssm'" and gated NOTHING — the real suite lived under a different aggregate name (`test_400`). A broken aggregate turns the regression gate into a silent no-op. Rule: before treating `make test` as the contract, confirm the `test:` target expands to the full set AND every named prerequisite has a rule and a source file. Distinct from P6 (duplicate rules shadow each other) — here the aggregate itself pointed at a ghost, so nothing ran at all.

### P61 — A test referencing a vanished enum/function is a DROPPED FEATURE: restore from git, and patch the file the Makefile actually links
When a test fails with `'GGML_TYPE_Q2_0' undeclared` / `undefined reference`, run `git log --oneline -- <test>` before touching anything — the feature (here a whole quant-type family: the 42→47 legacy remap, the `raw_size` cases, the enum values, AND the dequantizers) was silently dropped from a prior refactor. Restore it; do NOT weaken the test to match the gutted code. CRITICAL: two readers can coexist (`gguf_reader.c` and a `wubu_gguf_*` split) with DUPLICATE symbols; the Makefile/test target links only the SPLIT, so patching `gguf_reader.c` changed nothing (the link still pulled the split). Rule: before patching, identify the ACTIVE source file — the one the build actually links (a `multiple definition of` link error across two files reveals which is live) — then restore the missing enum/remap/switch-case THERE.

### P62 — A fail-closed NULL contract must cover EVERY public function, including trivial helpers
A module's test asserts `wubu_hm_norm(NULL, 8) == 0.0` (fail-closed), but the `norm` helper had no NULL guard and dereferenced `v` → the FAIL-CLOSED TEST ITSELF segfaulted before it could report. Rule: when a module's stated contract is "NULL → safe 0 / -1", implement the guard in every exported function down to the smallest helper (`norm`, `count`, `size`, `best`); the fail-closed test exercises exactly those trivial entry points, so an unguarded helper converts the safety test into a crash. Same family as P58 — the fail-closed invariant is only real if the whole surface honors it.

### P63 — A struct array sized for fewer entries than init writes: glibc fortify aborts at RUNTIME
A policy/table struct declared `char prefix[8][48]` but whose `init` writes 14 entries (7 read-only + 7 writable rows) compiles clean under `-Wall -Wextra` and aborts at runtime with `*** buffer overflow detected ***: terminated` (glibc `_FORTIFY_SOURCE`). The compiler cannot see the row-count overflow because the writes go through an index variable, not a literal. Rule: when a fixed-row-count table is filled by a loop in `init`, either size the array to the maximum writes AND bound-check in the `add` accessor, or have `init` count and return -1 on overflow. Grep every `arr[n++]` write site against the declared dimension before shipping. A green compile proves nothing here — run the module.

### P64 — `snprintf` returns the INTENDED length, not bytes written: truncation tests assert buffer contents
A cap test `int n = snprintf(small, 6, "count=42"); CHECK(n < 6)` fails because snprintf returns 8 (what it WOULD have written) while safely writing 5 chars + NUL. The return value equals bytes-written ONLY when no truncation occurred. Rule: to test truncation, assert on the BUFFER — `strlen(out) < cap && out[cap-1] == '\0'` — never on the return value.

### P65 — A producer that returns 0-at-EOF does not clear its out-param: rewind before a determinism check
A streaming loader's `next()` returns 0 at end-of-epoch and leaves `*out` UNTOUCHED. A test that drained a full epoch then called `next(&c, &e1)` to assert "same seed → same first example" read STALE data (the last epoch's final example), so the comparison failed on correct code. Rule: before any "same seed reproduces the stream" assertion, rewind/reset the producer to position 0; and treat any 0-return producer's out-param as undefined until it returns success.

### P66 — Cannot take the address of a function-return value: struct-returning test helpers need a local
`wubu_wasm_run(&mk(code, len))` → `error: lvalue required as unary '&' operand` because `mk(...)` returns a struct BY VALUE. Rule: assign to a local first (`wubu_wasm_mod_t m = mk(code,len); run(&m);`) or wrap in a `#define RUN(c) ({ wubu_wasm_mod_t _m = mk(c, len); run(&_m); })` statement-expression; never `&fn()`.

### P67 — Define an enum/struct BEFORE the struct that uses it as a member type
Drafting a header, `wubu_mcard_kind_t kinds[N];` inside the struct with the `typedef enum {...} wubu_mcard_kind_t;` declared AFTER the struct → `unknown type name 'wubu_mcard_kind_t'`. Rule: when a struct member's type is a type you are also defining in the same header, the type definition must precede the struct. Same self-containment discipline as P10 — a header must be readable top-to-bottom without forward references to types defined later in the same file.

### P68 — A green gate must prove it RAN; and zero-init dims silently size buffers to 0

Three ways a test aggregate lies, all found in one audit:

1. **Make skips a test whose binary is newer than its sources.** `make test_all`
   returned EXIT=0 while executing 18 of 173 binaries. A gate script must delete
   the top-level test binaries first
   (`find . -maxdepth 1 -type f -name 'test_*' ! -name '*.c' -delete`) and print
   the RUN count beside the pass/fail counts. A pass count with no run count is
   not evidence. A single `make test_X` has the same hole in a different form:
   when the recipe compiles the test source inline but the target's prerequisite
   list omits that source, editing the `.c` does not rebuild and the OLD binary
   reports the OLD verdict. `rm -f <binary> && make test_X` (or `make -B`) before
   believing either a pass or a failure; `ls -l --time-style=+%T binary source`
   is a one-second check that the build is current.
2. **Phantom prerequisites.** Targets referencing sources that never existed
   (empty `git log -- <file>`, no analogue on disk) stop the build 30 binaries
   in. Audit before running: parse the `test_all` line, resolve every `src/X.o`
   to `src/X.c`/`.cpp`, and list targets with missing sources. Delete the
   phantom target and its rules; never stub a test or invent a module to
   satisfy the graph.
3. **Tests stale against moved APIs.** A test referencing members/helpers
   removed with an old struct is dead code. Confirm with `git log -- <test>`
   plus a `-fsyntax-only` sweep using the REAL build flags — the repo builds
   with the gnu17 default, so `-std=c11` falsely flags `M_PI`/`int64_t` in
   files that compile fine.

**Zero-initialised runtime dims.** `WUBU_DIMS` and `WUBU_RUNTIME_DIMS` are
`{0}` until a default/probe call. A test using `D_MODEL`/`WUBU_DIM` without
`wubu_dims_default()` (or `wubu_runtime_dims_default()`) computes 0 →
`calloc(0)` then `memcpy` → glibc fortify abort, or `wubu_buf_alloc` FAIL.

It has a **silent** shape too, which is the dangerous one: with `D_MODEL=0`
every loop bounded by it is zero-length, so a gradient test asserts `max|d_x| > 0`
against a buffer that was never written. The suite reports a cluster of
"non-zero gradients" failures (seen as 4/15) while everything else looks fine.
Signatures to check first: the test's own `D_MODEL=` printout reads 0, forward
weights come out uniform (e.g. 0.1250 for 8 experts), and `d_x`/`d_coarse`/
`d_fine` are all exactly zero. Add `wubu_dims_default()` at the TOP of `main()`
when you CREATE any test that touches `D_MODEL`/`D_FF`/`SHARED_D_FF` — not after
it fails; a test that has never run at real dimensions has never tested anything.

Call the default first, and link the defining object into every rule that
compiles the consumer directly: `src/wubu_dims.o` + `src/wubu_dims_gpu_stub.o`
for the wizard model, `src/wubu_runtime_dims.c` for `src/wubu.c` (same
stale-link family as P48-5, new module name). Signature:
`undefined reference to 'WUBU_DIMS'` / `'WUBU_RUNTIME_DIMS'`.

**A microbenchmark must vary the work per candidate.** If every precision runs
the same loop over the same float32 buffer, every candidate moves identical
bytes and the winner is timing noise (observed 0/4/0 across identical runs).
Make the footprint differ (packed bit widths), gate on accuracy (relative RMS),
and re-run 5× to prove determinism. A test that is pass/fail/pass on reruns is
measuring noise — fix the measurement or delete the claim; never wrap it in a
retry loop.

### P69 — A header's declaration is not a definition: one function defined in three TUs (latent duplicate symbol)

`undefined reference to 'wubu_exp_map'` appeared while the header that declares
it (`wubu_mobius.h`) was included — because the canonical module never defined
the maps. `grep -rn 'void wubu_exp_map' src/*.c` found the SAME body in
`wubu_gguf_bridge.c` and `gguf_reader.c`. It only linked because no target pulled
both copies; linking `wubu_mobius.o` with the bridge would be a duplicate-symbol
error. Rule: when a link error names a function the headers declare, search the
SOURCES for definitions before adding a link dependency — a declaration proves
nothing. If copies exist, move the body to the module that declares it (the
canonical TU) and delete every copy, then rebuild the full gate so any target
that relied on an incidental copy surfaces.

### P70 — An unchecked `malloc` is dereferenced before the NULL test

`wubu_poincare_dist` allocated `neg_x` and `diff`, filled `neg_x` in a loop, and
only used the pointers — no NULL check anywhere. On allocation failure that is a
NULL dereference, and a caller checking only the float result cannot tell. Rule:
allocate all buffers, NULL-check them TOGETHER before the first write, and return
a truthful failure value — `NAN` for a distance, `-1` for a count. Returning
`0.0f` from a distance function on OOM is a lie that reads as "same point".
Compile with `-Wmaybe-uninitialized` and treat the warning as a real finding
until proven otherwise.

### P71 — Riemannian gradients: the ambient gradient is NOT the tangent step

On a Poincaré ball, `dL/dx` (ambient coordinates) and `dL/du` (tangent at x)
differ by the metric factor. Feeding an ambient gradient into `u -= lr*g` and
mapping back diverges: a 300-step classifier run went 1.07 → 30 (the loss cap)
and pinned the point to the boundary. Rule: a manifold optimizer consumes the
TANGENT gradient. Either return `dL/du` from the loss (compute logits in the
tangent chart so the chain is exact) and step `u ← u - lr·dL/du; x ← exp_map(u)`,
or convert explicitly with the inverse metric. Verify: loss decreases over 300
steps AND `‖x‖ < R` at every checkpoint — divergence plus boundary-pinning is
the signature of an ambient/tangent mix-up.

### P72 — A hinge exactly on the band boundary converges only asymptotically

A radius regulariser `pen = (lo - r)²` for `r < lo` approaches `lo` from BELOW
forever, so a strict `r >= lo` occupancy assertion fails at any finite step
(observed 0/64 inside after 300 steps). Two valid fixes: hinge at an INWARD
margin (e.g. 5% of the band width in tangent units) so the band is genuinely
occupied, or assert with a tolerance. Prefer the margin — it is also the better
product behaviour (the regulariser should place points inside the band, not on
its edge). Convert the radius band to tangent coordinates first:
`‖u‖ = R·atanh(r/R)`; hinge there, then step in `u`.

### P73 — Manifold adapter backward: exp-map Jacobian + two outer products

For `out = exp_map(u + B(A u))` the gradient chain is:
1. `du' = exp_map_backward(u', out, dL/dout)` (the canonical module already has
   this Jacobian — never hand-roll it);
2. `r = A u`, `dr = Bᵀ du'`;
3. `dL/dB = du' ⊗ r`, `dL/dA = dr ⊗ u` (outer products, no per-element loops).
Verify with a linear functional `L = <out, g>` and CENTRAL finite differences on
a few entries of A and B: `eps = 1e-2`, relative error ~2e-3 in fp32 is normal
and the acceptance bar is `< 1e-2`. A forward-only adapter test proves nothing
about A/B; FD is the oracle.

### P74 — A cross-process lock needs a real race test, not two sequential calls

Two calls in one process prove nothing about mutual exclusion between
processes. Pattern that actually tests it: `mmap(MAP_SHARED|MAP_ANONYMOUS)` a
small `{volatile int start; volatile int accepted; volatile int rejected;}`
block; fork N children; each spins on `start`; the parent sets `start = 1` so
they race from the same instant; the winner takes the lock, performs the
guarded action (promotion) and bumps `accepted`, the loser bumps `rejected`
and exits with a DISTINCT status; the parent `waitpid`s and asserts exactly
one of each status plus `accepted == 1`. Have the winner hold the lock ~150ms
(`nanosleep`) so the overlap is guaranteed rather than hoped for. Then assert
the lock is acquirable again after release — a lock that never frees passes
the race and wedges production. Note `flock` is per open-file-description and
`fcntl(F_SETLK)` is per-process, so a same-process double-acquire is not a
substitute for the fork test.

### P75 — Building a string in place: terminate at the index you wrote, and never copy a buffer onto itself

Two defects in one search-update path, both silent and both only visible when
the test exercises a one-character query:

1. **Uninitialized terminator.** A local `char lower[MAX];` filled by a loop and
   then terminated with `lower[strlen(lower)] = '\0'` reads UNINITIALIZED memory
   for the length. The string is never correctly terminated: a single-character
   query matches nothing while a two-character query happens to work (the byte
   after the copy was zero by luck). Terminate with the loop index
   (`lower[n] = '\0'`) or `snprintf`.
2. **Self-aliasing copy.** Callers pass the module's own global buffer into
   `update(const char *q)`, which does `strncpy(g.query, q, N)` — `dst == src`
   is undefined, and `-O3` turns it into corruption (the query survives one
   call, then truncates to garbage on the next, so a backspace check narrows
   instead of widening). Copy through a local of the same size, or `memmove`.

Rule: any `set_string(dst_global, src)` API must assume `src` aliases
`dst_global`; and any locally-built C string is terminated by the counter that
wrote it, never by `strlen` on the buffer just filled.

### P76 — Inserting a Makefile target can steal the previous target's run line

A make recipe ends at the first line that is not tab-indented. Inserting a new
`test_X:` block immediately after another target's COMPILE line — but before its
`\t./$@` line — re-parents that run line to the new target: the old target keeps
compiling and silently stops executing its binary. Symptom: `make test_prev`
prints a compiler line and exits 0 with no test output, while the gate looks
finer because the binary was rebuilt.

Anchor new targets AFTER the previous recipe's last line (usually `\t./$@`), and
verify by running the previous target and looking for its result line, not just
exit 0. When a patch output shows a `./$@` line now hanging under the target you
just added, that is the bug — add the missing run line back rather than
re-running the build.

### P77 — Boltzmann weights over a potential: the deepest well must win, so the sign is `exp(-(φ−φ_min)/T)`

A router that ranks bodies by gravitational potential `φ = −G·M·m/r` must give
the LARGEST weight to the MOST NEGATIVE φ. Writing `w = exp((φ−φ_max)/T)` — a
softmax over φ as if it were a logit — inverts the field: the shallowest body
dominates, and with a small T the exponent `8/0.05` overflows to `inf` before
normalization. Use `w = exp(-(φ−φ_min)/T)`, subtract the MINIMUM, and assert on
a two-body fixture that the inner body wins and the weights sum to 1. The same
rule applies to any energy-based routing or attention where lower energy means
more probable: the sign is part of the contract, and a fixture with one clearly
deeper well is the oracle that catches it.

### P78 — A pipeline's exit status is the LAST command's: `make ... | tail` hides failure

`make test_x 2>&1 | tail -5; echo $?` reports tail's status (0), so a failing
target reads as success and the failing line can scroll out of the tail window.
For a gate, redirect instead of piping (`make ... > log 2>&1; echo $?`) or read
`${PIPESTATUS[0]}` in bash. When a pipe is genuinely wanted for brevity, grep
the log for `FAIL|Error` and print those counts alongside the exit code — an
exit code taken from a pipe is not evidence that the build passed.

### P79 — A terminator-scanned array with no length is an overread; a layout-sensitive test flip means "run ASan"

Two connected rules from one bug in the capability code.

1. **Sentinel-scanned arrays need an explicit count or a documented full-size contract.**
   `cap_copy_audience()` takes `const int32_t *src` and scans up to
   `WUBU_CAP_AUDIENCE_MAX` looking for `WUBU_PID_NONE` (-1). There is no length
   argument, so a caller passing `int32_t aud[] = { pid };` is read past its end.
   ASan reported `stack-buffer-overflow ... READ of size 4` at the scan loop, and
   the worst instance was production code (`wubu_cap_system_install_to_pid`), not
   the test that exposed it. Either add a count parameter, or write the contract
   in the header next to the constant ("must hold MAX entries terminated by
   SENTINEL") and make EVERY caller allocate that many. Grep every call site
   before declaring the contract satisfied — a fixed test plus one unfixed
   producer still overreads in production.
2. **A test that flips only because you changed unrelated code is UB, not a flaky test.**
   Adding a new test block and a linked module made three *early, untouched*
   assertions fail deterministically. The old test binary against the new object
   passed 34/34; the new binary failed 3. That is heap/stack layout moving onto
   latent UB. Do not rewrite the assertion — build the same suite under
   `-fsanitize=address,undefined` and let it name the real defect. Establish the
   pre-existing behaviour cheaply with `git show HEAD:<file>` into a temp tree and
   build both variants; "did my change cause this?" is answerable in one compile.
   A green suite on a module that does pointer arithmetic is a coincidence until
   ASan has run.

When the sanitizer finds an overread in a producer that the tests never call,
fix the producer and keep the ASan-clean run as the evidence — a 41/41 pass with
an ASan abort is a failing gate.

### P80 — Patching a Makefile backslash continuation: use Python, not the patch tool

A recipe line ending in `\` makes the `patch` tool refuse with "escape-drift
detected" (it will not risk doubling a continuation), and a hand edit can split
one logical command into two — which truncates a link line silently, because
make treats the second half as a new recipe line. Do the edit in Python with the
continuation built as `chr(92)` and assert exactly one occurrence before
replacing:

```python
bs = chr(92)
old = "\t\t$(RT)/a.c $(RT)/b.c " + bs + "\n"
assert s.count(old) == 1
s = s.replace(old, old + "\t\t$(RT)/new.c " + bs + "\n", 1)
```

Then run the modified target AND its neighbour and confirm each prints its own
result line (P76: a new target can steal the previous `./$@`).

### P81 — A test that reuses a fixture after freeing it passes VACUOUSLY

A test built an edge image, ran the contour call, then `wubu_img_free(&edges)` and
much later called a new function on `edges`. The call returned `-1`, and because
the follow-up assertion looped `for (i = 0; i < n; i++)` with `n == -1` it ran
zero times and PASSED — a green check guarding nothing. Two rules: (1) a test
fixture stays alive until every assertion that touches it is done — if the block
runs late, rebuild the fixture locally in that block; (2) assert the COUNT
before looping over returned items (`CHECK(n > 20, ...)` precedes any per-item
loop), so a failure return cannot silently empty the loop. Signature to suspect:
a brand-new assertion passes on its first run while the function returned -1.

### P82 — Image/geometry assertions must exclude the border where the operator clamps

Sampling `at(x-3, y-4)` clamps at the edges, so border blocks/pixels legitimately
contain repeated content and recover the WRONG displacement. A whole-field
"80% of blocks recover the shift" assertion failed at 49/64 (77%) on correct
code; the same measurement over interior blocks was 36/36. Rule: measure
accuracy away from the border (one block/pixel margin per search radius), state
in the test comment WHY the border is excluded, and never loosen the interior
threshold to absorb border error — that hides a real regression.

### P83 — Declaring a sibling module's type in your header: use a local plain struct

`wubu_cv.h` declaring `wubu_keypoint *out` failed to compile because that type
lives in `wubu_features.h`. The reflex fix (include the sibling header) pulls a
whole API surface into a leaf module and invites a cycle. When the type is only
a small POD (x, y, score), declare a local struct in your own header instead
(`typedef struct { int x, y; float score; } wubu_corner;`) and keep the module
dependency-free. This is the deliberate exception to P10: P10 says a header must
include what it NAMES — but the better move is often not to name a foreign type
at all. Rule: cross-include for a macro/enum you cannot restate; define a local
POD for a 2-3 field struct.

### P84 — Never ship an approximation under a famous algorithm's name; log the rejection

A cheap shortcut was labelled and declared as Farneback flow, returned 475 px
mean error on a known (2,3) shift, and looked plausible in the header. The
shortcut dropped the intensity centering that normalized convolution provides,
which is the entire method. Rules: (1) name the method you actually implemented
(block matching stayed "block matching"; Horn-Schunck is "Horn-Schunck"); (2)
when a first attempt lands a huge error, DELETE it and revert rather than
tuning coefficients around a wrong derivation — a wrong coefficient set can be
made to "pass" on one fixture and stays wrong everywhere else; (3) record the
rejected approach, its measured error, and the correct route in the module doc,
so the next session does not re-walk it. A shipped-but-wrong function under a
respected name is worse than a gap.

### P85 — Normalised DLT/RQ: denormalise through the right matrix, and QR-of-transpose is LQ

Two silent-wrong-answer traps in camera geometry, both caught only by an exact-data oracle:

1. **Denormalisation must undo BOTH transforms with the right row weights.** After
   Hartley normalisation, `P = T2⁻¹ · P_n · T3`: rows 0/1 carry `1/s2` and add
   `c2·row2`; row 2 stays unscaled. Scaling all three rows by `1/s2` and then
   adding the centroid term from the pre-scaled matrix produced **94 px RMS** on
   exact synthetic correspondences; the corrected form gives **2.4e-14**.
2. **RQ is not QR of the transpose.** `M = R Q` with `R` upper triangular is the
   bottom-up Gram–Schmidt sweep: for `i = n-1..0`, subtract projections onto
   `Q[i+1..]`, then `R[i][i] = ‖v‖`, `Q[i] = v/‖v‖`. The "reverse and QR the
   transpose" identity yields an **LQ** factorisation — K came back with entries
   around `2.6e14`.

Oracles that catch both: synthesise exact correspondences from a KNOWN P, then
require reprojection RMS `< 1e-6`, K equal to the known intrinsics, and R = I for
an axis-aligned camera. On `t`: it is `K⁻¹ p4`, so intrinsics fold into the
translation column — a "shifted" t is usually arithmetic, not a bug (check
`p4 == K·t` before editing code).

Same family as P57: when K and R come back exact and one vector looks off, verify
the definition before touching the implementation.

See `references/camera-geometry-oracles.md` for the full DLT/RQ/homography/marker
recipes and their synthetic oracles.

## Verification recipes (Triple-DA)- **Oracle match**: chunked/parallel path vs serial reference → `maxdiff < 1e-4f`.
- **Alignment**: `assert(((uintptr_t)ptr & 63) == 0)` after every 64B alloc.
- **Collision**: different inputs → different hash; same input → same hash.
- **No regress**: `make test_all` green before commit; `make test_400` for the
  improvement suite. Run `make test_all` (not just the one new test) — a local
  fix can break a shared module's other tests.
- **In-forward kernel probe (prove standalone kernels run in the ENGINE)**:
  a ported kernel that only runs in its own `test_X` binary isn't proven to
  run inside the model. Add an env-gated probe in `wubu_model_forward`:
  `WUBU_REF_KERNELS=1` runs each kernel once per forward against the REAL
  hidden state (`x + (N-1)*d_model`) with synthetic-but-real-scale inputs,
  and prints `[ref-kernels] <name> OK` on success. Verify the gate-off path
  prints NOTHING (zero-cost: `env ... | grep -c ref-kernels` == 0) and the
  gate-on run shows all kernels. Also link the new `.o` files into `CORE_OBJ`
  (not just the test target) so `gen_text`/engine binaries actually carry
  them — and expect `undefined reference` to the REUSED modules (e.g.
  `wubu_mxfp4_pack`, `wubu_deltanet_update`) when their objects aren't in
  `CORE_OBJ`; add them too. Env-gated runs via `env VAR=1 ./bin` (bare
  `VAR=1 ./bin` trips the terminal guard — see hermes-terminal-guard-patterns).
- **GPU-vs-CPU numeric parity (MANDATORY before wiring any new GPU kernel into
  training)**: build a tiny `gpu_matmul_check` that runs the SAME inputs through
  the CPU loop and the cuBLAS kernel and asserts `max_diff < 1e-4`. Orientation
  bugs (P20) and transpose errors are silent until the loss diverges — the
  parity check catches them at the boundary.
- **Finite-difference gradient check (MANDATORY for any analytic backward)**: a
  backward pass is verified by perturbing ONE weight of EVERY parameter type
  (`h = 1e-2`, loss re-forwarded) and comparing `(L(w+h) − L(w−h))/2h` against
  the analytic grad; tolerance `max(1e-3, 0.1·|ana|)`. tests ≠ correct — this
  is how `wubu_backprop` was proven real (26/26 parameter checks incl.
  input-path rows, `tools/test_backprop.c`). See P26 (degenerate tokens nullify
  it) and P27 (a GPU weight cache nullifies it) before trusting a green run.
  Add a **forward-parity check** alongside: the
  recording forward's loss must equal the released forward's loss to 1e-3 for
  the same tokens — this is what caught all five P24 aliasing bugs. And assert
  layers specialize: the old shared-proxy backward gave every layer the
  identical gradient; `sum|g[l0] − g[l1]| > 0` catches it.
- **Parity-debugging playbook**: when two implementations of the same math
  disagree, the systematic hunt is in `references/backprop-parity-debugging.md`
  — bisect by input size (seq=1 matches, seq=2 diverges ⇒ the bug involves the
  second position), compare per-stage buffers at the right stride, print exact
  values at the divergence point, recompute from recorded buffers
  (self-consistency), and beware debug-tool bugs of your own making (variable
  shadowing, wrong strides, greps missing indented output).
- **Weak-symbol GPU dispatch for dual CPU/GPU builds**: `__attribute__((weak))`
  on the GPU entry points (`gpu_wubu_init/ready/matmul`) means a CPU-only
  link (no `-lcublas`) still resolves — missing weak symbols become NULL, and
  the caller checks `if (gpu_wubu_ready && gpu_wubu_ready() && ...)` before
  dispatching. Without weak symbols, adding GPU calls to a shared module breaks
  every CPU-only test link with `undefined reference`.
- **BPE merge-loop speed (O(n²) → hash table)**: a byte-level BPE tokenizer
  whose `apply_bpe` scans ALL merges per adjacent pair is O(n_merges·n) PER
  merge pass — a 640MB corpus took hours. Fix: build a pair→rank hash table
  (FNV-1a over `a + sep + b`, open addressing, 65536 buckets) once at load;
  each pair lookup becomes O(1). Plus: chunk long input lines (~256 chars,
  cut at spaces) so the per-line merge cost stays bounded. Measured: 65×
  faster (1MB in 1.8s vs >120s).

See `references/bug-transcripts.md` for the exact before→after diffs that
fixed P1–P8 (drawn from commits 78e06d3, d9944cb, b0f71f7).

See `references/gp-cholesky-collision-patterns.md` for the Cholesky backsolve
direction (P9), header self-inclusion (P10), static-TU visibility (P11), the
silent-overwrite file-collision rescue, and the BO/SINDy/CEGIS/invariant
verification cheatsheet (passes 41–44).

See `references/model-growth-bringup.md` for the growth operator (Net2Net
zero-init identity insertion, the per-block rhythm-flag shift that keeps the
function preserved under layer insertion, the active-layer-count contract, the
train-state pointer shift, the fp32-honest FD sampling for grown models, the
`make test_all` silent-skip trap, the 8MB-stack hash-table segfault, and the
leftover-kernel-printf hygiene).

See `references/asan-build-recipe.md` for how to actually GET a sanitizer
trace out of this engine: the Makefile env-CFLAGS override trap (build by
hand with `-static-libasan -O2`), `stdbuf` for live logs, `--ckpt 0` FPE,
`MALLOC_CHECK_=2` fast pre-check, and the minimal-harness pattern
(`tools/test_grow_free.c`) that reproduces a teardown double-free in seconds
instead of the 420-step CLI.

See `references/deterministic-rng-testing.md` for the PCG-XSH-RR recipe and the
four-check battery (pinned vector, chi-square critical value 310.46 for df=255,
run/bit balance, 10k FNV hash as the cross-arch guard) — use it whenever a goal
claims a named generator or a simulation must replay identically.

See `references/manifold-training-pitfalls.md` for P71–P73 with the full
formulas, the tangent-kludge vs tangent-gradient comparison, and the four-test
matrix (hierarchy ordering, radius band occupancy, LoRA FD, ball closure).

See `references/amoeba-weights-c11-bugs-2026-08-04.md` for the P29–P32
transcripts: realloc-dangling parent in grow (wubu_gravity), struct-field
addr free vs heap-wrapper free (wubu_orbits), `const char *` member written
via strncpy (wubu_boot), the bulk-rewrite-script-empty-file disaster + the
GNU-free doctrine detail (legit vs cargo-cult `_GNU_SOURCE` per symbol).

See `references/tokenizer-oom-leak-2026-08-08.md` for the P40 transcript:
the cap-exit loop leak + non-NUL-terminated chunk windows + j_skip leak that
ballooned to 17.6GB and OOM-killed the gateway (dmesg evidence, the ASan
leak-count debugging path, the vocab-hash speedup, and the scaled proof:
32,581 files / 621M tokens in 51s at 4.5MB RSS).

See `references/router-slot-plumbing-bugs.md` for the P44–P46 transcripts:
the anonymous-struct type-punning fix in wubu_hive.c, the Poincaré
native-dim heap overflow, the MoE D_MODEL stack over-read (gdb
disambiguation path), and the weightless-MoE probe recipe (n_experts_loaded
= 1 trap, zeroed F32 expert-0 blob, shared-expert buffers, link chain).

Session companions (2026-08-08, both under `wubuwizard-c11-engineering`):
- `references/orphaned-module-makefile-wiring.md` — the orphaned-module trap
  (a module fully written but in NO build/test/callers — the real gap is
  wiring, not writing) + the block-aware Makefile link-line edit technique
  (rule bodies span continuation lines; naive per-line edits double-add or
  miss).
- `references/shell-injection-argv-fix-2026-08-08.md` — the user-string →
  `/bin/sh -c` command-injection audit grep + the run_argv/run_chroot_argv
  argv-exec fix pattern + the metacharacter-inert gate test.

See `references/property-test-oracles.md` for the module-wave recipe (implement
→ property test → honest gate → commit) and the oracle patterns that proved
CV/geometry primitives: known-transform recovery, exact round-trip identities,
lattice counting, sub-pixel error bounds, and the interior-vs-border rule.

## Overlap note
`wubuwizard-c11-engineering` covers *wiring/extending* modules; this skill
covers *correctness traps + oracle verification* for that work. They are
complementary; the background curator may fold P1–P8 into the engineering skill
if consolidation is desired.
