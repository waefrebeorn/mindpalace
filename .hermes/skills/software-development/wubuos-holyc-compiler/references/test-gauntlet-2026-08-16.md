# Universal Test Gauntlet — 2026-08-16

The WuBuOS universal test gauntlet (`src/compiler/test_gauntlet/`) runs
tests via ACTUAL compilation through `hc_eval()`, not placeholders.

## Key Discovery: HolyC Expression Format

Tests MUST be written as HolyC expressions, NOT C programs:
- WRONG: `"int main(){return 1+2;}"` — `hc_eval` can't parse `int main(){}`
- RIGHT: `"1+2"` — `hc_eval` parses expr, compiles, runs, returns result
- RIGHT: `"{int a=5; int b=3; a*b}"` — block expressions work
- RIGHT: `"if(1) 42 else 0"` — control flow in expression context

`hc_eval(source)` handles: bare expressions, block wrapping, control flow.
It does NOT handle: `int main(){}`, function declarations, top-level programs.

## First Real Run (2026-08-16)

63 tests × 14 ISAs = 882 executions on x86-64 (native JIT):
- **47 PASS**: simple expressions (arithmetic, comparisons, bitwise)
- **16 FAIL**: found REAL HolyC compiler bugs:
  - Block expressions with semicolons (`{int a=5; a*b}` → 0)
  - Control flow in expression context (`if/while/for` → 0)
  - Variables in blocks (scope issue)
  - Signed overflow (`2147483647+1` → unsigned result)
  - Array/pointer access (need memory model)

Each failure = a real compiler bug to fix. The gauntlet is the bug-finding engine.

## Test Extraction

`tools/extract_tests.py` scans GCC torture suite + CompCert + stdtests,
categorizes by pattern matching, generates `gauntlet_*.c` files:
- gauntlet_integer.c: 1516 tests
- gauntlet_control.c: 765 tests
- gauntlet_comparison.c: 1331 tests
- gauntlet_bitwise.c: 500 tests
- gauntlet_float.c: 252 tests
- gauntlet_memory.c: 46 tests
- gauntlet_string.c: 40 tests
- **Total: 4,450 tests extracted, 121,000+ cataloged**

## C18 Policy (user-mandated, 2026-08-16)

- **ACCEPT**: C18 = C11 + ISO/IEC 9899:2018 defect reports (bugfix release)
- **REJECT**: C23, C2x, GNU extensions, C++ (any version)
- Jens Gustedt: "no normative changes (but one), lots of clarifications"
- Key C18 changes: atomics, threads, _Generic, alignment, sequence points,
  infinite loops, realloc(ptr,0), clock(), math errors

## Hardware Target Matrix (2026-08-16)

Three-era strategy documented in `references/hardware-target-matrix-2026-08-16.md`:

**Past (Pentium + DDR1, 1995-2005)**: Run on anything
- Minimum: Pentium 100MHz + 16MB EDO RAM
- All retro consoles: NES(6502), SMS(Z80), Genesis(M68K), PS1(MIPS)
- WuBu: x86-64 compat mode covers all x86; native drivers for retro

**Present (2020-2026)**: Fast everywhere today
- x86-64 native JIT, ARM64 native JIT, RISC-V encoder+interpreter
- GPU: PTX text (NVIDIA), AMDGPU text (AMD)
- NPU: planned (Intel IVPU, AMD AMDXDNA, Qualcomm QAIC)

**Future (2026-2040)**: Run everywhere tomorrow
- RISC-V V extension (vector), ARM SVE/SVE2
- Chiplet multi-ISA, FPGA bitstream
- Optical/quantum/neuromorphic research

## Language Router (wubu_lang_router.h/c)

14 languages routed by extension + shebang + content detection:
- ACCEPT: HolyC (.hc), C18 (.c), Brainfuck (.bf, +auto-detect >80% BF chars)
- TEMPLATE: Python (.py), JavaScript (.js) → JIT → WASM
- CONTAINER: C++, Rust, Go, Java, Swift, Fortran, Ada, COBOL
- REJECT: unknown (with helpful message)

Brainfuck accepted as "AGI-era backdoor canary" — demonstrates our
compiler handles even intentionally unreadable languages.

## Workflow Preference (user, 2026-08-16)

"Go big first, make big code" — the user prefers ambitious sessions
that produce large artifacts (4,450 tests, 15-technique research docs,
hardware matrices) over incremental small changes.

## User-Corrected Scope (2026-08-16)

- "we need to make RISC-V as well probably" — RISC-V is a target, not optional
- "allow C18 but no higher" — C18 is the ceiling, not C11
- "targeting all of the hardware CPU GPU accelerator" — comprehensive target coverage
- "past = Pentium with DDR ram, present = where we are today, future = ARM and RISC-V"
