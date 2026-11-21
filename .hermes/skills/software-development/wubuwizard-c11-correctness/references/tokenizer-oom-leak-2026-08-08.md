# Tokenizer OOM crash — 2026-08-08 (the gateway-crashing leak)

## The incident
`wubu_pond2tok` (new corpus-pipe tool: ponds → trainer `.tok` streams) was
processing a 1MB `docs/` tree and got SIGKILLed after ~76s. dmesg:

```
[322964.436426] hermes invoked oom-killer ... oom_score_adj=200
[322964.441237] Out of memory: Killed process 611390 (wubu_pond2tok)
               total-vm:17611608kB, anon-rss:13774584kB
```

**17.6GB total-vm / 13.7GB anon-rss on a 1MB input.** The gateway crashed
with it. Lesson: exit code 137 (SIGKILL) → `dmesg | grep -i oom` first.

## Root cause (three compounding bugs, all in the tokenizer pipe)

### Bug 1 — cap-exit loop leak in `wubu_tok_hf_encode`
```c
for (int i = 0; i < n && cnt < max_ids; i++) {
    int id = vocab_find(t, syms[i]);
    if (id >= 0) out_ids[cnt++] = id;
    free(syms[i]);          // only reached while cnt < max_ids
}
```
Once `cnt` hits `max_ids`, the loop exits and every `syms[i]` past the cap
leaks. On chunked input the leak is O(n²). ASan on a 50-pass probe of one
28KB file:
```
Direct leak of 169494450 byte(s) in 78939400 object(s)
    #1 local_strdup  src/wubu_tokenizer_hf.c:25
    #2 wubu_tok_hf_encode  src/wubu_tokenizer_hf.c:497
```
**78.9M allocations leaked in 50 passes.** Fix: free unconditionally,
gate only the output write.

### Bug 2 — non-NUL-terminated chunk windows → O(n²) work
`pond2tok` fed `buf + off` (256-char window) to the encoder, but the only
NUL was at the end of the whole buffer. `strlen(buf+off)` walked the ENTIRE
remaining file every chunk → every chunk re-processed the tail → O(n²/512)
work AND a growing leak. Fix: NUL-terminate each window, restore after.

### Bug 3 — `j_skip` leaked every skipped JSON string
`j_skip` called `j_str(j)` (malloc) for string values and never freed it.
Fix: `char *s = j_str(j); free(s);`

## Debugging path (the recipe)
1. Exit 137 + long kernel time → `dmesg | grep -i oom` confirms OOM-kill,
   names the task, shows the balloon.
2. Small bounded probe + `-fsanitize=address -O0 -g` +
   `ASAN_OPTIONS=detect_leaks=1` → LeakSanitizer summary with the allocation
   count and stack. `78.9M allocations` in 50 reps is the smoking gun.
3. The leak stack points at `local_strdup` inside encode — read the loop
   that frees, spot the `&& cnt < max_ids` terminator.
4. Fix, re-run ASan: 78.9M → 10 (remaining j_skip leak) → fix → 0.
5. Rebuild `-O2`, re-run the tool: 76s+OOM → 0.067s for 31 files.
6. Scale proof: 32,581 files / 621M tokens in 51s, max RSS 4.5MB
   (`/usr/bin/time -v` for RSS).

## Also fixed in the same file
- **Vocab hash**: `vocab_find` was a linear scan over 16384 entries per
  byte → O(16384·n). Added an FNV-1a open-addressing hash (65536 buckets)
  built once at load. 10KB file: ~1s → 7ms. Same pattern as the existing
  pair→rank BPE hash.

## Verified .tok output
BOS=0x0200 (id 2), byte tokens, EOS framing — matches `wubu_tokenc` format
the trainer (`wubu_train_cli`) consumes.
