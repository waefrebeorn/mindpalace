# C11 monolith split — slicer pitfalls + Makefile link-unit pattern

Captured 2026-07-18 while dissolving the 1048-line `wubu_dos_emu.c` monolith into 6
units. Reusable for any WuBuOS C11 monolith split.

## Slicer pitfalls (the bugs that cost iterations)

1. **Don't brace-match the body.** A naive `{`/}` counter mis-balances when the
   function's opening `{` shares the signature line (e.g. `uint8_t rd8(...) {`). Slice
   each def as `[def_start, next_def_start)` — boundaries are guaranteed by the def
   positions, so you never match braces across the body. See `scripts/c11_monolith_split.py`.

2. **`static` in a prototype = conflict.** Extracting a signature by grabbing the whole
   first line (e.g. `static uint16_t rw(...) { ... }`) as a "declaration" puts a
   `static` *definition* into the header → `implicit declaration` / `conflicting types`.
   The internal header must carry **non-static declarations** (`static` stripped); the
   leaf modules carry the **non-static definitions** (or match the header exactly).

3. **`static inline` helpers belong in the header, once.** `phys()` (address compute)
   is wanted by every leaf, so define it `static inline` in the internal header and
   DROP its body from the leaf entirely. Leaving a leaf copy → `redefinition of 'phys'`.

4. **Forward-declaration lines in the monolith must be skipped**, not duplicated.
   A leaf may contain `static int decode_main(...);` as a forward decl. Filter pure
   `static <ret> name(...)；` lines (no `=` / no `{`) out of the body before writing —
   the header already declares it.

5. **`back_capture` must validate the merged text.** When pulling a type-continuation
   line above the def (multi-line return type), only prepend it if the merged string
   still contains the function name; otherwise you silently merge two adjacent defs
   (the prior one's closing `}` gets swallowed → a duplicated/truncated function).

6. **Generate from `git show HEAD:<path>` when the working tree is suspect.** A prior
   broken slicer run can leave the working file in a half-written state; deriving from
   the pristine blob avoids self-corruption. Verify: `grep -c wubu_dos_emu_create`.

7. **Don't trust a stale binary for green-checking.** A failed `gcc ... -o bin` leaves
   the OLD `bin` on disk; re-running it reports 22/22 from before. `rm -f bin` before
   each compile, then check `build_rc` separately from `run_rc`.

## Makefile link-unit pattern (the part that usually breaks the build)

After a split, the engine is multiple `.o` files that must ALWAYS travel together.

- **Define one variable for the unit:** `WUBU_DOS_EMU_OBJS = $(RT)/wubu_dos_emu.o
  $(RT)/wubu_dos_emu_mem.o ... $(RT)/wubu_dos_emu_decode.o`. Reference it from
  `RT_OBJS`, `HOSTED_OBJS`, and every test recipe. Adding a function to a leaf then
  never requires touching link lines.

- **The `hosted` link line does NOT expand `$(RT_OBJS)`.** It lists explicit
  `$(RT)/*.o` files. So merely adding to `RT_OBJS` is not enough — you must also add
  `$(WUBU_DOS_EMU_OBJS)` to `HOSTED_OBJS` (the list the hosted recipe actually links).

- **Never list both a `.c` source and its `.o` for the same TU on one link line.**
  `test_dos_window` had this exact bug (compiled `wubu_dos_proc.c`/`wubu_dos_emu.c`
  AND linked `wubu_dos_proc.o`/`wubu_dos_emu.o`) → `multiple definition of wubu_dos_emu_*`.
  Pick ONE form per translation unit across the whole recipe.

- **Verify the split end-to-end:**
  ```
  make runtime            # builds every leaf .o
  make hosted             # full binary links (proves no undefined ref)
  make test_dos_emu       # 22/22
  make test_dos_proc test_styxfs test_dos_window
  # duplicate-symbol scan:
  for f in wubu_dos_emu wubu_dos_emu_{mem,regs,alu,int,decode}; do
    nm -gC --defined-only src/runtime/$f.o | awk '{print $3}'; done | sort | uniq -d
  # (empty = no duplicate definitions)
  ```
