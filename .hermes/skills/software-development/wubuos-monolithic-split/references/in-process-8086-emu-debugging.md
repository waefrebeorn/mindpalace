# Debugging an in-process 8086 / DOS-shim interpreter (WuBuOS `wubu_dos_emu`)

Concrete bug classes found while building the real 8086 + DOS-INT shim
(`src/runtime/wubu_dos_emu.{c,h}`) and its unit test harness
(`wubu_dos_emu_test.c`). Each cost a multi-hour hang or a silently-failing test.
Capture them so the next session doesn't re-derive them.

## 1. A runaway program hangs the host process (1800s timeout)

Symptom: `gcc ... -o /tmp/x && /tmp/x` never returns; `timeout 1800` kills it.
Root cause: the `run()` loop had `max_steps==0` meaning "unbounded", and a COM that
falls through into a zeroed region loops forever on `add [bx+si],al` no-ops.

Two fixes (both non-negotiable for any CPU/VM step loop):
- **Handle the terminate vector explicitly.** DOS `int 20h` was not special-cased; the
  generic `int` dispatch read an uninitialized IVT slot (0:0x80) -> no-op -> fall-through
  loop. Add `if (vec == 0x20) { e->exit_code = 0; e->state = TERMINATED; return -1; }`
  in the `case 0xCD` handler (alongside 0x10/0x16/0x21).
- **Hard step ceiling inside `run()` even for `max_steps==0`.**
  ```c
  uint64_t hard_cap = (max_steps != 0) ? max_steps : 20000000ULL;
  while (e->state == RUNNING) {
      if (e->steps >= hard_cap) { e->state = ERROR; break; }
      ...
  }
  ```
  This also makes `exec`/spawn safe - never call `run(child, 0)` trusting the child to exit.

## 2. `load_com` offset arithmetic (test-harness trap, NOT an engine bug)

`wubu_dos_emu_load_com` copies source buffer byte `K` to **emulator mem index `0x100 + K`**
(DOS COM convention: PSP at seg:0, program at seg:0x100). The program runs with `ds=0x1000`,
so a memory read at `ds:0xMMMM` hits **mem index `0xMMMM`**.

Rule for hand-assembled `.COM` test programs:
- **Program pointers** (the `dx` you load into a register) are **mem indices** `M` -> write the
  pointer bytes as `M` directly.
- **Data you place in the source buffer** at source index `K` lands at **mem index `0x100+K`**.
  So to put a string where the program reads `ds:0x170`, write it at **source index `0x70`**
  (`= 0x170 - 0x100`), because `load_com` shifts everything by +0x100.
- **Read-back assertions**: `peek16(e, 0x1000, M)` reads mem index `M`. So if the program stored
  `ax` at `ds:0x202`, the assertion is `peek16(e, 0x1000, 0x202)` (NOT `0x102`).

Common failures from getting this wrong: file path read as empty (creat fails -> file never
created), far-call cell at the wrong address (call jumps into the instruction stream), data
overlapping the code. Fix = place data at `source = mem - 0x100` and load the full 1024-byte
image (`wubu_dos_emu_load_com(e, c, 1024)`) so high-offset bytes are present.

## 3. GRP encodings: EA (displacement) MUST be consumed BEFORE the immediate

8086 encoding order for `C6/C7`, `C0/C1`, `F6/F7`, `80-83` (memory operand) is:
`op  modrm  [disp16]  imm`. The displacement comes **before** the immediate.

The original handlers fetched the immediate first, then called `ea()` - so `ea()` consumed the
immediate's bytes as the displacement (and vice-versa). Symptom: `mov word [0x20A], 1` decoded
with `o=0x0001, v=0x020A` (swapped) -> wrote to the wrong address.

Correct pattern for `C7 /r imm16` (and analogs):
```c
int m = fetch8(e);
uint16_t s, o; uint16_t v;
if ((m >> 6) == 3) { v = fetch16(e); rm_write(e, m, 1, v); }   // reg form: no disp
else { ea(e, m, &s, &o); v = fetch16(e); wr16(e, s, o, v); }   // mem form: ea FIRST, then imm, write via wr16
```
Key subtlety: do **NOT** call `ea()` manually and then pass `m` to `rm_write()` - `rm_write()`
calls `ea()` *again* internally, re-consuming the next 2 bytes as a (phantom) displacement and
writing to the wrong address. After computing `s,o` with one `ea()`, write with `wr16(e,s,o,v)`
/ `wr8(e,s,o,v)` directly. Same caution for `C0/C1` shifts and `F6/F7`: call `ea()` once, then
`rd8/rd16(e,s,o)` / `wr8/wr16(e,s,o,...)`.

## 4. Hand-assembly gotchas in the test harness

- **Uninitialized stack buffers**: `uint8_t c[1024];` is garbage; a "t.txt" string is NOT
  NUL-terminated, so the DOS path reader grabs trailing garbage -> `creat` fails. Always
  `memset(c, 0, sizeof c)` and place data at the right source index (see Sec 2).
- **Spurious `0x00` byte in the instruction stream**: `c[p++]=0xB4; c[p++]=0x42; c[p++]=0x00;`
  silently dropped the intended `xor cx,cx` (33 C9), leaving `cx=5` so an `int 21h/42` (lseek)
  sought offset `0x50000` -> read hit EOF. Assemble the exact bytes: `B4 42 33 C9 33 D2`
  (ah=42h; xor cx,cx; xor dx,dx).
- **far CALL `disp16` must equal the cell's mem index**: `call far [ds:0x200]` is encoded
  `FF 1E 00 02` (disp16 = 0x0200), and the far-pointer cell must sit at **mem index 0x200**
  (source 0x100), holding `ip, seg` little-endian. Encoding disp16 as 0x0100 reads the
  instruction bytes themselves as the pointer.

## 5. Verification recipe (bounded, no hangs)

```sh
gcc -O2 -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Isrc/runtime \
    src/runtime/wubu_dos_emu.c src/runtime/wubu_dos_emu_test.c -o /tmp/emu_test
timeout 60 /tmp/emu_test > /tmp/emu_out.txt 2>&1; echo "rc=$?"
rm -f t.txt d.dir child.com
tr -c '[:print:]\n' ' ' < /tmp/emu_out.txt | grep -aE 'FAIL|Results'
```
If a sub-test loops, bound it: build a tiny standalone harness that loads one COM and
`wubu_dos_emu_run(e, 0)` (the hard cap in Sec 1 now prevents the infinite loop), then
inspect with `wubu_dos_emu_peek16(e, 0x1000, M)` to inspect stored values.
