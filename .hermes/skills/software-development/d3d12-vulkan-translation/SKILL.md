---
name: d3d12-vulkan-translation
description: Use when porting D3D12 semantics onto Vulkan (VKD3D).
category: software-development
version: 1.0.0
author: WaefreBeorn
license: MIT
metadata:
  hermes:
    tags: [wubuos, vkd3d, d3d12, vulkan, compatibility]
    related_skills: [wubuos-architecture, wubuos-test-suite]
---

# D3D12 onto Vulkan (the VKD3D class)

WuBuOS runs Windows graphics through a D3D12 personality over the Vulkan leg.
This skill is the always-on rule set for that translation. The enum-level
divergences alone are worth the file: several of them are silent-visual-bug
shaped, not error-shaped.

## When to Use

Load this when:
- building or extending the `wubu_vkd3d_*` module family (resource states,
  descriptor heaps, command lists, PSOs, the device, present);
- mapping ANY D3D12 enum, state or object onto a Vulkan equivalent;
- writing or reviewing a test that asserts a D3D12->Vulkan translation;
- deciding whether a D3D12 concept has a Vulkan counterpart at all.

Not for: the DXVK config surface (D3D9/10/11), which is a different layer, or
Proton/Wine process management.

## Non-negotiable rules

1. **Every enum mapping is a test, not an assumption.** D3D12 and Vulkan
   disagree in ways that compile fine and render wrong. The full divergence
   table is in `references/d3d12-vulkan-divergence.md`. Never pass a D3D12 enum
   value through to Vulkan because "they look the same" -- check the table.
   **Cross-check the FINISHED mapping against the table row by row, not just
   the values you remember writing.** A mapping you wrote from memory passes
   your own tests, because the tests were written from the same memory. Reading
   the table against the shipped code is the only check that is independent of
   it -- this is what caught a blend-factor off-by-one that had a green suite.
2. **A state map is a triple, and unknown bits are REJECTED.** D3D12 resource
   states carry no layout; Vulkan infers a transition from
   (pipeline stage, access mask, image layout). An unmapped bit must fail the
   call, never be defaulted -- a guessed state corrupts rendering.
3. **Not everything D3D12 calls a descriptor IS one.** Render target and depth
   stencil views are framebuffer ATTACHMENTS in Vulkan: they consume no
   descriptors, so their descriptor pools need no sizes. Conversely a
   CBV_SRV_UAV heap is a MIXED heap (CBV + SRV + UAV) and its pool must be
   sized for the union of the descriptor types it can hold.
4. **Some D3D12 distinctions do not exist in Vulkan.** COMPUTE and COPY command
   lists are a QUEUE FAMILY, not a command-buffer level; a D3D12 bundle IS a
   secondary buffer. Map the concept, do not invent a level Vulkan lacks.
5. **A PSO is immutable and must match EXACTLY.** There is no partial state
   and no fallback: a near-miss is a miss, not an approximation. The cache key
   covers the whole desc, and a hash match is only a CANDIDATE -- confirm it
   with a full `memcmp` of the stored desc, or a hash collision hands back a
   pipeline built for different state.
6. **Prove key coverage with a mutation sweep.** For every scalar field of a
   state struct, flip it and assert the key changes. A field missing from the
   key means two different pipelines share one entry. This is the single most
   valuable test in the class.
7. **Never reuse command memory while the GPU may still be reading it.** Model
   the four-state machine (recording / closed / executing / invalid) and
   refuse every transition that would recycle memory in flight. A wrong
   transition here shows up frames later as corruption, not as an error.
8. **The mapping layer opens no device.** Translate enums, state triples,
   barriers, keys and state machines in pure C11 against `<vulkan/vulkan.h>`
   only. Do NOT link `-lvulkan` into these tests: the whole point is that the
   correctness-critical translation is provable without a GPU, on any host.
   Reserve real-device work for the slices that create a `VkDevice`.
9. **When Vulkan cannot express a D3D12 value, SAY SO -- never approximate.**
   A layer that silently substitutes the nearest Vulkan value gives the app a
   mode it did not ask for and cannot detect. A D3D12 sync interval above 1 has
   no Vulkan equivalent (FIFO is every frame, IMMEDIATE is none): map to FIFO and
   REPORT that an app-level limiter is required. Same for `NO_ACCESS` (map to
   `DONT_CARE` on both sides, and say the contents are then undefined).
10. **Validation returns a REASON, not a boolean.** An app that cannot create a
    device, a memory type or a render pass needs to know WHICH requirement
    failed, or it cannot fall back to a lower one. Return a static string
    naming the first violated rule; a bare `false` is not actionable. The same
    applies to a missing memory type, where the reason must distinguish
    "not host-visible" from "not device-local" -- they have different fixes.
11. **Vulkan may return MORE than you asked for, so RAISE the request rather
    than rejecting a legal config.** `vkCreateSwapchainKHR` may return more
    images than `minImageCount`, so a frame-latency requirement that the
    requested buffer count seems to violate is met by RAISING the image count,
    not by refusing the desc. Rejecting a config the app is entitled to is
    worse than not checking it -- distinguish "raise the count" (latency vs
    buffer count) from "genuinely impossible" (a one-buffer flip chain, which
    no image count fixes).
12. **Do not validate a field the API IGNORES.** A mapper that requires a
    valid enum for a disabled feature rejects legal configs. D3D12 comparison
    functions are 1-BASED, so 0 is not a valid value -- and an app that turns
    depth testing OFF has no reason to set one, because the field is ignored.
    Gate every enum mapping on the flag that makes it matter: map the compare
    op only when `depth_enable` is set, the blend factors only when blending is
    enabled. An unconditional `map_X(...)` that returns false turns "the app
    did not care" into "the pipeline cannot be built".
13. **A descriptor pool's lifetime must OUTLIVE every set allocated from it.**
    `vkDestroyDescriptorPool` invalidates ALL descriptor sets allocated from
    it, so a set handle saved earlier becomes stale and binding it crashes
    INSIDE THE DRIVER (`libnvidia-glcore`) with no validation layer to name the
    cause. Keep the pool alive until teardown; if a pool must be destroyed
    early, destroy it only after every set from it is no longer referenced, and
    never let a helper free a pool it was handed a set from.

## SHADER COMPILER TRAP: separate `texture2D` + `sampler` folds into a COMBINED sampler

Writing GLSL the "separate" way does NOT keep the bindings separate:

```glsl
layout(binding = 0) uniform texture2D tex;
layout(binding = 1) uniform sampler samp;
... texture(sampler2D(tex, samp), uv) ...
```

glslang **folds this into one `OpTypeSampledImage` at binding 0 and deletes the
`sampler` binding entirely** (verify with `spirv-dis ... | grep OpTypeSampledImage`).

So a pipeline layout declaring binding 0 = `SAMPLED_IMAGE` and
binding 1 = `SAMPLER` does NOT match what the shader wants, and the failure is
**silent**: with no validation layers the draw still runs and samples with a
DEFAULT NEAREST sampler.  Symptom: texels at exact coordinates are correct but
LINEAR filtering is wrong (a 2x2 red/green/blue/white texture sampled at its
centre returns pure WHITE -- one texel -- instead of the average).

**Rule: declare `layout(binding = 0) uniform sampler2D tex;` and build the
descriptor set layout with `VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER`, writing
both the image view and the sampler in one `VkDescriptorImageInfo`.**  That is
also what D3D12's SRV + static sampler really is, so it is not a workaround --
it is the honest mapping.

## D3D12 depthClipEnable is Vulkan depthClampEnable

Same word, different name and slightly different meaning.  `depthClipEnable = FALSE`
(D3D12) maps to `depthClampEnable = VK_FALSE` (Vulkan): geometry outside the
depth range is CLAMPED rather than clipped.  Passing D3D12's value through as
"clip" compiles and behaves differently.

## What actually shipped (the build order that worked)

Each slice is pure C11 and unit-tested BEFORE it touches a device.  The live
targets are thin glue over already-validated logic, which is why the first real
submission worked instead of needing a debug session.

1. resource states + barriers (all THREE: transition, UAV, aliasing)
2. descriptor heaps  3. command allocators/lists  4. PSOs
5. feature-level device  6. fences (timeline semaphores)  7. swapchain/present
8. physical-device selection  9. logical device  10. render pass
11. framebuffer/image views  12. memory types  13. root signature -> pipeline layout
14. sample descriptions (MSAA)  15. shader pre-cache

Live targets, in dependency order: enumerate -> device -> allocate -> clear ->
pipeline+draw -> readback -> push constant + CBV -> texture/SRV -> UAV/compute
-> 4x MSAA + resolve -> swapchain + present.

**The method: write the test that would embarrass you, then fix what it finds.**
Of ~15 slices, essentially none were right on the first write.  The bugs were
version bases (D3D12 comparison funcs are 1-based, Vulkan's are 0-based), field
widths (a both-endian UINT16 read as a u32), alignment (D-Bus, Vulkan
swapchain), lifetime rules (a descriptor pool must outlive its sets), unit
factors (milli-tokens refill per MILLISECOND), allocator semantics (a monotonic
counter is not an allocator), and the checkers' own false positives.  A test
that restates the implementation passes; a test asserting the BEHAVIOUR YOU
CLAIMED is what finds them.

**Three driver bugs found on the RTX 5050 / Intel RPL-S box:**
- The NVIDIA ICD SEGFAULTS in `vkGetPhysicalDeviceSurfaceSupportKHR` for a
  headless surface -- the process dies with NO output at all, before its first
  `printf` flushes.  The Intel iGPU answers the same query with `present=1`.
  A PRESENT path must therefore pick a device whose queue family can present,
  which is a different primary filter from the render tests (those prefer the
  discrete GPU).  Query present support per device and per family, prefer an
  integrated GPU, and fall back to a discrete one only when nothing else
  exists.  Do not blindly take the fastest device for a present path.
- `VK_KHR_swapchain` is a DEVICE extension; `VK_KHR_surface` and
  `VK_EXT_headless_surface` are INSTANCE extensions.  Enable BOTH sides or the
  pair half-works: without `VK_KHR_swapchain` on the device the loader returns
  `VK_SUCCESS` from a NULL function pointer for `vkCreateSwapchainKHR`, so the
  failure appears later and somewhere else entirely.
- An extension function that is not in the loader's export table MUST be
  fetched with `vkGetInstanceProcAddr`.  Calling `vkCreateHeadlessSurfaceEXT`
  directly links (the symbol resolves through the ICD) and then jumps to an
  unresolved address, crashing INSIDE `libnvidia-glcore` with no diagnostic.
  Symptom: a segfault whose backtrace is only driver frames and never your
  code.  Load every `*EXT`/`*KHR` entry point you call.

## Build order (each slice is independently testable)

1. Resource-state translation (state -> stage/access/layout, barriers,
   per-resource tracker).
2. Descriptor heaps (heap model, handle arithmetic, copy rules, pool sizing).
3. Command allocators and lists (the state machine + the Vulkan pool flags).
4. Pipeline state objects (the exact-match key + cache).
5. The feature-level device, then the swapchain/present path.
6. Physical device selection, then the logical device (the first slices that
   need a real `VkDevice`).
7. Memory types / heaps, then render pass and framebuffer.
8. Live paths: real images, a real render pass, a real clear.

Slices 1-4 (and the pure halves of 5-7) need no device. Do not start a device
slice before the pure slices it depends on have green tests -- the device slice
is where a wrong mapping from any earlier slice becomes untraceable.

**The ordering principle: prove the mapping in pure C11 FIRST, then wire it to
a device as thin glue.** Every slice that opens no device has its correctness
provable on any host, and in practice every bug in this class was caught by a
test rather than by a crash -- the first real GPU submission worked because it
was glue over validated logic, not because it was debugged. Keep that property:
a slice that needs a GPU should be a thin wrapper around a pure core.

**Live/device-requiring tests are SEPARATE targets, never in the gate.** A suite
that needs a Vulkan loader or a GPU reds on every machine without one, and the
gate must stay runnable anywhere. Put it in its own `test_*_live` target, link
`-lvulkan`, and note in the recipe that it is not in any tier.

**The readback recipe is in `references/live-gpu-verification.md`.** A green
`vkQueueWaitIdle` proves the command stream was LEGAL, not that the pipeline
drew the right thing. The recipe covers the transition -> copy -> barrier ->
map sequence, how to choose sample points that isolate the property under test
(texel-exact proves the upload, an AVERAGE proves filtering, outside proves
the clear), the NDC->framebuffer transform with Vulkan's y pointing down, and
the strongest form of all: change the bound input and observe the output
change.

## Pitfalls

- **State structs must use plain integer fields, not bitfields.** The key is a
  hash of a serialised blob; bitfield padding is unspecified, so two identical
  descs could hash differently and a pipeline would miss its own cache.
  Serialise explicitly (little-endian byte writes), never `memcpy` the struct.
- **Cache capacity must REJECT, never evict silently.** A silently evicted
  pipeline is a frame-time stall with no diagnostic. Report the full cache.
- **Double-release of a pipeline is an app bug, not a no-op.** Returning 0 for
  an unknown handle hides the bug; returning -1 makes it visible.
- **A rejected copy/transition must leave the destination UNCHANGED.** Check
  every bound BEFORE the copy, so a failure cannot half-apply.
- **Overlapping copies within one heap are legal** (memmove semantics), and a
  cross-type or mismatched-stride copy is forbidden -- D3D12 refuses both, and
  a mismatched descriptor size reinterprets records at the wrong stride.
- **Naming a Vulkan enum that does not exist is the common first error**
  (`VK_COMPARE_OP_LESS_OR_EQUAL` not `LESS_EQUAL`; `PATCH_LIST` not `LIST`).
  Compile the mapping TU first; the compiler is the cheapest oracle here.
- **A reference/study doc's feature-to-module map is a HYPOTHESIS.** Verify each
  named module exists in the tree before reporting it as grafted or missing;
  feature names get written down long before the files do.
- **A `VkSurfaceKHR` is not presentable by default, and not every queue family
  presents.** The render tests' "prefer the discrete GPU" rule is WRONG for a
  present path: present support is a property of a (device, queue family) pair,
  not of a device, and querying a family that cannot present can crash the
  driver outright rather than return false.  Query present support for every
  candidate family and select on the answer; never infer it from the device
  type.
- **A crash with no output at all is a crash before the first flushed write.**
  Run the binary under `stdbuf -o0` (and/or `gdb -batch -ex run -ex bt`) to see
  how far it actually got; a buffered stdout that dies with SIGSEGV reports
  nothing, which reads like an early failure rather than a late one.
- **When a test crashes and the code looks right, bisect with a minimal
  standalone program.** A 30-line C file that creates the instance, the surface
  and calls the one function isolates "my test is wrong" from "the driver is
  wrong" in a single run, and it is the only way to tell a driver crash from a
  bug in the test's own setup.  Confirmed this way: a headless surface works
  end-to-end on the iGPU, and the same call crashes only on the NVIDIA device.
