---
name: wubuwizard-rebuild-linux
description: "Rebuild WuBuWizard brain: clone, dims migration, blockers."
---
# wubuwizard brain: rebuild on a Linux x86_64 host

Repo: `waefrebeorn/wubuwizard` (the brain). Clones PUBLIC over HTTPS (no token):
`git clone --branch main https://github.com/waefrebeorn/wubuwizard.git ~/opt/wubuwizard`

Build (CPU-only host, no nvcc): `make gen_text` (uses gcc; .cu GPU targets won't build).

## The S6/S7 WUBU_DIMS runtime-dims migration (must know before editing)
The refactor `0e614de` removed per-model dim fields from `wubu_model_t` and routes them
through a single runtime global `WUBU_DIMS` (include/wubu_dims.h). Consumers read dims via
macros that expand to `WUBU_DIMS.<field>`: `D_MODEL`, `SSM_D_STATE`, `SSM_K_HEADS`,
`SSM_V_HEADS`, `KEY_DIM`, `CONV_DIM`, `VALUE_DIM`, `DT_RANK`, `CONV_KERNEL`, `GQA_Q_HEADS`,
`GQA_KV_HEADS`, `GQA_HEAD_DIM`, `GQA_KV_DIM`. Expert/FFN compile-time constants renamed to
`DEF_N_EXPERTS`/`DEF_N_ACTIVE_EXPTS`/`DEF_D_FF` (in wubu_moe.h). The old dim names
(`N_EXPERTS`, `D_FF`, `N_ACTIVE_EXPTS`) NO LONGER exist for C — always use `DEF_*`.

Loader wiring: `wubu_dims_default()` (legacy 2048 defaults) then build a `wubu_dims_t`,
override the GGUF-derived fields (d_model, gqa_head_dim), then `wubu_dims_set(&wd)` — that
call finalizes derived cross-products internally (key_dim, conv_dim, value_dim, gqa_kv_dim).
Wiring dims into a loader = populate wubu_dims_t + call wubu_dims_set; do NOT assign struct
fields (they don't exist anymore). See src/wubu_model_safetensors_bridge.c for the pattern.

`wubu_ssm_forward` signature is `(x, B, T, w, ssm_state, conv_state, output, gpu_qkv, gpu_z, ws)`
— 10 args; old CPU call sites miss the final `ws`, add `, NULL`.

Build wiring: CORE_OBJ must include `src/wubu_dims.o src/wubu_dims_gpu_stub.o` (Linux Makefile
stale; Makefile.win already has them). `wubu_dims_gpu_stub.c` is the no-nvcc shim for
`wubu_dims_sync_gpu()` — never require the .cu when no CUDA.

## Verified checkpoint (2026-11-06)
Applied to ~/opt/wubuwizard main @ d27ed4e (working tree, NOT committed/pushed — user's
main-only/ff-only rule):
- wubu_model.c: full WUBU_DIMS migration in init + ~106 `model->d_model`→`D_MODEL` etc.
- header: `[N_ACTIVE_EXPTS]`→`[DEF_N_ACTIVE_EXPTS]` (expert_recorder, expert_history)
- 4 wubu_ssm_forward calls: added ws=NULL
- all src/*.c bare `D_FF|N_EXPERTS|N_ACTIVE_EXPTS`→`DEF_*`
- Makefile CORE_OBJ += wubu_dims.o wubu_dims_gpu_stub.o
RESULT: src/wubu_model.o compiles clean (was ~40 errors).

## Remaining blocker (pre-existing, NOT from the migration)
Building gen_text stops at `src/wubu_moe.o`: 2 unbalanced braces (git HEAD has open=91/
close=89 even BEFORE edits) → undeclared indices_s/weights_s/e/out_s etc. + "expected
declaration at end of input". Fix the brace imbalance in wubu_moe.c (before line ~540) then
continue; more CORE_OBJ files may carry similar stale-code breaks. Always verify the whole
target links and run a numeric test (prove a number, not just compile), per user's standing
rule: no fabricated results.

## Test targets

`make test_<name>` BUILDS AND RUNS `tools/test_<name>.c` -- it is the gate, not
just a compile. Add the target beside the others and end the recipe with `./$@`
so `make test_<name>` actually verifies:

    test_magnet: tools/test_magnet.c src/wubu_magnet.c
    	$(CC) $(CFLAGS) -Iinclude -o $@ $^ $(LDFLAGS)
    	./$@

The repo's `.gitignore` ignores `/tools/test_*`, so a new driver needs
`git add -f tools/test_<name>.c`; a plain `git add` silently skips it and the
test exists only on your disk.

The wubuwizard working tree usually carries unrelated uncommitted changes
(WUBU_DIMS edits, other people's in-flight work). Stage only your own hunks:
write the hunk to a file and `git apply --cached --recount <file>`. Never
`git add -A` -- it commits someone else's work under your name.
