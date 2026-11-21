# The ISA `run` contract: arg is a MEMORY POINTER, not a value (2026-09-30)

Cost me a false "x86-64 is broken" diagnosis. Read this before writing any
standalone backend probe.

## The contract

`driver->run(code, size, arg)` treats `arg` as `(int64_t)` cast of a
**pointer to the program's memory cells**. In `x86_run`:

    wubu_jit_mem_ptr = (int64_t*)arg;

and the emitted code loads that base and indexes into it. Passing `0` sets
`wubu_jit_mem_ptr = NULL`; the JIT'd code then dereferences NULL and the
process dies inside the generated code, with a backtrace that points at
libc rather than at the compiler.

The correct sequence, mirroring `holyd_mir_eval.c`:

    wubu_mir_prog_t prog;  hd_build_mir(src, &prog);

    int64_t mem_hi = 0;
    for (i in prog) if (op is MIR_LOAD/MIR_STORE) mem_hi = max(mem_hi, ins.a);
    mem_hi = max(mem_hi, prog.next_vr_hi - 1);
    size = (mem_hi < 1) ? 1 : mem_hi + 1;
    uint8_t *mem = calloc(size + 16, sizeof(int64_t));   /* +16: memset/memcpy
                                                            may write 7 bytes
                                                            past the last cell */

    wubu_mir_prog_t copy = prog;  copy.mem = mem;
    d->compile(&copy, &code, &csize);
    int64_t r = d->run(code, csize, (int64_t)mem);

## The trap

Straight-line expressions like `127 + 1` **never touch memory**, so passing
`0` appears to work — and did, for a dozen probes, silently validating
nothing about memory-using programs. The first loop or array dereference is
where it dies.

Symptom seen: `SIGSEGV` with `#0` in an anonymous library address, `#1` in
`__printf_buffer_flush_to_file`, `#3 x86_run`. It looks like a printf bug or
a JIT allocator bug. It is neither; it is a NULL memory base.

## Second trap: a wrong hypothesis that looked right

Before finding this, I assumed the byte-patching loop in `x86_run`

    if (patch[i] == 0x48 && patch[i+1] == 0xBE)   /* movabs rsi, imm64 */
        patch[i+1] = 0x89; patch[i+2] = 0xDE;     /* -> mov rsi, rbx */

was corrupting instructions, because it matches on bytes with no opcode
decode. It is still a latent hazard, but it had **zero** collisions in the
failing 567-byte program. Dumping the code and counting the byte pair is
what settled it — do that before "fixing" a scanner.

## Verification that resolves backend questions

Run the same source through both the native backend and `wubu_mir_interp`
and compare. When they agree, the compiler and the interpreter are both
right and any other backend's disagreement is that backend's bug. When they
disagree with each other, suspect the probe first.
