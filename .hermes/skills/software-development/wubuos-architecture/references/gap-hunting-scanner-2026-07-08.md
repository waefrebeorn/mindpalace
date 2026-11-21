# Gap-Hunting Python Scanner (2026-07-08)

## Problem
BATTLESHIP.md gap counts are hypotheses, not ground truth. Naive `grep '(void)'`
flags 140+ hits in VSL syscall files that are ALL intentional (6-register dispatch
convention). Real gaps need body-content analysis, not void-cast counting.

## Scanner Script

This Python script walks the entire `src/` tree, finds function definitions with
opening brace on same line, collects the body, and flags functions whose body
contains ONLY void-casts + `return 0;` / `return -1;`.

```python
import os, re

src_dir = '/home/wubu/.hermes/profiles/mind-palace/home/myseed/src'
real_gaps = []

for root, dirs, files in os.walk(src_dir):
    if '_legacy_bak' in root:
        continue
    for f in files:
        if not f.endswith('.c') or 'test' in f or 'stub' in f:
            continue
        path = os.path.join(root, f)
        with open(path) as fh:
            content = fh.read()
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Match function definition with opening brace on same line
            m = re.match(r'^(?:static\s+)?(?:int|int64_t|uint\d+_t|void|bool|size_t'
                         r'|char\s*\*|double|float|long|unsigned)\s+(\w+)\s*'
                         r'\(.*\)\s*\{', line)
            if m:
                fn_name = m.group(1)
                body_lines = []
                j = i + 1
                brace_depth = line.count('{') - line.count('}')
                while j < len(lines) and brace_depth > 0:
                    bl = lines[j]
                    brace_depth += bl.count('{') - bl.count('}')
                    if brace_depth > 0:
                        body_lines.append(bl.strip())
                    j += 1
                non_comment = [l for l in body_lines if l and
                               not l.startswith('//') and
                               not l.startswith('/*') and
                               not l.endswith('*/')]
                real_stmts = [l for l in non_comment
                              if not l.startswith('(void)')]
                if (len(real_stmts) == 1 and
                    real_stmts[0] in ('return 0;', 'return -1;',
                                      'return 0; /* stub */',
                                      'return -1; /* stub */') and
                    any('(void)' in l for l in non_comment)):
                    real_gaps.append((path, i+1, fn_name,
                                     ' | '.join(body_lines[:3])))
                i = j
            else:
                i += 1

for g in sorted(real_gaps):
    relpath = g[0].replace(src_dir + '/', '')
    print(f'{relpath}:{g[1]} {g[2]} — {g[3]}')
print(f'\nTotal: {len(real_gaps)} real gaps found')
```

## Results (2026-07-08 baseline)

After closing 42 gaps across v23→v25 sessions, the scanner found 3 remaining:

```
src/bear/bear_nn.c:957 bear_checkpoint_save — CLOSED v25
src/bear/bear_nn.c:962 bear_checkpoint_load — CLOSED v25
src/bear/bear_ppo.c:811 bear_trainer_save — CLOSED v25
src/bear/bear_ppo.c:816 bear_trainer_load — CLOSED v25
src/hosted/wubu_metal.c:1103 wubu_x11_set_mode — #else stub (NOT a gap)
src/kernel/libc.c:143 vsprintf — CLOSED v25
src/runtime/styxfs.c:1121 styxfs_closedir — REMAINING (valid gap)
src/runtime/styxfs.c:1127 styxfs_readdir_r — REMAINING (valid gap)
src/runtime/wubu_anticheat.c:294 wubu_anticheat_proton_config — CLOSED v25
```

## Triage Rules

After running the scanner, manually triage each hit:

1. **Is it in a `#else` block?** → NOT a gap (compile-time absent hardware).
2. **Does the function name end in `_shutdown` / `_flip` / `_close` and live in `wubu_metal.c`?** → NOT a gap (backends not compiled in).
3. **Is the function called by real code downstream?** → IS a gap (e.g., `vsprintf` called by `sprintf` — form≠function).
4. **Does the struct it takes have real downstream consumers?** → IS a gap (e.g., `bear_checkpoint_save` — RL training stack expects checkpoints).
5. **VSL syscall handlers** — the scanner does NOT flag these because they have real `vsl_get_host_fd()` / `vsnprintf()` / `strncpy()` calls in the body, even though they void-cast params d,e,f. The body-content check correctly distinguishes them from stubs.

## Bear Checkpoint Binary Format (v25)

The `bear_checkpoint_save` implementation uses this file layout:

```
Offset  Size   Field
0       4      magic "WUBR" (0x52425557 LE)
4       4      version (uint32 = 1)
8       4      type (int32 = BearNetType)
12      4      num_layers (int32)
16      4      obs_dim (int32)
20      4      act_dim (int32)
24      4      act_discrete (int32)
28      4      hid_size (int32)
32      4      has_logstd (int32, 1 if logstd != NULL)
36      4      logstd_fixed (float)
40      var    per-layer: w_rows, w_cols, b_len, weight_data, bias_data
             (repeats num_layers times)
       var    if GRU: gru_count=9, then 9×(rows, cols, data)
       var    if has_logstd: act_dim floats
```

Trainer checkpoint sidecar format: trainer scalar state + PPO config + policy_ok flag
pointing at `.policy` file.