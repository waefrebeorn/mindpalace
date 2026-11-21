---
name: wubuwizard-kvfs-modules
description: Build and verify WuBuWizard KV-FS C11 modules.
category: mlops
---

# WuBuWizard KV-FS module work

Repo: `/home/wubu/opt/wubuwizard` (branch `main`, public HTTPS push works). Layout: `src/wubu_<m>.c`, `include/wubu_<m>.h`, tests as `tools/test_<m>.c`. The KV-cache-as-filesystem stack:
- `wubu_kvfs` (namespace mount/unmount/lookup/open+handle) -> `wubu_kv_embedding` (encode/decode/coherence) -> `wubu_coherence_reward`
- `wubu_fs_dataset`, `wubu_pond_streamer`, `wubu_grow_kv`+`wubu_kv_shrink` (the wired shrink — the plan table calls it `wubu_shrink_kv`, the codebase's real name is `wubu_kv_shrink`), `wubu_kv_coherence_diag`, `wubu_poincare_kv`, `wubu_kv_tier`, `wubu_kv_audit`, `wubu_semantic_router`, `wubu_kv_shell`. All 12 exist (build order per docs/wubu1-improvement-plan.md).

## Build + verify a module
Add a `test_<m>` target to the Makefile linking `tools/test_<m>.c src/wubu_<m>.c` + deps (`src/wubu_kvfs.c` `src/wubu_kv_embedding.c`). Direct CPU-compile fast path:
```
gcc -O2 -g -Wall -I include -o /tmp/test_<m> tools/test_<m>.c src/wubu_<m>.c src/wubu_kvfs.c src/wubu_kv_embedding.c -lm
```
`wubu_fs_dataset` pulls `wubu_tokenizer_hf.c` (wubu_tok_hf_encode). `make` CFLAGS carry `-fopenmp -I$(CUDA_HOME)/...`, so direct gcc is the honest gate.

## Pitfalls (each cost a debug round)
- **`wubu_kvfs_mount` refuses a SECOND mount of the same path.** Re-encoding an existing file must drop the old mount first. `wubu_kv_embedding_encode_tokens` now REPLACES in place (KV-FS write semantics): find the prior path record, unmount, remount, refresh the record — never append (a stale duplicate makes `region()` return the old n_floats).
- **`.gitignore` explicitly lists `/tools/test_kv_embedding.c` + `/tools/test_kv_hierarchy.c`** and broadly `/tools/test_*`. Source and header are NOT ignored; commit the test with `git add -f`, the source with a normal `git add`.
- **`*/` inside a `/* */` comment breaks the build** (e.g. writing `pond-*/text/`). Use `pond-NAME/text/`.
- Confirm a test PASS via `echo $?` plus the banner — a reversed ternary (`fail ? "PASS" : "FAIL"`) prints FAIL at 0 failures.
- **Audit by USAGE, not the plan-table filename.** Plan tables (docs/wubu1-improvement-plan.md) can name a module differently from the codebase's real file. Before building a "missing" module, grep who #includes / references the concept it serves (e.g. the diagnose module includes `wubu_kv_shrink.h`) — a near-equivalent may already be shipped under another name and be the one consumers actually use. Building the table-named duplicate created a module I had to revert.
- **Reconciling two overlapping implementations: the WIRED one wins.** Consumers' #include is the authority; a second module under a different name is debt, not a variant to keep side-by-side. A cleaner richer rule belongs folded INTO the wired module, never kept as a parallel module. Undo a clean single-purpose commit with `git revert <sha>` after `git show --name-only <sha>` confirms it touched only the intended files.
- **git "nothing to commit" on a file you staged = the blob is already in HEAD.** If `git ls-files --stage <path>` shows the file but `git status` is silent and `git commit` reports nothing, check `git ls-tree HEAD <path>` (`git cat-file -e HEAD:<path>`): it is committed byte-identically — a prior session shipped it. A file can also be BOTH committed and listed in .gitignore (the ignore rule never applies to tracked files), which is exactly why status shows nothing.
- Check whether a module/test is ALREADY committed before re-creating: `git cat-file -e HEAD:<path>` / `git ls-tree HEAD <path>`. The improvement-plan "already started" hints usually mean already shipped.
