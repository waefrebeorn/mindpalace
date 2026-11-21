# Native backend variable gap (x86-64 / arm64) — `--core` is misleading

## What `--core` 247/247 does NOT prove
The scorecard in SKILL.md (13/14 targets = 247/247 on `--core`) is real **for the
`--core` test subset**, but that subset does NOT exercise MIR variables. The full
19,088-test gauntlet (suites like `comprehensive`, `control`, `memory`) DOES use
`MIR_LOAD`/`MIR_STORE` (variable reads/writes, `while`/`for` loops, arrays).

## Root finding (2026-08-19)
Only **x86-64, arm64, ptx** are `WUBU_ISA_NATIVE`. The other 11 are
`WUBU_ISA_INTERPRETED` and execute canonical MIR via `wubu_mir_interp()` — which
handles `MIR_LOAD`/`MIR_STORE` against its flat `mem[]` array. So those 11 always
work for variables.

The native backends, however, have **no `case MIR_LOAD` / `case MIR_STORE`** in their
emitter switch. Confirmed by grep across `wubu_isa_x86_64.c` and `wubu_isa_arm64.c`
(24 `case MIR_` each, none for LOAD/STORE). Consequence:
- x86-64 `--dump-asm` on `while (i<10){...}` returns garbage / **infinite-loops**
  (the hang that blocked the full gauntlet child). `MIR_STORE` is silently dropped
  by the `switch` `default`, so the loop variable never updates.

## The memory model
`wubu_mir_alloc(p, n)` returns a `MIR_CONST` vr holding a **cell index**
(`base = total_mem+1`; addr 0 reserved as null). `MIR_LOAD dst,addr` =
`dst = mem[addr]`; `MIR_STORE addr,val` = `mem[addr] = val`. The interpreter does
this in C via a flat `int64 mem[]` indexed by the cell index. A native backend must
replicate this with a stack-resident `mem[]` region + emit `lea rsi,[rbp-mem_off]` +
`shl rax,3` + `add rsi,rax` + `mov [rsi],rdi` / `mov dst,[rsi]`.

## RESOLVED — x86-64 JIT memory base fix (2026-08-28)

The x86-64 JIT's `MIR_LOAD`/`MIR_STORE` emitted `movabs rsi, p->mem` at compile time, but `p->mem` is NULL when `wubu_mir_init` zeroes the struct. **Fix applied:**
1. `holyd_mir_eval.c`: `driver->run(code, csize, (int64_t)prog->mem)` — pass mem base as arg.
2. `wubu_isa_x86_64.c`: `x86_run` patches emitted code at runtime — scans for `48 BE <imm64>` (movabs rsi, imm64) and replaces with `48 89 F3` (mov rsi, rbx), where rbx holds the mem base from SysV arg rdi.
3. Verified: x86-64 memory test now passes (was SIGSEGV).

## x86-64 JIT entry trampoline fix (2026-08-28)

The entry trampoline (`jmp rel32` over function bodies to main code) was emitted
unconditionally when `p->n_funcs > 0`. But in the HolyD MIR layout, main code comes
FIRST (indices 0..funcs[0].start-1), then function bodies. The trampoline jumped
to `entry_off = (size_t)-1` (never set because `i` never equals `max_func_end`),
causing a jump to garbage → SIGSEGV.

**Fix:** only emit trampoline when function bodies start at index 0:
```c
// WRONG: if (p->n_funcs > 0) { ... }
// RIGHT: if (p->n_funcs > 0 && p->funcs[0].start == 0) { ... }
```

## x86-64 JIT mem allocation fix (2026-08-28)

`prog->mem` is NULL when `wubu_mir_init` zeroes the struct. The JIT embeds `p->mem`
as an absolute immediate in `movabs` instructions. Since `prog` is `const` in
`hd_run_prog`, we allocate mem and pass a mutable copy:

```c
int64_t *mem_ptr = prog->mem;
if (mem_ptr == NULL) {
    int64_t mem_hi = prog->total_mem;
    if ((int64_t)(prog->next_vr_hi) - 1 > mem_hi) mem_hi = (int64_t)(prog->next_vr_hi) - 1;
    int64_t mem_size = (mem_hi < 1) ? 1 : (mem_hi + 1);
    mem_ptr = (int64_t *)calloc((size_t)mem_size, sizeof(int64_t));
}
wubu_mir_prog_t prog_copy = *prog;
prog_copy.mem = mem_ptr;
driver->compile(&prog_copy, &code, &csize);
```

## Remaining gap: HolyD function-call frontend (7 WRONG tests)

The 7 WRONG tests in `test_mir_battery` are **pre-existing HolyD frontend bugs**, not JIT bugs:
- `func 2 params`, `multi-arg call`, `ptr arith`, `array init`, `float add`, `scope shadow`, `comma op`
- These fail identically with the interpreter (`hd_eval_mir(src, NULL)`), proving the bug is in HolyD→MIR lowering, not in any backend.
- **x86-64 JIT MIR_CALL is implemented** (`call rel32` + return-address stack). The interpreter's MIR_CALL is a stub.

## RESOLVED — x86-64 JIT register mapping + patch offset (2026-08-30)

Three critical bugs fixed in `wubu_isa_x86_64.c`:

### Bug 1: Register mapping mismatch
`emit_mov_reg(&e, 0, X)` mapped allocator register 0 (r10) not rax (x86 reg 0).
ALL arithmetic/comparison/LOAD/STORE/JZ/JNZ/NEG/NOT used wrong registers.
**Fix:** New helpers `emit_mov_rax_from_vr`, `emit_mov_rdi_from_vr`,
`emit_mov_vr_from_rax` that bypass the VR-to-reg mapping.

### Bug 2: Patch rel32 off-by-one
Jump rel32 calculation used `pos + 5` instead of `pos + 4`. Since `pos` is the
start of the rel32 field, the next instruction is at `pos + 4`. This caused all
forward jumps to land 1 instruction too late.
**Fix:** Changed to `pos + 4` for both JZ/JNZ/JMP and CALL rel32 patches.

### Bug 3: REX bit swapped in LOAD
`rex(&e,1,0,0,reg_needs_rex(sd))` put the extend bit in REX.B (rm field) instead
of REX.R (reg field). Loads into r14/r15 read from wrong address and corrupted rsp.
**Fix:** `rex(&e,1,reg_needs_rex(sd),0,0)`.

### Bug 4: Peephole breaks jump targets
`x86_peephole_optimize()` runs AFTER rel32 patching and can shrink instructions,
invalidating jump offsets.
**Fix:** Skip peephole when `n_patches > 0`.

### Gauntlet build fix
The `gauntlet` Makefile target was missing `wubu_isa_vulkan.c`,
`wubu_isa_x86_64.c`, `wubu_isa_spirv.c`, `wubu_spawn.c` in its link.
Also removed conflicting `jit_stub.c` (OS repo's `jit.c` provides same symbols).

## Current test gate state (2026-08-30)
- MIR battery: 69/69 PASS
- MIR float: 3/3 PASS
- Softfloat: 906/906 PASS
- ELF64 cubin: PASS
- x86-64 gauntlet --core: **246/247 pass** (was 245/247 pre-fix)
  - Previously: `stress_signed_overflow` failed (64-bit JIT doesn't emulate 32-bit overflow)
  - Now: FIXED via `movsxd rax,eax` truncation after integer arithmetic
  - Remaining: `stress_fib` crash (pre-existing, separate issue)
- ISA driver matrix: x86-64 PASS, 8086/m68k/6502/riscv/z80/mips/8051/avr/pic PASS, arm64 COMPILE FAIL (expected on x86 host)

## x86-64 JIT debugging methodology (2026-08-30)

When debugging x86-64 JIT codegen bugs, this isolation workflow is effective:

1. **Minimal MIR program**: Write a tiny MIR program via `wubu_mir_*` API (not HolyD frontend) to isolate the exact instruction sequence triggering the bug. Example:
   ```c
   wubu_vr_t a = wubu_mir_const(&prog, 5);
   wubu_vr_t b = wubu_mir_const(&prog, 3);
   wubu_vr_t c = wubu_mir_binop(&prog, MIR_ADD, a, b);
   wubu_mir_ret(&prog, c);
   ```

2. **Compare interpreter vs JIT**: Run both `wubu_mir_interp()` and `jit->compile()`+`jit->run()` on the same MIR program. If interpreter passes but JIT fails, the bug is in the JIT codegen, not the MIR.

3. **Hexdump JIT code**: Write JIT bytes to a file and disassemble with `objdump -D -b binary -m i386:x86-64`. This reveals wrong register encodings, incorrect rel32 offsets, and swapped REX bits.
   ```c
   FILE *f = fopen("/tmp/jit_code.bin", "wb");
   fwrite(code, 1, code_size, f);
   fclose(f);
   ```

4. **GDB backtrace**: Run JIT under GDB to catch SIGSEGV location:
   ```
   gdb -batch -ex run -ex bt ./test_program
   ```

5. **Debug prints in JIT**: Add `f(stderr, ...)` in `wubu_isa_x86_64.c` to trace label offsets, patch positions, and register assignments during compilation. Remove after fixing.

6. **Incremental test gate**: After each fix, run the minimal test first, then MIR battery (69/69), then gauntlet --core (245/247).
