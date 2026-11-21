# Self-contained test fixtures (generate in-code, don't depend on a missing file)

A test that opens a fixture path (e.g. `mount_zip("/tmp/test.zip")`) but never
creates it reddens the gate with a misleading "mount failed" — the gap is only
visible when you read the test body. Fix: build the fixture inside the test.

## Verified STORE-zip builder (minimal, spec-valid, no libzip headers needed)
Hand-roll an uncompressed ZIP: local-file-headers + central-directory + EOCD.
The central-directory + EOCD block mirrors the LFH field order shown below.
```c
static int make_real_zip(const char *path, int nfiles) {
    FILE *f = fopen(path, "wb"); if (!f) return -1;
    uint32_t sig_lfh = 0x04034b50u, sig_cdh = 0x02014b50u, sig_eocd = 0x06054b50u;
    uint32_t cdir_off = 0, cdir_size = 0;
    for (int i = 0; i < nfiles; i++) {
        char name[32]; snprintf(name, sizeof name, "data%d.bin", i);
        uint16_t nl = (uint16_t)strlen(name);
        size_t payload = 16 + (size_t)i;
        fwrite(&sig_lfh, 1, 4, f);
        uint16_t ver=20, flags=0, method=0, mt=0, md=0;
        uint32_t crc=0, csize=(uint32_t)payload, usize=(uint32_t)payload;
        uint16_t el=0, cl=0;
        fwrite(&ver,1,2,f); fwrite(&flags,1,2,f); fwrite(&method,1,2,f);
        fwrite(&mt,1,2,f); fwrite(&md,1,2,f);
        fwrite(&crc,1,4,f); fwrite(&csize,1,4,f); fwrite(&usize,1,4,f);
        fwrite(&nl,1,2,f); fwrite(&el,1,2,f);
        fwrite(name,1,nl,f);
        for (size_t b=0;b<payload;b++) fputc((int)(b&0xff),f);
        cdir_off += (uint32_t)(30 + nl + payload);
    }
    /* central directory: per entry repeat the CDH field order (sig_cdh, ver_made_by,
       ver_needed, flags, method, mt, md, crc, csize, usize, nl, el, cl, disk#, ia,
       ea, lho, name) then EOCD (sig_eocd, dsk#x2, entries_total_x2, cd_size, cd_offset,
       comment_len). Mirror the LFH layout; keep cdir_off/cdir_size tallies. */
    fclose(f); return 0;
}
```
Call `make_real_zip("/tmp/test.zip", 5)` in the test's setup before `mount_zip`.

## GOTCHA — magic-field width
Store 32-bit signatures in `uint32_t`, NEVER `uint16_t`. A
`uint16_t sig = 0x04034b50u` truncates to `0x4b50`, and `fwrite(&sig,1,4,f)`
then reads 2 bytes past the 2-byte var → garbage in the header → the loader
rejects the file. This exact bug reddened `test_explorer` until the field
was widened to `uint32_t`.

## Why in-code vs external
Self-contained fixtures need no `zip` binary, no libzip dev headers, and no
pre-seeded file on disk — the test is reproducible on any checkout.
