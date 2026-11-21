# Training-path bug family — 2026-08-09 session transcript (P48)

The "training has issues" session. Root cause: a pre-existing bug family in the
load/train path that only showed once we stopped using the pre-trained 448 seed and
tried fresh/agnostic runs. All verified fixed; see P48 for the rules, this file for
the debug path.

## Symptom chain
1. `make test_diag` failed to LINK: `undefined reference to 'WUBU35_DIMS'`.
   Root: the Makefile rule linked `src/wubu.o` (which references the runtime
   dims global) WITHOUT `src/wubu35_dims.o`. The revolver dims landed but every
   training-tool rule rotted: test_wubu_train, wubu_train, wubu_live_learn,
   wubu_boot, wubu_train_gpu, test_wubu, test_backprop, wubu_cli, test_wubu_save,
   test_diag. Swept with a sed one-liner appending `src/wubu35_dims.o` to each
   rule's dependency list; test_diag additionally needed `-fopenmp`.
2. `wubu_load` crashed `embedding.weight has 7340032 elems, expected 0` — the
   caller never probed dims. Every training tool did the probe dance or crashed.
   Fix: probe inside wubu_load, set runtime dims from the probe's `ckpt_*` fields
   (the file's real, unaligned geometry), delete the aligned-padding dual path.
3. After the loader fix: `corrupted size vs. prev_size` / ASan
   `attempting free on address which was not malloc()-ed ... 64 bytes after
   128-byte region`. Root: q_norm/k_norm allocated as WUBU_ROPE_DIM (32 for the
   448 seed) but written/freed as WUBU_HEAD_DIM (64) — the per-head norms were
   under-allocated. Both wubu_train.c (alloc + zero) and wubu_backprop.c
   (norm_slot_weight) had the bug.
4. Also in the sweep: hardcoded 448/64/1228/2456/16384 in wubu_train.c alloc +
   wubu_backprop.c grad-clip/scale/Muon/AdamW. Any model with different dims
   crashed in backprop. All replaced with WUBU_* macros.

## Verification
- Old 448 seed loads AND trains through the agnostic loader: loss 11.36 on a real
  microbatch, clean free, exit 0.
- ASan clean on the tokenizer (j_skip leak fixed: 832 bytes → 0).
- test_diag passes (oracle 7 skips cleanly without a 512-aligned checkpoint —
  the SD seed is 448-dim and predates Theory/08 alignment; probe + set then
  graceful skip when load can't succeed).
- test_fs_trainer (Phase 8): files → coherence 0.408 (real, bounded) → GROW
  signal → 14/14 KV-FS gates green.
- `make all` 0 errors after the whole sweep.

## Debugging tools that worked
- gdb on the SIGFPE: `idiv %esi` with `esi=0` pinpointed the modulo/division by
  `full_every=0` / `selectors=0` in synthetic-model tests.
- ASan with `-fno-omit-frame-pointer` gave the exact leak site: j_skip → j_str
  at line 107/114 (the discarded malloc).
- The dims probe (tools/dimprobe.c pattern): prints vocab/dim/layers/heads/ffn
  + the ckpt_* truth — the fastest way to confirm what a checkpoint actually is.
