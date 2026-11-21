# Minimal native-backend harness (isolate x86-64/arm64 emitter bugs fast)

The full `make test_gauntlet` link compiles ~70 source files in ONE gcc invocation
(no `.o` caching) and takes 30-40 min. You cannot iterate on a backend emitter that
way. This harness links only ~6 files and validates a native backend's emitted code
in seconds.

## What it does
Builds a MIR program **directly** via the `wubu_mir_*` API (no HolyC frontend, no
optimizer — raw MIR = what the emitter consumes), runs it through
`wubu_isa_x86_64.compile` + `.run` under `alarm(10)` to catch infinite loops, and
prints the generated code bytes for decoding.

## Files (drop in repo root, e.g. `/home/wubu/wubuos/`)
- `loop_mir_test.c` — the test (constructs `while(i<10){s=s+i;i=i+1;} return s;`
  expecting 45; hexdumps `code`/`sz` after compile; `alarm(10)` around `.run`).
- `isa_stubs.c` — zero-init `const wubu_isa_driver_t wubu_isa_*` for the 13 drivers
  your test doesn't use (the driver table in `wubu_isa_driver.c` references all 14).
- `jit_stub.c` — minimal `jit_alloc_exec`/`jit_free_exec` (mmap RWX / munmap) so
  `x86_run` works WITHOUT pulling in the entire `jit.c` dependency tree (encoders,
  minic, etc.). `wubu_clear_cache` is already defined in `wubu_isa_driver.c` — do NOT
  redefine it (duplicate-symbol link error).

## Build + run
```sh
cd /home/wubu/wubuos
gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_HOSTED \
  -include wubu_gnu_compat.h -I src/compiler -I src/jit -I src/runtime \
  loop_mir_test.c isa_stubs.c jit_stub.c \
  src/compiler/wubu_mir.c src/compiler/wubu_mir_opt.c \
  src/compiler/wubu_mir_regalloc.c src/compiler/wubu_isa_driver.c \
  src/compiler/wubu_isa_x86_64.c -o loop_mir_test
./loop_mir_test          # stdout: result; stderr: n_spilled/frame/assign dump
```

## Debugging emitter crashes (SIGSEGV inside generated code)
1. Hexdump the emitted bytes (already in `loop_mir_test.c`) and decode by hand:
   prologue `55 48 89 e5 48 81 ec NN` → frame = NN. `movabs rN, imm64` =
   `49 bd <8 bytes>` (r13). `lea rsi,[rbp-NN]` = `48 8d b5 <disp32>`.
   `mov [rsi],rdi` = `48 89 3e`. `shl rax,3` = `48 c1 e0 03`.
2. Add a temporary `fprintf(stderr, ...)` block at the top of `x86_compile` that
   prints, per instruction: `op_name`, `dst/reg/stack`, `a/reg/stack`, `b/reg/stack`.
   This reveals the regalloc assignment (e.g. spilled vr shows `reg=-1` and its
   `.stack` value) — decisive for spill-framing bugs.
3. `gdb -batch -ex run -ex "info reg rax rdi rsi rsp rbp rip" -ex "x/5i \$rip"`
   on the harness: the faulting instruction + registers pinpoint whether a store's
   `rsi` is wild (bad `mem_off` / bad addr vr) or a spill reload read garbage.

## Pitfalls
- A segfault at `mov [rsi],rdi` with huge `rsi`/`rax` = the **frame is undersized**
  (spill slots or `mem[]` region extend below `rsp`) OR `mem_off` computed wrong.
  Check `n_spilled` and `mem_off` from the debug dump against the actual spill count.
- `--dump-asm` on the full gauntlet binary ALSO runs the code, so a hang there =
  the same loop bug; the minimal harness is faster to iterate because it skips the
  70-file link and lets you add `alarm()` + hexdump.
- `wubu_isa_driver.h` already declares `extern const wubu_isa_driver_t wubu_isa_x86_64;`
  — do NOT re-declare it in your harness (conflicting-qualifier error).
