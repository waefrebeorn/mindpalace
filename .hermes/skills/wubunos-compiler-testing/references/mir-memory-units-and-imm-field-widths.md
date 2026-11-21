# MIR memory units and imm field widths

Two recurring defect classes in the WuBuOS/WuBuNOS compiler. Both produce
WRONG ANSWERS rather than errors, so they pass any "does it run" check.

## 1. MIR addresses are BYTE offsets

`wubu_mir.h` declares byte-addressable helpers:

```c
static inline int64_t mem_load64(const uint8_t *mem, int64_t byte_addr) {
    const int64_t *p = (const int64_t *)(mem + byte_addr);
    return *p;
}
```

So a MIR STORE of value V at address A lands at `((int64_t*)mem)[A/8]`.

Consequences:
- Base addresses of int64 arrays MUST be multiples of 8. Advancing a base
  by 1 element writes a misaligned int64 and every read-back is garbage.
- `op_t_gemm` used to index `uint8_t *mem` as `int64_t*` with the raw
  register value: that reads 8x past every address. Convert the base once
  (`base >> 3`) and scale element strides by the cell width.
- `total_mem` is a CELL count; `mem_size = total_mem + 1` CELLS; the byte
  bound used by STORE/LOAD is `mem_size * 8`. Programs that never set
  `total_mem` get `mem_size = next_vr_hi` (the register count) and every
  store is out of range. `holyd_mir_eval.c` maintains it on every alloc --
  hand-written test programs must too.

### The rule generalizes: ANY backend indexing an element array

Every backend that materialises MIR memory as an array of 8-byte cells must
convert the byte address once, at the point of indexing. Three surfaces have
had this bug independently:

| backend | what it indexes with | consequence |
|---|---|---|
| `wubu_mir_interp` | `uint8_t *mem` as `int64_t*` | read 8x past every address, walked off the heap |
| `wubu_isa_x86_64.c` | `prog.mem + byteaddr` | correct; comment says "No shl rax,3 -- addresses are byte offsets" |
| `wubu_isa_spirv.c` | SSBO element index | read 8 cells too far; memory programs returned 0 |

In SPIR-V the fix is a logical shift right by 3 before the `OpAccessChain`:

```
cell  = a >> 3          ; OpShiftRightLogical, u64
idx64 = cell + 1        ; element 0 is the return slot
```

Note the `+1` offset is the backend's own business (cell 0 is the return
slot); the `>>3` is the unit conversion and is not optional.

**Arithmetic-only tests cannot catch this class.** Straight-line add/mul
never emit MIR_LOAD, so they pass while every memory-using program is
silently wrong. Any memory-using backend change needs a program that stores,
loads, and combines -- see the oracle discipline below.

## 1b. Verify against an independent oracle, not against yourself

A backend change is not proven by the backend's own passing test. Write one
tiny program, compute the expected value by hand, and require agreement across
at least two independent backends plus the interpreter:

    (7+9)*56 - 4 = 892     x86-64 892   ptx 892   spirv 892
    (7+9)*3      = 48      x86-64  48   ptx  48   spirv  48

Use two differently SHAPED programs, not one: a single program can pass while
a high index is still wrong (the first probe here used cells 0-3 and a larger
`total_mem` changed the answer from 7 to 0, exposing an out-of-range read
rather than a conversion bug). Probe a non-zero high address too -- a store at
byte 32 must land at cell 4, which distinguishes a correct conversion from an
off-by-one that happens to work at low indices.

Reuse a WORKING sibling target's link line rather than assembling sources by
hand: `make -n <sibling>` gives the exact object list, and swapping only the
main source for your probe is enough to get a linked driver binary.

## 1c. Negative-control every test-oracle fix

When you change a test's OWN checker (rather than the code under test),
prove the fix did not merely weaken the check. Inject a deliberate violation
and confirm it still fails:

```python
# force two genuinely-simultaneously-live vrs to collide
a[v3].reg = a[v1].reg
assert verify_no_conflicts(&p, a, count, 6));   # must still abort
```

A test-only fix that makes an assertion pass without making it TRUE is worse
than the original failure: it converts a visible defect into permanent green.
Restore the file and re-run clean afterwards.

## 2. imm field widths must match the encoder exactly

`MIR_T_GEMM` packs three dims into one `imm`:

```
imm = (M << 22) | (N << 11) | K
```

N occupies bits 11..21 -- exactly 11 bits, because M starts at bit 22.
Masking N with `0x7FFF` over-reads into M: N=2 decodes as 4098, every
store lands out of range, and C reads back all zeros while looking like a
plausible-but-slow GEMM.

`wubu_isa_x86_64.c` used `0x7FF` (correct); only the interpreter used
`0x7FFF`. Whenever an encoder/decoder pair disagrees, diff the masks
across ALL backends -- the interpreter is the usual outlier because it is
the least exercised.

## 3. The ISA `run` contract

```c
run(code, size, (int64_t)(intptr_t)memory_pointer)
```

The third argument is the MEMORY POINTER, not a flags word. Backends do
`wubu_jit_mem_ptr = (int64_t *)arg`, so passing 0 makes every generated
store/load write through NULL and the JIT faults inside an mmap'd page
(looks like a corrupted jump, not a NULL deref). Standalone ISA probes
must calloc a real cell array and pass it.

## Debugging recipe

When an MIR program "runs but returns 0":

1. Print the program opcodes (`p.n`, `p.ins[i].op`) and confirm the
   instruction is actually emitted. A breakpoint on a `&&label` may not
   fire as expected -- set it by FILE:LINE inside the handler body, and
   remember the line number you picked may now be inside a comment.
2. Break in the handler and print the decoded dims/addresses. Wrong
   decoded dim = class 2.
3. Print the raw memory words at the bases. Zeroes where values were
   stored = class 1 (misaligned or unsized).
