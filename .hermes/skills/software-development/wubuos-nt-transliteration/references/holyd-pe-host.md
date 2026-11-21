# Hosting holyd output via the PE loader (the P1 forcing function)

Goal: prove WuBuOS self-hosts — a holyd-compiled blob runs through the kernel PE
loader (`wubu_pe_*`) end to end, instead of only via `hd_eval`'s execute-in-place JIT.
This is the tie-in between `wubunos` (the compiler) and `wubuos` (the loader); the
ReactOS-loader contract (header parse / section map / base reloc / IAT / TLS / entry)
is implemented and tested in `src/kernel/wubu_pe.c` (see SKILL.md P1 steps 1-4).

## holyd's executable-blob API (confirmed by reading holyd_codegen_api.c)

Two entry points in `wubunos/holyd_codegen_api.c` produce RAW machine code you can
wrap as a PE `.text` (no PE emitter needed — the blob IS the payload):

- `void *hd_compile(const char *source, size_t *out_size)` — compiles an EXPRESSION
  (`hd_parse_expr` + `emit_ret`), allocates executable memory via `jit_alloc_exec`,
  copies code then data (string literals) contiguously after it. The code leaves the
  expression's value in `rax` and `ret`s. Callable directly as `int64_t (*)(void)`.
- `void *hd_compile_func(const char *source, const char *func_name)` (line ~347) —
  compiles a NAMED FUNCTION (proper prologue/epilogue); call with args.

Executable allocation only happens under `-DWUBU_HOSTED` (same as the JIT tests).
Both blobs are position-relative when the body is SELF-CONTAINED (pure constant like
`"42;"`, or a pure-arg function like `"int f(int n){return n+1;}"`) — because code
and data are copied contiguously, internal RIP-relative references stay valid across a
map. Blobs that reference module GLOBALS are NOT directly callable on their own: they
carry `global_offset` entries and need `hd_eval`'s exec-copy fix-up pass
(`holyd_codegen_internal.h` note) to patch in addresses. For the first host round-trip
use only a self-contained blob.

## Build a cross-repo probe WITHOUT hand-copying the compiler source list

The holyd compiler is ~12 TUs; do NOT hand-list them. Reuse a target that ALREADY
links holyd and is known-green (`test_hedge` or `test_battery` in `mk/tests.mk` both
compile `-DWUBU_HOSTED` + `$(JIT_SRCS)` + `src/runtime/wubu_spawn.c` + all
`$(COMP)/holyd_*.c` + `$(COMP)/wubu_preproc.c` + `$(COMP)/holyd_runtime.c` + `-ldl`,
with `COMP = src/compiler` which is a symlink to `wubunos`):

```bash
make -n test_hedge 2>/dev/null | grep 'gcc' | head -1 > /tmp/hd_blob_cmd.txt
# edit: replace tools/probe/hedge_verify.c with your probe .c, change -o target
bash -c "$(sed 's#tools/probe/hedge_verify.c#/tmp/myc.c#; s#-o src/compiler/hedge_verify#-o /tmp/myc#' /tmp/hd_blob_cmd.txt)"
```

`make -n` prints the fully-expanded `$(CC) ...` command (all vars resolved), so you get
exactly the working link without chasing `$(JIT_SRCS)`/`$(COMP_OBJS)`. Include the
compiler headers as `"holyd.h"` + `"holyd_codegen.h"`.

## Probe shape (author, then run)

```c
#include <stdint.h>
#include <stdlib.h>
#include "holyd.h"
#include "holyd_codegen.h"
int main(void){
  size_t sz=0; void *b=hd_compile("42;",&sz);
  int64_t a = (b&&sz)? ((int64_t(*)(void))b)() : -999;   /* expect 42 */
  void *f=hd_compile_func("int f(int n){return n+1;}","f");
  int64_t c = f? ((int64_t(*)(int))f)(41) : -999;        /* expect 42 */
  return (a==42 && c==42)?0:1;
}
```

Confirm the algorithms return 42 FIRST; only then wrap the blob as a PE. Good wrap:
place the holyd code at `.text` RVA base and data right after (contiguous), entry_rva
= start of blob, run through the `wubu_pe` full pipeline (parse -> copy sections -> map
at preferred base -> relocate no-op -> snap IAT -> call entry). The loader already
proves a dependency-importing entry runs (`test_pe_full`, 8/8); a holyd blob that
returns a value OUT of the loader is the self-hosting point.

## Validated status (2026-11-06) — forcing function GREEN
Blob-callability probe + blob->PE wrapper are now BUILT, RUN, and green:
- `hd_compile("42;")` -> blob, direct call -> **42**.
- `hd_compile_func("int f(int n){return n+1;}","f")` -> func ptr, `f(41)` -> **42**.
- `test_holyd_pe` (make target, `src/kernel/test/wubu_pe_holyd_test.c`): the holyd
  blob for `40+2` is packaged as a PE `.text`, run through parse->map->relocate->
  call_entry, and returns **42** at BOTH the preferred base (0x00400000) AND a
  shifted base (0x00420000) — proving the position-independent blob survives base
  relocation with zero fixups. **9/9.**
- `make test_holyd_pe` exits 0; `make all` still EXIT 0 after the compiler edits.
- **Rung 2 (GREEN, same day): a holyd module that WRITES a global survives the
  emitter -> loader round trip.** `holyd_pe.c` was upgraded to emit a `.data`
  section and fix each module-global store's RIP-relative disp32 against the
  .data section's REAL RVA (not the old "data right after code" convention);
  the loader maps that section in, so the store lands in mapped memory.
  `test_pe_globals` (make target, `src/kernel/test/wubu_pe_globals_test.c`)
  compiles `int g = 40;` through the holyd API, emits a `.text`+`.data` PE, and
  runs it at TWO bases — mapped `.data[0]` becomes **40 at both 0x00400000 and
  0x00420000**, proving code<->data distance is base-invariant with NO .reloc
  directory. Rationale: holyd's global access is a `[rip+disp32]` operand, so
  once the emitter fixes disp against the data RVA the image is fully PIC — a
  DIR64 reloc entry inside the loader would wrongly patch that disp32 as an
  absolute u64. **9/9.**
- Passing globals to the emitter: use `compile_main`-shape codegen (emit_prologue
  + gen_stmt on each top-level decl + emit_epilogue), read `gen.global_patches`
  (module-level patches live there, NOT `functions[].global_patches` for a bare
  top-level store), and pass `gen.data` (the .data payload) + those patch arrays
  to `hd_write_pe`. The OLD caller pre-patched `func_size + go` then passed
  `n_patches=0` — that dropped the data section entirely; the fixed caller
  passes the real arrays and lets the emitter do it.
- **The compilation-unit parser accepts only DECLARATIONS at top level** — a bare
  trailing expression like `int g=40;  g+2;` is a parse error the recovery loop
  silently skips, so a module can't compute-and-return in one pass via
  `hd_parse_compilation_unit`. To assert a RESULT, either wrap it in a function
  or (as test_pe_globals does) assert the .data side-effect on the mapped image.
- **Rung 3 (GREEN): a holyd PROGRAM self-hosts as ONE image.** `hd_write_pe_program`
  (new in holyd_pe.c) lays module code + compiled function bodies contiguously as
  .text, fixes every RIP-relative global disp32 (module AND each function) against
  the .data RVA, and rewrites a module->function `call rel32` to be IMAGE-RELATIVE
  (function-index based, not an absolute JIT ptr). `test_pe_program` compiles
  `int g=40; int f(){return g+2;}` and runs it at 0x00400000 AND 0x00420000: the
  module writes g, calls f, reads g+2, returns 42 at both bases — a two-part
  program (init + helper) with a cross-function call, position-independent, no
  .reloc. To drive gen_stmt of a trailing FUNC_DECL correctly: `gen_stmt` compiles
  the body into its OWN buffer AND registers it as `functions[n_functions-1]`, so
  capture the target index via `last_fn_idx = gen.n_functions - 1` AFTER the
  gen_stmt call (never before — the name isn't registered yet). Emit the E8+disp32
  placeholder into the restored module buffer (gen_stmt restores code/code_size),
  record code_patch_pos, then have the program-emitter patch it to the function's
  image offset.
- **Call_patch position = the DISP32 slot, NOT the opcode.** `hd_eval` stores the
  call-patch `code_patch_pos` AFTER emitting `0xE8` (so it points at the 4-byte
  displacement that follows the opcode), and patches `*(int32_t*)(exec+pos)` with
  `disp = target - (exec+pos+4)` — RIP-after is `pos+4`, not `pos+5`. The program
  emitter you write MUST match this contract or the `call` jumps to
  image+~0x1e21 (past .text) and SIGSEGVs. When reusing `gen.code` bytes, the
  module's trailing call is written at `code_size` BEFORE `emit_byte(0xE8)`,
  i.e. opcode at `pos-1`, disp at `pos`.
- **DETERMINISM (GREEN): two independent compiles of the same source emit
  BYTE-IDENTICAL PEs** — the fixpoint test (dusk/30cc/Hermit "two --strict
  compiles must SHA-equal"). `test_pe_program` compiles `int g=40; int f(){return
  g+2;}` a second time from scratch and re-emits; the two 1536-byte files are
  identical. holyd has no `__TIME__`/`__DATE__`, so codegen is a pure function
  of the source; this is what lets a self-build (stage0->stage1->stage2) collide
  to a deterministic hash.
- **`hd_gen_init` PRESERVES state by RE-READING uninitialized pointers.** It copies
  `gen->data`/`gen->data_size`/symbols/functions BEFORE `memset(gen,0)` (for REPL
  persistence). If you declare `HDGen gen;` on the stack and call it in a SECOND
  compile, `gen` holds stale stack bytes (often the first call's already-freed
  pointers), so the preserved `data` slice aliases freed memory and the tail
  `free(gen.data)` double-frees. **Always `memset(&gen,0,sizeof gen)` before
  `hd_gen_init` when compiling repeatedly.** `hd_eval` is shaped identically and
  only survives because its stack frame happens not to collide — do not copy it.
- **Module-runner primitive (`wubu_zx.{c,h}`, rung 4 GREEN):** `wubu_zx_run(ops,
  bytes, size, base, resolve, out_err)` is the ONE reusable "run a raw PE" call:
  parse -> sections -> map (via caller `ops.map` so kernel allocator or host
  mmap both work, keeping it kernel-clean) -> copy sections -> relocate ->
  snap IAT (resolve==NULL => wubu_modsym_resolve) -> call entry. `test_wubu_zx`
  proves the SAME call runs BOTH a registry-import image (`call [rip+disp]`
  -> IAT -> `NTOSKRNL.EXE!ANSWER` -> host fn -> 7) and the holyd-emitted
  program (init + cross-call + .data -> 42). This is the loader core a .ZXE /
  /n namespace loader / boot shell call — the "modules resolve against the
  VSL/NT export table" seam from the P2 plan. Error codes are negative
  WUBU_ZX_ERR_* (distinct from any user return); wired into `mk/objects.mk`. 
  Beware: the ops mapper MUST zero the span (bss-like section tails depend on
  it), and guard raw_ptr+raw_size against `size`.
- **Namespace loader (`wubu_zxload.{c,h}`, rung 5 GREEN):** `wubu_zxload_run(ops,
  path, base, resolve, out_err)` reads a PE BY NAME from the /n filesystem
  (at `<g_ns_root>/<path>`, normalizing a leading `/n/` or root) and hands it to
  `wubu_zx_run`. `test_wubu_zxload` drops BOTH images into a real ns root
  (g_ns_root set directly; links wubu_ns_fs.o, NOT wubu_ns_bridge.o, per the
  memory-constrained rule) and loads them BY NAME: `answer.exe`
  (import-through-registry -> 7) and `prog.bin` (holyd program ->
  42). This is the P2 "/n module loader" seam: writers publish PE bytes into the
  namespace; any reader loads+runs by name with one call, imports resolving
  against the registry. Hosted path uses stdio; keep `<string.h>` at the top
  (build_path uses strcpy/strcat in BOTH the hosted and non-hosted paths, so the
  include must not live inside `#ifdef WUBU_HOSTED`).
- **Import-carrying emitter (`hd_write_pe_imported`, rung 6 GREEN):** lets the
  holyd emitter produce a PE that CARRIES and resolves its own imports. Emits a
  standard-layout PE32+ (entry at opt+16, data-dir base 112, import dir at
  opt+120) with .text + .idata; builds the descriptor/ILT/INT/IAT + name rows +
  dll string and rewrites each `call qword[rip+disp32]` (disp at call_disp)
  to point at its IAT slot. `wubu_zx_run` snaps that IAT via the registry and
  the entry calls through it. `test_pe_import` emits a one-import PE
  (NTOSKRNL.EXE!ANSWER), runs it, and gets 7 -> 5/5. CRITICAL layout rule:
  the loader walks import descriptors back-to-back at `i*20` and breaks only
  on a descriptor whose name_rva==0 — so reserve the NULL-terminator descriptor
  (20 zero bytes) as part of the descriptor block BEFORE the 8-aligned
  ILT/INT/IAT tables; padding only to 8 after the real descriptors makes
  descriptor[n] land on nonzero thunk bytes -> bogus name -> snap -1 (after
  already patching slot 0, so entry may still return the right value and the
  bug is masked).
- **Module registry (`wubu_zxreg.{c,h}`, rung 7 GREEN):** ZXE-style bookkeeping on
  top of wubu_zx_run + wubu_zxload. `wubu_zxreg_load` reads + SHA-256s the /n
  PE bytes, exact-match dedups (same bytes at same base -> REUSE the slot,
  refcount++ and serve the cached result — the module ran once), and
  `wubu_zxreg_unload` decrements to zero then frees the slot + compacts the
  fixed table. `test_wubu_zxreg` loads mod.bin twice -> 7 both times, same
  entry ptr, refcount 2, registry count 1; unloads back down to 0. Uses
  wubu_sha256 for dedup. LAYERING RULE: wubu_zxreg is a KERNEL module, so it
  must NOT include the runtime wubu_zxload.h —  forward-declare
  wubu_zxload_read locally (the kernel object build has no -Isrc/runtime, a
  header include breaks `make all`). MULTI-MODULE (extended 15/15): two
  distinct modules coexist in one registry (holyd program -> 42 and import
  module -> 7 at separate bases/slots, count 2); dedup is per-module by
  SHA-256 (reload reuses the slot, count stays 2); unloading one leaves the
  other; unloading both empties the registry.
- **Session app-launch bridge (`wubu_applaunch`, rung 9 GREEN, 6/6):** the
  P3<->module seam. `wubu_applaunch_as_session_launcher` is a `wubu_sboot_launch_fn`
  that starts a session autostart app by loading its executable from /n through
  `wubu_zxreg_load` (config `wubu_zx_applaunch_cfg {ops; resolve; base}`, in `ud`);
  the registry keeps the reference so a later unload releases an ephemeral app.
  `test_wubu_applaunch` builds a real session boot (autostart scan + bus), points
  a .desktop Exec at `/n/apps/prog.bin`, and `start_all` -> 1 app started, registry
  slots 1. PITFALL: the launcher MUST pass the exec path verbatim to zxreg_load —
  `build_path` already resolves `/n/...` AND keeps subdirs. Stripping argv[0] to its
  final component turns `apps/prog.bin` into `/n/prog.bin` (a MISS). Also: the test
  must #include `wubu_applaunch.h` or `wubu_zx_applaunch_cfg` / the launcher are
  undeclared (2 compile errors), and `make test_wubu_applaunch` needs `-DWUBU_HOSTED`.
- **Stage-0 self-build harness (`wubu_selfbuild`, rung 10 GREEN, 6/6):** the seed
  loop for self-hosting. `test_wubu_selfbuild` reads a holyd-LANGUAGE source FILE
  from the repo (`src/runtime/selfbuild/hello.hd` — its own language, NOT C, so
  the source text differs from the C harness), compiles it through the program
  emitter (`emit_holyd_file`, the same AST-walk as test_pe_program), drops the PE
  into /n/apps/, and runs it through `wubu_zxreg_load` -> the entry runs a
  CROSS-FUNCTION CALL (f() -> sum(), each a real for-loop/global-store holyd
  function) and returns 55, registry count 1. Swap hello.hd for any holyd source
  that parses and the loop carries it. EXTENDED (11/11): the same self-built PE
  runs at a SECOND base 0x00420000 -> 55 (position-independent for a self-hosted
  FILE, not just the hardcoded program string); cross-base loads are NOT deduped
  (count 2); unloading each reference returns count to 0 (the ephemeral-app
  lifecycle the applaunch launcher promises — a session can unload after start_all).
  ARRAY-INIT FIX (11/11): a GLOBAL char array with a brace initializer
  (`char buf[9] = {72,...}`) in a self-hosted file now works — buf[0] -> 'H'=72 at
  BOTH bases. ROOT CAUSE was in holyd_codegen_stmt.c: the MODULE-level VAR_DECL
  branch had no brace handling (it called gen_expr(init)+ONE qword store, so a
  brace array stayed zeroed) while the LOCAL branch had it. FIX: module-level
  brace inits now lea rdi,[rip+glo] (patched to .data exactly like the scalar
  store, same disp32 mechanism the program emitter fixes) and store each element
  at consecutive offsets, mirroring the local path.
  `mk/tests.mk` target `test_wubu_selfbuild` (needs `-DWUBU_HOSTED`; links the
  applaunch + zxreg + holyd_pe source set).
- **Self-build now hosts RECURSION (rung 10f, 16/16).** `fib.hd` = a holyd program
  with a PARAMETRIZED recursive function (`int fib(int n){ if(n<=1) return n;
  return fib(n-1)+fib(n-2); }`) + a zero-arg entry. The harness emits it to /n and
  the registry loads+runs it -> fib(10)=55. Closes the "it's a hello world" gap:
  self-hosted modules exercise params + recursion. 3 modules coexist (data-array
  hello + recursive fib + a cross-base load, NOT deduped) and unload cleanly.
- **PITFALL: `wubu_zxreg_unload` COMPACTS the fixed table when a slot's refcount
  hits 0** — it shifts later entries left and memsets the old, so a pointer held
  to a (not-yet-unloaded) entry is INVALIDATED by unloading an EARLIER slot.
  Unload LAST-registered first (highest index), so compaction never moves an
  entry a still-held pointer refers to. (test_wubu_selfbuild hit exactly this:
  unloading the first hello invalidated the fib pointer -> count never reached 0.)
- **Self-hosted MULTI-DIGIT integer parsing (B3 depth, `test_wubu_tokenizer`
  28/28).** `num.hd` = `v=v*10+(s[i]-'0')` folds "321" -> 321 through
  `wubu_zx_run`, at two bases. This is what separates expr-eval's single-digit
  toy from a real lexer. Completes the self-hosted compiler-stage skeleton:
  lex (4), parse/eval (14), 2-arg helper (9), multi-digit parse (321).
- **Self-hosted PARAMETER passing — 2-arg ABI locked (B3 depth,
  `test_wubu_tokenizer` 21/21).** `param.hd` = `int add(int a,int b){return a+b;}`
  `f(){return add(2,7);}` -> 9 through `wubu_zx_run`, at two bases. `fib.hd`
  already covers 1-arg recursion; this locks the 2-arg case explicitly.
- **Self-hosted EXPRESSION EVALUATOR — a SECOND compiler stage (B3 depth,
  `test_wubu_tokenizer` 14/14).** `expr.hd` = parse+eval of "3*4+2" (left-to-right,
  char arithmetic c-'0', `*` multiply, nested if/else-if, multi-var state) -> 14
  through the loader, at two bases. The compiler now self-hosts TWO stages:
  lexing (tokenizer.hd -> 4 tokens) AND parsing/eval (expr.hd -> 14). This is the
  furthest the loader has carried holyd programs doing real compiler-ish work.
- **Self-hosted TOKENIZER — a compiler STAGE runs through the loader (GAP B3,
  `test_wubu_tokenizer`, 7/7).** The compiler reads its own `tokenizer.hd`
  (holyd-language), emits a PE, and `wubu_zx_run` runs it -> counts 4 tokens in
  "int x = 42". This is the holyd-compiles-holyd seed: a real compiler sub-stage
  (lexing) executes as a holyd program through the loader, not a host harness.
  Uses char literals, '||', nested if/else, computed-index char walk, a loop.
  CAREFUL: the correct count is 4 (space-delimited runs int,x,=,42) — a first
  expectation of 5 wrongly counted the space delimiter as a token. Prerequisites
  (all proven red): string literals (B2b), computed-index char read + while +
  comparison (walkprobe r=5 for "HELLO"). This is the furthest the loader has
  carried a holyd program that does real compiler-ish work.
- **Self-hosted STRING LITERAL (GAP B2b, `str.hd`, test_wubu_selfbuild 28/28).**
  `char* s="HELLO"; return (int)s[0]` now returns 72 through the emitter->loader.
  ROOT CAUSE fixed in wubunos holyd_codegen_expr.c: string literals emitted
  `movabs rax, <host gen->data+offset>` — an ABSOLUTE HOST pointer that only
  worked in the live JIT REPL; across emit->map->run s[0] read garbage (142).
  FIX: `lea rax,[rip+disp32]` + a global patch to str_offset (same shape as the
  array-to-pointer decay global case). The string bytes were always in gen.data;
  only the pointer wasn't relocatable. This unblocks B3 (holyd-compiles-holyd),
  which needs string/char handling. probe: emit funcs=1 data=8 glob(report)=0
  but the patch lands in the FUNCTION list and resolves against .data — r=72.
- **Computed-index data access (GAP B2, `test_wubu_selfbuild` 22/22).** Added
  `sumbuf.hd` — reads a GLOBAL int array by a VARIABLE index (`buf[i]`) in a
  loop through the emitter -> loader, sum(1..10)=55 at both bases. Proves the
  loaded .data is indexable by a computed offset (not just static buf[0]).
  Params/recursion were proven by fib; this adds computed-index data. Three
  self-built programs now coexist (data-array hello, recursive fib, computed-index
  sumbuf) at four bases, then unload 4->3->2->1->0 strictly LAST-index-first.
  RE-CONFIRMS the compaction rule: the unload order MUST be by load index
  (highest index first); unloading a MID slot first (e.g. fib before sumbuf)
  shifts later entries and invalidates their pointers -> count never reaches 0.
- **Kernel-clean 9P client (GAP A2 DONE, `test_w9pc`, 8/8 + freestanding).** The
  completable half of the on-kernel leg. `wubu_9pc.{c,h}` reimplements the 9P2000
  T-version/attach/walk/open/read/clunk encoders kernel-clean (only memcpy; local
  strlen) and hands each frame to an abstract `w9pc_transport_fn`. test_w9pc proves
  (1) wubu_9pc.c compiles under `-ffreestanding -nostdlib -fno-pie -fno-pic
  -mcmodel=kernel`, and (2) the SAME client fetches a module over real Styx/9P
  byte-exact and wubu_zx_run runs it -> 7 at two bases (the real server accepting
  the frames = the codec is correct). This is the seam the booted kernel's 9P
  client attaches to. NOTE: -mcmodel=kernel requires -fno-pie -fno-pic (Ubuntu gcc
  defaults to PIE) or cc1 errors 'code model kernel does not support PIC mode'.
  Encoding must match styx_enc.c byte-for-byte (payload at +7, size/type/tag over
  [0..6], 9P string = u16 len + bytes; Rread count at rsp+7, data at +11).
- **Loader over real 9P (rung 11, `test_wubu_zx9p`, 8/8).** Shrinks the DA#3
  "hosted-only / stdio-only" gap at the TRANSPORT. A module PE is published under
  a host dir mounted as a 9P fs; a 9P client WALK+OPEN+READs the bytes over real
  Styx/9P (`styxfs_init`/`styxfs_mount("/",root,0)` + `styx_build_twalk/topen/
  tread/tclunk` + `styxfs_serve`); `wubu_zx_run` runs them (import via registry ->
  7) at both bases. Prior green loads used `fopen`/stdio from a flat /n dir; this
  proves the loader is transport-agnostic — module bytes arriving over 9P run the
  same. MINIMAL LINK (no compiler): `build_pe_a` from wubu_zx_test + the `cli_*`
  9P client from wubu_ns_9p_test + wubu_pe/zx/modsym + the styx set + wubu_container
  (styxfs_util needs wubu_container_validate/parse — missing it = link error).
  In the test-module aggregate. NO on-kernel 9P client exists yet (the real 9P
  *server* is hosted; the bare-metal kernel reads nothing from /n) — that is the
  remaining DA#3 gap, requiring a kernel 9P client + the booted image.
- **Coverage audit = `make test-cover` (GAP C1 tooling, `scripts/unowned_surface.py`).**
  Run it before any junk-drawer/vendor-raft reorganization: it reports which
  `src/kernel` + `src/runtime` `.c` files are textually referenced by ANY makefile.
  PITFALL: match FILENAMES across every `mk/*.mk` + the top Makefile, NOT literal
  `src/...` paths — recipes reference sources through `$(KERNEL)/`/`$(RT)/` make-vars,
  so a literal-path scan falsely classifies ~everything as unowned (a first cut
  reported 533 unowned, the correct figure is 50). And it is a TEXTUAL sieve, not a
  build graph: files the bare-metal kernel links via a wildcard/indirect obj list
  (metal_main.c, libc.c, interrupt_*, ps2) show as unnamed even though they ARE built —
  verify each sieve hit against `make -n <kernel-target>` before deleting anything.
- **Naming/organization map: `docs/naming.md`** (wubuos). Documents the #1
  collision: kernel `wubu_ns` = NVMe block namespace, NOT the /n Plan9 filesystem
  (`wubu_ns_fs`/`wubu_ns_bridge_internal.h`) nor the 9P transport (`styxfs_*`).
  Proposes the `mod_` rename-forward family for the loader stack (mod_run/mod_reg/
  mod_load), prefix governance table, and notes `.o`/`.d` are ALREADY gitignored
  (a prior "committed artifacts" claim was wrong). DO NOT mass-rename (regex
  rename already corrupted 9 files).

## WORKFLOW RULES (obey these)
- NEVER commit+push until the exact make target passed on the exact committed
  tree (`Results: N passed, 0 failed`). Twice a fused add+commit+push ran from a
  build that hadn't passed and pushed a RED main. Gate the build, then ship.
- Use `make test-module` for the whole stack (18 module/PE/self-build/9P targets, one
  verdict). Don't hand-loop targets — that's how partial-green got committed.
- Prefer in-tree make targets over standalone /tmp probes; probes re-linking the
  compiler source set are fragile (sed drops sources -> undefined refs). Reuse the
  exact `make -n` link line, don't prune the source list.
- `wubucontainer` submodule is dirty every session — grep it out, never stage it.
- A compiler fix is proven through the wubuos test-module gate; commit wubunos
  (wubu-integration) AND the wubuos test/hello.hd together.

- **A C function defined in a `.c` but absent from its header makes every caller an
  implicit-int declaration — and a 64-bit pointer RETURN gets truncated to a bogus
  low-32 address (often `NULL`).** Before debugging a "the pointer API returns
  garbage/NULL" symptom, `grep` the header for the prototype. `hd_compile_func` was
  missing from `holyd_codegen.h` (it had `hd_compile`/`hd_eval`); once declared, the
  same caller returned the correct exec pointer. This rule is general: any
  function-returning-pointer missing a prototype silently truncates at the call site.
- **Do not re-allocate an exec buffer by summing `gen.code_size + data_size` after
  compiling FUNC_DECLs.** The `HD_AST_FUNC_DECL` codegen compiles each function body
  into its OWN `jit_alloc_exec` buffer (stored in `functions[i].func_ptr`) and then
  RESTORES `gen.code_size` to 0. Summing that zeroed size and calling
  `jit_alloc_exec(code_size+data_size)` requests `jit_alloc_exec(0)` → NULL (jit.c
  ~line 130), so the API bails before ever returning the function. Return the
  already-minted `functions[i].func_ptr` for the named function instead — and check
  `func_ptr != NULL` (registration writes placeholder entries with `func_ptr=NULL`,
  so a name match alone is not proof the body compiled).
- **Before wrapping a holyd blob as PE `.text`, disassemble it and confirm it carries
  NO RIP-relative or absolute memory references** — only pure-register code is safe to
  copy into a mapped image. `hd_compile("40+2;")` emits `movabs rax,40; push; movabs
  rax,2; pop rdi; xchg; add; movsxd; ret`. A body that loads a module global is NOT
  self-contained and must go through `hd_eval`'s fix-up pass **or** (since same-day
  rung 2) the upgraded `holyd_pe.c`, which fixes the disp32 against the .data RVA —
  the emitter path that powers the self-hosting rung.
- **Trust the green make suite over a synthetic probe; gdb the REAL binary.** When an
  isolated `/tmp` probe you compiled by hand (own `mmap`/`MAP_FIXED_NOREPLACE` bases,
  own section-copy loop) reports a loader result that contradicts a make-target test
  that has been green all session, the PROBE is wrong, not the suite — re-deriving the
  parse in a fresh process with different pg-residency can misread entry/geometry and
  "call zeros" yet still print a value. Do not chase the contradiction in the probe;
  break in `gdb --args <the actual built test binary>` at `wubu_pe_call_entry` and step /
  read `info->entry_rva` / `x/… image+entry_rva` to get the real linked behavior. The
  suite + gdb on the real binary are ground truth; a hand-recompiled probe is not.
- **Kernel-clean `.c` has no `<stdio.h>`:** a debug `fprintf(stderr,…)` in `wubu_zx.c`
  (wired into `mk/objects.mk`) fails to compile with `'stderr' undeclared`. Kernel-clean
  modules ship no stdio; instrument them with gdb on the real binary (or host-side
  `#ifdef WUBU_HOSTED` stdio), never with a bare `fprintf`.

All PE-loader contract steps validated green: reloc 14/14, exec 13/13, iat 18/18,
full 8/8, **holyd-pe 9/9, globals 9/9, program(+determinism) 14/14**.

## WORKFLOW RULES (obey these)
- NEVER commit+push until the exact make target passed on the exact committed
  tree (`Results: N passed, 0 failed`). Twice a fused add+commit+push ran from a
  build that hadn't passed and pushed a RED main. Gate the build, then ship.
- Use `make test-module` for the whole stack (18 module/PE/self-build/9P targets,
  ONE verdict). Don't hand-loop targets - that is how partial-green got committed.
- Prefer in-tree make targets over standalone /tmp probes; probes re-linking the
  compiler source set are fragile (sed drops sources -> undefined refs). Reuse the
  exact `make -n` link line, don't prune the source list.
- `wubucontainer` submodule is dirty every session - grep it out, never stage it.
- A compiler fix (holyd_*) is proven through the wubuos test-module gate; commit
  wubunos (wubu-integration) AND the wubuos test/hello.hd changes together.
