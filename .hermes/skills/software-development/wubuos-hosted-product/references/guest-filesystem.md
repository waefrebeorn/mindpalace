# The guest filesystem: one owner, one API, one durable image

Depth for work on WuBuOS file persistence, app file I/O, or the Styx namespace.
The always-on rules live in SKILL.md; this is the design behind them.

## The problem this solves

The guest namespace was a flat array in process memory:

```c
styxfs_file_t g_fs[STYXFS_MAX_FILES];   /* hosted_styxfs.c */
int           g_nfiles = 0;
```

No backing store, no flush, no snapshot -- every restart discarded everything.
An OS where nothing persists cannot be used for anything.

## There are TWO filesystems today, and they do not share a namespace

This is the single most expensive trap in the file layer. Two independent
implementations coexist, and applications reach them through different APIs:

| Store | Implementation | Reached by | Backing |
|---|---|---|---|
| Guest table | `src/hosted/hosted_styxfs.c` (`g_fs`, `guest_file_*`) | Notepad, Run dialog | in-memory + `fs.img` image |
| Host-path proxy | `src/runtime/styxfs_host.c` (`styxfs_opendir` -> `styxfs_path_to_host`) | Explorer / File Manager | real host directories |

Consequence, seen in the product: **Explorer could not see a file Notepad had
just saved**, because one wrote into the in-memory table and the other listed
host directories. Reading code looks consistent -- both call themselves "the
Styx namespace" -- so the divergence only appears as "the app does nothing"
or "my file disappeared". Any new app must be checked against WHICH of the
two it is talking to before its behaviour is judged correct.

The durable fix is to make one store real files under a single root; until then
treat the split as known and do not add a third writer.

### The guest sandbox root

With no 9P server mounted there is no mount table, so `styxfs_path_to_host()`
fell back to an IDENTITY mapping and guest paths resolved onto raw Linux paths.
File Manager started at `getenv("HOME")` and therefore opened showing the real
Linux home directory.

Now: `$WUBU_GUEST_ROOT` (default `~/.local/share/wubu/guest`). Guest `/` IS that
directory, `/apps/x` is `<root>/apps/x`. The root is CACHED AT FIRST USE -- a
running guest cannot change its own filesystem root underneath itself -- so the
override must be set before anything queries it.

Mapping rules:
- guest paths are absolute by definition (`/` is the namespace root);
- a non-`/` path is already a host path from a caller that knows better and is
  passed through untouched (the hosted port's own tests address `.`);
- the output buffer must ALWAYS be written. An early return that leaves it
  uninitialised hands the caller garbage, which reads as a crash or a bogus path.

## Ownership

| Layer | File | Responsibility |
|---|---|---|
| Namespace owner | `src/hosted/hosted_styxfs.c` | owns `g_fs`, `fs_add_*`, `fs_find`, every `styx_*_cb` |
| Durable image | `src/hosted/hosted_fs_persist.{c,h}` | serialize/restore only; knows nothing about applications |
| App-facing API | `src/apps/guest_file.h` | read / write / exists -- the ONLY way an app touches files |
| Flush trigger | `hosted_shutdown()` -> `hosted_fs_flush()` | performs disk I/O off the dispatch path |

Applications include `guest_file.h` (no host types leak through it) and never
`hosted_internal.h`. That boundary is what stops three editors from growing three
opinions about where a file lives.

## Contract of `guest_file`

- Names are FLAT strings matched literally (`notes/todo.txt`). No tree yet;
  interpreting `/` belongs in this one place.
- `write`: replaces IN PLACE when the name exists (qid/path stays stable, so
  nothing holding a handle sees the entry move); refuses a directory name.
- Every failure returns -1 and leaves the caller's buffer untouched.
- Capacity per file is `GUEST_FILE_MAX_LIMIT` (8192), the size of the inline
  `data[]` field. The RUNTIME bound is `guest_file_max()` (revolver
  `WUBU_FS_FILE_MAX`); `GUEST_FILE_MAX` stays a macro because callers size arrays
  with it.
- An add or write ABOVE capacity is REFUSED with -1. Never truncate to fit:
  returning success while storing a shortened file is silent data loss.

## Image format

Little-endian, fixed-width, explicit byte loops (never a struct dump -- dumping
a struct bakes in host padding and endianness into a file meant to survive a
rebuild):

```
0   char     magic[8]   "WUBFS01\0"
8   uint32   count       must be <= STYXFS_MAX_FILES
12  record[]
        uint64 path
        uint8  qtype      STX_QTDIR | STX_QTFILE
        uint32 data_len   must be <= sizeof(f->data)
        char   name[256]  NUL-terminated inside the field
        uint8  data[data_len]
```

Location: `$WUBU_FS_STORE` > `$XDG_DATA_HOME/wubu/fs.img` >
`$HOME/.local/share/wubu/fs.img`.

### Durability mechanics

- **Atomic replace**: write `<path>.tmp`, flush, `rename()`. A crash mid-write
  can never leave a half-written store; the old image stays valid.
- **Deferred save**: mutations set a dirty flag; `hosted_fs_flush()` does the
  I/O. Saving inline inside a Styx callback would put disk latency in the
  message-dispatch path.
- **Loud failure**: a failed flush prints the target path. Continuing silently
  tells the user their work is safe when it is not.

### Load must fail closed

Decode into a scratch array and commit only when EVERY record validates. Refuse:
bad magic, short header, short record, `count > STYXFS_MAX_FILES`,
`data_len > capacity`, `qtype` neither dir nor file, a name whose terminator is
not inside its field. Return **0 for a missing store** (first boot is normal)
and **-1 for a corrupt one**, leaving the live namespace untouched.

A half-loaded namespace is worse than none: the desktop shows files whose
contents do not exist.

## Boot order

Load BEFORE registering built-ins, and make built-in registration consult
`fs_find(name)` first. Otherwise a rebuilt default silently reverts a persisted
user edit on every restart. A name the user deleted comes back as a built-in on
the next boot -- acceptable, and worth knowing rather than debugging.

## Testing notes

- Test binaries must set `WUBU_FS_STORE` BEFORE the first `fs_persist_path()`
  call -- the path is cached in a static buffer, so changing it later has no
  effect.
- Probe the size boundary at `GUEST_FILE_MAX + 1`; a write of exactly
  `GUEST_FILE_MAX` bytes at offset 0 FITS.
- Stub the GUI, not the filesystem: `DosGuiWindow` is opaque, so a stub
  `wm_create` should return NULL (a test that never draws tolerates it), and the
  real `hosted_styxfs.c` / `hosted_fs_persist.c` should be linked so the bytes
  being asserted are the bytes the product writes.
- A round-trip test that ends by resetting the namespace, reloading the image and
  comparing content proves more than a same-process save/load.
