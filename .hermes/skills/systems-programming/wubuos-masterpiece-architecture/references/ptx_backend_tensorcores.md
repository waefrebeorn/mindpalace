# PTX Backend for HolyC — Tensor Core Access

## Overview
The PTX backend (`holyc_ptx.c/h`) emits PTX 7.8 assembly targeting `sm_80` (Ampere/A100) with full `mma.sync.aligned.m16n8k16.row.col.f16.f16.f16.f16` Tensor Core MMA instruction support.

## Key Structures

```c
// In holyc_ptx.h
typedef enum {
    HC_TARGET_X86_64 = 0,
    HC_TARGET_PTX    = 1,
} HCTargetArch;

typedef struct PTXGen {
    char      *code;
    size_t     code_size;
    size_t     code_cap;
    int        label_count;
    int        reg_count;
    HCTargetArch target_arch;
} PTXGen;
```

## Public API

```c
// Initialize generator
void ptx_gen_init(PTXGen *gen);

// Emit PTX kernel (internal)
void ptx_emit_header(PTXGen *gen);
void ptx_emit_matmul_kernel_prologue(PTXGen *gen, const char *name);
void ptx_emit_mma_f16_m16n8k16(PTXGen *gen, const char *d_a, const char *d_b, const char *d_c);
void ptx_emit_holyc_gpu_matmul(PTXGen *gen);

// Public: Compile HolyC → PTX string
char *hc_compile_ptx(const char *source);

// Public: Execute PTX via CUDA driver (stub)
int hc_exec_ptx(const char *ptx_code, void **args, int num_args);

// Public: Built-in HolyC function (stub)
int64_t hc_builtin_gpu_matmul(int64_t A, int64_t B, int64_t C, int64_t M, int64_t N, int64_t K);
```

## Generated PTX Kernel Template

```ptx
.version 7.8
.target sm_80
.address_size 64

.visible .entry gpu_matmul(
    .param .b64 A_ptr,
    .param .b64 B_ptr,
    .param .b64 C_ptr,
    .param .u32 M,
    .param .u32 N,
    .param .u32 K
) {
    .reg .b64 A_addr, B_addr, C_addr;
    .reg .u32 M_dim, N_dim, K_dim;
    .reg .b32 tid_x, tid_y;

    ld.param.u64 A_addr, [A_ptr];
    ld.param.u64 B_addr, [B_ptr];
    ld.param.u64 C_addr, [C_ptr];
    ld.param.u32 M_dim, [M];
    ld.param.u32 N_dim, [N];
    ld.param.u32 K_dim, [K];

    mov.u32 tid_x, %ctaid.x * %ntid.x + %tid.x;
    mov.u32 tid_y, %ctaid.y * %ntid.y + %tid.y;

    setp.ge.u32 p0, tid_x, M_dim;
    @p0 ret;
    setp.ge.u32 p1, tid_y, N_dim;
    @p1 ret;

    .reg .b16 Ra0, Ra1, Ra2, Ra3;
    .reg .b16 Rb0, Rb1;
    .reg .f32 Rc0, Rc1, Rc2, Rc3;

    /* Load matrix tiles via ldmatrix.sync.aligned.x1.m8n8.shared.b16 */
    /* Then: mma.sync.aligned.m16n8k16.row.col.f16.f16.f16.f16 */
}
```

## MMA Instruction Format (FP16 Tensor Core)

```ptx
mma.sync.aligned.m16n8k16.row.col.f16.f16.f16.f16
    {Ra0, Ra1, Ra2, Ra3},      // Matrix A (4 registers, row-major 16x16)
    {Rb0, Rb1},                 // Matrix B (2 registers, col-major 16x8)
    {Rc0, Rc1, Rc2, Rc3},       // Matrix C (4 registers, accumulator)
    {Ra0, Ra1, Ra2, Ra3};       // Result D (overwrites A registers)
```

## Test Coverage

- `test_holyc_ptx`: 31 tests (header emission, kernel prologue, MMA instruction, full kernel, compile API)
- Run: `make test_holyc_ptx`

## Next Steps (Phase 2)

1. Implement `ldmatrix.sync` shared memory loading for efficient tile transfer
2. Add warp-level primitives (`shfl.sync`, `vote.sync`) for reduction
3. Implement `hc_exec_ptx()` with CUDA Driver API (`cuModuleLoadData`, `cuLaunchKernel`)
4. Add `bear_cuda.c` integration for BearRL training from HolyC
5. Add PTX JIT compilation path alongside x86-64 codegen