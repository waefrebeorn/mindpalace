# mips uses FRAME-RELATIVE memory; every other backend uses the raw cell

Found by tools/test_backend_diff.c (commit 990cb37). Do not "fix" this by
papering over it in a test.

## The convention

`wubu_mips_interp.c` implements MIR memory through two hostcalls:

    case 25: /* MEM_LOAD */  uint32_t cell = read32(&cpu, basev + sa);
                              r = (basev + cell < MIPS_MEM) ? cpu.mem[basev + cell] : 0;
    case 26: /* MEM_STORE */ uint32_t cell = read32(&cpu, basev + sb);
                              cpu.mem[basev + cell] = (uint8_t)(val & 0xFF);

`basev` is `$sp` (`cpu.r[29]`, set to `MIPS_MEM/2 & ~15`, then reduced by the
backend's `addiu $sp, $sp, -frame` prologue; observed basev = 32676).

So a MIR cell address is interpreted RELATIVE TO THE FRAME on mips.

Every other backend (x86-64, 8086, m68k, riscv, z80, 6502, ptx, spirv)
indexes the raw cell in the flat `int64_t*` memory passed to
`run(code, size, memory_pointer)`.

Consequence: a program that stores through cell N and loads through cell N+0
disagrees on mips. Storing through `base` and loading through `base + 0` is
the concrete failure -- that is what the oracle caught first.

## Also: mips memory ops are ONE BYTE wide

`MEM_STORE` writes `(uint8_t)(val & 0xFF)` and `MEM_LOAD` returns a single
byte, even though the MIR contract is 64-bit CELLS (`int64_t`). That happens
not to show up for small values such as 63, but it will for any value above
255 and it disagrees with the flat backends.

## How to settle a mips memory question quickly

Do NOT reason about it -- instrument. The confusing part is that
`fetch32(cpu, code, size)` reads the ORIGINAL `code` buffer, not `cpu.mem`, so
a slot write CANNOT clobber the instruction stream. That rules out the
code/frame collision theory, which looks plausible and is wrong. (I tried it;
it did not change the result and had to be reverted.)

Build a standalone probe (`/tmp/mipsmem.c` pattern): build the MIR program,
call `d->compile`, then `d->run(code, sz, mem)`. A program that fails inside
the 13-backend oracle but returns the right answer standalone means the ORACLE
is at fault, not the backend -- that is how the addressing mix-up was
identified.