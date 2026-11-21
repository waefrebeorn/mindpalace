# Research Harvest Pipeline — Session Notes

## Session: 2026-08-06 (AN24 Research)

### What Worked
- `harvest_pond.py` worked well for steps 01-03 (arXiv API available)
- Subagents built custom 7-layer harvesters for steps 04-07 (arXiv API 429)
- ar5iv HTML parsing: 54-177 KB/paper, 99.3% printable
- Semantic Scholar API: resolved citations via externalIds
- OpenAlex: concept-based paper discovery returns arXiv IDs

### What Failed
- arXiv API rate limiting (429) on steps 04, 05, 06, 07 — all search terms failed
- harvest_pond.py exits silently on 429, no fallback
- `tee logs/...` fails when logs/ dir doesn't exist
- Glob expansion `ponds/an24-step01-*.json` fails in bash without proper quoting

### Custom Harvester Pattern (Step 04 Success)
```python
# 1. Seed from existing pond (reuse purity-gated text)
# 2. web_search to expand ID pool (31 queries)
# 3. ar5iv HTML reference-section mining (2 levels)
# 4. arXiv PDF download (works when API blocked)
# 5. PyMuPDF extraction + purity gate
# 6. SHA-1(3000 chars) dedup
# 7. Resume support via seen.json
```

### Corpus Results
- Step 01: 17MB (327 text files)
- Step 02: 348MB (57 papers, 8 repos, 12 blog posts, 9 notes)
- Step 03: 644MB (10,005 files: 82 papers, 9 repos, 866 cross-ref IDs)
- Step 04: 80MB (1431 text files)
- Step 05: 42MB (601 text files)
- Step 06: 19MB (282 text files)
- Step 07: 91MB (4605 text files: 158 papers, 6 repos)
- TOTAL: 1.24GB, 20,585 files — 247% of 500MB target

### Key Insight
The subagents' approach of building custom harvest scripts per topic —
using web_search for ID discovery, ar5iv HTML for content, and Semantic
Scholar for citations when arXiv API is rate-limited — was more robust
than the generic harvest_pond.py. This is the recommended approach.
