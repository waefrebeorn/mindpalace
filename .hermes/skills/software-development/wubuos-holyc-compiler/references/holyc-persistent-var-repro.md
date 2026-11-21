# HolyC Persistent-Variable Repro (module-level global vs stack local)

Symptom: `I64 x = 123;` then `x + 10` returns garbage instead of `133`;
`test_holyd` "persistent variable across evals" fails. Also affects
"persistent function across evals" (`I64 sq(I64 n){...}` then `sq(7)`).

## Root cause (2026-07-07)
`gen_stmt` VAR_DECL chose global (data-section) vs local (stack) via
`is_module_level = (code_size==0 || n_locals==0) && !gen->has_prologue`.
But `wubu_holyd_eval` calls `emit_prologue()` BEFORE `gen_stmt()`, so
`has_prologue` is already true at module level → top-level `I64 x=123` was
emitted as a stack local (`mov [rbp-8], rax`) instead of a data-section
global. The symbol kept the stack offset; on the next eval the frame is
fresh/uninitialized, so `x` reads garbage.

## The fix
Add `bool in_function` to `struct HCGen` (holyc_types.h). Set it true just
before and false just after emitting the FUNC_DECL body in
`holyc_codegen_stmt.c`. Replace the discriminator with
`is_module_level = !gen->in_function`. Module vars now go to the data
section (global), persist across evals, and `x+10` → 133.

## Minimal standalone repro (mirrors wubu_holyd_eval, no daemon)
Drop into /tmp/repro_holyd.c, build, run. Expect PASS.

```c
#include <stdio.h> #include <stdlib.h> #include <string.h>
#include <stdint.h> #include <sys/mman.h>
#include "holyc_types.h" #include "holyc_codegen_internal.h"
/* same do_eval() shape as wubu_holyd_eval: lex -> parse -> hc_gen_init ->
   emit_prologue -> gen_stmt -> emit_epilogue -> run -> copy data back */
int main(void){
  HCCompiler c; memset(&c,0,sizeof(c));
  hc_lex_init(&c.lex,""); hc_parse_init(&c.parse,&c.lex); hc_gen_init(&c.gen);
  long a = do_eval(&c, "I64 x = 123;");
  long b = do_eval(&c, "x + 10");          /* expect 133 */
  do_eval(&c, "I64 sq(I64 n){ return n*n; }");
  long c2 = do_eval(&c, "sq(7)");          /* expect 49 */
  printf("x+10=%ld sq(7)=%ld\n", b, c2);
  return (b==133 && c2==49) ? 0 : 1;
}
```

Build (links JIT + codegen; jit_alloc_exec/jit_free_exec come from src/jit):
```bash
gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -I src/compiler -Isrc/jit \
  /tmp/repro_holyd.c src/compiler/holyc_lexer.c src/compiler/holyc_parse.c \
  src/compiler/holyc_codegen.c src/compiler/holyc_codegen_emit.c \
  src/compiler/holyc_codegen_expr.c src/compiler/holyc_codegen_stmt.c \
  src/compiler/holyc_codegen_api.c src/jit/jit_minic.c -o /tmp/repro_holyd \
  && /tmp/repro_holyd
```
(NOTE: jit_minic.c pulls in wubu_x86.h; if the link drags extra deps, just
run `make test_holyd` instead — it exercises the exact same path.)

## Verify
- `make test_holyd` → "persistent variable across evals" ✅, "persistent
  function across evals" ✅. (Counter prints 33/32 — harness off-by-one, not
  a failure; exit 0.)
- Run FULL gate: `make clean && make runtime && make hosted && make test`.
