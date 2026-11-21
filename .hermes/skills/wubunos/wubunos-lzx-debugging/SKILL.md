---
name: wubunos-lzx-debugging
title: WuBuOS LZX Decompressor Debugging
description: Fix in-kernel LZX decoder bugs — ReactOS bit-reader quirks, per-CFDA calling convention, UNCMP realign, underfilled Huffman tables, 7z oracle verification.
---

# WuBuOS LZX Decompressor Debugging

## When to load
- LZX decode fails with `LZX_ILLEGALDATA` or `LZX_DATAFORMAT`
- Post-UNCMP header reads wrong block type (`type=2` instead of `type=3`)
- `make_decode_table` fails on valid (underfilled) Huffman code lengths
- Need to verify LZX output against 7z oracle

## 1. ReactOS Bit-Reader Quirks
ReactOS `fdi.c` uses a 16-bit LE word read: `bitbuf |= w << (32 - 16 - bitsleft)`. On x86, when `bitsleft > 16` the shift operand is negative and wraps mod 32. This is **undefined behavior** in C but works consistently on this platform. Within a block, Huffman decode uses the same reader so errors self-cancel. **The danger is at block boundaries**: zeroing the bitbuf mid-stream makes the next header read from misaligned bits.

## 2. Per-CFDATA Calling Convention (ReactOS Model)
`LZXfdi_decomp` is called **once per CFDA block** with the current block's data. The bit reader resets every call:
```c
br.ip = in; br.bitbuf = 0; br.bitsleft = 0;  /* INIT_BITSTREAM — EVERY call */
```
Persisted in `lzx_state`: `block_type`, `block_length`, `block_remaining`, `R0/R1/R2`, Huffman tables, `window_posn`, `intel_curpos`, `header_read`.

**LZX bitstreams are byte-aligned at CFDA boundaries** — no bits carry across blocks. Pass `cbData + 2` bytes (2 zero-pad) per call so `lzx_ensure` reads safely past `endinp`.

**Never persist `br_ip`/`br_bitbuf`/`br_bitsleft`** — the accumulated-buffer model that did this caused stale-pointer corruption at the post-UNCMP boundary.

## 3. UNCOMPRESSED Block: Realign + Raw-byte R0/R1/R2
After UNCMP (`block_remaining == 0`):
```c
if (s->block_type == LZX_BLOCKTYPE_UNCOMPRESSED) {
    if (s->block_length & 1) br.ip++;   /* skip pad byte if odd length */
    br.bitbuf = 0; br.bitsleft = 0;     /* zero bitbuf only — no ensure(16) */
}
```
R0/R1/R2 in UNCMP are **raw byte reads** (4 bytes each), not bit reads. libmspack uses the same pattern (no `inpos -= 2`).

## 3b. Block Header — No Leading `lzx_ensure(24)`
ReactOS reads headers with `READ_BITS(3); READ_BITS(16); READ_BITS(8)` — each ensures only its own nbits. **Do NOT** add a leading `lzx_ensure(&br, 24)`. When `bitsleft` is 16–23, the 24-bit pre-ensure over-reads a word, overflowing the 32-bit bitbuf and corrupting the header. For CAB1.CAB this caused UNCMP `block_length=66432` (wrong) vs `66529` (true, matching 7z oracle).

## 4. make_decode_table Underfilled-Huffman Fix
Underfilled codes (Kraft sum < 1.0) are valid in CAB LZX (e.g. ALIGNED `[6,4,6,6,3,3,3,1]`). After the secondary loop, if `pos != table_mask`, fill remaining primary entries with `0` and verify all non-zero-length symbols were placed. Return success if placed.

## 5. Block Type Table Build Order
For VERBATIM/ALIGNED: PRETREE → MAINTREE lens → MAINTREE table → LENGTH lens → LENGTH table → (ALIGNED only): ALIGNED lens → ALIGNED table. Do NOT rebuild the ALIGNED table in the VERBATIM fallthrough.

## 6. BFINAL Masking
3-bit header `[BFINAL:1][BTYPE:2]`. `BFINAL=1` gives raw 5/6/7; mask with `& 3`.

## 7. 7z Oracle Verification (CAB1.CAB)
```bash
/home/wubu/opt/bin/7zz x /tmp/CAB1.CAB -o/tmp/cab_oracle_full
```
Compare decoder output against `redist/instmsia.exe`. **Verified: 1,709,160/1,709,160 match (100%)** including the Intel E8 transform. Full folder: 19,476,546 bytes decoded across 595 CFDA blocks, zero failures.

## 8. Pitfalls

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| UNCMP `len=66432` vs true `66529` | Spurious `lzx_ensure(24)` before header | Remove pre-ensure; per-field `lzx_read_bits` |
| Post-UNCMP `type=2` not `type=3` | Stale `bitsleft` via UB shift at boundary | Zero bitbuf at entry; never persist br state |
| OOB / stale `br_ip` | Accumulated-buffer persisted `br_ip` into reused buffer | Per-CFDA reset each call |
| `make_decode_table` fails `[6,4,6,6,3,3,3,1]` | Underfilled Huffman | Apply underfilled fix |
| `debug_fail=9` ALIGNED | Missing ALIGNED table build | Build only in ALIGNED case |
| Wrong match offset after UNCMP | `br.ip -= 2` alignment shifts pointer | Use direct zeroing only |
