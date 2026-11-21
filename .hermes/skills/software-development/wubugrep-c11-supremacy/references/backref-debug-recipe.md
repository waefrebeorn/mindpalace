# Backreference backtracking matcher — debug recipe

A recursive backtracking matcher for BRE `\1..\9`. The NFA (Russ Cox) path is
left untouched; backref patterns dispatch to `wubre_compile_bre` / `wubre_search_bre`
/ `bt_match`. Session: GNU grep suite went BRE 36/64 → 43/64 (67.2%) and simple
backrefs are byte-identical to `/usr/bin/grep`.

## Pitfalls hit (in order) and how to recognize each

### 1. Off-by-one in backref numbering
BRE `\N` references the *Nth* group (1-indexed), but the engine stores groups
0-indexed (`\(` assigns g=0,1,...). The backref node must store
`g = (N-'0') - 1`. **Symptom:** `\(a\)\1` returns rc=1 (no match) instead of rc=0.
Every backref pattern silently fails. The unit harness (single char) returns 0
where grep returns 1.

### 2. `\)` parsed as a literal `)` instead of group-close
In `bt_parse_atom`, the escape branch must return `-1` (terminator) for `\)`,
NOT fall through to `bt_lit(')')`. Otherwise the group never closes and the
body parser swallows the `\)` as a literal, producing extra spurious nodes.
**Symptom:** AST dump shows a `LIT ')'` node mid-group; CAP node wiring wrong;
`\(a\)\1` produces 6 nodes instead of 4.

### 3. Root node is not node 0
`bt_parse_alt` returns the top SEQ node index, which is NOT necessarily the
first-allocated node (the first node allocated is an inner atom). Hardcoding
`root = 0` matches an inner atom and produces garbage/false-matches.
**Symptom:** false positives — `\(a\)\1` matches `ab` (should require `aa`),
`a\(b\)c\1d` matches `abcad` (should require `abcbd`). **Fix:** store
`re->bt_root = root`; read it in `wubre_search_bre`.

### 4. Leaf nodes reference an uninitialized continuation (`nd->a`)
LIT/DOT/CLS/BOL/EOL/BREF nodes have their continuation handled by the SEQ wrapper,
but the matcher was calling `bt_match(nd->a, ...)` on them — and `nd->a`
defaults to 0 (the root / self-loop). **Symptom:** matches succeed via wrong
paths or loop. **Fix:** leaf nodes return the advanced position directly
(`pos+1` for consuming atoms, `pos` for zero-width BOL/EOL, `pos+len` for BREF);
only SEQ/ALT/quantifiers thread via structure fields.

### 5. Catastrophic backtracking (DoS)
Nested-group + nested-backref patterns (`a\(\(b\)*\2\)*d`) blow up exponentially.
A `steps` budget (decremented per `bt_match` call, **shared across ALL start
positions** in `wubre_search_bre`) bounds worst case to ~tens of ms.
A per-start budget is WRONG — it exhausts on the first pathological start and
starves later (cheaper) starts that would have matched.

## Verification pattern
Tiny harness calling `wubre_compile` + `wubre_search` directly (the public
struct is opaque, so read fields via the harness). Positives: `\(a\)\1`→`aa`,
`\(x\)\1\1`→`xxx`, `a\(b\)c\1d`→`abcb d`. Negatives: `\(a\)\1` must NOT match
`ab`. Plus the GNU grep backref test lines. **Always ASan+UBSan the backtrack
path** (`-fsanitize=address,undefined`) — `group[]` calloc/free and the
`BTProg` node array are the alloc sites.
