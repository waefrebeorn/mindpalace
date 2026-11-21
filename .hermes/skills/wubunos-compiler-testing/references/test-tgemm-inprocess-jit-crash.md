# test_tgemm / dump-asm in-process JIT crash — RESOLVED 2026-10-11

## Symptom (historical)

`./test_tgemm 24 24 24` and `./gauntlet_runner --dump-asm` on
programs with stores or user calls segfaulted; the forked gauntlet
suite masked it (children `_exit` before the C aftermath).

## Root cause chain (all fixed in 560d0ce + 561adf1)

1. **Double frame unwind**: in-func-body `MIR_RET` emitted
   `leave; pop rbx; ret` while the callee shares the caller's
   frame under the flat-register model. Fixed by an entry-mode-
   aware RET: a function entered via the entry trampoline `jmp
   rel32` (funcs[0] when funcs[0].start == 0) owns fn()'s frame
   and runs the full teardown; a function entered via MIR_CALL is
   a callee return (bare `ret`, caller tears down).
2. **T_GEMM helper got mem=NULL**: the emitter embedded
   `prog->mem` (NULL at compile time). Fixed: `mov rdi, rbx`
   (runtime base from `wubu_jit_mem_ptr`).
3. **K stack arg in the wrong slot**: pad was pushed ABOVE the
   arg, leaving K at [rsp+16] instead of [rsp+8]. Fixed: pad
   below (`sub rsp,8; push K; call`).
4. **`48 BE` exec-buffer scan in x86_run** corrupted legitimate
   `movabs rsi, imm64` const loads (48 B8+r includes 48 BE).
   Removed.
5. **r12-r15 clobbered without save** (the crash that survived
   1-4): the allocator assigns vr homes to r12-r15 and the JIT
   never saved them. A -O2 caller keeping a live local in r14
   across `drv->run` (test_tgemm's `jmem`) saw it replaced by a
   compiled-code pointer -> double free / invalid pointer. Fixed:
   prologue pushes r12,r13,r14,r15 (alongside rbx); frame-owning
   epilogues pop them.
6. **rbp anchoring**: all six callee-saved pushes (rbp, rbx,
   r12-r15) happen BEFORE `mov rbp,rsp`, so rbp points at the r15
   slot and spills (rbp-negative) never overlap the pushes. The
   epilogue is `mov rsp,rbp; pop r15; pop r14; pop r13; pop r12;
   pop rbx; pop rbp; ret`. A plain `leave` there pops the r15
   slot into rbp and the final ret jumps to the saved rbp value
   (a stack address — observed as execution inside the
   environment strings on the stack).

## Verified final state

- `tools/test_tgemm 24 24 24`: correctness 576/576 vs naive C,
  exit 0.
- wubunos `make test`: ALL TESTS PASSED 195/195, 0 segfaults.
- `gauntlet_runner --core`: 3458 pass / 0 fail / 0 error.
- `--dump-asm` repros: `result=11` (array stores), `result=49`
  (user call) — no crash.
- Minimal T_GEMM harness (compile + run + free): JIT RESULT=24,
  exit 0.

## Diagnostic lessons

- The `--dump-asm` hex dump prints 16-bit words BIG-endian in
  memory order; reconstructing them little-endian byte-swaps
  every pair and produces phantom instructions (one bogus
  "store" chased for an hour was pure reconstruction artifact).
- A hardware watchpoint on `&exec`'s slot never firing while the
  value "changes" means gdb reads different spill slots at
  different lines — do not trust a single-slot watchpoint as
  proof of no-write.
- gdb bt through a broken stack chain (rip in the env strings)
  shows garbage frames; trust the register dump (rdi=rbx=result)
  and the constant crash rip over the unwinding.
- The forked gauntlet suite masks in-process JIT bugs: the child
  runs the JIT and `_exit()`s without the C aftermath. Any
  in-process caller (test_tgemm, dump-asm) is the real test.
