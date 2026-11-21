# `#define` Macros Referring to Function-local Variables (C11 inline patch trackers)

## The trap

When writing a JIT codegen backend in C11, the natural instinct is to use a
`#define` macro to record a branch/jump that needs patching later, e.g.:

```c
static int m68k_compile(const wubu_mir_prog_t *p, uint8_t **out, size_t *out_size)
{
    m68k_emitter_t e = {0};
    m68k_patch_t *patches = NULL;
    size_t np = 0, cp = 0;

    #define PATCH_AT(pos, cond, lbl) do { \
        if (np == cp) { cp = cp ? cp * 2 : 16; \
            patches = realloc(patches, cp * sizeof(*patches)); } \
        patches[np].pos = (pos); patches[np].cc = (cond); \
        patches[np].label = (lbl); patches[np].direct = (size_t)-1; np++; \
    } while (0)
    #define PATCH(cond, lbl) PATCH_AT(e.n, (cond), (lbl))
    ...
