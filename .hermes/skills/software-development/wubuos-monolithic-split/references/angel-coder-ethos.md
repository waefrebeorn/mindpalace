# Angel Coder Ethos (User Preferences)

The following principles govern ALL code work in this project. They were expressed
as standing orders and override any "practical" shortcut. **Read this file before
starting any gap-closing or monolithic-split session.**

## Core Principles

### "Be the angel coder."
Fix the broken code. Don't paper over it. Every stub, void-cast, or `TODO` is a
debt that compounds — close it now. When uncertain what to work on,
**find something broken and fix it**.

### "Stop lying about time scale to skip work."
Never claim a task is "too big" or "will take too long." Agentic AI work completes
in minutes. Time estimates are an excuse — do the work. "For later", "stub for
extension", "scaffolding for future work" are not acceptable responses to a REAL_GAP.

### "Time is irrelevant and it takes minutes."
Maximum effort, always. Do it all. This is an operating system — the scale demands
completeness. Every gap closed makes the system more real.

### "Go heavy first and you conquer more."
Start with the hardest, most leveraged task. A heavy first move solves more
downstream problems than a cautious one. When facing multiple gaps, do the one
that unlocks the most others.

### "Small wastes time first but is great polished and makes excellent work."
Once the heavy foundation is laid, iterate into polish. Both modes are valid —
heavy first for leverage, small for quality.

### "There is no such thing as 'third party' if we can properly make the code."
No external dependencies. Every component is rewritten from scratch in C11.
"Third party" is a classification error — all code is ours to write. This applies
to system libraries, SDKs, translation layers, and runtime dependencies.

## Code Architecture Rules (Hard)

- **Opaque structs + minimal includes + C11 only** — no exceptions.
- **No god headers** — a header that includes more than one subsystem is wrong.
- **Keep every module self-contained** — .c includes its .h first, then system headers.
- **As you code, the issue is solved by properly splitting up and reusing
  functions.** The act of splitting monoliths is also the act of finding the
  right function boundaries. Split to find the architecture.
- **No monolithic files.** A file that handles two or more distinct concerns
  must be split. See the parent skill's procedure for how.

## Verification

- After EVERY change: `make runtime && make test` must be green.
- Every new function must have a test that asserts the FIXED behavior, not just
  non-crash.
- If a test file does not exist for the module you're fixing, create one.
