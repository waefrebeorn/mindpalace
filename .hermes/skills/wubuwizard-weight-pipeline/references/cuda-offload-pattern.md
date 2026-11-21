# CUDA Offload Build/Test Recipes for wubuwizard

## Compile flags

This repo compiles `.c` files with gcc plus the CUDA runtime API headers.
Never use `__CUDACC__` in wubuwizard C files; use `#ifdef WUBU_ENABLE_CUDA`.

```makefile
CFLAGS += -DWUBU_ENABLE_CUDA
LDFLAGS += -lcudart -lcublas
```

Include the runtime header, not the full runtime header:
```c
#ifdef WUBU_ENABLE_CUDA
#include <cuda_runtime_api.h>
#endif
```

## Linking

`$(MODEL_OBJ)` expands to 100+ objects. When a test only needs the weight
pipeline + stager, link those objects explicitly to avoid `multiple
definition` errors.

Correct:
```makefile
tools/verify_maya_stager: tools/verify_maya_stager.c src/wubu_weight.o src/wubu_stager.o include/wubutbe.h include/wubu_stager.h
	$(CC) $(CFLAGS) -DWUBU_ENABLE_CUDA -o $@ $< src/wubu_weight.o src/wubu_stager.o $(LDFLAGS)
```

Wrong (pulls in wubu_dense_ffn.o and other duplicates):
```makefile
tools/verify_maya_stager: tools/verify_maya_stager.c $(MODEL_OBJ) src/wubu_stager.o ...
	$(CC) $(CFLAGS) -DWUBU_ENABLE_CUDA -o $@ $(MODEL_OBJ) src/wubu_stager.o $(LDFLAGS)
```

## Runtime initialization

RTX 4050 via WSL works with default device 0. No `CUDA_VISIBLE_DEVICES`
needed. The stager falls back to `malloc` if `cudaHostAlloc` fails.

## Bandwidth expectations

RTX 4050 via WSL (PCIe x8 gen4):
- `cudaMemcpyAsync` staged copies: 3–5 GB/s
- Enqueue/wait cycle without auto-workers: ~200k GB/s reported (measurement
  artifact — no real copy in flight)
- Real DMA only shows when `cudaMemcpyAsync` is called explicitly

## Verify target

```bash
make verify_maya_stager
```

Runs 5 tensor sizes: 128×128, 512×1024, 1024×4096, 4096×1024, 512×65536.
Expected: 5/5 PASS, bit-exact roundtrip, real CUDA DMA bandwidth on
CUDA-capable machines.
