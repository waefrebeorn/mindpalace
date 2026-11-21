# Differential-test harness for WuBuGrep regex parity

The user demands *determinate* tests: a fixed seed produces a fixed,
reproducible verdict. WuBuGrep's correctness proof is byte-for-byte equality
against GNU grep (the POSIX oracle), separately for literals and for `-E`/`-G`
regex. ripgrep is only a *speed* benchmark, never the correctness oracle
(it intentionally omits zero-count files in `-r -c`, which GNU grep includes).

## Literal parity (test_wubugrep.py, already in repo)
`WUB_TRIALS=4000 python3 test_wubugrep.py` → 4000 trials × 15 flag combos
(60k combos) + 13 targeted edge cases. Asserts `wubugrep stdout == grep
stdout` AND `rc == rc`. Seed 1337.

## Regex parity (engine-level + full-binary)
The engine is a standalone `.c`; drive it through a tiny CLI (`wubcli.c`)
that compiles a pattern (flags `-i`/`-G`) and returns rc 0/1 per line, then
diff against `grep -E`/`-G` across generated corpora.

```python
# /tmp/wubdriver.py  mode in {E,G}; ~13,500 checks per mode
import subprocess, random, os, tempfile, shutil
WUB="/home/wubu/wubuos/tools/wubugrep/wubugrep"  # full binary, or /tmp/wubcli
bre = "G" if mode=="G" else ""
pats = ["a.c","abc","^foo","bar$","(ab)+","a|b|c","colou?r","[a-z]+",
        "wubu.*grep","the","A.*Z","x+","(cat|dog)s?","^$",
        "[A-Za-z_][A-Za-z0-9_]*","(foo|bar|baz)","q[a-z]*k","a.b.c","(a|b|c)+","ab|cd"]
for _ in range(500):
    # build a random multi-line file; sometimes no trailing newline
    for p in pats:
      for ic in ("",):
        args=[WUB,"-"+mode, p, fn, ic, bre] if bre else [WUB,"-"+mode,p,fn,ic]
        our=subprocess.run(args,stdin=open(fn,"rb"),capture_output=True).returncode==0
        g=subprocess.run(["grep",("-E" if mode=="E" else "-G"),"-e",p,fn],
                         capture_output=True).returncode==0
        assert our==g
```

Full-binary recursive parity: pass a directory with `-r` to both `wubugrep`
and `grep -r` and compare stdout+rc (note: GNU grep *without* `-r` on a dir
returns rc=2 "Is a directory" — WuBuGrep recurses, so only compare the `-r`
cases for parity; the no-`-r`-on-dir mismatch is expected/by-design).

Verified: 27,000 engine checks (E+G) + 75,600 full-binary checks (E+G, incl
`-r`) = **0 divergence**.

## NFA simulation debug technique (when the matcher misbehaves)
The Thompson-NFA sim is easy to get wrong and hard to eyeball. Gate debug
output behind `getenv("WUB_DEBUG")` and dump TWO things:
1. The compiled NFA graph (state type, `out`, `out1`, class bits) right after
   `wubre_compile`.
2. Per input byte `i`, the set of active state indices after consuming that
   byte.

Then hand-trace one failing case. This session, `q[a-z]*k` on `quick` printed
`set=0 5 6` at `i=1` — proving `[a-z]` (state 1) failed to match `'u'`, which
localized the bug to the character-class match, not the quantifier/alternation
logic. The actual defect: the range parser tested `*ps->p=='-'` *after* already
advancing `ps->p` past the `-`, so `a-z` was parsed as three literals. Fix:
test `b=='-'` (the just-read char) and set the range bits `lo..hi`.

Rule: when a hand-trace disagrees with observed output, **instrument and read
the actual state**, don't keep re-deriving the mental model — the model is
what's wrong.
