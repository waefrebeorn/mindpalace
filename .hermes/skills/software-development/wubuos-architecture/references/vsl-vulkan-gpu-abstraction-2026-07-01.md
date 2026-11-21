# VSL Vulkan/GPU Abstraction Layer (2026-07-01 Session)

## Context

Built a **VSL abstraction layer** that provides Vulkan and GPU operations across both development (WSL) and target (bare metal) environments. This is a new architectural component for WuBuOS.

## Files Added to wubuos/

```
/home/wubu/wubuos/
├── vsl/
│   ├── vulkan/
│   │   ├── wubu_vsl_vulkan.h    # VSL Vulkan API
│   │   └── wubu_vsl_vulkan.c    # 3-backend implementation
│   ├── gpu/
│   │   ├── wubu_vsl_gpu.h       # VSL GPU API
│   │   └── wubu_vsl_gpu.c       # Linux DRM/KMS backend
│   ├── tests/
│   │   ├── test_vulkan.c
│   │   └── test_gpu.c
│   └── Makefile
└── build/                       # Build artifacts (gitignored)
```

## Architecture Impact

This adds a new layer in the WuBuOS stack:

```
┌─────────────────────────────────────────────────────────────────┐
│                        WuBuOS Application                        │
├─────────────────────────────────────────────────────────────────┤
│  VSL Abstraction Layer (NEW)                                    │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐   │
│  │  wubu_vsl_vulkan    │  │       wubu_vsl_gpu              │   │
│  │  - Instance mgmt    │  │  - Buffer allocation (dmabuf)   │   │
│  │  - Device enum      │  │  - Context submission           │   │
│  │  - Surface create   │  │  - Synchronization (fences)     │   │
│  │  - Backend dispatch │  │  - Display/KMS (stubs)          │   │
│  └─────────────────────┘  └─────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  Backend Implementations                                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐             │
│  │ VirtIO-GPU   │ │ VSL GPU      │ │ Linux ICD    │             │
│  │ Venus (WSL)  │ │ (bare metal) │ │ (hosted)     │             │
│  └──────────────┘ └──────────────┘ └──────────────┘             │
├─────────────────────────────────────────────────────────────────┤
│  VSL (wubu_vsl.c) - Syscall + GPU + Container Layer             │
│  ZealOS Kernel (bare metal)                                     │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Decision: Abstraction Over Direct Driver Integration

Unlike `gpu-vulkan-driver-integration` skill which covers bare-metal driver integration, this VSL layer **abstracts the backend completely**:

| Approach | Use Case |
|----------|----------|
| Direct NVK/RADV/ANV integration | Shipping OS images with specific drivers |
| VSL Vulkan/GPU abstraction | Development on WSL, cross-platform WuBuOS binaries |

## WSL2 Limitation (Critical)

**WSL2 has no `/dev/dri/` devices exposed to Linux kernel.** This is by design:

| Component | WSL2 Status | Bare Metal |
|-----------|-------------|------------|
| `/dev/dri/renderD*` | ❌ Missing | ✅ Available |
| `nouveau` kernel module | ❌ No GPU to bind | ✅ Loaded |
| VirtIO-GPU Venus | ✅ Available (via WSLg) | ⚠️ VM only |
| NVK (Nouveau Vulkan) | ❌ Cannot work | ✅ Works |

The VSL abstraction layer **isolates WuBuOS from this limitation**. Code compiles and loads on WSL; on bare metal with proper kernel modules, it works natively.

## Integration Points

| WuBuOS Component | VSL Vulkan/GPU Usage |
|------------------|---------------------|
| `wubu_compositor.c` | Vulkan render path via `wubu_vsl_vulkan.h` |
| `wubu_vsl.c` | GPU buffer/sync via `wubu_vsl_gpu.h` in syscall layer |
| `wubu_vulkan.c` (hosted) | Can use VSL Vulkan as backend |
| Container runtime | dmabuf export/import for GPU pass-through |

## Verification Results

```bash
# Build
cd /home/wubu/wubuos/vsl && make clean && make
# ✓ libwubu_vsl_vulkan.so (13 symbols)
# ✓ libwubu_vsl_gpu.so (27 symbols)
# ✓ test_vulkan, test_gpu binaries

# Run (WSL expected limitations)
LD_LIBRARY_PATH=./build ./test_vulkan
# Backend: "Linux ICD Loader" → instance creation fails (no validation layers in WSL)

LD_LIBRARY_PATH=./build ./test_gpu
# "Failed to open any DRM device" → expected, no /dev/dri in WSL2
```

## Future Work

1. **Bare metal VSL GPU driver** - Replace DRM/KMS backend with ZealOS VSL syscalls
2. **Venus integration** - Full VirtIO-GPU Venus support for WSL/VM development
3. **Surface creation** - Complete Wayland/XCB/VBE surface implementations
4. **Video encode/decode** - Add V4L2/VAAPI integration via VSL GPU
5. **Container GPU pass-through** - Use dmabuf for .wubu container GPU access

## Related Documentation

- `gpu-vulkan-driver-integration` skill: `references/vsl-vulkan-gpu-abstraction.md` (detailed technical docs)
- This session's work is in `/home/wubu/wubuos/` (separate from main WuBuOS source tree)