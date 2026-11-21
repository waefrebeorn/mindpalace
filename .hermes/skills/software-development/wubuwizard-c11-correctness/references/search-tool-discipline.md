# Search-Tool Discipline: the anti-grep-loop protocol

**Trigger:** any code-search or file-inspection task in the wubuwizard/wubuos repos
**Origin:** user correction — *"can we make it so deepseek cant use grep? its always a grep loop"* (2026-08-06). The agent repeated the same `grep -n "GGML_TYPE_Q8_0" src/gguf_reader.c` ~30+ times, never converging.

## The rule

**Terminal `grep`/`rg`/`find` are forbidden for code search.** Use `search_files` instead. One call does what 30 greps do.

## Tool mapping (what replaces grep)

| You want... | Use this instead of... | One shot? |
|---|---|---|
| A string across all files | `grep -rn "foo" src/` | YES — `search_files("foo", target="content")` |
| A string in one file (+context) | `grep -n "foo" file.c` | YES — `search_files("foo", target="content", path="file.c", context=4)` |
| A filename by name/glob | `find . -name "*.c"` | YES — `search_files("*.c", target="files")` |
| A line range inside a file | `sed -n '1400,1420p'` | YES — `read_file(path, offset=1400, limit=20)` |
| Several files at once | sequential greps | YES — batch all `read_file` calls in ONE tool block |

## The batching discipline

Independent reads MUST be in the same assistant turn (same function_calls block). The runtime executes them concurrently. Only serialize when a later call's input depends on an earlier call's output (e.g. read file → patch file with the old_string you just saw).

## The 3-grep hard stop

If, mid-session, the SAME grep string has already appeared 3+ times in the transcript, STOP. Switch to `search_files`. This is a standing self-check — the session is looping, not converging.

## Why `search_files` is strictly better here

- ripgrep-backed (same engine as `rg` under the hood), returns line numbers + optional context lines.
- No terminal output truncation (terminal caps stdout at 50KB).
- No risk of `echo pass | sudo -S` prompting or buffer issues.
- Returns structured match data you can reason over directly — no manual `awk`/`sed` post-processing.

## When terminal search IS acceptable (and terminal is unblocked)

- `git log --oneline -3` / `git status --short` (git plumbing, not grep).
- `nm <binary> \| grep " U "` / `ldd <binary> \| grep ggml` (symbol-table inspection — no `search_files` equivalent in the file corpus).
- `git bisect` / `make` output filtering (already running a command, just narrowing its output).

## Quick mnemonic

> "grep is a loop with a keyboard. search_files is grep, but bounded and batched." — the user knew.
