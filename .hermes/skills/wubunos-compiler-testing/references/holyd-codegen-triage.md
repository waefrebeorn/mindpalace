# Triaging a HolyD/JIT codegen bug from a wrong value

Class of task: a `selfhost_battery` probe (or `test_holyc` Codegen/Eval case)
returns a wrong value instead of crashing. The pipeline is
preprocess -> parse -> AST -> codegen -> JIT -> execute, and a wrong value can
originate in any stage. This is the procedure that actually converges.

## Order of operations (do not reorder)

1. **Reproduce in a standalone probe, not the test binary.** Copy the exact
   source-list and flags from the `test_battery` Makefile rule and link a
   10-line `main` that calls `hd_eval(<source>)` and prints the result. The
   test harness forks, isolates, and prints in its own format; a probe gives
   you a single number and a gdb you can break on.

2. **Bisect the source expression before reading any C.** Split the failing
   one-liner into its smallest working parts and print each. For
   `struct S{int a;int b;}; struct S s; s.b=20; int* p=&s.b; *p;` this showed
   `s.b` OK, `*(&s.b)` OK, and only `int* p=&s.b; *p` broken — which
   immediately localizes the bug to "address of a member stored into a
   pointer", not to member access or deref in general.

3. **Dump the preprocessed text BEFORE reading the parser or codegen.** Break
   in gdb where `hd_eval` computes `effective = pp ? pp : source` and print
   both. This is the single highest-value check: a surprising number of
   "parser/codegen" bugs are the preprocessor deleting text. Compare
   `source` against `effective` character by character — the fix is obvious
   once you see a construct missing.

4. **Only then break in gdb on the codegen line and read the AST.**
   `p node->kind`, `p node->then_branch`, `p node->else_branch->kind` etc.
   A NULL child field means the parser built a node the codegen cannot
   consume — go back to step 3 and ask why.

5. **Dump the emitted bytes and the relocation table, and disassemble by hand.**
   `x/40bx gen->code`, `p gen->code_size`, and
   `p gen.global_patches[i].code_patch_pos` / `.global_offset`.
   Compute each RIP-relative displacement yourself and compare against what
   the patch loop actually wrote
   (`disp32 = code_size + global_offset - patch_pos - 4`). Watch for the
   patch positions that were registered but never filled — a zero
   displacement where you expected a small positive one is the tell.

6. **Use MIR as the oracle.** `mir_gen_stmt` / the interpreter usually
   implement the construct correctly while the JIT does not. When the two
   disagree, the JIT is the bug — read the MIR version and match it rather
   than designing a new lowering.

## Pitfalls

- **Stale probe binary.** gdb prints "Source file is more recent than
  executable" and you will happily debug last week's build. Rebuild the
  probe after every source edit and confirm the failure still reproduces
  before drawing any conclusion from gdb state.
- **Never stack a speculative fix on an unverified theory.** Patch one
  hypothesis, rebuild, and if it does not change the result, `git checkout --`
  that file immediately. Three wrong theories compounded in one file cost far
  more than they saved and leave the tree lying about its own state. Reverting
  is not lost work — the gdb evidence you gathered is the work.
- **Byte dumps read as instruction groups, not per-byte fields.** A
  displacement byte that looks like an opcode (`0f 18`, `1f 18`) is usually
  just the tail of the previous instruction's disp32. Count instruction
  lengths forward from the last known-good boundary before concluding an
  instruction is wrong.
- **Check the unit convention once, at the source of truth.** Struct member
  offsets and type sizes are stored in CELLS in the AST while
  `hd_type_size()` returns BYTES, so any member-offset use site needs
  `* 8`. Grep for *every* use of `members[i].offset` and confirm each one
  converts exactly once — a site that omits it and a site that does it twice
  look identical until you read the arithmetic below it.
- **A test expectation can itself be the bug.** Before "fixing" a probe,
  check that a correct implementation could produce the expected value.
  `(int)(long)(void*)(long)&x == 0` cannot hold, since `&x` is a real
  address. Report it as a bad expectation instead of contorting the codegen
  to satisfy it.
- **A hanging probe is a finding, not a tooling problem.** `goto loop` whose
  body was never emitted spins at 100% CPU forever. Any harness that reads a
  child's output with a blocking `read()` will hang `make test` with no
  output at all; give it a `select()` budget plus SIGKILL so a spin becomes a
  visible WRONG rather than a stalled build.

## Symptom-to-stage quick map

| Tell | Stage to suspect |
|---|---|
| Result equals the JIT allocation address | AST built no expression (prologue+epilogue only, `code_size` ~13) |
| Result is the *then* value of every ternary | preprocessor stripped the else branch, or `else_branch` is NULL |
| Result is a plausible but wrong host address | missing/wrong global relocation patch |
| `gen.data_size` far larger than the source implies | preprocessor injected declarations |
| Infinite loop at 100% CPU, no crash | label/loop body never emitted |
| Correct in MIR/interpreter, wrong in JIT | JIT lowering diverged from `mir_gen_*` — match MIR |