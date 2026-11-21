# Stranded Statics Above the Extracted Block

## Symptom

After a brace-counting extraction, the new module fails to compile:

```
src/gui/wubu_session_autostart.c:15:9: error: 'g_autostart_path' undeclared
  (first use in this function); did you mean 'session_autostart_path'?
```

but `g_autostart_path` clearly exists — in the *host* file, on a line ABOVE the
first function you extracted.

## Root cause

The brace-counting extractor (Step 4) builds a remove-mask from **function
definitions** — it finds each function by signature + `{` and masks everything
from the opening brace to the matching close. Any `static` global, array, or
buffer declared on lines *above* the first extracted function is NOT inside any
masked function body, so it stays in the host `.c` while the function that
references it moves to the new module. Same for a state struct/array that lives
at file top before the extracted subsystem.

## Reproduction (B7, wubu_session.c)

```
 1  /* -- Session State -------------------------------------------- */
 3  static SessionState g_session = {0};
 4  static AutostartEntry g_autostart[MAX_AUTOSTART_ENTRIES];   // <- state array, ABOVE block
 5  static int g_autostart_count = 0;                          // <- counter, ABOVE block
 ...
11  static char g_autostart_path[512] = {0};                    // <- buffer, ABOVE block
12  static char g_session_path[512] = {0};
13
14  static const char *session_autostart_path(void) {           // <- first EXTRACTED fn (line 33 originally)
15      if (g_autostart_path[0] == '\0') { ... }                // uses buffer that stayed in host
```

Extract start = `session_autostart_path` (line 33). Buffers at 11-12 and state at
4-5 are above it → stranded in host. Module fails: `g_autostart_path`,
`g_session_path`, `g_autostart`, `g_autostart_count` all undeclared.

## Fix (in the extraction script, BEFORE writing)

1. Find the first extracted function's line number `F0`.
2. Scan lines `[0 .. F0)` for declarations matching
   `^\s*static\s+(?:const\s+)?\w[\w\s\*]*\s+\w+\s*[\[(]` — i.e. `static` globals,
   arrays, buffers (anything that looks like a file-scope `static` definition,
   not a function).
3. For each such declaration that the extracted functions reference, add it to the
   block being moved (prepend to the new module, after the includes).
4. Remove those same declarations from the host.
5. If a stranded symbol is referenced by BOTH the extracted block and remaining
   host code (e.g. `g_autostart_count` used by `wubu_autostart_count()` left in
   host), move it to the internal header as `extern` and keep ONE definition in the
   module (preferred) — or keep it in the host and `extern`-declare in the module's
   header. Either way: exactly one definition.

## General rule

The extractor's remove-mask is **function-bounded**. Non-function declarations in
the same region must be handled separately — manually moved into the module (or
promoted to `extern` in the internal header), never left to be masked. Always
re-scan the 10-30 lines above your first `extract(sig)` hit before committing the
mask.
