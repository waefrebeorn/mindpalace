# AN12 amoeba-weights session (2026-08-04) — C11 memory-bug transcripts

Four DA-caught bugs from the gravity/boot/orbits wave, with exact
repro paths and fixes. The one-line lessons are in SKILL.md (P29–P32);
this file has the full before→after and the error signatures.

## 1. P29 — realloc invalidates the captured parent pointer

Module: `wubu_gravity.c` (`wubu_gravity_grow`).

The buggy shape:
```c
wubu_gravity_cell_t *parent = &g->cells[cell_id];
... find free slot ...
if (slot == n) {
    g->cells = realloc_or_new(...);   /* FREES the old array */
    ...
}
wubu_gravity_cell_t *d1 = parent;    /* DANGLING */
d1->r = clamp_r(g, d1->r + dr*0.5);  /* heap-use-after-free */
```

ASan signature:
```
ERROR: AddressSanitizer: heap-use-after-free on address ...
READ of size 8
  #0 wubu_gravity_grow src/wubu_gravity.c:153
  #1 main tools/test_gravity.c:85
SUMMARY: AddressSanitizer: heap-use-after-free
```

Fix:
```c
/* snapshot BEFORE the realloc */
const double pr = parent->r;
const double ptheta = parent->theta;
... realloc ...
/* RE-DERIVE after (the old pointer dangles) */
wubu_gravity_cell_t *d1 = &g->cells[cell_id];
```

Rule: after any realloc/free of a container, all old pointers are dead —
re-derive by index. The plain `-O3` build RUNS (the freed page is often
still mapped); only ASan sees it.

## 2. P30 — freeing a struct-FIELD address as a heap wrapper

Module: `wubu_orbits.c`. Slot embeds the address by value:
```c
typedef struct { wubu_orbit_addr_t addr; void *item; } orbit_slot_t;
```
The heap-wrapper free does `free(a)` — calling it on the FIELD address:
```c
wubu_orbits_addr_free(&c.oldest->addr);  /* free(&slot->addr) — frees INSIDE the slot */
free(c.oldest);                           /* double-free of the slot */
```

ASan signature:
```
ERROR: AddressSanitizer: attempting double-free on 0x...
  #0 free
  #1 wubu_orbits_write src/wubu_orbits.c:145
  #1 wubu_orbits_addr_free src/wubu_orbits.c:85
```

Fix: field-owned sub-structs get a field-safe free (arrays only):
```c
static void slot_addr_free(wubu_orbit_addr_t *a) {
    free(a->r); free(a->theta); a->r = NULL; a->theta = NULL;
}
```
And the transfer into the slot must move ARRAYS, not the wrapper struct:
```c
s->addr.r = a->r; s->addr.theta = a->theta; s->addr.n_levels = a->n_levels;
free(a);   /* wrapper only — the arrays now belong to the slot */
```
A struct copy `s->addr = *a` creates a second owner of the arrays.

## 3. P31 — `const char *` member written via strncpy

Module: `tools/wubu_boot.c`. The writer struct (safetensors_writer.h):
```c
typedef struct { const char *name; const float *data; ... } st_writer_tensor_t;
```
The caller assumed a char array:
```c
strncpy(out[n_out].name, e->name, sizeof(out[n_out].name) - 1);  /* name is NULL */
```

Crash: immediate SEGV at `__strncpy_evex` (gdb frame in strncpy, NOT your
code — the classic "wrong line" symptom).

Fix: assign the pointer to a stable owner (the catalog stays open through
the write):
```c
out[n_out].name = e->name;
```

Rule: check member type (array vs pointer) before writing into it.

## 4. P32 — bulk-rewrite script emptied 20+ files

The strip script (removing cargo-cult `_GNU_SOURCE`) had:
```python
out, i, n = [], len(lines), 0   # n=0! loop never runs
while i < n: ...
open(p, "w").write("".join(out))  # writes EMPTY
```

Every file it touched became 0 bytes; the build failed with a cascade of
`undefined reference` (functions vanished). Recovery (restore all emptied
tracked files from git):
```bash
git status --short | awk '$1=="M"{print $2}' | while read f; do
  if [ ! -s "$f" ]; then git checkout -- "$f"; fi
done
```

Prevention (the fixed script):
```python
if not new.strip() and src.strip():
    print(f"REFUSE (would empty): {p}"); continue   # never empty a file
```

Also: stripping `#ifndef _GNU_SOURCE / #define _GNU_SOURCE / #endif`
guard pairs — the pair may NOT be adjacent (blank line / comment between),
so a naive pair-remover leaves a dangling `#endif` that breaks the next
compile (`#endif without #if`). After any strip, grep for a leading
`#endif` in the first ~12 lines of each touched file.

## The GNU-free doctrine (context for P18)

The user's directive: "we keep having to add that string gnu source...
are we eventually gonna need to make our own compiler using our own
operating system style... they're tricking us into bringing a string that
makes us have a license that we don't wanna have." The answer: YES —
wubuos already has a working HolyC compiler (src/compiler/, ring-0 JIT) —
when we self-host we define the feature surface and there is no glibc.

Immediate fix: `include/wubu_std.h` (wubuwizard) / `src/runtime/wubu_std.h`
(wubuos) — M_PI/M_PI_2/M_E constants + wubu_strdup, no feature macro.

Legitimate `_GNU_SOURCE` (kept localized, with a comment):
- CPU_ZERO/CPU_SET/pthread_setaffinity_np (wubu_affinity, wubu_thread_spec,
  wubu_tandem)
- FTW_DEPTH/FTW_DP (wubu_fs_util, wubu_image_tar — nftw post-order)
- CLONE_NEW* (wubu_ct_isolate, ct_iso_seccomp)
- DT_DIR/d_type (styxfs_callbacks — hidden by the build's
  -D_POSIX_C_SOURCE=200809L)
- st_atime (styxfs_posix, wubu_archd_daemon)

Cargo-cult `_GNU_SOURCE` (stripped, zero gated symbols): gguf_reader.c,
wubu_tokenizer.c, debug_beta_layout.c (wubuwizard); ~37 files (wubuos).
