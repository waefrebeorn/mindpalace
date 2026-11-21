# WuBuGrep Monolith → Module Split (2026-08-21)

Concrete recipe used to split `src/tools/wubre.c` (~1000 LOC, one opaque
`WURegex`, scalar Pike-VM NFA + BRE backtracker) into self-contained modules
**with separate compile units** (not the `#include` shim). The goal was both
legibility AND a speed win (whole-buffer single-pass NFA + SIMD literal
prefilter) while keeping **byte-identical 100% parity with GNU grep** on the
canonical `bre.tests`/`ere.tests` suites.

## Module layout that resulted

```
wubre.h            public API (opaque WURegex; wubre_compile/search/search_buf/free)
wubre_internal.h   INTERNAL types + cross-module bridges (NOT a god header)
wubre_compile.c    parser + Thompson NFA construction + prefilter extraction
wubre_match.c      wubre_search (per-line) + wubre_search_buf (whole-buffer)
wubre_simd.c       wub_memmem (AVX2) + wub_simd_has_window (2-literal window)
wubre_bre.c        BRE backtracking engine (backreferences \1..\9)
wubre.c            API shim: wubre_free only
wubugrep.c         CLI driver; calls wubre_search_buf for the regex fast path
```

## Key techniques (reusable)

### 1. Separate .c compile units + one shared internal.h
Unlike the `#include`-shim variant (everything stays one TU), here each module
is its OWN TU. The price: `static` helpers that were visible across the
original file must become **non-static + declared in `wubre_internal.h`** (the
cross-module bridge), OR stay `static` in ONE module and be declared `extern`
there. The internal header holds ONLY: shared struct DEFINITIONS (WURegex,
State, Frag, Ptx, BTNode), forward decls of cross-module functions, and
`static inline` helpers (each TU gets its own copy, no linkage conflict).
Public `wubre.h` stays opaque (forward-declares `WURegex`, declares only the 4
public funcs). This is the "no god header" doctrine in practice: the internal
header is INTRA-module, the public header is INTER-module.

### 2. Dead-code removal is part of the split ("fix broken code first")
The monolith carried `dq_init/dq_push/dq_pop`, `g_dq`, `g_is_tty` (unused) and
`prev` in `parse_class` (write-only), `last_atom/last_quant` in `validate_regex`
(write-only). Removed them during the move. This silenced `-Wunused` and
`-Wset-but-not-used` and shrank the surface. The user's standing rule: when
refactoring, delete the dead/broken code rather than hiding it with `(void)x;`.

### 3. Whole-buffer single-pass NFA (the speed lever)
`wubre_search` (per-line) runs the Pike VM once PER LINE — millions of resets
over a big file. `wubre_search_buf` runs it ONCE over the whole `[base,end)`
buffer, evaluating `^`/`$` against `\n` positions (identical per-line
semantics to GNU grep). A precomputed line-start index (`size_t lo[]`) makes
each matching-line emit O(1). wubugrep's scan loop calls `wubre_search_buf`
for the common case (`!g_opt_invert`) and keeps the per-line loop as the `-v`
fallback. Result: on a 38 MB / 1M-line corpus, `-F` and `-c` became
**2–3× faster than ripgrep** (was 2.9× on `-F` already; the whole-buffer pass
removed the per-line wall).

**The non-obvious bug that broke it first:** the unanchored NFA only enters at
`re->start`, so over a whole buffer it matched the FIRST occurrence then never
restarted (per-line worked only because each line reset the VM). Fix: **re-admit
`re->start` into the active set at EVERY step** (seed `dense` each iteration).
For anchored `^` patterns `re->start` IS the ANCH_START state; the anchor's own
`at_start` guard correctly suppresses it except at line starts, so unconditional
re-admit is correct for BOTH anchored and unanchored. Add `int
re->unanchored` (or just always re-admit when `re->start>=0`) — don't gate on a
flag you can get wrong.

### 4. SIMD literal prefilter + 2-literal window (Hyperscan-style)
- `wub_memmem` (AVX2, `target("avx2")`) scans 32 bytes/cycle for a required
  literal; scalar fallback for non-AVX2 paths. Per-project rule: we BUILD OUR
  OWN SIMD (no vectorscan/PCRE dependency) — "there is no such thing as third
  party if we can properly make the code".
- `wub_simd_has_window(buf,n,la,la_n,lb,lb_n,window)` detects a pattern of the
  form `LIT1 .* LIT2` (extracted in `wubre_compile` when it sees
  `RUN1 .* RUN2`) and SIMD-scans for LIT1, then verifies LIT2 within a bounded
  forward window. Used as a fast reject in `wubre_search_buf`: if the window
  cannot exist, the NFA is skipped entirely.

### 5. Parity gate — never declare a split "done" without it
After every move, run the canonical diff:
```bash
python3 - <<'PY'
import subprocess
W='./wubugrep'; G='/usr/bin/grep'
def run(b,fl,pat,inp):
    r=subprocess.run([b,fl,pat],input=(inp+"\n").encode(),capture_output=True,timeout=6)
    return r.returncode,r.stdout
fc=pc=0
for fl,tf in [("-G","bre.tests"),("-E","ere.tests")]:
    for raw in open(f"external_tests/{tf}"):
        L=raw.rstrip("\n")
        if not L or L[0]=="#": continue
        a=L.split("@"); pat,inp=a[1],a[2]; pc+=1
        g=run(G,fl,pat,inp); w=run(W,fl,pat,inp)
        if g[0]==w[0] and g[1]==w[1]: fc+=1
fc,pc  # expect 281/281
PY
```
Plus `wubre_test` (unit, ALL PASS) and an ASan+UBSan build (`-fsanitize=address,undefined`). The whole-buffer path must ALSO be diffed against grep on a
**stable** corpus (`-c` counts + full `diff` of `-E` output) — a randomized
corpus regenerated between runs produces false "DIFF"s that look like engine
bugs but are just different input data. **Lesson: generate the benchmark corpus
ONCE with a fixed seed and reuse it; never regenerate between the grep and
wubugrep runs.**

## What did NOT close (honest gap, next wave)
The `.*` / `fox.*dog` path is still ~68× slower than ripgrep because the NFA is
scalar per-byte. ripgrep uses a SIMD DFA. The remaining SOTA move is a
bit-parallel (Parabix-style) NFA or a `LIT1.*LIT2` short-circuit that replaces
the NFA with the window check entirely (no NFA run when the pattern is exactly
`LIT .* LIT`). That short-circuit was identified but not yet implemented at
session end.
