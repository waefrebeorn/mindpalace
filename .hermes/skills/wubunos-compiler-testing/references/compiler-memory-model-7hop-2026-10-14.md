# Compiler memory-model + struct-layout 7-hop (2026-10-14)

Seed gap (verified this session): `int* vp = malloc(8); *vp = 80;` (and calloc)
core-dumps. Root cause traced to `wubu_isa_x86_64.c`: the JIT uses a **split
memory model** where every pointer VR is a byte *offset* into a flat `prog.mem`
buffer, and `MIR_LOAD/MIR_STORE` unconditionally compute `rsi = rbx + addr`
(`rbx` = `wubu_jit_mem_ptr`, the mmap'd base). `MIR_TO_PTR` converts an offset
to a *real* address only at the libc-call boundary. malloc/calloc are dlsym'd
and return REAL heap addresses, which then flow back into the offset world and
get `rbx` added a second time → `prog.mem_base + 0x5555…` → segfault.

## Hop chain + convergence

1. **chibicc (rui314) codegen** — `gen_addr` produces a REAL address in a
   register: local = `x29(frame) + offset`, global = `adrp/:lo12:`, member =
   `gen_addr(lhs); add x0,#offset`. `load`/`store` deref that register
   DIRECTLY (`ldr x0,[x0]` / `mov rax,[rax]`) — **no base is ever added**.
   There is no separate offset world. Pointers ARE real addresses.
   (github.com/rui314/chibicc/codegen.c; chibicc-aarch64/codegen.c)
2. **tcc / every JIT** — the JIT's "memory" IS the process address space (or a
   big mmap'd region); pointers are real addresses. The mmap research (Daniel
   Morris ARM64 JIT, rodrigodd Brainfuck JIT, the NCKU slides) all converge:
   allocate the *code* buffer via mmap(PROT_EXEC); *data* lives in the normal
   address space and pointers are ordinary real addresses.
3. **Verified-compiler memory model (CompCert / Appel / MIT 6.820)** — formal
   C memory models represent a pointer as (block-id, offset). This is the
   "tagged" alternative to real-addresses. Correct but heavy: needs
   block-tracking in every load/store. Not worth it for a teaching JIT.
4. **Glow CPU JIT** — a static-allocator JIT that assigns OFFSETS into one
   buffer ("allocator assigns offsets for each alloc activation… a single call
   to malloc initializes the heap"). This is the managed-heap alternative that
   PRESERVES the offset model — relevant only if malloc'd memory is never
   passed to real libc.

**Convergence principle:** a JIT must pick ONE pointer model and hold it
everywhere. chibicc/tcc pick *real addresses*; Glow picks *offsets + a runtime
that never hands them to libc*. Our JIT currently mixes both (offsets for data,
real addresses at the libc boundary via MIR_TO_PTR), which is exactly why
malloc's return value breaks the invariant. The split-model symptom is already
visible in the code comment at wubu_isa_x86_64.c:1748 ("a duplicate add
corrupted external-call string pointers, offset + 2*mem_base -> segfault").

## The fix (recommended: Option A — real addresses everywhere)

Adopt chibicc's model. Mechanical, gates on the full suite:

1. Every address producer emits `mem_base + offset` (a REAL address):
   - `&x` (ADDR), `p->m` (member offset), `a[i]` (index), and the current
     `MIR_TO_PTR` — all become `add rax, rbx` (or are folded into the addr reg).
2. `MIR_LOAD`/`MIR_STORE` (wubu_isa_x86_64.c:1689/1722) **drop the
   `mov rsi,rbx; add rsi,rax`** and deref the address register directly:
   `mov rsi, rax` (rax already holds the real address) then `mov rdi,[rsi]`.
3. `MIR_TO_PTR` becomes a no-op (addresses are already real) — remove it or
   make it a copy. This deletes the fragile double-add path entirely.
4. `prog.mem` stays an mmap'd RW buffer (`wubu_jit_mem_ptr`); only the MEANING
   of address VRs changes (offset → real). malloc/calloc/free from real libc
   then Just Work: deref uniform, libc-interop uniform (pass real addrs).

Risk: touches every address computation → run the FULL gate (`make test`,
`gauntlet_runner --core`, `gauntlet_v3`) — the interpreter path
(`wubu_mir.h:285 mem_load64/mem_store64`) uses `mem[byte_addr]` and must stay
offset-based (it has no rbx), so only the x86-64 backend and the address
producers change; keep the interpreter's flat-offset semantics.

## Alternative (Option B — managed-heap bump allocator, smaller/fragile)

Ship our OWN `malloc`/`calloc`/`free` (bump allocator over a tail region of
`prog.mem`) that hand out OFFSETS. malloc'd pointers become prog.mem offsets
like every other pointer, so MIR_LOAD/STORE work unchanged. Only viable if
malloc'd memory is NEVER passed to real libc (strcmp/strlen/printf %s expect
real addresses). Many gauntlet tests DO pass malloc'd buffers to libc, so this
is fragile — verify per-test before choosing it. Preferred only as a stopgap if
Option A regresses.

## Separate gap 2 — byte-precise struct layout (padding/alignment)

Our structs are 8-byte-CELL based ((msz+7)/8). Real C uses BYTE offsets with
alignment padding. Proven algorithm (chibicc `assign_lvar_offsets`; GNU C
manual §15.5; Wikipedia "Data structure alignment"):

```
offset = 0
for each field f in declaration order:
    align   = align_of(f.ty)          # typically sizeof(f.ty), capped (e.g. <=8 on x86-64)
    offset  = align_up(offset, align) # offset = (offset + align-1) & ~(align-1)
    f.offset = offset
    offset += sizeof(f.ty)
struct_align = max(field aligns)
struct_size  = align_up(offset, struct_align)   # trailing pad
```

Fields keep declaration order (C99); no reordering (that's the separate
struct-reorder optimization #19 from the JIT campaign). Bit-fields pack into
adjacent bits of the same unit. This is needed for `sizeof`, `sizeof_exps`,
`member_offsets`, `page_boundary`, and any struct shared with real libc.

## Separate gap 3 — SysV x86-64 struct-by-value ABI classification

For struct/union params and returns (<=16 bytes -> registers; >16 or unaligned ->
MEMORY). Proven algorithm (SysV AMD64 ABI §3.2.3; Harvard cs61 PDF; the
opensmalltalk #443 thread which works through the edge cases):

1. size > 2 eightbytes (16B) OR contains unaligned fields -> class MEMORY.
2. Split into eightbytes; classify each field recursively; merge per eightbyte:
   (a) both equal -> that class; (b) one NO_CLASS -> the other; (c) any MEMORY ->
   MEMORY; (d) any INTEGER -> INTEGER; (e) X87/COMPLEX_X87 -> MEMORY; (f) else SSE.
3. Basic classes: {bool,char,short,int,long,long long,ptr} -> INTEGER;
   {float,double,_Decimal32/64,__m64} -> SSE.
4. Assignment: INTEGER args -> rdi,rsi,rdx,rcx,r8,r9 (in order); SSE -> xmm0-7.
   MEMORY -> caller stack. If no reg left for ANY eightbyte of an arg, whole arg
   goes on the stack. Return: INTEGER -> rax,rdx; SSE -> xmm0,xmm1; MEMORY ->
   hidden pointer in rdi (caller-allocated), copied to rax on return.

Edge case (opensmalltalk #443): a struct needing >2 return registers (e.g. 2
long + 1 double = 3 eightbytes) is returned via hidden pointer in rdi.

## Separate gap 4 — struct-member array decay

`big.substruct.arr` (a char[] member reached through a struct member) decays to
`char*` with a WRONG pointer (direct indexing `big.substruct.arr[i]` is correct,
but the decayed pointer is not). The decay must compute `base + member_offset +
0` (the member's real address), same as the address-of path — currently the
member-array-decay path resolves the base without the member offset. Same fix
family as Option A (addresses must be real, offsets added at decay time).

## Landing / next action

**IMPLEMENTED 2026-10-14 (commit 55c6925) — chose Option B (managed heap), NOT
Option A.** Rationale: this codebase's interpreter oracle (wubu_mir_interp /
mem_load64) is ALSO offset-based, so Option A (real addresses everywhere) would
have desynced the JIT from the interpreter and destabilized the whole address
model. Option B completes the offset model instead of fighting it:

- `wubu_mir.c`: bump allocator over a 4 MB heap reserved at the tail of
  prog.mem; `wubu_jit_malloc/calloc/realloc/free` return byte OFFSETS into
  prog.mem. `wubu_jit_mem_ptr` definition moved here (wubu_mir.c is linked in
  more targets than the ISA backend).
- `wubu_isa_x86_64.c`: dlsym path routes the 4 allocators to the managed heap.
- `holyd_mir_eval.c` run dispatch: reserve + `wubu_jit_heap_init` before run.

Heap pointers are first-class offsets: MIR_LOAD/STORE deref them, and MIR_TO_PTR
(already applied to external-call pointer args) gives libc the real address into
the same buffer — so malloc'd buffers work with strcpy/strlen too. Verified:
malloc/calloc deref, index, compound-assign, calloc-zeroes, and libc interop all
pass. Gate: 195/195, 247/247, gauntlet_v3 1536→1562 (58.5%); 31 crashing errors
became 26 passes + 7 fails. scalar_member_access_arrow passes.

**LESSON: when a 7-hop recommends an architectural rewrite (Option A), check
whether the codebase has a second consumer of the same invariant (here, the
interpreter oracle) before committing to it. The smaller fix that COMPLETES the
existing model (Option B) often beats the one that REPLACES it — lower risk,
same test-class win.**

Still open (separate commits): gap 2 (byte-precise struct layout) and gap 3
(SysV struct-by-value ABI) — algorithms below.
