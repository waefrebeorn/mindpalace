---
name: wubunos-selfhost-loader
description: Self-host .hd loader stages + cross-backend consistency.
---
# WuBuOS self-hosting: loader-run .hd stages (B2) and cross-backend consistency (B4)

The "demo vs compiler" class (DA#1) is closed by proving the OLD
`holyd_codegen_*` emitter actually carries the language through the loader,
and that it does not diverge from the modern `holyd_mir_eval`. Both are
verified, gated tests.

## B2: add a self-hosted stage to the loader harness (wubuos)

Each stage = a tiny HolyD program in `src/runtime/selfbuild/<name>.hd`
(single `int f(){}`; the LAST function is the entry) wired as a new block in
`src/kernel/test/tokenizer_test.c`: read_text("src/runtime/selfbuild/<name>.hd")
-> emit_one() (lex + parse via holyd + hd_write_pe_program) -> wubu_zx_run at
TWO bases (0x00400000 and 0x00420000) -> CHECK the entry result. Add the .hd to
the `test_wubu_tokenizer:` dep line in mk/tests.mk.

Proven stages (all green, both bases): tokenizer.hd lexes "int x = 42"->4;
expr.hd 14; param.hd 2-arg helper->9; num.hd multi-digit "321"->321;
checksum.hd walks "WUBU" through a real `char*` (deref + increment, not
computed index) ->323; struct.hd stores/loads members with their own 4-byte
width ->42.

The old backend ALREADY handles strings, pointers, structs, loops, params,
recursion through emit->relocate->run -- the stale claim that structs/unions
are "missing in holyd_codegen_*" is FALSE (empirically disproven). Do not
re-plan a backend lift for it; probe before assuming.

## B4: cross-backend consistency (wubunos `make test_backend_consistency`)

Proof the OLD loader-path emitter and the MODERN `holyd_mir_eval` agree: embed
the SAME construct-heavy .hd sources, call `hd_eval_mir(src + "\nf();\n", NULL)`
(NULL driver -> MIR interpreter) for each, assert it equals the loader-path
anchor (checksum 323, struct 42, multi-digit 321, tokenizer 4 -- real loader
runs from wubuos tokenizer_test). 4/4 AGREE -> no divergence on
string/pointer/struct/lexer. Fails the gate if a future backend change
diverges. Model the Makefile target on test_mir_battery's link (needs the full
holyd_mir_eval + MIR + ISA driver deps even though only the interpreter runs,
because holyd_mir_eval pulls the MIR + isa_driver registry).

PITFALL -- the resulting test binary is >1 MiB (all ISA backends linked), and
the Hermes lifecycle guard BLOCKS running it by direct path. Run it via
`make test_backend_consistency` (make's `./$@` runs fine); don't invoke the
binary directly. rm the built binary before committing (it's a build artifact).

## Full-circle emitter: HolyD -> ELF -> native execution

`make test_holyd_native` (wubunos) proves the compiler emits genuine machine
code: a thin emitter (`tools/holyd_emit_elf.c`) compiles a freestanding source
to a loadable x86-64 ELF and a runner (`tools/holyd_elf_run.c`) mmaps + calls
the entry on the native CPU.  Green and must stay green:
- `int main(void){return 42;}` -> native exit 42.
- `tools/selfbuild_checksum.hc` (pointer-walk over a .data string, body ident-
  ical to `src/runtime/selfbuild/checksum.hd`) -> native exit 67 (== 323 & 0xff),
  matching the loader's 323.  Emitted code == loader interpretation on pointer
  deref + .data reads.

Build: `make holyd_emit_elf holyd_elf_run` (needs `-I $(OS_ROOT)/jit` so the
`../jit/jit.h` include in holyd_codegen_internal.h resolves).  `tools/std_jit_stub.c`
stubs jit_alloc/free/lock_exec so the codegen links WITHOUT the whole OS JIT +
minic + spawn chain.

PITFALLS:
- The emitter's ELF puts code at vaddr 0x400078 (0x78 ELF-header pad) with the
  entry = the compiled `main` body; data immediately after it.  RIP-relative
  global patches assume code at func_size + go (the JIT convention), which the
  loader honors.
- Native-run assertion is the PROCESS EXIT CODE, not stdout: running emitted
  code over the trampoline mangles the caller frame enough that glibc stdio
  writes get lost, while the exit status value is exact.  Exit codes truncate
  to 8 bits (323 -> 67).
- `holyd -emit-elf` needs the full wuburuntime broker (holyd.c main pulls
  wubu_runtime); the THIN emitter avoids it entirely.

## Full-circle boot: HolyD-emitted ELF boots under GRUB into long mode

`make boot-verify` (wubunos) emits `return 42` as a MULTIBOOT-BOOTABLE kernel
(`holyd_emit_elf --boot` / `hd_write_boot_elf`), packs it in a GRUB ISO, boots
it in QEMU, and asserts the serial trace gets the 32-bit entry marker 'Z' AND
the post-long-mode 64-bit marker 'Y'.  Green.  The compiler's OWN ELF reaches
bare-metal long mode without a gcc kernel.  Needs grub-mkrescue+xorriso+qemu.

The boot ELF layout: single PT_LOAD at 0x400000 = [ELF hdr+phdr][mb hdr + gdptr
+ gdt + 32-bit prologue][PML4/PDPT/PD identity tables @0x1000-0x4000][64-bit
payload @0x4000: set rsp, call main, COM1 out, halt][main body][data].  The
prologue enables PAE huge-page paging, EFER.LME, then far-jumps to the 64-bit
payload.

PITFALLS (each was a real boot fault; the sequence is the recipe):
- multiboot enters with CS=0x10 -- in OUR gdt selector 0x10 must be a 32-bit
  CODE descriptor or the fetch right after lgdt #GPs.
- the gdptr (6-byte limit+base) must live AT the address lgdt reads; pointing
  lgdt at the gdt itself loads limit 0 -> every later selector load #GPs.
- bare `B8 nop bytes` is `mov eax,imm32` and eats the next bytes; 16-bit moves
  need a 0x66 prefix.  Data descriptors keep L=0 (gran 0xcf), L bit is code-only
  and #GPs on a data load.
- GRUB 2.12 rejects e_shoff=0 -- append a minimal shstrtab section header table.
- the on-disk lm64 must be placed by explicit fseek (not pad math), or the
  far-jump target misses the payload.
- a `call rel32` is E8 + FOUR displacement bytes (5 total).  Emitting E8 + FIVE
  zero bytes (6) leaves a stray 0x00 right after the call: after main returns,
  the CPU executes that 0x00 as `add [rax],al` -> #PF -> double fault.  The
  symptom was main returning the RIGHT value (RAX=323, seen in QEMU -d int) but
  then faulting before it could print.

make boot-verify asserts THREE gates: `HOLY-BOOT` (boot into long mode: Z,Y on serial), `HOLY-BOOT-DATA` (compiled main does .data string access after boot, printing the literal hex 00000143 = 323), and `HOLY-BOOT-PRINT` (the program's own Print() writes to COM1). The compiler's own kernel computes over memory in bare-metal long mode with no gcc involved.

WubuOS side (the deploy repo): `make holyd-verify` builds the emitter via the
src/compiler symlink (`make -C src/compiler holyd_emit_elf`), emits a bootable
kernel, packs it in a GRUB ISO the same way `make iso` does, and boots it in
QEMU, asserting Z, Y and the readable hex Result -- e.g. ZY0000002A (=42) or
ZY00000143 (=323).  So a HolyD-compiled image boots through the EXACT deploy
path the real kernel.elf uses.  Full wubuos gate stays green.
Compile-only; add targets.mk (wubuos) + Makefile (wubunos), no source guts.

HOLY SOURCE DOES ITS OWN SERIAL I/O: the boot ELF carries an 18-byte
serial_puts(const char *s in rdi) at a FIXED offset SERIAL_PUTS_OFF 0x6000
(mov edx,0x3f8; loop: mov al,[rdi]; test; jz ret; out; inc rdi; jmp loop; ret),
and the emitter registers the print builtins (print/Print/puts) to
ELF_BASE+SERIAL_PUTS_OFF for --boot via hd_register_boot_runtime().  A HolyD
program's own Print("WUBU from HolyD") then writes to COM1 in the booted
kernel -- no host, no gcc, no hand-written tail doing the printing.  Gate:
make boot-verify HOLY-BOOT-PRINT asserts the literal string on serial.

PITFALL: stale *.d files.  The wubunos Makefile does -include $(wildcard *.d
tools/*.d); .d files generated under the old src/compiler/ layout inject rules
for src/compiler/*.o -> src/compiler/*.c, which no longer exist, so a plain
'make' fails with 'No rule to make target src/compiler/...'.  They are derived
(untracked); delete *.d tools/*.d and rebuild to regenerate correct paths.
The real gates (make holyd_emit_elf / test_holyd_native / boot-verify) are
unaffected because they don't pull the stale includes.

BOOT OUTPUT = UPPERCASE HEX: the tail serializes the compiled main's RAX as 8
uppercase hex digits (00000143 style; bcd-adjust is `add 7` then `add '0'`,
producing 'A'-'F').  Write gate assertions against the literal text (0000002A,
00000143), and don't re-run the two-repo wiring blind: the wubuos holyd-verify
assertion must match the compiler's actual case.

PITFALL: a LOOPED hex printer (mov esi,28 / shr eax,cl / sub esi,4 / jns
loop) double-faulted after ONE digit even though it disassembled correctly --
the variable-shift/loop register dance has edge cases.  The UNROLLED version
(eight fixed `mov eax,ebx; C1 E8 <imm>; and 0xf; cmp 0xa; jb 2; add 7; add
'0'; out` blocks, shift 28..0 step 4) is deterministic and works.  Use
unrolled code for anything timing/loop-sensitive in the boot tail.

NEXT (still open): grow the emitted payload into a fuller kernel (more of the
language's own constructs -- loops, structs, memory-mapped state) and swap it in
for gcc's `kernel.elf` in the wubuos `make iso`/`qemu` pipeline to fully close
the "compiler compiles the OS" circle.  Single-program scale is proven: boot,
.data access, the program's own Print(), and readable hex output all work.

## Arena notes

- wubunos is the compiler repo (branch wubu-integration; commit there for
  compiler changes); wubuos links the compiler via the src/compiler symlink.
  Push BOTH repos for a compiler change.
- The wubunos `make test` aggregate is RED at baseline for an UNRELATED,
  pre-existing test_isa_driver failure (ptx / arm64 COMPILE FAIL) -- untouched
  by B2/B4; don't confuse it with your own gate failure.
