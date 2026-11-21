# Hugging Face dataset harvest

For "add datasets to the corpus" requests. The deliverable is a curated,
verified, downloaded pack with a manifest — not a list of links.

## Endpoints (all stdlib urllib; no HF SDK needed)

```
search   https://huggingface.co/api/datasets?search=<q>&limit=25&full=true&sort=downloads&direction=-1
info     https://huggingface.co/api/datasets/<id>
tree     https://huggingface.co/api/datasets/<id>/tree/main?recursive=true
rows     https://datasets-server.huggingface.co/splits?dataset=<id>
         https://datasets-server.huggingface.co/first-rows?dataset=<id>&config=<c>&split=<s>
file     https://huggingface.co/datasets/<id>/resolve/main/<path>?download=true
```

`full=true` is required to get `cardData`, `tags`, `downloads`, `likes`,
`lastModified`. The search response has **no byte size**; `usedStorage` is not
reliable. Only the tree endpoint gives real sizes.

## Funnel (repeatable shape)

1. **Discovery** — 25-36 topic queries. Dedupe by id. A second pass over
   under-covered axes (terminal, bash, linux, syscall, assembly, compiler,
   debugging, git, docker, fuzzing, posix, filesystem, bare metal) finds the
   OS/agent sets that general queries bury.
2. **Small filter** — `size_categories` in {`n<1K`, `1K<n<10K`,
   `10K<n<100K`} as a first cut, then exact bytes from the tree call.
3. **Cap** — keep datasets between ~1 MB and the cap you will actually train
   on (300 MB is a useful micro cap). Below 1 MB is usually a toy test set.
4. **License** — permissive for TRAINING: apache-2.0, mit, cc-by-4.0,
   cc0-1.0, odc-by, bsd-3-clause. Anything `other` gets a human read: it can
   still be valuable as an eval/research corpus (role `eval`, never trained).
5. **Usage signal** — downloads and likes are a weak prior, not quality.
   A dataset with 40k downloads and 0 likes is often a bench dump.
6. **Schema** — `first-rows` gives real field names. Drop anything whose only
   field is `image` when the corpus is text.
7. **Download + verify** — container magic, per-dataset MANIFEST, merged INDEX.

## Scripts to reuse

- `tools/wubu_download_micro.py` — reads `docs/micro-datasets.json`, pulls
  every file, verifies magic, writes per-dataset `MANIFEST.json` and a merged
  pack `INDEX.json`. Supports `--id`, `--only`, `--max-mb`, `--workers`.
- `tools/wubu_download_finefineweb.py` — domain-selective, resumable fetcher
  for `m-a-p/FineFineWeb` (68 domains, 66k shards, ~350 MB per shard).
  `--list` prints domains and counts; `--domains a,b --max-files N` bounds it.

## Pitfalls

- **A 0-byte `.part` with a 600s timeout stalls the whole run.** One bad file
  holds a worker for 30 minutes across retries. Use a short per-file timeout
  (~120s), and delete stale `.part` files on retry.
- **Repos with thousands of tiny files are slow** (one request each). Check the
  file count first; 700 files is fine, 9,800 is not worth it for a micro pack.
- **`gated: "auto"`** means the resolve URL returns 401. Register it, do not
  queue it.
- **JSON magic**: pretty-printed arrays start with `[` then a newline, so a
  first-line `json.loads` marks valid data as corrupt. Check the first
  non-space byte instead; only `.jsonl` gets a line parse.
- **A partial run must not clobber the index.** Merge new entries into the
  existing `INDEX.json` keyed by id, then recompute totals from disk.
- **Benchmarks are not training data.** Record them in an `eval_only` array
  in the spec and carry a `role` field into the index, or a later mix script
  will happily train on the test set.
- **`license: other` is a decision, not an automatic skip.** Check whether the
  aggregate is stricter than the seed: a corpus can have an MIT upstream
  (RAGTruth) yet record `mit-with-upstream-review-required` and grant no
  training or redistribution rights. Such a set is still usable for
  measurement — register it with `role: "eval"` plus the reason, keep it out
  of every train mix, and do not silently discard it as if it were unusable.
- **Derived splits leak.** A regenerated train/test split often shares
  query/context groups (or even identical serialized requests) across sides.
  Read the card's leakage note before scoring; regroup by group id, and treat
  any split-based number as optimistic until you have checked.
- **Verify a sample row after download** (`json.loads` first record, or `PAR1`
  + nonzero size). A manifest that lists bytes but never parsed a row is not
  evidence the dataset is usable.

## Manifest shape

```json
{"id": "owner/name", "category": "math", "license": "mit",
 "fields": ["problem", "solution"], "files": 3, "bytes": 21500000,
 "path": "/home/wubu/models/corpus/micro/owner__name",
 "source": "https://huggingface.co/datasets/owner/name", "role": "train"}
```

Slug directories by `owner__name` so two owners' `code` datasets do not merge.
