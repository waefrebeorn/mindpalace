# The egojar — one-file POSIX seam for the wubunos transition

Goal: build the same tree with **wubunos** instead of gcc. What blocks that is
not logic, it is hundreds of `#include <unistd.h>` lines plus hundreds of
scattered `-D_POSIX_C_SOURCE` / `-D_GNU_SOURCE` flags across the makefiles.

`src/egojar.h` makes that seam exactly one file wide. Reimplement the header
for WuBuOS (or let wubunos provide the names) and nothing else moves.

## What belongs in the jar

- Feature-test macros, FIRST, before any system header:
  `_POSIX_C_SOURCE 200809L`, `_DEFAULT_SOURCE 1`, and `_GNU_SOURCE` only
  behind an opt-in (`WUBU_EGOJAR_GNU`).
- Every POSIX / Linux / libc-extension header the tree uses: `unistd.h`,
  `fcntl.h`, `sys/{stat,types,mmap,wait,time,ioctl,resource,socket,un,syscall,prctl,select}.h`,
  `signal.h`, `dirent.h`, `dlfcn.h`, `pthread.h`, `poll.h`, `errno.h`,
  `termios.h`, `netinet/in.h`, `arpa/inet.h`, `getopt.h`, `strings.h`,
  `zlib.h`, `math.h`.

## What does NOT

- Standard C: `<stdio.h>`, `<stdlib.h>`, `<string.h>`, `<stdint.h>`,
  `<stddef.h>` — any compiler has them; they do not belong in a suit.
- Declarations, code, `static inline`, typedefs. The jar carries flags, not
  an API. A wrapper-per-module design doubles the seam and defeats the point.

## Converting a file

1. Delete the file's POSIX/Linux includes.
2. `#include "../egojar.h"` as the FIRST include (relative path to the tree
   root, or add `-I$(SRC)` and use `"egojar.h"`).
3. Leave standard C includes where they are.
4. Build and run the file's own test — a green aggregate gate says nothing
   about a single TU's include order.

## Pitfalls

- **Feature-test macros only take effect before the FIRST system header.**
  If the jar is included after any `<...>` include, the macros are inert and
  the TU compiles as if the jar were absent — the failure looks like a
  missing declaration, not a missing jar.
- **Do not "fix" a missing declaration by flipping `_GNU_SOURCE` globally.**
  That re-widens the seam the jar exists to close. Add the header to the jar.
- **Do not put the jar's includes in a `.c`.** The jar is a header; a `.c`
  would compile once per TU and break the ordering rule.
- **The makefile `-D` flags become redundant once a file includes the jar**,
  but leave them until the whole tree is converted — removing them early
  breaks every TU that has not been converted yet.

## Scale at introduction (measure, then re-measure after the sweep)

```
grep -rhoE '#include\s*<(unistd|sys/[a-z_/]+|pthread|dlfcn|fcntl|signal|errno|strings|poll)\b' \
  --include=*.c --include=*.h src/ | sed 's/#include\s*//' | sort | uniq -c | sort -rn
grep -rho 'D_POSIX_C_SOURCE\|D_GNU_SOURCE\|D_DEFAULT_SOURCE' mk/ Makefile | wc -l
```

Exclude standard C from the POSIX count — `math.h` and `time.h` are C11, not
POSIX gratification, and pulling them into the jar would be wrong.
