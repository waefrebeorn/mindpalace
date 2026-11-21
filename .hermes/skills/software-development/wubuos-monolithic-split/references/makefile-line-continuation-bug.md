# Makefile Line-Continuation Double-Backslash Bug (WuBuOS build-breaker)

## Symptom
`make hosted` (or any target whose recipe lists `.c` files inline with backslash
continuations) fails with:
```
cc1: fatal error:  src/gui/wubu_wallpaper.c: No such file or directory
```
Note the **LEADING SPACE** before the filename — cc1 received ` src/gui/...` as
one token. The file obviously exists (`gcc -fsyntax-only src/gui/wubu_wallpaper.c`
succeeds). `make runtime` passes; only the hosted/main binary recipe fails.

## Root Cause
A recipe line that should end with a single line-continuation backslash `+` newline
instead has **TWO** backslashes:
```
... $(GUI)/wubu_pkgmgr_txn.c \\ $(GUI)/wubu_wallpaper.c \\
```
The first `\` continues the line; the SECOND `\` is literal and **escapes the
newline**, so the logical line ends at `wallpaper.c \`, and the next physical line
becomes a broken separate token. Make's `$(CC)` still emits a plausible command in
`make -n` dry-run (it re-joins continuation lines), which **masks** the bug — the
real failure only surfaces when cc1 parses the joined argument with a leading space.

## How it gets introduced
Editing the inline `.c` list with a Python heredoc or `write_file` that escapes
backslashes twice. e.g. inside `r'''...'''` heredocs, `\\\\` becomes two real
backslashes on disk. Or a `patch`/`execute_code` round-trip that wrote `\\` intending
one. The session that hit this burned ~30 tool calls throttling between `make -n`
(doesn't show it) and `od -c` (does) before pinning it.

## Diagnosis (exact, trust this over dry-run)
```bash
# Dump the raw trailing bytes of the recipe line
sed -n '169p' Makefile | tail -c 30 | od -c
```
- **Broken** trailing bytes: `... wallpaper.c` ` ` `\` `\` `\n`  (TWO backslashes)
- **Correct** trailing bytes: `... wallpaper.c` ` ` `\` `\n`  (ONE backslash)

Also a quick scan for any line ending in a doubled backslash (all are suspect):
```bash
grep -nE '\\\\\\\\$' Makefile      # matches lines ending in '\\'
```

## Fix
Byte-exact replace via Python (avoid shell escaping pitfalls — do NOT use
`sed 's/\\/\\/'` which re-escapes):
```python
data = open('Makefile','rb').read()
bad  = b'wubu_wallpaper.c \\\\\n'   # wallpaper.c + \ + \ + newline  (TWO backslashes)
good = b'wubu_wallpaper.c \\\n'     # wallpaper.c + \ + newline      (ONE backslash)
assert data.count(bad) == 1, "expected exactly one doubled-backslash occurrence"
open('Makefile','wb').write(data.replace(bad, good))
```
Then verify: `sed -n '169p' Makefile | tail -c 16 | od -c` shows a single `\` before
`\n`.

## Prevention
- When adding files to the hosted link recipe (the ~line 166 inline `.c` list),
  append BEFORE the existing trailing backslash and keep exactly ONE continuation
  backslash per line.
- After ANY Makefile edit to a continuation list, run `make clean && make hosted`
  (or `make <target>`) — `make -n` dry-run does NOT catch this class of bug.
- Prefer editing the inline `.c` list via the same byte-exact Python pattern above
  rather than heredocs that double-escape backslashes.
