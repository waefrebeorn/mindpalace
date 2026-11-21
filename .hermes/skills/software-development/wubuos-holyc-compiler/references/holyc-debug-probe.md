# HolyC Compiler Debug Probe Recipes

Copy these into `/tmp/*.c` and build against the tree at
`/home/wubu/.hermes/profiles/mind-palace/home/myseed`.

## 1. Standalone build (all compiler + jit objects)

```bash
JIT=src/jit COMP=src/compiler
gcc -O0 -g -I src/compiler -I src/jit -I src/runtime \
  src/jit/jit.c src/jit/wubu_x86.c src/jit/wubu_disasm.c src/jit/x86_regalloc.c src/jit/jit_minic.c \
  src/compiler/holyc_lexer.c src/compiler/holyc_parse.c src/compiler/holyc_codegen.c \
  src/compiler/holyc_codegen_emit.c src/compiler/holyc_codegen_expr.c \
  src/compiler/holyc_codegen_stmt.c src/compiler/holyc_codegen_api.c src/compiler/holyc_ptx.c \
  /tmp/probe.c -o /tmp/probe -ldl
```

Note: include paths are `-I src/compiler`, so `#include "holyc.h"` (not
`compiler/holyc.h`). Use `holyc_parser.h`/`holyc_lexer.h` directly.

## 2. Lexer probe (confirm tokenization)

```c
#include "holyc.h"
#include "holyc_lexer.h"
#include <stdio.h>
int main(void){
  HCLexer lex; hc_lex_init(&lex, "++x;");
  for (int i=0; i<10 && lex.tok.type != HC_TOK_EOF; i++){
    printf("tok=%d text='%s'\n", lex.tok.type, lex.tok.text);
    hc_lex_next(&lex);
  }
}
```

## 3. Hang detector (GDB SIGALRM backtrace)

```c
#include "holyc.h"
#include <stdio.h>
#include <signal.h>
#include <unistd.h>
int main(void){
  alarm(4);                       // fires SIGALRM if stuck
  int64_t r = hc_eval("{ I64 x = 5; ++x; }");
  printf("result=%lld\n", (long long)r);
}
```

```text
# gdbcmds.txt
set pagination off
handle SIGALRM stop print
run
bt 20
```

```bash
gdb -batch -x gdbcmds.txt /tmp/probe
# Infinite-loop frames show e.g. parse_block -> parse_stmt -> hc_ast_new
```

If the backtrace is inside glibc `malloc`/`memset` (not JIT code), the loop is
in the **C parser/codegen**, not the emitted machine code.

## 4. JIT crash byte-dump

Temporarily add to `hc_eval` just before `JIT_CALL(exec)`:

```c
fprintf(stderr, "[DBG code %zu] ", gen.code_size);
for (size_t _i = 0; _i < gen.code_size; _i++)
  fprintf(stderr, "%02x ", ((uint8_t*)exec)[_i]);
fprintf(stderr, "\n");
```

Decode by hand: `55`=push rbp, `48 89 e5`=mov rbp,rsp,
`48 b8 .. .. .. .. .. .. .. ..`=mov rax,imm64 (8 bytes),
`48 89 05 dd dd dd dd`=mov [rip+disp32],rax (global store),
`48 8b 85 dd dd dd dd`=mov rax,[rbp-disp32] (local load),
`48 ff c0`=inc rax, `48 89 85 dd dd dd dd`=mov [rbp-disp32],rax,
`5d`=pop rbp, `c3`=ret, `c9`=leave.

Garbage constant returned across many tests ⇒ missing `sub rsp,N` frame.
`[rip+00 00 00 00]` store ⇒ unpatched global relocation.

Remove the dump after diagnosing.

## 5. Parser bisect (which statement hangs)

```c
#include "holyc.h"
#include "holyc_parser.h"
#include "holyc_lexer.h"
#include <stdio.h>
#include <signal.h>
static void alrm(int s){ (void)s; _exit(2); }
int main(void){
  const char *cases[] = {"{ ++x; }","{ I64 x = 5; }","{ I64 x = 5; x; }",
                          "{ I64 x = 5; x++; }","{ I64 x = 5; ++x; }"};
  for (int i=0;i<5;i++){
    signal(SIGALRM, alrm); alarm(2);
    HCLexer lex; hc_lex_init(&lex, cases[i]);
    HCParser p; hc_parse_init(&p, &lex);
    HCASTNode *a = hc_parse_stmt(&p);
    alarm(0);
    printf("[%s] ast=%p has_error=%d\n", cases[i], (void*)a, p.has_error);
  }
}
```
