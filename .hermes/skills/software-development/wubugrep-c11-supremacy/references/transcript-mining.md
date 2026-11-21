# Mining a YouTube transcript for exact requirements

When a task references a video ("he described X challenges…"), **do not guess
what was said** — pull the real captions. The user explicitly demands we
"reach all the described needs / challenges" — guessing them is a failure mode.

## Working recipe (this environment)
`yt-dlp` is installed; `node` is at `/usr/bin/node`. yt-dlp needs a JS runtime
to sign the subtitle URL; tell it to use the installed node:

```bash
cd /tmp
# automatic captions need --write-auto-subs (NOT --write-subs, which only
# fetches manually-uploaded tracks and silently returns nothing)
yt-dlp --js-runtimes node --skip-download \
       --write-auto-subs --sub-lang en-orig --sub-format vtt \
       "https://www.youtube.com/watch?v=<ID>" -o "nathan.%(ext)s"
```

Pitfalls hit:
- `--write-subs` with no manual track → `There are no subtitles for the
  requested languages` and a 0-byte file. Use `--write-auto-subs`.
- Without `--js-runtimes node` (or deno) yt-dlp warns it can't sign the URL
  and still emits nothing. `which node` first; pass `--js-runtimes node`.
- The `.vtt` has `00:00:00.000 --> …` timing lines and HTML-ish duplicate
  lines. Strip to plain text:
  ```bash
  sed -e 's/<[^>]*>//g' nathan.en-orig.vtt \
    | grep -v '^[0-9]*$' | grep -v '^$' | grep -v '^WEBVTT' \
    | sed 's/  */ /g' > nathan.txt
  ```
- Transcripts are large (190 KB). Grep the cleaned `.txt` for the speaker's
  exact enumerated rules ("three strict rules", "4 GB", "self-contained",
  "io_uring", "vectorscan", "ripgrep") to build an honest coverage checklist
  rather than recalling from memory.

## Why this matters for supremacy work
Nathan's video ended with his tool *losing* to ripgrep by 80ms — so "beat him"
means beat ripgrep, not him. The transcript is the only authoritative source
for that conclusion and for his explicit challenge list. Treat any summary
(including this one) as secondary to the primary artifact.
