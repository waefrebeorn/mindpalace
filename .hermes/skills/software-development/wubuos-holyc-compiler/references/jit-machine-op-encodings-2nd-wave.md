# Minic JIT Machine-Op Encodings — 2nd Wave (2026-08-13, commits e4f9692/8d11933)

Second wave of machine-code optimizations implemented in `src/jit/jit_minic.c`
+ `src/jit/wubu_x86.c`. Each cost real debugging; the encoding facts below are
the durable lessons. All gates green: test_jit_regalloc 13/13, test_jit_remat
20/20, test_peephole_superopt 8/8, full make test all tiers.

## Div-by-constant magic (Granlund–Montgomery) — the bug cluster

Signed `x/d` for a constant d emits magic-multiply instead of `idiv` (3 cyc vs
18–28). Three separate bugs cost real time; all are gcc-verifiable:

1. **`p` must START at 63**, not 62. Off-by-one in the Hacker's Delight loop
   produces a magic value whose low bit differs → result exactly 2x too big
   (1000/7 = 285 instead of 142). The wrong p gives a DIFFERENT magic constant,
   visible by comparing the emitted `mov r64,imm` against gcc's `movabs`.

2. **Negative-magic compensation:** when the computed magic M has its sign bit
   set (M ≥ 2^63), gcc adds `x` to the high product BEFORE the shift. Emitted
   as `movabs $M; imul <rm>; add <hi>, <x-reg>`. Skip this and negatives are
   off by 2.

3. **Sign correction is `q -= (x>>63)`** (subtract the arithmetic-shift mask),
   applied unconditionally — NOT "add 1 if M<0" and NOT "and 1 then add".
   The gcc shape is: `sar hi,s; mov rax,hi; sar x,63; sub rax,sign`.

Power-of-2 `|d| = 2^k`: `q = (x + ((x>>63) & (d-1))) >> k` — add-round then
arithmetic shift (rounds toward zero for negatives). `x/1=x`, `x/-1=-x` are
early returns (no idiv).

**The magic loop's termination test** is `!(q1 < delta || (q1==delta && r1==0))`
— continue doubling while the opposite holds. Getting this inverted = infinite
loop (the whole build hung).

**Scratch regs MUST be allocated through the allocator**, not hard-coded
rcx/rdx: an enclosing expression's live vreg can be sitting in rcx/rdx, and
clobbering it corrupts the outer result. Use `xra_alloc_evict`, and if the
allocator spills (returns WREG_NONE), fall back to plain `idiv`.

## lea strength reduction — SIB scale is 2 bits

`lea r, [base + base*2^scale]` = `base*(1+2^scale)` in 1 cycle, no flags.
The SIB scale field is **2 bits → only 1,2,4,8**. So the legal multipliers are
`c-1 ∈ {1,2,4,8}` → c ∈ {3,5,9}. `*17` (scale 16) is **NOT lea-able** — falls
back to 3-op `imul r,imm32`. Don't list 17; you'll get garbage (scale 16
encodes as scale 0).

Power-of-2 multiply `x*{2,4,8,16,32,64,128,256}` → `mov; shl` (1 cyc).

REX bits for the SIB form: REX.R = dst hi, REX.X = base hi (index field),
REX.B = base hi (base field) — all three can differ from 0x48.

## Branchless idioms — cmov operand order

- `abs/fabs(x)` = `(x ^ (x>>63)) - (x>>63)`: `mov rdx,x; sar rdx,63; xor x,rdx;
  sub x,rdx`. No branch, no cmov.
- `min/max(a,b)` = `cmp a,b; cmovcc rax,other`.

**CMOVcc r64,r/m64 has DST in the reg field, SRC in rm** — opposite of most
2-operand ops. Get it backwards and `min(5,3)` returns 5 (it computes
`cmov reg_field=src, rm_field=dst`). Use `wx86_rex(dst, src, true)` +
`emit_modrm(e,3,dst,src)`.

## test-vs-cmp

`x==0` / `x!=0` when the RHS is the constant 0 → emit `test rax,rax`
(`48 85 c0`, 1 byte shorter than `cmp rax,0`), it sets ZF identically. Only
for EQ/NEQ — the other comparisons need the full cmp flags.

## New encoder primitives added (wubu_x86.{c,h})

- `wx86_imul_rax_rm` — one-op `48 F7 /5`: rdx:rax = rax*rm (full 128-bit
  product; high word lands in rdx). REQUIRED for magic-multiply — the
  3-operand `imul r,imm32` only gives the low 64 bits.
- `wx86_imul_reg_reg_imm32` — `69 /r id` (6B REX.W+69+modrm+imm32).
- `wx86_lea_scaled_index` — SIB lea for strength reduction.
- `wx86_cmovcc_reg_reg` — DST=reg field (see above).
- `wx86_test_reg_reg` — `85 /r`.
- `wx86_and_reg_imm32` — `81 /4` (opcode extension 4, like SUB /5).

## Souper-style superoptimizer (tools/peephole_superopt.c)

Discovery engine: enumerate shortest instruction sequences from a primitive
op set (ADD SUB MUL SHL SHR SAR AND OR XOR NEG NOT) that match a reference
expression on all seed inputs. Model = constant-free stack: seed the stack
with x, each op pops 2 (underflow→x), pushes result. Shortest-first search,
exact simulator as verifier → cannot emit a wrong peephole.

Found: `x*3=ADD ADD` (the lea pattern), `x*8`=7 ADDs, `(x>>63)&1=SAR NEG`,
`x|x`=AND, `x&-1=NEG NOT`. Gate `test_peephole_superopt` (8/8).

**Documented limitation (not a bug):** the constant-free model can't express
`x<<3` (needs a constant 3 the model doesn't carry). The op set bounds what
can be found — that's the point of a bounded enumerator. When a target isn't
found, either widen the op set or accept the model limit, don't chase a phantom
bug.

**Reference parser bug that bit:** the first version returned on the primary
('x') without parsing the following binary operator, so `x*3` ref-evaluated to
just x. Use a proper recursive-descent parser (primary + binary loop), not a
single-token dispatch.
