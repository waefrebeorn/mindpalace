# NVK on WSL2: Limitations & Paths (2026-07-01)

## Summary
NVK (Mesa's Vulkan driver for NVIDIA GPUs) is **already installed** at standard paths:
- Driver: `/usr/lib/x86_64-linux-gnu/libvulkan_nouveau.so` (16 MB, Mesa 25.2.8)
- ICD: `/usr/share/vulkan/icd.d/nouveau_icd.json`

**But it cannot work in WSL2** — not due to PATH, but due to missing kernel driver + DRM device.

## Why NVK Fails in WSL2

| Component | Status | Required for NVK? |
|-----------|--------|-------------------|
| NVK userspace driver (Mesa) | ✅ Installed | Yes |
| ICD manifest | ✅ Installed | Yes |
| NVIDIA GPU (RTX 4050) | ✅ On Windows host | Yes |
| **Linux `nouveau` kernel driver** | ❌ No device to bind | **YES — mandatory** |
| **`/dev/dri/renderD*` (DRM device)** | ❌ Missing | **YES — mandatory** |
| WSL2 GPU passthrough | ✅ CUDA/DX12 only | Not nouveau |

**Key string in NVK binary**: `"DRM kernel driver '%.*s' in use. NVK requires nouveau."`

WSL2 exposes the NVIDIA GPU via:
- **CUDA**: NVIDIA proprietary userspace (`libcuda.so` → `nvcuda.dll` thunk)
- **DX12/Vulkan**: Microsoft's `d3d12`/`virtio-gpu` translation layer (not nouveau)

Neither provides the Linux `nouveau` kernel driver or `/dev/dri` device that NVK requires.

## Working Vulkan ICDs in This WSL2

| ICD | Driver | Works? |
|-----|--------|--------|
| `virtio_icd.json` | `libvulkan_virtio.so` (WSLg) | ✅ With WSLg enabled |
| `lvp_icd.json` | `libvulkan_lvp.so` (LLVMPipe) | ✅ Always (software) |
| `nouveau_icd.json` | `libvulkan_nouveau.so` (NVK) | ❌ No DRM device |

## For WuBuOS Architecture

- **Hosted binary** (`src/hosted/wubu`): VSL loads Vulkan via `dlopen("libvulkan.so.1")` → loader auto-discovers ICDs
- **VSL Driver Init** (`src/runtime/vsl/vsl_driver.c`): Creates `VkInstance` with whatever ICD loader finds
- **Bear RL Vulkan**: `bear_vulkan_init()` uses same loader path

**Recommendation**: Don't force NVK in WSL2. Let loader pick working ICD (virtio for WSLg, lvp for software). For bare-metal targets with NVIDIA GPUs, ensure `nouveau` kernel module loaded and `/dev/dri/renderD*` exists.

## Verification Commands

```bash
# List ICDs
ls -la /usr/share/vulkan/icd.d/

# Test each ICD
VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/virtio_icd.json vulkaninfo --summary
VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json vulkaninfo --summary

# Check DRM devices (bare metal only)
ls -la /dev/dri/

# Check nouveau module
lsmod | grep nouveau
dmesg | grep nouveau
```