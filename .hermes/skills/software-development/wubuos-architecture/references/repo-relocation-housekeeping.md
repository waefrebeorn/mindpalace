# WuBuOS Repo Relocation / Housekeeping (2026-07-19)

The tree was moved from `/home/wubu/.hermes/profiles/mind-palace/home/myseed`
(a deep Hermes-profile path) to the canonical `/home/wubu/wubuos`. This is the
verified procedure + the pitfalls hit, so a future move is mechanical.

## Why move
A repo nested under `.hermes/profiles/<profile>/` is an accident of how it was
first cloned, not a deliberate home. A top-level `/home/wubu/wubuos` is the
"proper folder" for an OS-scale project.

## Procedure

1. **Check the target is free / understand what's there.**
   ```sh
   ls -la /home/wubu/wubuos
   cd /home/wubu/wubuos 2>/dev/null && git rev-parse --show-toplevel   # is it a repo?
   ```
   If a non-git dir with the same name already exists, inspect it (see Merge
   below) — do NOT blindly `mv` over it.

2. **Move the git tree.** `git` is robust to relocation because it tracks paths
   relative to `.git`; the working tree just needs to keep `.git` with it.
   ```sh
   shopt -s dotglob
   mv -n /old/repo/* /new/repo/        # -n = no-clobber: safer first pass
   # then bring dotfiles (the glob above excluded .* on some shells)
   ```
   **Pitfall:** `mv -n` keeps an EXISTING file in the destination and leaves the
   source copy behind. After the move, check `git status --short` in the SOURCE
   dir — any leftover means a name collided. Move those stragglers explicitly.

3. **Submodules travel with the move.** The `.gitmodules` path is relative
   (`path = src/runtime/container/wubucontainer`), so it stays correct. Verify:
   ```sh
   cd /new/repo && git submodule status src/runtime/container/wubucontainer
   # leading space = clean; the pinned commit must match what origin expects
   ```
   No re-init needed as long as the submodule dir moved with the parent.

4. **Merge an orphan same-named tree (if one existed).** The old `/home/wubu/
   wubuos` held real but unversioned code (VSL GPU/Vulkan modules). Folding it
   in properly:
   - Inspect each orphan dir: `du -sh`, `ls -A`. Empty dirs (`scripts/`,
     `compositor/`, `toolchain/`) → drop.
   - Real source that the repo LACKS → place under the correct `src/` subtree.
     Here `vsl/{gpu,vulkan,tests}/*.c` + `Makefile` became
     `src/runtime/vsl/gpu/{kern,vulkan,tests}/` + `Makefile`.
   - Compiled artifacts (`build/*.so`, `*.o`, test binaries) → drop (regenerable;
     and `.gitignore` already covers `*.o`/`*.so`).
   - A duplicate of a tracked file (orphan `scripts/wubu_manifest_gen.py` == repo
     `scripts/wubu_manifest_gen.py`) → keep the repo's; remove the orphan.

5. **Recover a mistakenly-deleted tracked file.** If a later `rm -rf` deletes a
   file git tracks, restore it (don't re-add from memory):
   ```sh
   git checkout -- scripts/wubu_manifest_gen.py
   ```

## Integrity checks (MUST pass before declaring done)
```sh
git fsck --full            # expect only dangling commits/blobs (harmless)
git rev-parse --show-toplevel   # must print the NEW path
git status --short        # should be clean except build-ignored binaries
git submodule status ...  # clean (space-prefixed), pin matches
make runtime              # MUST still build at the new path
make test_manifest        # or any make test_* — proves relative-path tests work
```

## Security aside encountered during this move
The `wubucontainer` submodule was `-dirty` because its working tree had locally
**deleted** `src/handlers/shToElf/stub.c` + `stub.elf` — a self-extracting
shell-ELF dropper (`/proc/self/exe`, seek back `cmd_size` bytes, `execl("/bin/
bash","-c",payload)`). It was unreferenced by any build and not WuBuOS code.
Resolution (the repo is "all ours", no PR barrier):
- In the submodule: `git rm` the two files, set a local identity
  (`git config user.name/email` — parent had one, submodule didn't, causing an
  "empty ident" commit failure), commit, `git push origin master`.
- In the parent: `git add src/runtime/container/wubucontainer` to bump the
  pinned commit, commit, push. Parent is now clean.
Rule: do NOT restore a dropper, and do NOT silently commit into a sub-repo
without intent — but when it's all-ours, removing hostile/unreferenced code is
the right call.
