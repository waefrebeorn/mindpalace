# Multi-ISA Driver Space — 14 ISAs from ONE MIR (2026-08-15)

The ISA driver space grew from 6 to 14 drivers. Each is a `wubu_isa_driver_t` in `src/compiler/`:

| ISA | Year | Family | Exec | Status |
|-----|------|--------|------|--------|
| x86-64 | 1995 | cpu | NATIVE (mmap JIT) | ✅ |
| ARM64 | 2011 | cpu | NATIVE (mmap JIT) | ✅ |
| MIPS | 1985 | cpu | INTERPRETED | ✅ |
| 8051 | 1978 | mcu | INTERPRETED | ✅ |
| AVR | 1996 | mcu | INTERPRETED | ✅ |
| PIC | 1976 | mcu | INTERPRETED | ✅ |
| 8086 | 1978 | cpu | EMULATED (DOS emu) | ✅ |
| M68K | 1979 | cpu | INTERPRETED | ✅ |
| 6502 | 1975 | mcu | INTERPRETED | ✅ |
| RISC-V | 2010 | cpu | INTERPRETED | ✅ |
| Z80 | 1976 | mcu | INTERPRETED | ✅ |
| PTX | 2024 | gpu | TEXT EMISSION | ✅ |
| AMDGPU | 2022 | gpu | TEXT EMISSION | ✅ |
| WASM | 2017 | vm | INTERPRETED | ✅ (in JIT space) |

**Adding a new ISA** = ~200 lines: one `wubu_isa_*.c` with `{name, family, exec, compile, run, describe}`.

**Test gauntlet**: `test_drivers` (33 exprs × all drivers) + `test_isa_driver` (72 tests) + `test_album` (72 tests). All green.

**Executable emission**: ELF64 (`holyc_elf.c`), PE32+ (`holyc_pe.c`), raw binary (`holyc_bin.c`). All use byte-level serialization (no `__attribute__((packed))`).

**Portable patterns**: `wubu_clear_cache()` replaces `__builtin___clear_cache`. `jit_alloc_exec()`/`jit_free_exec()` use `malloc` in self-hosted mode, `mmap` in hosted. All `sys/mman.h` guarded behind `WUBU_HOSTED`.

## Language Routing System (2026-08-15)

`wubu_lang_router.h/c` routes 14 languages with policy flags:

| Language | Policy | Action |
|----------|--------|--------|
| HolyC | ACCEPT | Native on all 14 ISAs |
| Brainfuck | ACCEPT \| MEME \| AGI_READY | Compiled for real |
| Python/JS | TEMPLATE \| WASM_FALLBACK | JIT → WASM |
| C/C++/Rust/Go/Java/Swift/Fortran/Ada/COBOL | CONTAINER | Route to container |
| Unknown | REJECT | Helpful error |

**The Brainfuck exception**: Accepted because (1) it's a funny meme, (2) demonstrates simplicity, (3) AGI-era "backdoor coding" canary — hard-to-read languages that humans can't audit but AGIs can generate. See `~/vault/research/AGI_BACKDOOR_CODING.md`.

## Test Gauntlet Framework (2026-08-15)

`wubu_test_gauntlet.h/c`: universal test harness. Memory-structured (16KB result store), C11 pure.

**Downloaded test suites** (in `~/vault/test-suites/`):
- GCC Torture: 1,918 tests
- CompCert: 221 tests
- Csmith: unlimited (generator)
- stdtests: 5,000+ tests

**Extracted**: 4,450 tests categorized into integer(1516), control(765), comparison(1331), bitwise(500), float(252), memory(46), string(40).

**Extractor**: `tools/extract_tests.py` scans suites, categorizes by pattern matching, generates `gauntlet_*.c` per category.

## Research References (2026-08-15)

- `~/vault/MANIFESTO.md` — mission statement ("WuBu magic, not GNU bullying")
- `~/vault/research/MEGA_RESEARCH_COMPILER_IMPROVEMENTS_2026-08-15.md` — 33 sources, 15 techniques, 4-phase roadmap
- `~/vault/research/FAST_COMPILER_TIBLEIZ_2024-02-04.md` — 8 speed techniques from Marc Kerbiquet
- `~/vault/research/COMPILER_IMPROVEMENTS_25RESEARCH_2026-08-15.md` — 25 Kevin-Bacon queries
- `~/vault/research/TEST_GAUNTLET_REFERENCE.md` — 12 test suites, 121K+ tests cataloged
- `~/vault/research/AGI_BACKDOOR_CODING.md` — why we accept brainfuck
