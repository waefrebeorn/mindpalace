# HolyC Global-var SIGSEGV Fix (2026-07-07)

Two independent bugs made `hc_eval` on ANY top-level var-decl crash
(`{ I64 x = 5; x; }` → SIGSEGV before printing anything; `test_holyc` died at
the first Inc/Dec case `{ I64 x = 5; ++x; }`). Both are pre-existing (reproduce
at `git stash` HEAD).

## Symptom
`gdb -batch -ex run -ex "x/12i \$pc-10" --args ./src/compiler/holyc_test` shows:
```
rip  0x7ffff7fbc015
rax  0x5                       # value is correct up to the store
=> 0x...015: mov %rax,0x9(%rip) # 0x7ffff7fbc025  <- the CRASH (RX page write)
   0x...01c: mov 0x2(%rip),%rax
   0x...023: leave
   0x...024: ret
```
The faulting PC is INSIDE the JIT buffer at the `mov [rip+disp], rax` store.
`rax=5` (right value) → the crash is the store hitting a read-only page, not
bad codegen.

## Root cause A — `jit_lock_exec` makes data section RX
`jit_alloc_exec` `mmap`s RWX. `hc_eval` then called `jit_lock_exec(exec,total)`
(`mprotect` → `PROT_READ|PROT_EXEC`) over the WHOLE code+data page. A module-level
global stores into the data section at runtime → SIGSEGV on the write.
`wubu_holyd_eval` never locks → globals worked there.
FIX (holyc_codegen_api.c, `hc_eval`):
```c
if (gen.data_size == 0) {
    jit_lock_exec(exec, gen.code_size + gen.data_size);
}
/* else: keep page RWX so runtime global stores succeed */
```

## Root cause B — Inc/Dec and &x emitted stack-only `[rbp-off]`
Module-level `VAR_DECL` → data section, `off <= 0`, `global_offset = -off`.
The PRE_INC/PRE_DEC/POST_INC/POST_DEC and ADDR (`&x`) cases in
`holyc_codegen_expr.c` only emitted `mov rax,[rbp-off]` / `lea rax,[rbp-off]`.
For a global, `off` is 0 or negative → `mov [rbp - 0]` / `lea [rbp+offset]` =
bogus stack slot, and no `global_patches` entry was recorded.
FIX: dispatch on `off <= 0`:
- load  -> `emit_global_load_rax(gen, go)`  (RIP-relative `48 8B 05 disp32`)
- store -> `emit_global_store_rax(gen, go)` (RIP-relative `48 89 05 disp32`)
- &x    -> `lea rax,[rip+disp32]` (`48 8D 05 disp32`) -- returns the DATA-SECTION
          RUNTIME address so a later `*p` derefs the actual global.
All three helpers record `global_patches[]` with `patch_pos = code_size + 3`
(the disp32 start; instruction is 7 bytes: REX+op+modrm+disp32).
Stack locals (`off > 0`) keep the existing `[rbp-off]` path.

## Patch formula (applied in BOTH hc_eval and wubu_holyd_eval)
```c
for (i ...) {
    size_t pp  = gen.global_patches[i].code_patch_pos;   /* = code_size+3 at emit */
    size_t go  = gen.global_patches[i].global_offset;
    int32_t d  = (int32_t)(gen.code_size + go - pp - 4);
    *(int32_t*)((uint8_t*)exec + pp) = d;
}
```
RIP-after-instruction = `pp + 4`; target = `exec + code_size + go`; so
`d = (code_size + go) - (pp + 4) = code_size + go - pp - 4`.
Verified: `{ I64 x=5; ++x; }`=6, `{ I64 x=5; x++; }`=5,
`{ I64 x=42; I64 *p=&x; *p; }`=42, `I64 g=5; g++; g;`=6.

## Minimal repro (build standalone, link jit.c+wubu_x86.c+jit_minic.c+wubu_disasm.c)
```c
#include "holyc.h"
int main(void){
  printf("A { I64 x=5; x; }     = %lld\n", (long long)hc_eval("{ I64 x = 5; x; }"));
  printf("B { I64 x=5; ++x; }   = %lld\n", (long long)hc_eval("{ I64 x = 5; ++x; }"));
  printf("C { I64 x=42; I64 *p=&x; *p; } = %lld\n",
         (long long)hc_eval("{ I64 x = 42; I64 *p = &x; *p; }"));
  return 0;
}
```
`gcc -O0 -g -std=c11 -Isrc/compiler -Isrc/jit -o /tmp/r /tmp/r.c \
  src/compiler/holyc_*.c src/jit/jit.c src/jit/wubu_x86.c \
  src/jit/jit_minic.c src/jit/wubu_disasm.c -ldl`

## Gate
`make test_holyc` -> 84/84. Full `make test` green.
