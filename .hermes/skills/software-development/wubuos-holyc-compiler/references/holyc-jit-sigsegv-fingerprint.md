# HolyC JIT SIGSEGV — classify the crash in 10 seconds

A `hc_eval` / `wubu_holyd_eval` run that dies inside the JIT buffer is one of
THREE distinct bug classes. Read the gdb fingerprint before editing:

```bash
gdb -q -batch -ex run -ex bt --args ./your_test_bin
# or for the in-tree demo path:
gdb -q -batch -ex run -ex 'x/12i $pc-10' --args ./src/gui/era_apps_test
```

## Class 1 — Unresolved extern → `call 0` (the `rax=0` tell)
**Fingerprint:** `bt` shows the faulting PC inside a `rwxp` (JIT) page, the
crashing instruction is `call *%rax` (or `call *%rXX`), and **`rax = 0`**
(`rax`/`rdi` may point at a BSS string like `"runtime"` — the first
`Print("...")` argument). The codegen emitter fell through to its UNresolved
identifier fallback, which emitted `mov rax, 0; call rax` — a NULL-pointer
indirect call.

**Why:** the JIT has a real extern mechanism (`gen->extern_funcs[32]`, registered
via `hc_register_extern`) but nothing registered the identifier the HolyC
program called (e.g. the era demo's `Print()` / `FpWriteFile()`). This is a
GENUINE bug, not a stub — there is a legitimate HolyC runtime the program
expects.

**Fix (3 parts, see `wubuos-holyc-compiler` "Unregistered extern" entry):**
1. Create `src/compiler/holyc_runtime.c` with real host implementations
   (`wubu_print`, `wubu_fp_write_file`, …).
2. In `hc_eval`, after `hc_gen_init`, call `hc_register_holyc_runtime()` which
   registers `Print→wubu_print` etc.
3. Harden the JIT fallback so it NEVER emits `call 0` — emit `mov rdi, rax`
   (name ptr) then `call hc_unresolved_trap` (a real `fprintf(stderr)` + return
   trap) so a still-unknown call fails loudly, not with a SIGSEGV.

**Consequence:** adding `hc_register_holyc_runtime` means `holyc_runtime.o`
must be on EVERY link recipe that compiles `holyc_codegen_api.c` — see
`wubuos-build-recovery` Mode H (the `COMP_OBJS` + per-target sweep).

## Class 2 — Missing stack frame (garbage constant)
**Fingerprint:** `rax` holds a CORRECT-ish value but the store/load is at a
bogus stack slot; every local-var eval returns the same garbage constant across
tests. The prologue is only `push rbp; mov rbp, rsp` with no `sub rsp, N`.
Fix: reserve a frame (`sub rsp, 256`) in `emit_prologue`.

## Class 3 — Unpatched global relocation (RX-data / RIP-relative)
**Fingerprint:** faulting PC is at a `mov %rax,0xN(%rip)` (global store) with
`rax` already correct, or a `mov [rbp - (negative)], rax` (global misrouted to
stack). Data-section is RX (`jit_lock_exec` called when `data_size>0`), or the
Inc/Dec/`&x` cases emit `[rbp-off]` instead of RIP-relative for a global.
Fix: don't lock when globals exist; dispatch globals on `off<=0` to
`emit_global_*` + `global_patches[]`.

## One-line triage rule
`rax==0` at a `call *%rax` in a `rwxp` page ⇒ Class 1 (unregistered extern).
Everything else ⇒ Class 2/3 (codegen frame/relocation). Don't touch the
emitter's extern fallback until you've confirmed the class.
