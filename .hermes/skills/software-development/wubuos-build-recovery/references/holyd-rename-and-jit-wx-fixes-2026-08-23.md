# holyd rename integration + JIT W^X test-target fixes (2026-08-23)

Session that integrated the wubunos `holyc_* → holyd_*` rename into wubuos,
and fixed a family of "test segfaults right after clean link" failures.

## Failure class 1: stale names after repo-wide rename
wubunos renamed every frontend file `holyc_* → holyd_*` (git rename history
proves it: R100 holyc.c→holyd.c etc.). wubuos still referenced the old names
in three layers:

1. **mk/objects.mk** — `COMP_OBJS` listed `$(COMP)/holyc_lexer.o ...`. Symptom:
   `make compiler` fails with `No rule to make target 'holyc_lexer.o'` or
   compiles nothing and links with undefined refs. Also missing every module
   added in recent waves (softfloat, cubin, regalloc, interp, pic/amdgpu
   drivers). Fix: rewrite COMP_OBJS to current filenames + add new modules.
2. **mk/tests.mk** — 9 targets carried inline `$(COMP)/holyc_*.c` source
   lists. Symptom: `cc1: fatal error: src/compiler/holyc_codegen.c: No such
   file or directory`. Fix: define ONE canonical var in mk/vars.mk:
   ```make
   HOLYD_SRC = $(COMP)/holyd_lexer.c $(COMP)/holyd_parse.c \
               $(COMP)/holyd_parse_ast.c ... $(COMP)/holyd_runtime.c
   ```
   then regex-substitute all inline lists with `$(HOLYD_SRC)`. Never hand-edit
   9 copies of the same list.
3. **Source-level identifiers**: `HCCompiler→HDCompiler`, `HCParser→HDParser`,
   `HCGen→HDGen`, `HCASTNode→HDASTNode`, `HC_AST_*→HD_AST_*`,
   `HC_TOK_*→HD_TOK_*`, `hc_lex_init/hc_parse_init/hc_gen_init/hc_ast_free/
   hc_eval/hc_compile → hd_*`, `#include "../compiler/holyc.h"→holyd.h`.
   Sweep with grep -rl per pattern; watch for false positives (zealos_parity.h
   #define mappings legitimately needed their RHS updated too).

## Failure class 2: JIT test targets segfault at first instruction
Symptom: `test_holyd` / `test_holyc_agi` / `test_jit*` link clean, then die
with SIGSEGV. gdb shows rip = the JIT'd code's FIRST instruction (push rbp),
si_code=2 (SEGV_ACCERR), si_addr = the code buffer itself.

Root cause: `jit_alloc_exec()` is `#ifdef WUBU_HOSTED`: mmap(PROT_RWX) with
the flag, plain `malloc()` without. Test targets missing `-DWUBU_HOSTED` got
heap memory; executing it faults immediately.

Diagnosis shortcut: print `exec` right before the call — a malloc-range
address (brk/heap, e.g. 0x5555...) vs an mmap address (0x7f...) tells you
which branch compiled in. Compare against a known-working probe built WITH
the flag.

Fix: add `-DWUBU_HOSTED` to those specific targets' compile lines in
mk/tests.mk.

## Secondary bug found on the same path (session eval)
Even with the flag, `wubu_holyd_eval` crashed because its codegen path (a)
never called `hd_register_holyd_runtime(&gen)` so builtin calls emitted
`call 0`, (b) never patched `n_call_patches` rel32 displacements after memcpy
to exec, (c) never called `jit_lock_exec` when data_size==0. All three exist
in hd_eval's standalone path — diff the session path against hd_eval line by
line before inventing new theories.

## Process lessons
- **Blanket sed over tests.mk is dangerous.** Multi-line recipes end in `\`;
  appending flags naively puts them after the backslash and ld eats them as
  an output name (`cannot find -Isrc/runtime: No such file or directory`).
  It also broke unrelated targets lacking `-Isrc/runtime`. Exact-string
  replaces anchored on the target name won.
- When incremental patches tangle a Makefile, `git checkout <file>` +
  re-apply surgical fixes beat more patching.
- A stray compiled binary at `/tmp/wubu` blocked creation of `/tmp/wubu/`
  state dir → GDPR consent file unwritable → EDR audit tests fail-closed
  (9/11). Check for path-collisions before assuming logic bugs.
- Debug-print discipline: when a fprintf debug block survives multiple edit
  rounds, remove it via exact-string replace, not regex — regex left a stale
  block behind twice.

## Verification
```
make compiler                    # ✅ HolyC compiler built
make test_holyd                  # 33/32 passed
make test_holyc_agi              # 11/11 (needs /tmp/wubu/gdpr_age consent file)
make test_jit                    # All tests passed
cd ../wubunos && make test       # 111/111
```

## Related
- references/link-line-rule-body-dedupe-2026-08-08.md (rule-body-aware object
  injection — the same tests.mk, different failure mode)
- `wubuos-battleship-gaps`
