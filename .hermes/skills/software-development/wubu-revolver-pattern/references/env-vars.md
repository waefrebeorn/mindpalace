# Revolver Environment Variables

All revolvers accept an environment variable override. The value is parsed
as a `long` and clamped to **[1, limit]** -- NOT to [default, limit].
Lowering below the default is usually the point (shrinking buffers on bare
metal), so the floor is 1.

Parse rules that must hold everywhere:
- require FULL consumption by `strtol`; refuse a trailing unit (`64K`) or a
  partial parse (`6O4` -> 6). A truncated read becomes a smaller limit nobody
  asked for.
- refuse values below 1 (zero can never be a bound);
- report every clamp through the warn callback -- a silent fallback reads as
  acceptance.

## GGUF Reader

| Env Var | Default | Limit | Description |
|---|---|---|---|
| WUBU_QK_K | 256 | 1024 | Elements per K-quant block |
| WUBU_Q4_K_BLOCK_SIZE | 144 | 512 | Q4_K_M block byte size |
| WUBU_Q5_K_BLOCK_SIZE | 176 | 512 | Q5_K block byte size |
| WUBU_GGUF_ALIGNMENT | 32 | 4096 | GGUF tensor alignment |
| WUBU_IQ4NL_BLOCK | 18 | 64 | IQ4_NL block byte size |

## Model / Context

| Env Var | Default | Limit | Description |
|---|---|---|---|
| MAX_CTX | 524288 | 1048576 | KV cache context length |
| WUBU_MAX_CTX | (alias) | (same) | GQA KV cache token slots |
| WUBU_MAX_EXPERT_TOKENS | 256 | 4096 | Expert token limit |
| WUBD_MODEL_DIM | model-derived | — | Runtime D_MODEL override (Qwen3.8 DT_RANK=48) |
| WUBU_Q8K_BLOCKS | ceil(D_MODEL/256) | ceil(MAX_CTX/256) | Q8_K activation buffer count |
| WUBU_THREADS | omp_get_max_threads | 64 | OpenMP thread pool size |
| GPU_MAX_CTX | 262144 | 1048576 | GPU KV cache max context |
| GPU_CHUNK | 256 | 4096 | GPU attention tile size |

## API Server

| Env Var | Default | Limit | Description |
|---|---|---|---|
| WUBU_MAX_TOKENS | 128 | 4096 | Max generation tokens |
| WUBU_TOP_K | 40 | 256 | Top-k sampling |
| WUBU_MAX_OUTPUT_CHARS | 2048 | 65536 | Output char cap |
| WUBU_INFER_TIMEOUT | 30 | 3600 | Inference timeout (seconds) |
| API_PORT | 8000 | 65535 | API server listen port |
| WUBU_MAX_HEADERS | 64 | 256 | Max HTTP headers |
| WUBU_MAX_BODY | 1M | 1G | Max body size |
| WUBU_MAX_PATH | 4096 | 8192 | Max path length |
| WUBU_PERSIST_MAX_TOKENS | 4096 | 65536 | Persistent mode output limit |
| WUBU_RATE_WINDOW | 60 | 3600 | Rate limit window |
| WUBU_RATE_LIMIT | 100 | 10000 | Rate limit per window |

## Stager

| Env Var | Default | Limit | Description |
|---|---|---|---|
| WUBU_MAX_THREADS | omp_get_max_threads | 64 | Stager thread count |
| WUBU_STAGER_SLOTS | 32 | 256 | Stager slot count |
| WUBU_STAGER_BUF | 65536 | 1048576 | Stager buffer size (bytes) |

## WuBuOS namespace limits

| Env Var | Default | Limit | Description |
|---|---|---|---|
| WUBU_FS_FILES | STYXFS_MAX_FILES_LIMIT (4096) | 4096 | Runtime number of usable guest namespace slots; the array extent stays at the ceiling |
| WUBU_FS_FILE_MAX | GUEST_FILE_MAX_LIMIT (8192) | 8192 | Per-file capacity in bytes; cannot exceed the inline payload |

Cannot be raised past the limit because the storage layout embeds the payload
inline; growing it means changing the layout, which no env var should paper over.

## Safekern

| Env Var | Default | Limit | Description |
|---|---|---|---|
| WUBU_OOM_CEILING_MB | 85 | 512 | OOM kill ceiling |

## Q4_K_XL usage

```
export WUBU_QK_K=512 WUBU_Q4_K_BLOCK_SIZE=272
./gen_text_cpu Hello
```
