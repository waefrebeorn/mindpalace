# crt0.S RIP-Relative Addressing Fix (2026-06-29)

## Problem
The crt0.S assembly file used 32-bit absolute addressing (`movl $_kernel_end, %edi`) which generates `R_X86_64_32` relocations. These relocations are truncated when linking a 64-bit kernel because 32-bit absolute addresses don't fit in 64-bit address space.

**Error**: `relocation truncated to fit: R_X86_64_32 against symbol '_kernel_end'`

## Root Cause
The original crt0.S used NASM syntax with 32-bit absolute addressing:
```nasm
mov edi, _kernel_end
add edi, 0xfff
and edi, ~0xfff
mov [page_table_base], edi
```

In GAS/AT&T syntax with 64-bit linking, symbol references must be RIP-relative:
```gas
movl $_kernel_end(%rip), %edi
```

## Fix Applied (2026-06-29)

### 1. Changed to GAS/AT&T syntax
- Removed `.intel_syntax noprefix`
- Used AT&T syntax throughout (`movl %eax, %ebx` style)
- Changed `.code32` / `.code64` to standard `.code32` / `.code64`
- Used `%` prefix for registers

### 2. RIP-relative symbol references
Changed all symbol references from absolute to RIP-relative:
```gas
# Before (NASM absolute)
mov edi, _kernel_end

# After (GAS RIP-relative)
movl $_kernel_end(%rip), %edi
```

### 3. Scale factor fixes
GAS only accepts scale factors of 1, 2, 4, 8 in addressing modes:
```gas
# Before (invalid scale 511*8 = 4088)
movl %eax, (%edi, 511*8)

# After (use leal with explicit offset)
leal 4088(%edi), %edx
movl %eax, (%edx)
```

### 4. Symbol references in 64-bit mode
In `.long_mode_start` (64-bit mode), use 64-bit registers with RIP-relative:
```gas
movq _stack_top, %rsp
movq %rsi, limine_boot_info
call kernel_main
```

### 5. Section directives
Changed from NASM to GAS directives:
```gas
.section .multiboot_header
.section .text
.section .rodata
.section .bss
```

### 6. Macro changes
- NASM `%macro` → GAS `.macro`
- `ISR_STUB` macro converted to GAS `.macro`/.`endm`
- `push 0` / `push 1` syntax for immediate values

## Build System Changes

### Makefile: Assembly compilation
```makefile
# Assembly files (use GCC for GAS)
$(KERNEL)/%.o: $(KERNEL)/%.S
	$(CC) $(CFLAGS) -DMYSEED_METAL -DWa -DWUBU_NO_LIBM -ffreestanding -nostdlib -nostartfiles -fno-pie -mno-red-zone -mcmodel=kernel -I$(KERNEL) -c $< -o $@
```

Note: Use `$(CC)` (GCC) not `nasm` — GAS handles the `.S` file with proper preprocessor support.

## Verification
After fix:
```bash
make kernel
# Should build without R_X86_64_32 relocation errors
# Generates kernel.elf at 1MB physical / higher-half virtual
```

## Key Symbols Fixed
- `_kernel_end` — now RIP-relative in 32-bit mode
- `_kernel_start` — RIP-relative in 32-bit mode  
- `_stack_top` — RIP-relative in 64-bit mode
- `page_table_base`, `pdp_base`, `pd_base`, `pt_base` — RIP-relative
- `limine_boot_info` — RIP-relative
- `gdt64_ptr` — RIP-relative in `lgdt`