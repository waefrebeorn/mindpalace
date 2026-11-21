# cuDNN CPU Fallback Patterns

## Overview
Phase 18 implementation of CPU fallbacks for all 117 void casts in `bear/bear_cudnn.c` `#else` stub blocks.
Uses `bear_simd.h` for SIMD-accelerated operations (AVX2/NEON/scalar).

## Architecture

### Feature Detection
```c
#if BEAR_HAVE_CUDA
    // cuBLAS implementation
#else
    // CPU fallback using bear_simd.h
#endif

#if BEAR_HAVE_CUDNN
    // cuDNN implementation
#else
    // CPU fallback using bear_simd.h
#endif
```

### Tensor Shape Packing (NCHW → 64-bit)
```c
// Pack: bits 0-15: w, 16-31: h, 32-47: c, 48-63: n
uint64_t *shape_ptr = (uint64_t*)&desc->desc;
*shape_ptr = ((uint64_t)n << 48) | ((uint64_t)c << 32) | ((uint64_t)h << 16) | (uint64_t)w;

// Unpack
uint64_t shape = *(uint64_t*)&desc->desc;
*n = (int)(shape >> 48);
*c = (int)((shape >> 32) & 0xFFFF);
*h = (int)((shape >> 16) & 0xFFFF);
*w = (int)(shape & 0xFFFF);
```

## cuBLAS Fallbacks (5 functions)

### sgemm — Matrix Multiply
```c
// C = alpha * A * B + beta * C
// A=[m,k], B=[k,n], C=[m,n] (row-major)
// bear_gemm expects A=[M,K], B=[N,K] (B transposed)
float* B_T = malloc(n * k * sizeof(float));
for (j) for (i) B_T[j*k+i] = B[i*ldb+j];  // Transpose B
bear_gemm(A, B_T, C, m, n, k);  // C = A * B_T^T = A * B
free(B_T);
// Scale by alpha
```

### saxpy — y = alpha*x + y
```c
float a_val = alpha ? *alpha : 1.0f;
if (incx == 1 && incy == 1) {
    for (i) y[i] += a_val * x[i];
} else {
    for (i, ix=0, iy=0; i<n; ++i, ix+=incx, iy+=incy) y[iy] += a_val * x[ix];
}
```

### sdot — Dot Product
```c
float result = 0.0f;
if (incx == 1 && incy == 1) {
    for (i) result += x[i] * y[i];
} else {
    for (i, ix=0, iy=0; i<n; ++i, ix+=incx, iy+=incy) result += x[ix] * y[iy];
}
return result;
```

### snrm2 — Euclidean Norm
```c
float sum = 0.0f;
if (incx == 1) for (i) sum += x[i]*x[i];
else for (i, ix=0; i<n; ++i, ix+=incx) sum += x[ix]*x[ix];
return sqrtf(sum);
```

### sscal — x = alpha * x
```c
float a_val = alpha ? *alpha : 1.0f;
if (incx == 1) for (i) x[i] *= a_val;
else for (i, ix=0; i<n; ++i, ix+=incx) x[ix] *= a_val;
```

## cuDNN Fallbacks

### Tensor Descriptors (2 functions)
- `create_tensor_desc`: Pack NCHW into descriptor pointer
- `destroy_tensor_desc`: Free (no cuDNN handle to destroy)

### Convolution (3 functions)
**Forward**: Direct NCHW convolution with stride/padding/dilation
```c
for (n,k,oh,ow) {
    for (c,r,s) {
        ih = oh*stride_h - pad_h + r*dil_h;
        iw = ow*stride_w - pad_w + s*dil_w;
        if (ih>=0 && ih<H && iw>=0 && iw<W) {
            acc += x[((n*C+c)*H+ih)*W+iw] * w[((k*C+c)*R+r)*S+s];
        }
    }
    y[((n*K+k)*out_H+oh)*out_W+ow] += alpha * acc;
}
```

**Backward Data** (input gradient):
```c
for (n,c,ih,iw) {
    for (k,r,s) {
        ih_padded = ih + pad_h - r*dil_h;
        iw_padded = iw + pad_w - s*dil_w;
        if (ih_padded%stride_h==0 && iw_padded%stride_w==0) {
            oh = ih_padded/stride_h; ow = iw_padded/stride_w;
            if (oh>=0 && oh<out_H && ow>=0 && ow<out_W) {
                acc += dy[...] * w[...];
            }
        }
    }
    dx[...] += alpha * acc;
}
```

**Backward Filter** (weight gradient):
```c
for (k,c,r,s) {
    for (n,oh,ow) {
        ih = oh*stride_h - pad_h + r*dil_h;
        iw = ow*stride_w - pad_w + s*dil_w;
        if (ih>=0 && ih<H && iw>=0 && iw<W) {
            acc += x[...] * dy[...];
        }
    }
    dw[...] += alpha * acc;
}
```

### Activation (1 function)
```c
switch (mode) {
    case 0: result = 1.0f/(1.0f+expf(-val)); break;  // sigmoid
    case 1: result = val>0?val:0; break;             // relu
    case 2: result = tanhf(val); break;              // tanh
}
y[i] = alpha*result + beta*y[i];
```

### Pooling (1 function)
- **Max**: Track max_val in window
- **Average**: Sum valid elements / count (include padding)

### Softmax (1 function)
- **Instance mode** (per spatial location): softmax over C
- **Channel mode** (per channel): softmax over H×W
- Numerical stability: subtract max before expf

### Workspace Queries (3 functions)
Return im2col buffer size estimates:
```c
size_t im2col = N * C * R * S * out_H * out_W * sizeof(float);
size_t weight = K * C * R * S * sizeof(float);
size_t output = K * out_H * out_W * sizeof(float);
return im2col + weight + output;
```

### CUDA Memory (2 functions)
```c
// cudaMalloc → malloc
void* hc_builtin_cuda_malloc(size_t bytes) { return malloc(bytes); }

// cudaFree → free
void hc_builtin_cuda_free(void* ptr) { free(ptr); }
```

## Key Patterns

### 1. Alpha/Beta Scaling
```c
float a = alpha ? *alpha : 1.0f;
float b = beta ? *beta : 0.0f;
if (b != 0) for(i) out[i] *= b;
else memset(out, 0, size);
// compute...
if (a != 1) for(i) out[i] *= a;
```

### 2. NCHW Index Calculation
```c
#define IDX(n,c,h,w) (((n*C+c)*H+h)*W+w)
#define OIDX(n,k,h,w) (((n*K+k)*out_H+h)*out_W+w)
```

### 3. Numerical Stability
```c
// Softmax: subtract max
float max_val = -INFINITY;
for (i) if (x[i] > max_val) max_val = x[i];
float sum = 0;
for (i) sum += expf(x[i] - max_val);
for (i) y[i] = expf(x[i] - max_val) / sum;

// Sigmoid: 1/(1+exp(-x))  // stable for all x
```

### 4. bear_simd.h Integration
```c
// GEMM uses bear_gemm (AVX2/NEON/scalar dispatch)
bear_gemm(A, B_T, C, M, N, K);

// Activation uses bear_act_batch for RELU
bear_act_batch(dst, src, n, BEAR_ACT_RELU);
```

## Verification
```bash
make bear          # Clean build
make test_vsl      # 52/52 passed
make test_network  # 139/139 passed
make test_oci      # 10/10 passed
make test_snapshot # 132/132 passed
```

## Notes
- All fallbacks are **functional** — not stubs
- Use `bear_simd.h` for SIMD acceleration where available
- Tensor shape packing avoids extra allocations
- Direct convolution is O(N×K×C×R×S×H×W) — acceptable for CPU inference
- Workspace estimates enable same API as cuDNN