# ASan/UBSan build recipe for wubuwizard + minimal-repro debugging

How to actually get a sanitizer trace out of the wubuwizard C11 engine
(learned 2026-08-03 while hunting a teardown double-free in the growth
operator; the full bug story is P28 in SKILL.md).

## The Makefile overrides CFLAGS from the environment — you cannot inject flags via env vars

`CFLAGS = ...` (plain `=`) inside the Makefile beats `CFLAGS=... make`.
Passing `CFLAGS="-g -fsanitize=address"` as an env prefix is silently
ignored; the binary comes out `-O3 -march=native -ffast-math` with no
sanitizer. Options that WORK:

1. **Build the target by hand with the source list from the Makefile** —
   the reliable path (no Makefile surgery, no risk of clobbering the
   tracked build):
```bash
cd /home/wubu/wubuwizard
gcc -g -O2 -fsanitize=address -static-libasan -fno-omit-frame-pointer \
    -I include -fopenmp -o /tmp/wubu_train_asan \
    tools/wubu_train_cli.c src/wubu.c src/wubu_train.c \
    src/wubu_backprop.c src/wubu_moe2.c src/safetensors_reader.c \
    src/wubu_grow.c src/wubu_plateau.c -lm -fopenmp
```
2. `make clean && make wubu_train CFLAGS=...` — command-line overrides do
   work, but `make clean` deletes the binary and the old queued background
   jobs then die with `EXIT: 127` "No such file or directory" — harmless
   noise, don't chase it.

## Pitfalls that burn you

- **`-O0` ASan is unusably slow** for the training CLI: a 420-step run
  times out at 25 min. Use `-O2` (near-native speed, still catches the bug).
- **`-static-libasan` matters**: without it the ASan runtime can fail to
  attach ("AddressSanitizer can not provide additional info", FPE-only
  reports). Link it statically.
- **stdout is fully buffered**: redirect to a file and you see nothing
  until the process exits or the buffer fills. Use `stdbuf -oL -eL` so
  step logs flush live (`timeout 1500 stdbuf -oL -eL ./wubu_train ... > log 2>&1`).
- **`--ckpt 0` divides by zero** (`step % ckpt_every` → FPE, ASan reports
  it as `AddressSanitizer: FPE tools/wubu_train_cli.c:264`). Always pass
  `--ckpt 50` in test runs; `--grow-check 0` is fine.
- **Minimal repro beats the full CLI.** The teardown crash reproduced at
  `--steps 100 --grow-check 50` (ONE growth, 2→3 layers) — a 90-second
  run. Even better: a standalone harness (`tools/test_grow_free.c`) that
  allocates model+train state like the CLI, does 4 grows, and calls the
  frees — crashes in SECONDS under ASan with the exact double-free site.
  Always try to shrink to the smallest harness before burning hours of
  ASan wall-time.
- **glibc malloc debug as a fast pre-check**: `MALLOC_CHECK_=2
  MALLOC_PERTURB_=42` changes the error text (`free(): invalid pointer`
  → `munmap_chunk(): invalid pointer`) which tells you the chunk was
  already unmapped — a quick signal before the slow ASan build.

## Reading the trace

ASan's `previously allocated by` / `freed by thread T0 here` blocks name
the exact allocation and free sites. In the growth double-free:
- `attempting free on address which was not malloc()-ed ... inside of
  9243648-byte region ... previously allocated ... zero_block` = freeing a
  sub-pointer of a single-calloc block (per-field free vs one-calloc layout).
- A second `free` at the SAME line = aliased struct copy (two slots own
  one region).

## The minimal-harness template

Copy `tools/test_grow_free.c` pattern: init model/train exactly like the
CLI loader (all 12 block slots, selectors, embedding), set `n_layers = 2`,
loop 4 grows at `pos = n_layers/2` passing `pre_layers = n_layers - 1` to
`wubu_train_grow`, then `wubu_train_free` + `wubu_free`. Build with the
recipe above; `ALL CLEAN` = pass.
