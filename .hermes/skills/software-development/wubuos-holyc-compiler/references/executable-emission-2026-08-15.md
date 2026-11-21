# Executable Emission from HolyC (2026-08-15)

The HolyC compiler emits x86-64 machine code into JIT buffers. Three emitters
wrap this code into executable file formats.

## Three Emitters

| Flag | Format | File | Use |
|------|--------|------|-----|
| `-emit-elf <src> <out>` | ELF64 (Linux) | `holyc_elf.c` | Linux executables |
| `-emit-pe <src> <out>` | PE32+ (Windows) | `holyc_pe.c` | Windows .exe |
| `-emit-bin <src> <out>` | Raw binary | `holyc_bin.c` | Bootloader/shellcode |

## Shared Architecture

All three emitters share the same extraction pattern:

1. **Compile via the normal JIT path** — `compile_main()` parses, generates, and JITs
   the source. Function bodies are stored in `gen->functions[f].func_ptr`
   (mmap'd RWX buffers) with size `gen->functions[f].code_size`.

2. **Extract the function body** — copy `func_ptr[0..code_size]` into a
   mutable buffer. Patch RIP-relative globals using the function's own
   `global_patches[]` array: `disp32 = code_size + global_offset - patch_pos - 4`.

3. **Wrap in container format** — prepend headers/trampoline, write to file.

## CRITICAL: Function Body Extraction Pattern

The HolyC compiler compiles function bodies into SEPARATE exec buffers
(via `jit_alloc_exec()`), not the main code buffer. The main code buffer
only has module-level code. To get the function body:

```c
HCFunction *mainfunc = &gen.functions[main_idx];
uint8_t *func_code = malloc(mainfunc->code_size);
memcpy(func_code, mainfunc->func_ptr, mainfunc->code_size);
```

### BUG TRAP (fixed 2026-08-15)

`HCFunction.code_size` must be saved BEFORE restoring the main code buffer
in `HC_AST_FUNC_DECL` codegen. The pattern is:

```c
size_t func_body_size = gen->code_size;  // SAVE FIRST
gen->code = saved_code;                  // THEN restore main buffer
gen->code_size = saved_code_size;
gen->functions[fn].code_size = func_body_size;  // use saved value
```

If you read `gen->code_size` AFTER the restore, you get the main code
size (e.g., 11 bytes for the prologue) instead of the function body
size (e.g., 23+ bytes) → truncated binary that segfaults.

## ELF64 Emitter (`holyc_elf.c`)

- Single PT_LOAD segment (RWX) covering entire file from offset 0
- Fixed base address `0x400000`, non-PIE
- Prepends `_start` trampoline (12 bytes):
  ```
  call main     (e8 07 00 00 00)  → jumps past trampoline
  mov rdi, rax  (48 89 c7)        → exit code = main's return
  mov al, 60    (b0 3c)           → syscall number for exit
  syscall       (0f 05)
  ```
- Entry point = trampoline address (NOT user code)
- Research: Nathan Otterness "Tiny ELF", tchajed/minimal-elf

## PE32+ Emitter (`holyc_pe.c`)

- MZ header (64 bytes) + PE signature at offset 0x80
- COFF header (machine = 0x8664) + PE32+ optional header (magic 0x20B)
- Single `.text` section with code
- Entry point = start of `.text` (no trampoline yet — code ends with `ret`)
- Recognized by `file` as "PE32+ executable (console) x86-64"
- Research: TinyPE-on-Win10 (ayaka14732), Microsoft PE Format spec

## Raw Binary Emitter (`holyc_bin.c`)

- Writes code as-is, no headers
- Optional `bootable` flag: pads to 512 bytes + adds 0x55AA signature
- Used for bootloaders, shellcode, custom boot protocols

## Global Patching for ELF/PE

When emitting a function body that references module-level globals,
the RIP-relative displacements must be recalculated for the new layout:

```c
for (int i = 0; i < mainfunc->n_global_patches; i++) {
    size_t pp = mainfunc->global_patches[i].code_patch_pos;
    size_t go = mainfunc->global_patches[i].global_offset;
    if (pp + 4 <= func_size) {
        int32_t disp32 = (int32_t)(func_size + go - pp - 4);
        memcpy(func_code + pp, &disp32, 4);
    }
}
```

This works because in the ELF/PE layout, data follows code contiguously
in memory, same as the JIT layout.

## Link Line Requirements

All three emitters must be in the `holyc` link line:
```
$(COMP)/holyc_elf.c $(COMP)/holyc_pe.c $(COMP)/holyc_bin.c
```

## Verification

```bash
# ELF: compile, run, check exit code
./holyc -emit-elf test.hc test.elf && chmod +x test.elf && ./test.elf; echo $?

# PE: compile, verify with `file`
./holyc -emit-pe test.hc test.exe && file test.exe

# Binary: compile, inspect raw bytes
./holyc -emit-bin test.hc test.bin && xxd test.bin
```

## User Directive: Research Before Assuming

The user explicitly directed: "online research and learn how to be the best,
do not assume." This applies to executable format work:

- **Research the format spec BEFORE writing code** — don't guess header layouts
- **Use authoritative sources**: Microsoft PE Format docs, OSDev ELF spec,
  TinyPE-on-Win10 (ayaka14732), Nathan Otterness "Tiny ELF"
- **Verify with `file` command** — `file test.exe` should recognize the format
- **Test with actual execution** — exit codes for ELF, `file` recognition for PE
