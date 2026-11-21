# WuBuOS Proton Stack Reference

## Overview
Proton/Gaming stack for WuBuOS: Custom GBM + Vulkan + Proton-GE bundle for Steam gaming compatibility.

**Files Created/Updated:**
- `src/hosted/wubu_gbm.h/c` — Pure C GBM (no libgbm)
- `src/hosted/wubu_vulkan.h/c` — Dynamic Vulkan loader + device/swapchain management
- `wubu_proton_ge_bundle.sh` — Proton-GE download/install manager
- `src/gui/wubu_proton.h/c` — Proton state management
- `src/runtime/wubu_proton.c` — Win32/DirectX translation layer
- `src/runtime/wubu_proton2.c` — Containerized Proton with bubblewrap

---

## Architecture

### Three Layers
```
┌─────────────────────────────────────────┐
│  Proton-GE Bundle Manager               │  (Shell script + GitHub API)
├─────────────────────────────────────────┤
│  WuBuOS Proton Translation Layer        │  (Win32/DirectX → Vulkan/VSL)
├─────────────────────────────────────────┤
│  Custom GBM + Vulkan                    │  (DRM/KMS + Dynamic libvulkan)
└─────────────────────────────────────────┘
```

---

## Custom GBM (`wubu_gbm.h/c`)

### Why Custom GBM?
- **No libgbm dependency** — SteamOS/Steam Deck use GBM directly
- **Pure DRM/KMS** — Dumb buffers via ioctls (CREATE_DUMB, MAP_DUMB, ADDFB)
- **Steam Deck compatible** — Matches exactly what Gamescope expects

### API
```c
wubu_gbm_device_t *wubu_gbm_create_device(int fd);
void wubu_gbm_destroy_device(wubu_gbm_device_t *gbm);
wubu_gbm_bo_t *wubu_gbm_bo_create(wubu_gbm_device_t *gbm, uint32_t w, uint32_t h, uint32_t format);
void wubu_gbm_bo_destroy(wubu_gbm_device_t *gbm, wubu_gbm_bo_t *bo);
void *wubu_gbm_bo_get_map(wubu_gbm_bo_t *bo);
uint32_t wubu_gbm_bo_get_stride/handle/width/height/format/fb_id(wubu_gbm_bo_t *bo);
```

### DRM Operations
| GBM Call | DRM Ioctl |
|----------|-----------|
| `bo_create` | CREATE_DUMB → MAP_DUMB → mmap → ADDFB |
| `bo_destroy` | RMFB → munmap → DESTROY_DUMB |

---

## Vulkan Implementation (`wubu_vulkan.h/c`)

### Architecture
- **Dynamic loading**: `dlopen("libvulkan.so.1")` → `vkGetInstanceProcAddr`
- **No static linking** — Works on any system with Vulkan ICD
- **RTX 5050 (sm_120) targeting**

### Key Structures
```c
WubuVkInstance, WubuVkPhysicalDevice, WubuVkDevice,
WubuVkSwapchain, WubuVkCmdPool, WubuVkAllocator, WubuVkPipelineCache
```

### Critical Functions
| Function | Purpose |
|----------|---------|
| `wubu_vk_instance_create()` | Create VkInstance with layers/extensions |
| `wubu_vk_physical_device_pick()` | Pick discrete GPU, enumerate queues |
| `wubu_vk_physical_device_init_surface()` | Query surface caps/formats/modes |
| `wubu_vk_device_create()` | Logical device with extensions |
| `wubu_vk_swapchain_create()` | Swapchain with mailbox/FIFO mode |
| `wubu_vk_swapchain_acquire/present()` | Frame pacing |
| `wubu_vk_cmd_pool_create()` | Command pool + buffers + fences |
| `wubu_vk_find_memory_type()` | Memory type selection |

### Present Mode Auto-Selection
```c
if (present_mode == VK_PRESENT_MODE_MAX_ENUM_KHR) {
    chosen_mode = VK_PRESENT_MODE_FIFO_KHR;  // VSYNC
    for (i in present_modes)
        if (present_modes[i] == VK_PRESENT_MODE_MAILBOX_KHR)  // Triple buffering
            chosen_mode = VK_PRESENT_MODE_MAILBOX_KHR;
}
```

---

## Proton-GE Bundle Script (`wubu_proton_ge_bundle.sh`)

### Features
- **GitHub API** integration for version discovery
- **SHA256 checksum verification**
- **Symlink management**: `$PROTON_BASE/current` → active version
- **Environment setup**: `PROTON_PATH`, `STEAM_COMPAT_CLIENT_INSTALL_PATH`, `WINEPREFIX`
- **Wine prefix initialization**: `wineboot -u`

### Usage
```bash
./wubu_proton_ge_bundle.sh install [version]    # Latest if omitted
./wubu_proton_ge_bundle.sh list                 # Available versions
./wubu_proton_ge_bundle.sh remove <version>
./wubu_proton_ge_bundle.sh current              # Show active
./wubu_proton_ge_bundle.sh run [version] <exe>  # Run Windows app
./wubu_proton_ge_bundle.sh env [version]        # Setup environment
```

---

## GPU Offload Thresholds (RTX 5050 sm_120)

| Component | GPU Threshold | Reason |
|-----------|---------------|--------|
| GQA attention (FP16 KV) | N>1 or cache_len>2048 | Small = CPU faster |
| SSM quant matmul (Q5_K/Q6_K) | N>1 (prefill) | Transfer overhead |
| SSM recurrence | Always | 10μs GPU vs 1ms CPU |
| MoE experts (IQ2_XXS) | Always | Weights on GPU |
| Output projection (Q4_K) | Always | 0.57ms vs 10ms |

### FP16 KV Cache
```c
// Store K/V as __half, cublasGemmEx with CUDA_R_16F
// cuBLAS: FP16×FP16→F32 ✅, FP16×F32→F32 ❌ (must convert Q to FP16)
```

### Strided-Batched SGEMM
```c
// Replace 32 launches/layer with 2 launches
cublasSgemmStridedBatched(handle, ...);
```

---

## Build Integration

### Makefile
```makefile
HOSTED_OBJS_LIST = $(HOSTED)/wubu_drm_direct.o $(HOSTED)/wubu_gbm.o $(HOSTED)/wubu_vulkan.o

hosted: $(HOSTED_OBJS) $(HOSTED)/xdg-shell-private.o
	$(CC) ... -lwayland-client -lxkbcommon -lm -lsqlite3 -lzstd -o $(HOSTED)/wubu
```

### Dependencies
```bash
sudo apt-get install libvulkan-dev libdrm-dev libwayland-dev libxkbcommon-dev \
    libsqlite3-dev libzstd-dev wayland-protocols
```

---

## Testing
```bash
# Build
make clean && make hosted

# Visual regression
timeout 10 ./src/hosted/wubu --screenshot test.ppm

# Proton bundle
./wubu_proton_ge_bundle.sh install
./wubu_proton_ge_bundle.sh run game.exe
```

---

## Debugging Pitfalls

### Vulkan
- `dlopen` fails → install `mesa-vulkan-drivers`
- Surface fails on Wayland → need `VK_KHR_wayland_surface` extension

### GBM
- `CREATE_DUMB` EINVAL → driver doesn't support dumb buffers
- `ADDFB` EINVAL → pitch must be 64-byte aligned

### Proton
- `wineboot -u` hangs → install `wine32:i386`
- DXVK not found → use Proton-GE bundle