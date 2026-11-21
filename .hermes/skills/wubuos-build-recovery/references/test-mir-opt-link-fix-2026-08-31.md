# test_mir_opt link fix (2026-08-31)

## Problem
`make test_mir_opt` in wubuos fails with undefined references to `wubu_isa_vulkan`,
`wubu_isa_wasm`, `wubu_tensor_dispatch`, `powf`, `GOMP_parallel`.

## Root cause
The `test_mir_opt` target in `mk/tests.mk` uses `$(ISA)` which includes
`wubu_isa_jit_stubs.c` (stubs) but NOT the real ISA drivers. The driver
(`wubu_isa_driver.c`) references `wubu_isa_vulkan` and `wubu_isa_wasm` but
the real implementations weren't in the link line.

## Fix
The `test_mir_opt` link command in `mk/tests.mk` needs:
- `$(COMP)/wubu_isa_vulkan.c $(COMP)/wubu_isa_spirv.c` — real GPU drivers
- `jit/wubu_isa_wasm.c` — real WASM emitter (exists in wubunos/jit/ dir)
- `$(COMP)/wubu_host_tensor.c` — provides `wubu_tensor_dispatch`
- `$(COMP)/wubu_tgemm_avx512.o` — AVX512 GEMM (needs `-mavx512dq -mavx512f -mavx512vl -mavx512bf16`)
- `-lm` — for `powf` in softfloat
- `-ldl` — for JIT loading
- `-fopenmp` — for GOMP_parallel in AVX512 GEMM

## Pitfall: wubu_isa_wasm.c location
`wubu_isa_wasm.c` exists ONLY in `wubunos/jit/` (the compiler submodule),
NOT in `wubuos/src/compiler/`. Do NOT create a stub — link the real file
from the submodule path. Creating a stub with wrong function signatures
causes pointer cast warnings and subtle bugs.

## Verification
```sh
cd /home/wubu/wubuos
make test_mir_opt 2>&1 | tail -3
./src/compiler/test_mir_opt  # should print "OPTIMIZER PASSED: 7/7 passed"
```
