# Proving GPU work: the readback recipe

"The GPU accepted the draw" is NOT "the GPU drew the right thing".
`vkQueueWaitIdle` returning `VK_SUCCESS` proves the command stream was legal,
not that the pipeline produced the intended pixels. The only proof is to read
the rendered result back and assert on it.

Use this recipe for any live GPU target in this class.

## The sequence

1. **Render** into the attachment as usual (clear + draw, or dispatch + copy).
2. **Transition** the attachment to `VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL` with
   an image memory barrier. Take the access masks from the slice-1 state map
   (`D3D12_RESOURCE_STATE_RENDER_TARGET` -> `COPY_SOURCE`) rather than
   hardcoding them, so the barrier is itself an exercise of the mapping.
3. **Copy** to a host-visible buffer (`VK_BUFFER_USAGE_TRANSFER_DST_BIT`, memory
   type from the `READBACK` heap mapping -- host-visible, cached preferred).
   Set `bufferRowLength` / `bufferImageHeight` to the image extent or the rows
   will be packed at the buffer's stride.
4. **Barrier** `TRANSFER_WRITE` -> `HOST_READ` so the CPU sees the writes.
5. **Map, assert, unmap.**

## Choosing the sample points is the whole test

Pick points that ISOLATE the thing you are proving -- a single point that
happens to be right proves nothing.

- **A texel-exact point proves the upload and the binding.** Sample where the UV
  lands exactly on a texel centre: `uv = (i + 0.5) / size`.
- **A point that is an AVERAGE proves filtering.** Sample the centre of a 2x2
  texture with `LINEAR` filtering: the expected value is the mean of all four
  texels. With `NEAREST` you get one texel instead -- which is exactly the
  symptom of a sampler mismatch (see the combined-sampler trap above).
- **A point OUTSIDE the drawn geometry proves the clear and the extent.**

## NDC -> framebuffer coordinates

Vulkan's framebuffer y points DOWN, so the transform is:

```
x_px = (ndc_x + 1) / 2 * W
y_px = (1 - ndc_y) / 2 * H      // note the 1 - , not ndc_y + 1
```

For a hardcoded triangle with vertices in NDC, compute the CENTROID and sample
there for the "inside" point; the centroid is `sum(vertices) / 3`.

## Keep the request conservative

The first live run of a pipeline should use the most conservative request
possible -- one queue, no extensions, no features, one graphics queue. Then a
failure means the device genuinely could not be opened, not that the request
was malformed. Add capability knobs only after the base path is proven.

## Verify by CHANGING the input

The strongest form: prove the bound value ARRIVED by changing it and observing
the output change.

- push constant `scale = 1.0` then `0.5`, same draw, read back both: if the
  pixel is exactly `base` then exactly `base/2`, both the constant and the
  shader's use of it are proven.
- CBV colour A then colour B: same reasoning.

A readback that matches a hardcoded expectation proves the whole chain; a
readback that tracks a CHANGED input proves the binding specifically.

## Reporting

Print the sampled pixels and their expected values. A live target that prints
`inside (960,603) = 64 166 255` next to the expected `(64,166,255)` is
evidence a human can read without re-running it; `ALL ... TESTS PASSED` alone
is not.
