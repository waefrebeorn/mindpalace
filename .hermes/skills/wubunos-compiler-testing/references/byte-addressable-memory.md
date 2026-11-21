# Byte-addressable memory + codegen-gap workflow (flat-cell MIR model)

The HolyD MIR memory model stores every value in an 8-byte cell in a flat
int64 memory array (`mem`). Scalar `char` variables already work (the cell
just holds 65); the model breaks only when a char value must be read/written
as a SUB-CELL byte — type-punning through a char pointer — or when a char
pointer's stride must be 1. `sizeof(char)` and plain char-array indexing are
already correct; do not "fix" them.

## Width flag, NOT a new opcode

Never add MIR_LOAD8/MIR_STORE8 opcodes: the enum feeds the interpreter's
computed-goto dispatch table AND every backend. Use the instruction's unused
`imm` field as a width flag on MIR_LOAD/MIR_STORE (`imm == 1` -> 1 byte):

- `wubu_mir_load8(p, addr)` / `wubu_mir_store8(p, addr, val)` set `imm = 1`;
  `wubu_mir_load`/`store` leave it 0.
- x86-64 backend: byte load -> `movzx reg, byte [rsi]` (`0F B6 /r`, same
  REX/ModRM shape as the qword load); byte store -> `mov [rsi], dil`
  (`40 88 3E`, low byte of rdi). The qword path stays byte-identical.
- Interpreter: `mem` is already `uint8_t *`, so byte access is `mem[addr]`
  (load) / `mem[addr] = val & 0xFF` (store); the qword path keeps using
  `mem_load64`/`mem_store64`.

## Frontend: where the byte load is emitted

Two sites produce a load: the DEREF case (`*p`) and the INDEX case (`p[i]`).
A DEREF/INDEX node's own `type` is often nil for a pointer variable, so
resolve the pointee with a ladder and take the first hit:

1. the node's own `type` (`HD_TYPE_I8` / `HD_TYPE_U8`),
2. the child pointer's `type->base` (when the child carries a PTR type),
3. the symbol table: the child IDENT bound to a `char *` variable -> `base`,
4. for `p[i]` (INDEX whose base is an IDENT): the base variable's pointer
   `base` kind.

Debug with a temporary env-gated `fprintf` at the site printing
`n->type`/child kinds — one run shows exactly which rung the ladder needs.

## char-pointer stride

`mir_index_stride` forces a minimum 8-byte stride (correct for cell-model
arrays). A char/uint8 POINTER pointee must return stride 1 BEFORE that array
logic runs, or `p[1]` advances 8 bytes and reads the wrong byte. Check the
base variable's pointer `base` kind first, return 1, fall through otherwise.
For a struct/union MEMBER base (`u.arr[i]`), `mir_index_stride`'s left-spine
walk only handles an IDENT root and returns 8 otherwise — add a MEMBER-root
rung that resolves the member's element kind. NOTE: the member-access node
kind is `HD_AST_MEMBER` (the parser builds MEMBER, not DOT, for `u.arr`), and
the MEMBER registration that actually runs for `union U {...}` is the
named-type site — a different one than the AST-decl site; populate member
type/element kinds at EVERY registration site or the ladder sees all-zeros.

## String literals: byte-pack them (stride 1)

String literals must be stored BYTE-PACKED (contiguous, stride 1) via
byte-width stores, NOT cell-packed (stride 8). The flat-cell model defaults
to one char per 8-byte cell, but a `char *` reads them with byte-stride 1, so
cell-packed storage makes `s[1]` read the wrong byte. Store each char with
`wubu_mir_store8(addr + i, char)`. The `char s[]="..."` array-init path then
byte-LOADS the source (stride 1) and cell-STORES into the array (stride 8) —
source and dest use different strides, do not copy cell-for-cell.

## The address-16 alloc black hole (x86-64)

`wubu_mir_alloc` aligns the first allocation to a 16-byte boundary, so a
program whose FIRST allocation is a string literal lands at byte address 16 —
which collides with the x86-64 JIT frame/spill layout. Writes there do not
persist and reads return the address, not the data
(`int *p=(int*)16; p[0]=42; p[0]` returns 0; `char *s="hi"; s[0]` returns 16,
not 'h'). Any prior allocation shifts the base and masks the bug, so it only
bites the first-allocation case. Fix: start allocations above the reserved
low region (`if (base < 32) base = 32;`). When a load returns a value that
looks like the ADDRESS itself, suspect a low-address collision, not the load.

## Adjacent string literal concatenation

C 5.1.1.2p6: `"a" "b"` is one string `"ab"`. The lexer emits each literal as
its own STRING token; `parse_primary`'s STRING case must consume following
STRING tokens and `strncat` their decoded values (bounded by
HD_MAX_STRING_LEN). Do NOT add a phantom-empty-token guard — the lexer does
not emit phantom tokens after a literal's trailing quote; that misdiagnosis
only breaks normal single strings. Verify the misdiagnosis with a real run
before adding a guard.

## NaN float compares (x86-64)

`ucomiss` on an unordered operand (NaN) sets CF=ZF=PF=1. FEQ/FNE already AND
with `setnp`; FLT/FLE used bare `setb`/`setbe` (CF-based), so `NaN < x`
evaluated TRUE. Fix: AND the setcc result with `setnp` — same pattern as
FEQ/FNE and the f64 path: `setb al; setnp cl; and al,cl`. IEEE-754: every
NaN comparison except != is false.

## Verification ladder (fast -> gate)

1. **`test_single`** — `make test_single`, then
   `./test_single '<C source>' <expected>`: HolyD -> x86 JIT -> run -> compare,
   in seconds. The iteration loop for any backend fix. NOTE:
   `test_mir_float` uses the INTERPRETER, not the x86 backend — it does NOT
   exercise codegen fixes; use it only for MIR-level float semantics.
2. **`test_isa_driver`** — rebuild + run; exercises x86-64 codegen broadly
   (ignore pre-existing arm64 COMPILE FAIL lines on an x86 host).
3. **`test_fuzz_diff`** — differential x86-vs-interpreter oracle (float /
   native-f32 / dtype seeds). Must be 0 mismatches after any backend change.
   `make` reports "up to date" — `touch` the sources to force a real rerun.
   **After reverting a source edit, force a clean rebuild of the test binary
   (`rm -f *.o test_single` then `make test_single`) before trusting a
   re-test** — `make` may link a stale `.o` and report the pre-revert
   behavior, which reads as "my revert broke it" when the binary never
   changed. Confirm the working tree is clean with `git diff --stat` when a
   re-test contradicts the source.
4. Full `make test` (195/195) + selfhost battery (155/155) before commit.
5. The full gauntlet (`--core`, and the 4588-test depot) is a many-minute
   run; never iterate on it — run it once for the final number.

## Re-measure gap-analysis claims before acting on them

Gap-analysis documents drift as the compiler improves. Before scheduling work
from one, verify each claim with a real command. Measured example: a stale
analysis claimed "no stack frame, 9+ argument calling convention broken,
56.6% gauntlet" — reality was an rbp frame present, 8/9/12/16-arg calls
correct via test_single, and `--core pass=3458 fail=0 error=0` with selfhost
155/155. The full-depot "failures" were unsupported upstream GCC/LLVM/LACC
extraction features (VLA, `__attribute__`), not correctness bugs. The
architecture also has ~9 allocatable VRs (r10-r15, r8, r9, rdx; VR0=r10 is
the return) with allocator spill — >8 args spill, they do not break.

## Batch-measuring a gauntlet chapter: parse the real expected value

When batch-running depot tests through `test_single`, do NOT assume every
valid test returns 0. Char/string tests return char values
(`return 'c'` == 99) and arithmetic tests return computed ints. Parse each
test's actual last top-level `return <expr>;` (char constant -> ord, plain
int literal -> itself, complex -> skip) and pass THAT as the expected arg;
otherwise a correct compiler reads as "failed" and the baseline is wrong
(an assumed-0 harness reported 11/40; the real baseline was 16/33). Group
remaining failures by the FEATURE they need (ptr-to-array types, external
libc calls, static arrays, escapes) — that grouping is the replan, not a
per-test fix list. Pointer-to-array `T (*p)[N] = &a; p[i][j]` is a known
pre-existing gap: `*p` works (re-derives the address) but `p` itself holds 0
because `&a`-into-ptr-to-array init does not store the address; `is_ptr_array`
is only set for function params, not locals.
