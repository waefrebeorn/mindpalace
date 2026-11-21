# Debugging a Hanging or Crashing WuBuOS Test Binary

When a `make test_<t>` target **hangs** (no output, or stuck) or **SIGSEGVs**, staring
at the source rarely finds it fast. The reliable path is a **minimal standalone
harness + gdb**, because the test binary links a huge object set and its buffered
stdout hides where it died.

This was proven on `test_apps2` (2026-07-09): the PNG/GIF loader SIGSEGVs inside
`wubu_cv_load_gif` at line 741, and the whole binary hung — `gdb` pinned it to a
`uint16_t` LZW table whose `-1` sentinel wrapped to `0xFFFF`.

## Step 1 — Reproduce in a minimal harness (no test framework)

Write `/tmp/<name>_harness.c` that calls ONLY the suspect function(s), linking the
module `.c` + its direct deps + `wubu_spawn.c` (codec/app code often needs
`wubu_run_program`). Mirror the test target's `-I` flags and `-lz -lm`.

```c
#include "wubu_canvas.h"
#include <stdio.h>
int main(void) {
    WubuCanvas *cv = wubu_cv_create(1, 1);
    int r = wubu_cv_load_gif(cv, "/tmp/wubu-cv-rt.gif");
    printf("load_gif returned %d\n", r);
    wubu_cv_destroy(cv);
    return 0;
}
```

Build it directly (don't go through Make, which hides the link detail):

```bash
cd /home/wubu/.hermes/profiles/mind-palace/home/myseed
gcc -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM \
  -Isrc/apps -Isrc/kernel -Isrc/runtime \
  src/apps/wubu_canvas.c src/apps/wubu_canvas_io.c \
  src/apps/wubu_codec.c src/runtime/wubu_spawn.c \
  /tmp/gif_harness.c -o /tmp/gif_harness -lz -lm
```

If the link fails with `undefined reference to wubu_run_program`, you forgot
`src/runtime/wubu_spawn.c` (the shared fork/exec helper).

## Step 2 — Catch the crash with gdb (batch mode)

```bash
timeout 15 gdb -q -batch -ex run -ex bt /tmp/gif_harness 2>&1 | tail -12
```

`SIGSEGV` prints the exact line + backtrace. `timeout` prevents an infinite loop
from hanging gdb itself.

## Step 3 — Find a HANG (no crash) with line-buffered output

Test binaries use block-buffered stdout, so a hang shows NOTHING. Force line
buffering to see which test is executing when it stalls:

```bash
stdbuf -oL -eL timeout 60 ./src/apps/wubu_apps2_test 2>&1 | tail -45
```

The last `✅` line before the freeze is the test that hangs; the next test's first
assertion is where the bug lives.

## Step 4 — Independent ground truth to localize encoder vs decoder

When a round-trip fails, decide whether the **encoder** or **decoder** is wrong using
an independent tool as oracle:

- **PNG/GIF**: generate or decode with **PIL** (`python3 -c "from PIL import Image;
  im=Image.open(p); ..."`). If PIL decodes a file the WuBuOS loader rejects → the
  encoder is wrong (bad CRC / wrong compression wrapper). If PIL also rejects it →
  the file is structurally broken → check the encoder's chunk/length/CRC.
- **CRC verification**: `python3 -c "import binascii; print(hex(binascii.crc32(b)&0xffffffff))"`
  on each chunk's `type+data` to confirm the encoder's CRC32 matches.

This session: the PNG loader rejected its own file, and PIL ALSO rejected it →
proved the encoder was broken (raw DEFLATE instead of a zlib stream), not the loader.

## Step 5 — Binary-step divergence for decode-correctness bugs

If the decoder runs but produces wrong pixels, dump the decoded buffer vs expected
and find the FIRST divergence — the pattern reveals the bug class:

- **Single wrong byte, rest correct** → off-by-one in mapping.
- **First row correct, then drift** → dictionary/code-width desync (GIF LZW) or
  row-pitch error (PNG unfilter omitted the per-row filter byte).
- **Rows in scrambled order (0,8,16,4,12,2,6,...) but each row internally correct**
  → **Adam7 interlace** not de-scrambled (PIL interlaces palette GIFs by default).
- **Uniform R/B swap** → pixel byte order wrong (`0xAARRGGBB` on canvas: R is bits
  16-23, B is 0-7; PNG/PPM are RGB on disk, BMP is BGR).

## Stale test binary masks a fix (separate from stale `.o`)

If you fixed the code but `make test_<t>` still reports the OLD failure identically,
the **test binary itself may be stale** — e.g. a previous run hung/segfaulted and
the link step never re-ran, or `make` thinks the binary is up to date. This is
DIFFERENT from stale `.o` masking *missing links*; here a *valid* binary is cached
with the old behavior.

Fix: delete the binary, then rebuild:
```bash
rm -f src/apps/wubu_apps2_test
make test_apps2
```
Or go nuclear with `make clean`. Always suspect this when "I fixed it but the test
didn't change."

## Reusable checklist for hand-rolled image codecs (PNG/GIF/BMP)

When touching `wubu_canvas_io.c` or similar, verify each:
- [ ] **PNG IDAT is a ZLIB stream** (RFC 1950: 2-byte header + DEFLATE + 4-byte
      Adler-32), NOT raw DEFLATE. Encoders must use `compress2()`; decoders must
      `inflateInit()` (not raw `inflateInit2(..., -MAX_WBITS)`).
- [ ] **CRC32 chains correctly**: `crc = ~crc_in` at the start of `crc32_update`
      (the incoming value is the previous already-inverted return), then `~crc`
      on return. Returning `~0` unconditionally restarts the CRC instead of
      continuing it → bad IHDR/IDAT CRC.
- [ ] **DEFLATE LEN/NLEN are little-endian** (RFC 1951 §3.2.4), NLEN = one's
      complement of LEN. Big-endian here → inflate fails.
- [ ] **PNG unfilter pitch = 1 + w*channels** (filter byte + pixels). Using
      `w*channels` as the row stride reads the NEXT row's filter byte as pixel data.
- [ ] **GIF LZW parent table is `int16_t`**, not `uint16_t` — the `-1` "no parent"
      sentinel must stay negative; `uint16_t` wraps `0xFFFF` and the decode-chain
      walk never terminates (SIGSEGV / infinite loop).
- [ ] **GIF LZW literal entries** (`0..clear_code-1`) must have `table_suffix[i]=i`
      initialized on CLEAR; uninitialized suffix → garbage decoded symbols.
- [ ] **GIF Adam7 interlace**: de-scramble the LZW row stream (passes start
      {0,4,2,1}, step {8,8,4,2}) into top-to-bottom rows before mapping to canvas.
- [ ] **Pixel byte order**: canvas is `0xAARRGGBB`; PNG/PPM store RGB, BMP stores
      BGR on disk. Swapping R/B is the most common silent error.
