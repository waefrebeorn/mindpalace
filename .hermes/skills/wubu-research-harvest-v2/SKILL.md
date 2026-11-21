---
name: wubu-research-harvest-v2
trigger: Use when harvesting a research or dataset corpus in layered passes.
description: 7-step paper/dataset harvest with verified manifests.
category: research
version: 1.0.1
---

# Research Harvest Pipeline

## When to Use

- The ask is "go deep" on a research topic: 7 layers x 25 queries, then a
  second 25 on the convergences.
- The ask is "add datasets/corpus": use the Hugging Face harvest section below
  and `references/hf-dataset-harvest.md`.
- You need a verified, resumable archive (papers or dataset shards) with a
  manifest, not a list of search hits.

## The 7-Layer Research Stack
Layer 1: Core paper (e.g. Nickel & Kiela 2017 for Poincare)
Layer 2: Follow references from Layer 1 (20-30 papers)
Layer 3: Search arXiv for related papers
Layer 4: Search GitHub for implementations
Layer 5: Extract code from top 5 repos (pure text)
Layer 6: Tutorials and blog posts
Layer 7: Criticisms and limitations

## Infrastructure
- tools/harvest_pond.py (arXiv API + PyMuPDF + dedup)
- ponds/<name>.json config
- AN24-step*/ output dirs
- Resume: pre-load SHA-1 hashes, continue numbering
- Purity gate: >85% printable, no NUL bytes

## Pitfalls: arXiv Rate Limiting (HTTP 429)
When arXiv returns 429, harvest_pond.py fails silently. This happened on steps 4-7.

### Fallback Stack
1. web_search for ar5iv HTML (bypasses API limits)
2. Parse ar5iv HTML directly (faster than PDF)
3. Semantic Scholar API for citations
4. OpenAlex API for discovery
5. Crossref API for DOI resolution

### Custom deep-dive scripts
Build per-step custom harvesters with retry/backoff and resume when harvest_pond fails consistently.

## 7-Step Plan (70MB each, 490MB total)
1. Fractal NN  2. KV Cache  3. Adapters  4. Self-Modifying
5. Poincare  6. Info Density  7. Hardware Scaling

## Run
python3 tools/harvest_pond.py ponds/an24-step01.json --arxiv-only

## Verify
du -sh research-ponds-work/AN24-step*/

## Deep-wave protocol (7 layers x 25 queries + 25 on top)

Use this when the ask is "go deeper" rather than "collect 70MB per step".
Depth is 25 PER LAYER, and the layers are:

1. Frontier-lab release sweep — one query per lab (25 labs), newest first.
2. Citation chase — from what the sweep surfaced PLUS the project's open gaps.
3. arXiv API category/keyword sweeps (real metadata, not snippets).
4. GitHub implementations.
5. Technique/code extraction (how the algorithm is actually built).
6. Engineering blogs and tutorials.
7. Criticisms, limitations, failed replications.

Then aggregate (dedupe URLs, count cross-layer arXiv-ID frequency, list
domains) and run a SECOND 25-query pass on the convergences, not on new
topics. Persist each layer to `<work>/layerN_<topic>.jsonl` as it finishes and
print per-layer counts — a timeout then loses one layer, not the wave.

### Budget the wave as batches, not one loop

- **The per-`execute_code` tool budget is 50 calls — stay under it.** A 200-query
  wave is five or more calls of ~40 searches each, appending to `layerN.jsonl`;
  a single loop over 200 queries dies at the budget with the later layers
  unwritten. A call that performs EXACTLY 50 searches (e.g. 25+25) can starve
  the next loop, which then returns 0 records without raising: a zero-row layer
  means the budget was hit, not that the topic had no results. Cap at ~45 per
  call, print each layer's rows/unique count immediately after writing it, and
  rerun any layer that came back empty before aggregating totals.
- **Grep the cached full text for the table numbers.** `web_extract` on the
  arXiv HTML writes the whole page to a cache file and prints its path; the
  abstract carries the headline percentages but the method and training config
  live in the appendices. After the wave, grep that file for `Table [0-9]`,
  the headline deltas and the GPU-hour / learning-rate lines, and quote the
  table rather than the abstract. A paper's abstract can be self-consistent and
  still hide the negative result in Table 12.
- **Search counts are records, not sources.** Report `200 queries → 1,000
  records → 969 unique URLs` and say plainly that layers 1–7 are discovery,
  with only the seed read in full.

### Verify every ID before you download

- Exact-phrase `all:"a b c"` frequently returns 0 on arXiv; use boolean
  `all:a+AND+all:b` (URL-encoded `+AND+`).
- Batch `id_list` about 50 per call with ~3s between calls; batch 50 is the
  cap that keeps the response parseable.
- Normalize the version suffix before comparing (`2501.12948v2` matches
  `2501.12948`), or every requested ID looks missing after verification.
- An ID that does not come back from the API is NOT a paper. Never put it in
  the manifest.

### Obtain and organize

- Download only bodies whose first 4 bytes are `%PDF` and size >= 10KB.
  Keep the downloader resumable and record `failures.json`; metadata can
  exist while the PDF endpoint 404s.
- PDFs are large: keep them OUTSIDE git under `<archive>/papers/` with
  `manifest.json` (id, title, published, authors, categories, theme, path,
  size, abstract head) and per-theme indexes `by-theme/<theme>.md`. Keep the
  raw JSONL layers and the synthesis in the repo (small).
- A resumable script is ~60 lines: skip valid existing files, retry once,
  write `<id>.pdf.part` then rename.

### Product releases: the launch post is an index, not a source

When the seed is a vendor announcement (a model launch, an X thread, a blog
post), treat it as a pointer and harvest in this order:

1. **Vendor blog + model card + API reference** — the card carries the real
   parameter counts, licence and benchmark table; the API doc carries the
   limits (questions, options, bytes).
2. **The reference implementation in the vendor's repo** — an actual training
   or serving file is stronger evidence than any announcement, and it often
   discloses details the post omits (copied head code, learning rates).
3. **Independent critique before design.** Search arXiv for the product name
   plus "evaluation", "audit", "calibration". Measured weaknesses (a
   probability-axiom violation, an accuracy non-result) change the design more
   than the launch table does.
4. **Reconcile the numbers.** Tweet numbers, docs tables and model cards
   routinely disagree (an aggregate "20.7 → 74.3" became 36→73 / 7→74 /
   19→76 in the docs). Quote the table, note the discrepancy, never average
   them.

### Primary sources beat snippets

For non-CS domains (theology, law, standards), fetch the primary document
(official site / full text) and quote from it; search snippets are stale and
paraphrased. Cite the verified title/ID, never the search-result title.

**A user-supplied image is a primary source too.** When the user says "here is
the real X for reference", read every label, axis tick, annotation and hex
value in it, then reconcile those numbers against the literature — sources
disagree (one object's effective temperature was 4,310 ± 190 K in one place and
3,660 ± 50 K in another). Quote both and say which you treat as canonical for
identity; never average them and never let the doc drift from the image. If the
attachment does not arrive, say so plainly and mark the document provisional
rather than inventing the missing detail.

### Repo lilypads: take the technique, not the dependency

When the user drops a repository link and says "add this to our AGI", the
deliverable is a small, owned mechanism — not a vendored crate and not a cloud
integration.

1. **Date the repo before trusting it.** Commit count, age, stars, releases.
   A public repo hours old with two commits is a *seed*; its benchmark table is
   a claim, not evidence. Say so in the note instead of repeating the headline
   speedup.
2. **Read the licence first.** Apache/MIT can be ported with attribution; a
   `CC BY-NC*` paper or weight release is research-only (rule 7 above) and must
   never enter a training shard.
3. **Extract one mechanism and re-express it in the project's own language.**
   Write the algorithm (integer-only C11 here), not a wrapper around their
   runtime. If the idea needs their cloud, GPU, or a calibrated sensor you do
   not have, it is not a lilypad — it is a dependency.
4. **Put the rejected parts in a table** with a one-line reason each (metered
   API, no calibrated camera, needs a residual-stream hook that does not exist
   yet). The rejection list is what keeps the next session from re-litigating
   the same repo, and it is evidence that the adoption was selective.
5. **Verify the port with its own oracle, never their benchmark.** Build a
   fixture with a known answer (identical frames → 0 changed patches; one changed
   patch → exactly 1), count your own checks, and run the project gate. Report
   "technique ported, N checks" — not "their model is 12x faster".
6. **Name the technique in the user's vocabulary.** Tying it to an existing
   metaphor (eyes, photosphere, corpus) is what makes it findable later; a bare
   `wubu_diff.c` gets orphaned.

### Honest output

State the counts (queries, records, unique, verified, PDFs), where the
archive lives, and what did NOT verify. Layer 1/2/4-7 rows are search hits,
not citations; say so in the README.

## Hugging Face dataset harvest (corpora, not papers)

When the ask is "add datasets to the corpus", the same funnel applies but the
authority is the HF API, not arXiv. Full recipe and commands:
`references/hf-dataset-harvest.md`. Short form:

1. **Discovery**: `/api/datasets?search=<q>&limit=25&full=true&sort=downloads`
   over 25-30 topic axes. Run a SECOND 25-query pass on the axes the first pass
   under-covers (terminal, bash, syscall, compiler, fuzzing, posix) — that is
   where OS/agent sets hide, and they are usually the most valuable ones.
2. **Size**: `size_categories` is a tag, not bytes. Confirm with
   `/tree/main?recursive=true` and sum the file `size` fields; filter at the
   cap you can actually train on.
3. **Schema**: `datasets-server/first-rows` returns the REAL field names.
   README prose drifts, and an image-only dataset (`fields: ["image"]`)
   is useless for a text corpus — check before downloading.
4. **License**: permissive set only (apache-2.0, mit, cc-by-4.0, cc0-1.0,
   odc-by). `gated: "auto"` means the download will 401 — skip or accept on
   the site first.
5. **Mark benchmarks eval_only** in the manifest. Training on SWE-bench /
   KernelBench / terminal-bench / SafetyBench makes every later number
   fiction; keep them for measurement only.
6. **`license: "other"` is not a licence — it is a question.** A derived
   corpus (seed data MIT/Apache + third-party text + provider terms) usually
   carries no training or redistribution grant even when the seed was
   permissive. Register it as EVAL/RESEARCH ONLY, write the reason into
   `docs/micro-datasets.json` (`eval_only`), and never mix it into a training
   shard. Same for anything whose card says "research use" without naming a
   licence.
7. **The seed paper's licence governs its artifacts too.** A `CC BY-NC` or
   `CC BY-NC-SA` paper (and any weights/harness released under it) is
   research-only: record the licence in the synthesis header, mark the
   artifact `research_only`, and never let derived outputs enter a training
   shard. Check the licence before fetching the repo, not after building on it.
8. **Check split leakage in derived eval sets before quoting a score.** Group
   by `group_id` (or query/context pair) and count groups appearing in more
   than one split; a benchmark rebuilt from an upstream log routinely shares
   hundreds of pairs across train/val/test, which makes any model that saw the
   train split look better than it is. Regroup, then report.
9. **Download resumably** and verify container magic: `PAR1` for parquet,
   first non-space byte `{` or `[` for JSON — never a first-LINE json.loads,
   because a pretty-printed array starts with `[` followed by a newline.
   Merge the run's entries into an existing `INDEX.json`; a partial run must
   not clobber the full pack index.
10. **The `datasets-server/rows` endpoint is rate-limited, not a bulk API.**
    It returns HTTP 429 within a few thousand rows; retry-with-backoff buys a
    little and then stalls. For anything bigger than a sample, stream a **raw
    file** the repo actually ships (`TinyStories-train.txt` and friends) with a
    single HTTP `Range: bytes=0-N` request — one request, no rate limit, and it
    is exactly budget-bounded. Parquet-only datasets then need a parquet reader
    (pyarrow or your own); do not pretend the rows API scales to them.
11. **Never open the output shard `wb` before the fetch succeeds.** Opening it
    first and hitting a 429 mid-run leaves a zero-byte shard in place of a good
    one — silent data loss that looks like "the download found nothing". Write
    to `.part`, rename only after rows > 0, and keep the previous shard intact
    on failure.

For a >1T-token corpus sharded by domain (FineFineWeb-style: tens of thousands
of shards, 300-400MB each), do not clone the repo. Write a domain-selective
downloader with `--list`, per-domain output `<out>/<domain>/<domain>_NNNNNN.jsonl`,
a `manifest.json`, and resume-by-skipping-complete-shards; cap each file at
~120s so one stalled 0-byte `.part` cannot hang a 600s timeout and read as a
network failure, and delete zero-byte `.part` files before resuming.
