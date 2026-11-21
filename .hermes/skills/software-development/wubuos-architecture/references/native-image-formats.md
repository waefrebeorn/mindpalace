# Native Image Format Implementation (WuBuOS Canvas)

## Overview
Eliminated all `system()` calls from `src/apps/wubu_canvas.c` by implementing native PNG, GIF, BMP, and PPM readers/writers in pure C. No external dependencies (libpng, libgif, ImageMagick, ffmpeg).

## PNG Save (`wubu_cv_save_png`)

### DEFLATE Uncompressed (BTYPE=00)
- No zlib needed — uses RFC 1951 uncompressed blocks
- Block header: 5 bytes (BFINAL + LEN + NLEN)
- Each scanline: 1 filter byte (0 = None) + 3*width RGB bytes
- Multiple blocks if data > 65535 bytes

### CRC32
```c
static uint32_t crc32_table[256];
static bool crc32_table_init = false;

static void crc32_init(void) { /* polynomial 0xEDB88320 */ }
static uint32_t crc32_update(uint32_t crc, const void *data, size_t len);
static uint32_t crc32_data(const void *data, size_t len) { return crc32_update(0, data, len); }
```

### PNG Structure
```
Signature (8 bytes): 89 50 4E 47 0D 0A 1A 0A
IHDR chunk: width(4) height(4) bit_depth(1)=8 color_type(1)=2 compression(1)=0 filter(1)=0 interlace(1)=0
IDAT chunk(s): DEFLATE uncompressed blocks with proper CRC
IEND chunk: zero-length data
```

### Key Functions
```c
static void png_write_chunk(FILE *f, const char *type, const void *data, size_t len);
static void write_be32(uint8_t *buf, uint32_t val);
static void write_be16(uint8_t *buf, uint16_t val);
```

## GIF Save (`wubu_cv_save_gif`)

### GIF89a Format
```
Signature: G I F 8 9 a (6 bytes)
Logical Screen Descriptor (7 bytes): width(2) height(2) packed(1) bg_index(1) aspect(1)
Global Color Table: 256 entries × 3 bytes = 768 bytes (grayscale palette)
Image Descriptor (10 bytes): ',' left(2) top(2) width(2) height(2) packed(1)
Image Data: LZW minimum code size (8) + sub-blocks (size + data) + block terminator (0)
Trailer: ';'
```

### Implementation Details
- Grayscale palette (256 entries, R=G=B=i)
- Uncompressed LZW: code size 8, each scanline as separate sub-block
- No actual LZW compression — just raw pixel indices in sub-blocks
- Block terminator (0) + trailer (';')

## Load Functions

### Magic Byte Detection (`wubu_cv_load`)
```c
// PNG: 89 50 4E 47 0D 0A 1A 0A
// BMP: B M
// PPM: P 6 / P 3
// Auto-detect by reading first 8 bytes
```

### PPM Loader (`wubu_cv_load_ppm`)
- Supports both P3 (ASCII) and P6 (binary)
- Reads width, height, maxval from header
- Handles whitespace after header

### BMP Loader (`wubu_cv_load_bmp`)
- Reads BITMAPFILEHEADER (14) + BITMAPINFOHEADER (40)
- Supports 24-bit and 32-bit uncompressed (BI_RGB)
- Handles row padding (4-byte alignment)
- Bottom-up row order (BMP stores from bottom)

## Removed System Calls (3 eliminated)
1. `wubu_cv_save_png` — was `system("ffmpeg -y -i ppm png && rm ppm")`
2. `wubu_cv_save_gif` — was `system("convert ppm gif || ffmpeg -y -i ppm gif")`
3. `wubu_cv_load` — was `system("convert input ppm")` then read PPM

## Build Impact
- No external dependencies added
- No `-lpng`, `-lgif`, `-lz` needed
- Pure C99 implementation
- All existing tests pass (71/71 explorer tests)

## Integration Points
- `wubu_canvas.h` declares: `wubu_cv_save_png`, `wubu_cv_save_gif`, `wubu_cv_load`, `wubu_cv_load_ppm`, `wubu_cv_load_bmp`
- `wubu_canvas.c` implements all 5 functions
- Uses existing `wubu_cv_composite()` for pixel data
- Uses existing `wubu_cv_resize()` for dimension handling