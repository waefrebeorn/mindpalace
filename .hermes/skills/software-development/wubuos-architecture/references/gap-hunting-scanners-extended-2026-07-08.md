# Extended Gap-Hunting Scanners (2026-07-08)

## Why these exist

The baseline scanner (`gap-hunting-scanner-2026-07-08.md`) only catches
`void-cast + return 0/-1` bodies. Once that class is closed (it is, as of
2026-07-08, except the intentional `#else` X11 stub), real form≠function gaps
hide in two other shapes the baseline misses:

1. **Real work but hardcoded return** — a function does loops/memcpy/computation
   yet still returns a literal `0`/`-1`/`-ENOSYS`/`NULL` instead of a computed
   result. (The proven `wubu_x86.c` class: 33 encoder fns returned hardcoded 0
   instead of byte counts. This session: `lvm_snapshot_create` returned hardcoded
   `-ENOSYS` instead of the `lvcreate` exit status.)
2. **No-op body with explicit `/* stub */` marker** — a function whose body does
   nothing real on its inputs, flagged by an inline comment. (This session:
   `bear_optimizer_step` had comment "This function is a no-op";
   `bear_optimizer_zero_grad` had `(void)opt;` with comment "Zero grads of
   registered params - stub".)

## The fastest signal: grep for the word "stub"

Before running any body scanner, grep for the marker. It finds the real gaps
with the fewest false positives — far better than the noisy out-param scanner
below.

```bash
grep -rnE 'stub|not implemented|placeholder|will not work|for later' src --include=*.c \
  | grep -v '_legacy_bak' | grep -viE 'provides stub|compiled with|wrapper' \
  | grep -iE 'return (0|-1|NULL)|void\)|/\* stub \*/'
```

Then for each hit, apply triage:
- Is it inside an `#else` hardware-absent block? -> NOT a gap.
- Is it an intentionally-empty lifecycle fn (`task_preempt_disable`)? -> NOT a gap.
- Is it a hosted-mode-correct return (anticheat `kernel_load` returns -1 in hosted
  mode and the test *asserts* -1)? -> NOT a gap.
- Otherwise -> real gap. Close it and add a regression test.

## Scanner A — real-work-but-hardcoded-return

Flags computing-named functions (get/len/size/count/encode/emit/serial/calc/
parse/find/.../forward/backward/gemm/conv/norm/...) whose body contains real
computation but where EVERY `return` is a literal constant.

```python
import os, re
src = '/home/wubu/.hermes/profiles/mind-palace/home/myseed/src'
susp = re.compile(r'(get|len|size|count|num|encode|emit|serial|calc|comput|'
                  r'measur|read|parse|find|index|resolve|write|send|recv|alloc|'
                  r'create|build|generate|estimate|predict|score|loss|forward|'
                  r'backward|gemm|conv|norm|dot|sum|max|min|sample|draw|render)', re.I)
hits = []
for root, dirs, files in os.walk(src):
    if '_legacy_bak' in root: continue
    for f in files:
        if not f.endswith('.c') or 'test' in f or 'stub' in f: continue
        p = os.path.join(root, f)
        try: lines = open(p, encoding='utf-8', errors='replace').read().split('\n')
        except: continue
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            m = re.match(r'^(?!.*\b(if|for|while|switch|do)\b)(?:static\s+)?'
                         r'(int|int64_t|uint\d+_t|size_t|ssize_t|float|double|long|'
                         r'unsigned|char\s\*)\s+(\w+)\s*\([^;]*\)\s*\{', line)
            if m:
                fn, j, depth = m.group(2), i+1, line.count('{')-line.count('}')
                body = []
                while j < len(lines) and depth > 0:
                    x = lines[j]; depth += x.count('{')-x.count('}')
                    if depth > 0: body.append(x.strip())
                    j += 1
                nb = [l for l in body if l and not l.startswith('//')
                      and not l.startswith('/*') and not l.endswith('*/')]
                rs = [l for l in nb if not l.startswith('(void)') and l != '}']
                rets = [l for l in nb if l.startswith('return')]
                const = [re.match(r'return\s+([^;]+);', r).group(1).strip()
                         for r in rets if re.match(r'return\s+([^;]+);', r)]
                if (rets and len(const) == len(rets) and
                        all(re.fullmatch(r'(-?\d+|0x[0-9a-fA-F]+|NULL|0\.0f|'
                                          r'0\.0|true|false)', c) for c in const)):
                    work = [l for l in rs if not l.startswith('return')]
                    comp = [l for l in work if any(k in l for k in
                            ('=', 'memcpy', 'for', 'while', 'strcpy', 'snprintf',
                             '+', '-', '*', '/', '<<', 'malloc'))]
                    if comp and susp.search(fn):
                        hits.append((p, i+1, fn))
                i = j
            else:
                i += 1
for g in sorted(hits): print(g[0].replace(src+'/',''), g[1], g[2])
print('candidates:', len(hits))
```

Caveat: this catches genuine cases (`lvm_snapshot_create`) but may miss functions
that compute into an out-param then `return 0` (those are fine — the 0 is success).
Always read the body before editing.

## Scanner B — out-param declared but never written (NOISY — candidate generator only)

**This scanner is a candidate generator, not a verdict.** It flags ~147 hits,
almost all false positives, because it does NOT recognize two common write forms:
- `snprintf(out, n, ...)`  (writes a string into the out buffer)
- `out->field = ...`       (writes a struct member)

So every config-loader / JSON-populator / list function (`wubu_settings.c`
`load_*`, `wubu_pkgmgr.c` `cb_*`, `oci_*_to_json`) gets falsely flagged. Use it
only to surface *candidates*, then read each one. The reliable signal remains the
explicit `/* stub */` marker combined with a void/empty body. The shape that
actually mattered this session (correctly surfaced): a function with an explicit
`/* ... stub */` comment whose body does nothing on its real inputs.

```python
import os, re
src = '/home/wubu/.hermes/profiles/mind-palace/home/myseed/src'
out_names = re.compile(r'^(out|o|dest|res|ret|result|output|num_?|count_?|len_?|'
                       r'size_?|n_?|written|read|got|found|status_?|rc_?|err_?)', re.I)
hits = []
for root, dirs, files in os.walk(src):
    if '_legacy_bak' in root: continue
    for f in files:
        if not f.endswith('.c') or 'test' in f or 'stub' in f: continue
        p = os.path.join(root, f)
        try: lines = open(p, encoding='utf-8', errors='replace').readlines()
        except: continue
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            m = re.match(r'^(?:static\s+)?[a-zA-Z_][\w\s\*]*?\s+(\w+)\s*\(([^;{]*)\)\s*\{', line)
            if m and '(' in line and '{' in line:
                fn = m.group(1); params = m.group(2)
                outs = []
                for pm in re.findall(r'(const\s+)?([\w\s\*]+?)\s*(\*+)\s*(\w+)\s*(?:,|$)', params):
                    is_const, ptype, stars, pname = pm
                    if stars.count('*') >= 2: outs.append(pname)
                    elif stars.count('*') == 1 and not is_const and out_names.match(pname): outs.append(pname)
                if not outs: i += 1; continue
                j = i + 1; depth = line.count('{') - line.count('}')
                body = []
                while j < len(lines) and depth > 0:
                    x = lines[j]; depth += x.count('{') - x.count('}')
                    if depth > 0: body.append(x)
                    j += 1
                txt = '\n'.join(body)
                written = [p for p in outs if re.search(r'\*\s*'+re.escape(p)+r'\b', txt)
                           or re.search(re.escape(p)+r'\s*\[', txt)
                           or (re.search(re.escape(p)+r'\s*=\s*(?!NULL)', txt))]
                if [p for p in outs if p not in written]:
                    nb = [b.strip() for b in body if b.strip() and not b.strip().startswith('//')]
                    work = [b for b in nb if not b.startswith('(void)') and not b.startswith('return')]
                    if any(k in b for b in work for k in ('=','memcpy','for','snprintf','malloc')):
                        hits.append((p.replace(src+'/',''), i+1, fn))
                i = j
            else:
                i += 1
for h in sorted(hits): print(h[0], h[1], h[2])
print('candidates:', len(hits))
```

## What 2026-07-08 closed via these scanners

| Function | Scanner | Before -> After |
|----------|---------|----------------|
| `lvm_snapshot_create` (`wubu_snapshot_fs.c`) | grep "stub" + Scanner A | `return -ENOSYS` -> real `lvcreate --snapshot` fork/exec |
| `bear_optimizer_step` (`bear_opt.c`) | grep "stub" (comment "no-op") | empty loop -> dispatch to per-param Adam/SGD/Muon |
| `bear_optimizer_zero_grad` (`bear_opt.c`) | grep "stub" (comment) | `(void)opt;` -> fills each param's grad with 0 |

## Lesson

The word "stub" in a comment is the single highest-signal marker. Grep for it
before running any body scanner — it finds real gaps fastest with the fewest
false positives. The out-param scanner is useful only as a last-resort candidate
generator after the marker grep and the baseline void-cast scanner come up empty.
