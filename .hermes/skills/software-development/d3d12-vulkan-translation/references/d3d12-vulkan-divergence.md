# D3D12 <-> Vulkan divergence table

Every row here is a place where the two APIs use the same word for different
values. Passing a D3D12 value straight through to Vulkan compiles cleanly and
renders wrong, so each mapping needs a test.

## Comparison functions (depth/stencil)

`D3D12_COMPARISON_FUNC` is **1-based**; `VkCompareOp` is **0-based**. The same
comparison is one number apart.

| D3D12 | value | Vulkan | value |
|---|---|---|---|
| NEVER | 1 | VK_COMPARE_OP_NEVER | 0 |
| LESS | 2 | VK_COMPARE_OP_LESS | 1 |
| EQUAL | 3 | VK_COMPARE_OP_EQUAL | 2 |
| LESS_EQUAL | 4 | VK_COMPARE_OP_LESS_OR_EQUAL | 3 |
| GREATER | 5 | VK_COMPARE_OP_GREATER | 4 |
| NOT_EQUAL | 6 | VK_COMPARE_OP_NOT_EQUAL | 5 |
| GREATER_EQUAL | 7 | VK_COMPARE_OP_GREATER_OR_EQUAL | 6 |
| ALWAYS | 8 | VK_COMPARE_OP_ALWAYS | 7 |

The signature of this bug: `LESS_EQUAL` becomes `GREATER`. Nothing errors.

## Blend factors

`D3D12_BLEND` is 1-based; `VkBlendFactor` is 0-based, and D3D12 has a hole at
12 (`BLEND_FACTOR`, which means "use the blend factor constant" and needs a
separate API call -- reject it rather than mapping it).

| D3D12 | value | Vulkan |
|---|---|---|
| ZERO | 1 | VK_BLEND_FACTOR_ZERO (0) |
| ONE | 2 | VK_BLEND_FACTOR_ONE (1) |
| SRC_COLOR | 3 | VK_BLEND_FACTOR_SRC_COLOR (2) |
| INV_SRC_COLOR | 4 | VK_BLEND_FACTOR_ONE_MINUS_SRC_COLOR (3) |
| SRC_ALPHA | 5 | VK_BLEND_FACTOR_SRC_ALPHA (4) |
| INV_SRC_ALPHA | 6 | VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA (5) |
| DEST_ALPHA | 7 | VK_BLEND_FACTOR_DST_ALPHA (6) |
| INV_DEST_ALPHA | 8 | VK_BLEND_FACTOR_ONE_MINUS_DST_ALPHA (7) |
| DEST_COLOR | 9 | VK_BLEND_FACTOR_DST_COLOR (8) |
| INV_DEST_COLOR | 10 | VK_BLEND_FACTOR_ONE_MINUS_DST_COLOR (9) |
| SRC_ALPHA_SAT | 11 | VK_BLEND_FACTOR_SRC_ALPHA_SATURATE (10) |
| BLEND_FACTOR | 12 | -- invalid without a separate API -- |
| INV_BLEND_FACTOR | 13 | -- invalid without a separate API -- |
| SRC1_COLOR | 14 | VK_BLEND_FACTOR_SRC1_COLOR (12) |
| INV_SRC1_COLOR | 15 | VK_BLEND_FACTOR_ONE_MINUS_SRC1_COLOR (13) |
| SRC1_ALPHA | 16 | VK_BLEND_FACTOR_SRC1_ALPHA (14) |
| INV_SRC1_ALPHA | 17 | VK_BLEND_FACTOR_ONE_MINUS_SRC1_ALPHA (15) |

## Blend operations -- MIN/MAX SWAP

This one is not a shift. A table, never arithmetic.

| D3D12 | value | Vulkan | value |
|---|---|---|---|
| ADD | 1 | VK_BLEND_OP_ADD | 0 |
| SUBTRACT | 2 | VK_BLEND_OP_SUBTRACT | 1 |
| REV_SUBTRACT | 3 | VK_BLEND_OP_REVERSE_SUBTRACT | 2 |
| MIN | 4 | VK_BLEND_OP_MIN | 3 |
| MAX | 5 | VK_BLEND_OP_MAX | 4 |

## Rasterizer

| D3D12 | value | Vulkan |
|---|---|---|
| FILL_MODE_WIREFRAME | 1 | VK_POLYGON_MODE_LINE |
| FILL_MODE_SOLID | 2 | VK_POLYGON_MODE_FILL |
| CULL_FRONT | 1 | VK_CULL_MODE_FRONT_BIT |
| CULL_BACK | 2 | VK_CULL_MODE_BACK_BIT |
| CULL_NONE | 3 | VK_CULL_MODE_NONE |
| FRONT_COUNTER_CLOCKWISE | bool | VK_FRONT_FACE_COUNTER_CLOCKWISE |
| FRONT_CLOCKWISE | bool | VK_FRONT_FACE_CLOCKWISE |

## Command lists -- a distinction Vulkan does not have

| D3D12 | Vulkan |
|---|---|
| DIRECT list | VK_COMMAND_BUFFER_LEVEL_PRIMARY on the graphics queue |
| BUNDLE list | VK_COMMAND_BUFFER_LEVEL_SECONDARY (a bundle IS secondary) |
| COMPUTE list | PRIMARY on the **compute** queue family |
| COPY list | PRIMARY on the **transfer** queue family |

Vulkan has no compute/copy command-buffer level. Every D3D12 allocator needs
`VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT`, because D3D12 lets the app
reset a SINGLE list.

## Topology -- a family, not a value

`D3D12_PRIMITIVE_TOPOLOGY_TYPE` is a FAMILY; `VkPrimitiveTopology` is concrete.

| D3D12 type | value | Vulkan (list form) |
|---|---|---|
| UNDEFINED | 1 | none |
| POINT | 2 | VK_PRIMITIVE_TOPOLOGY_POINT_LIST |
| LINE | 3 | VK_PRIMITIVE_TOPOLOGY_LINE_LIST |
| TRIANGLE | 4 | VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST |
| PATCH | 5 | VK_PRIMITIVE_TOPOLOGY_PATCH_LIST |

The strip and fan variants are selected by the concrete D3D12 topology, which
this module does not consume -- report them as not determined rather than
guessing.

## Resource states -- a bit set onto a triple

D3D12 `RESOURCE_STATES` is a bit set (composites such as `GENERIC_READ` are the
OR of others), and it carries no layout. Map to
`(VkPipelineStageFlags, VkAccessFlags, VkImageLayout)`.

| D3D12 state | stage | access | layout |
|---|---|---|---|
| COMMON / PRESENT (0) | ALL_COMMANDS | 0 | GENERAL |
| VERTEX_AND_CONSTANT_BUFFER | VERTEX_INPUT + all shader stages | VERTEX_ATTRIBUTE_READ \| UNIFORM_READ | n/a (buffer) |
| INDEX_BUFFER | VERTEX_INPUT | INDEX_READ | n/a |
| RENDER_TARGET | COLOR_ATTACHMENT_OUTPUT | COLOR_ATTACHMENT_READ \| WRITE | COLOR_ATTACHMENT_OPTIMAL |
| UNORDERED_ACCESS | ALL_COMMANDS | SHADER_READ \| SHADER_WRITE | GENERAL |
| DEPTH_WRITE | EARLY + LATE_FRAGMENT_TESTS | DEPTH_STENCIL_ATTACHMENT_READ \| WRITE | DEPTH_STENCIL_ATTACHMENT_OPTIMAL |
| DEPTH_READ | EARLY + LATE_FRAGMENT_TESTS | DEPTH_STENCIL_ATTACHMENT_READ | DEPTH_STENCIL_READ_ONLY_OPTIMAL |
| NON_PIXEL_SHADER_RESOURCE | vertex/tess/geom/compute | SHADER_READ \| UNIFORM_READ | SHADER_READ_ONLY_OPTIMAL |
| PIXEL_SHADER_RESOURCE | FRAGMENT_SHADER | SHADER_READ \| UNIFORM_READ | SHADER_READ_ONLY_OPTIMAL |
| STREAM_OUT | TRANSFORM_FEEDBACK | TRANSFORM_FEEDBACK_WRITE | n/a |
| INDIRECT_ARGUMENT | DRAW_INDIRECT | INDIRECT_COMMAND_READ | n/a |
| COPY_DEST | TRANSFER | TRANSFER_WRITE | TRANSFER_DST_OPTIMAL |
| COPY_SOURCE | TRANSFER | TRANSFER_READ | TRANSFER_SRC_OPTIMAL |
| RESOLVE_DEST | TRANSFER | TRANSFER_WRITE | TRANSFER_DST_OPTIMAL |
| RESOLVE_SOURCE | TRANSFER | TRANSFER_READ | TRANSFER_SRC_OPTIMAL |
| SHADING_RATE_SOURCE | FRAGMENT_SHADING_RATE_ATTACHMENT | FRAGMENT_SHADING_RATE_ATTACHMENT_READ | FRAGMENT_SHADING_RATE_ATTACHMENT_OPTIMAL |
| RAYTRACING_ACCELERATION_STRUCTURE | ACCELERATION_STRUCTURE_BUILD (+ ray tracing shader) | ACCELERATION_STRUCTURE_READ \| WRITE | n/a |

Rules that matter more than the table:
- **DEPTH_READ vs DEPTH_WRITE must differ in BOTH layout and write access** --
  conflating them is the classic bug.
- **COMMON maps to GENERAL for images** (Vulkan has no "idle" layout).
- Use the WIDEST correct stage mask. D3D12 states are coarser than Vulkan's, so
  overlap is safe (a wider barrier) and a too-narrow mask is a race.
- **Reject unknown state bits.** A layer that guesses corrupts rendering.

## Descriptor heaps

| D3D12 heap | Vulkan |
|---|---|
| CBV_SRV_UAV | MIXED -- pool sized for UNIFORM_BUFFER + SAMPLED_IMAGE + STORAGE_BUFFER + STORAGE_IMAGE |
| SAMPLER | VK_DESCRIPTOR_TYPE_SAMPLER |
| RTV | not a descriptor -- a framebuffer attachment; pool needs no size |
| DSV | not a descriptor -- a framebuffer attachment; pool needs no size |

A GPU-visible heap needs `UPDATE_AFTER_BIND` on BOTH the pool
(`VK_DESCRIPTOR_POOL_CREATE_UPDATE_AFTER_BIND_BIT`) and the binding
(`VK_DESCRIPTOR_BINDING_UPDATE_AFTER_BIND_BIT`), because the app writes into it
after the set has been bound.

## Barriers -- three D3D12 types, and only one is a resource barrier

| D3D12 type | Vulkan | notes |
|---|---|---|
| TRANSITION | `VkImageMemoryBarrier` / `VkBufferMemoryBarrier` | layout + access both change |
| UAV | **`VkMemoryBarrier` (global)** | execution + memory dependency ONLY; the layout must NOT change |
| ALIASING | resource barrier with `oldLayout == newLayout` | a resource reused at an address another occupied |

An emitted `VkImageMemoryBarrier` carries `VK_NULL_HANDLE` for the resource: the
barrier is built before the resource is looked up and patched in afterwards.

**A UAV barrier must never change the layout.** It orders every UAV access
against every other one, so it is a GLOBAL memory barrier; emitting a layout
change there costs a render-target resolve on some drivers for no benefit.
D3D12 apps issue UAV barriers constantly (every compute pass whose output the
next pass reads), so modelling only transitions is the biggest hole in a
state-translation slice.

## Fences -- a value, not a binary state

| D3D12 | Vulkan |
|---|---|
| `ID3D12Fence` (a 64-bit counter the CPU and GPU both signal and wait on) | `VK_KHR_timeline_semaphore` -- `vkSignalSemaphoreKHR` / `vkWaitSemaphoresKHR` |

A Vulkan BINARY semaphore cannot express this: it has no value. The timeline
semaphore matches 1:1.

**Timeline values must be STRICTLY INCREASING.** Accepting an equal or lower
signal collapses two submissions into one, so the CPU can believe the GPU
finished the first while it is still executing it -- a use-after-free that
surfaces frames later as corruption. Also: waiting on a value that was never
signalled is a programming error, not a block, because the GPU can never reach
it.

## Heaps -- three types onto a device-reported type array

| D3D12 heap | Vulkan memory properties |
|---|---|
| DEFAULT (render targets, textures) | `DEVICE_LOCAL` |
| UPLOAD (CPU writes, GPU reads) | `HOST_VISIBLE \| HOST_COHERENT` |
| READBACK (GPU writes, CPU reads) | `HOST_VISIBLE` (prefer `HOST_CACHED`) |

- UPLOAD must be coherent: without it the writes need an explicit invalidate to
  reach the GPU.
- READBACK must NOT REQUIRE coherent -- cached reads are faster, and requiring
  it excludes the best type on most devices. Prefer cached (two-pass
  selection: cached first, then either).
- The chosen type must satisfy the heap's properties, the app's extra
  requirements, AND `VkMemoryRequirements::memoryTypeBits`. A type outside the
  mask cannot back the resource however suitable it looks.
- A missing type is an ERROR, not a fallback: silently picking a slower type
  turns a staging upload into a stall.

## Swapchain / present -- the sync interval Vulkan cannot express

| D3D12 swap effect | Vulkan present mode |
|---|---|
| FLIP_SEQUENTIAL | `FIFO_KHR` (vsync, tear-free) |
| FLIP_DISCARD | `MAILBOX_KHR` (flip, tear-free, lowest latency) |
| DISCARD (legacy bitblt) | `IMMEDIATE_KHR` |

| D3D12 sync interval | Vulkan |
|---|---|
| >= 1 | `FIFO_KHR` |
| 0 + `ALLOW_TEARING` | `IMMEDIATE_KHR` |
| 0, no tearing | `MAILBOX_KHR` |

**A sync interval above 1 has NO Vulkan equivalent** (FIFO is every frame,
IMMEDIATE is none). Map to FIFO and report that an app-level limiter is
required; an app silently getting 60Hz instead of 30 would never know.

Frame latency: `SetMaximumFrameLatency(N)` means N frames in flight, so
`minImageCount = max(3, N + 1)`. Vulkan may return MORE images than requested,
so raise the count rather than rejecting a desc whose buffer count seems too
small for its latency.

A FLIP chain needs >= 2 buffers (there is nothing to flip TO with one); the
legacy DISCARD effect works with a single buffer.

## Render pass -- load/store, where NO_ACCESS is easy to get wrong

| D3D12 beginning access | Vulkan |
|---|---|
| PRESERVE | `LOAD_OP_LOAD` |
| CLEAR | `LOAD_OP_CLEAR` |
| NO_ACCESS | `LOAD_OP_DONT_CARE` |

| D3D12 ending access | Vulkan |
|---|---|
| PRESERVE | `STORE_OP_STORE` |
| DISCARD | `STORE_OP_DONT_CARE` |

**`NO_ACCESS` maps to `DONT_CARE` on BOTH sides.** Mapping it to LOAD reads
stale contents; mapping it to STORE keeps them -- and D3D12's contract is that
the contents are UNDEFINED afterwards. Both failures are silent corruption,
not errors.

Validation Vulkan rejects opaquely: `LOAD_OP_LOAD` with an `UNDEFINED`
initial layout is a contradiction (loading implies the contents already exist
in that layout); the depth-stencil attachment index must be inside the
attachment list; sample counts must be a power of two; the stencil load/store
ops mirror the depth ones.

## Image views and framebuffers -- the aspect comes from the FORMAT

| Format class | `VkImageAspectFlags` |
|---|---|
| `D16_UNORM`, `X8_D24_UNORM_PACK32`, `D32_SFLOAT` | `DEPTH` |
| `S8_UINT` | `STENCIL` |
| `D16_UNORM_S8_UINT`, `D24_UNORM_S8_UINT`, `D32_SFLOAT_S8_UINT` | `DEPTH \| STENCIL` |
| multi-planar (YUV) | none -- reject |
| anything else | `COLOR` |
| `UNDEFINED` | reject, never guess colour |

D3D12 says "depth-stencil view" and lets the format decide what it contains;
Vulkan requires the aspect to be named explicitly. Asking for the wrong aspect
does not error -- it binds a view the driver interprets differently and the
depth test reads garbage.

Vulkan requires every framebuffer attachment to share the framebuffer's width,
height and sample count. **D3D12 never checks this at all**, and the driver's
answer is a validation message rather than an error code, so a layer must check
it -- likewise a colour view claimed as depth-stencil.

## Logical device -- every field is a REQUEST

`vkCreateDevice` answers a bad request with a generic failure naming no field,
so validate before calling it:

- the queue family index must exist
- `queueCount` must not exceed what the family reported
- a family must NOT be requested twice -- two `DeviceQueueCreateInfos` for one
  family is invalid; the right shape is one info with `queueCount = N`
- every requested queue carries a priority in 0.0..1.0
- an extension must have a name (a `NULL` would be silently skipped)

D3D12 hides all of this: the app asks for a device and the runtime picks the
queues.
