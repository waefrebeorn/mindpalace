# `spirv mem[0]=0` is NOT a bug -- Vulkan is out-of-process

`vulkan_run()` shells out to /tmp/vk_run. It uploads the caller's memory to an
image file, dispatches on the GPU, and returns only the RESULT value. The
caller's buffer is never written back, so `mem[0]` stays at whatever it was
(calloc -> 0).

Do not "fix" this. Verified correct on the GPU side with WUBU_VK_DUMP:

    program (7+9)*56 - 4:  cell[0]=892  cell[1]=7  cell[2]=9  cell[3]=56  cell[4]=4
    program (7+9)*3:        cell[0]=48   cell[1]=7  cell[2]=9

The memory image is exactly right: result in cell 0, inputs preserved in
cells 1..4. `spirv result=892 mem[0]=0` means SUCCESS, not data loss.

## The one real bug in this area was the runner itself

The original untracked /tmp/vk_run computed 892 correctly but printed 0 to
stdout, and wubu_isa_vulkan.c parsed stdout as the result. Reconstructed
tools/vk_run.c (committed, built by `make vk_run`) prints the real value.

## Comparing a memory-using program across backends

x86-64 and PTX run in-process, so their `mem[0]` IS written back. For Vulkan,
read the GPU-side state instead:

    WUBU_VK_DUMP=8 /tmp/memprobe spirv 2>&1 | grep 'cell\['

Compare RESULT values across all three (they must agree); only compare
`mem[]` for the in-process backends.