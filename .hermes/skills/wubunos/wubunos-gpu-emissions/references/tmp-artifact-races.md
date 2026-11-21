# /tmp artifact races: the rule and how to prove the fix

## The rule

Any file a compiler backend writes for a LATER process to read must be
uniquely named per process, and per module if the content varies. A fixed
path in compiler/runtime code is a concurrency bug even when nothing is
supposed to run concurrently -- `make test` runs suites in parallel and
probes get launched by hand.

Do NOT use a `static int cached` flag to guard a global path. A function-local
cache cannot protect a global filename from another process. (That was the
original PTX defect.)

## Confirmed instances

  b5f7c0a  wubu_isa_ptx.c        /tmp/wubu_kernel.cubin + per-process `last_hash`
  3ef6ab1  wubu_isa_vulkan.c    /tmp/wubu_kernel.spv
  61fdd02  wubu_isa_ptx_tgemm.c  /tmp/wubu_tgemm.{cubin,ptx} and a shared
                                 /tmp/ptxas_tgemm.log

`wubu_tgemm_gemm.c` and `wubu_isa_amdgpu.c` still use fixed paths, but nothing
references those files outside themselves, so they are not currently reachable.

## A/B proof recipe -- do not skip this

Write a probe that compiles and runs a PROGRAM DERIVED FROM AN ARGUMENT:

    /* (a + 2) * 56 */
    wubu_mir_ret(p, wubu_mir_binop(p, MIR_MUL,
               wubu_mir_binop(p, MIR_ADD, va, wubu_mir_const(p, 2)),
               wubu_mir_const(p, 56)));

Launch two processes at once with different `a`, each checking its own answer.

    for i in 1 2 3 4; do
      (/tmp/vkconc 7 504 &); (/tmp/vkconc 11 728 &)
    done; wait

Before the fix (fixed path):

    pid=915709 a=11 got=504 want=728 MISMATCH
    pid=915710 a=11 got=504 want=728 MISMATCH
    pid=915712 a=11 got=504 want=728 MISMATCH

After (per-pid + per-module path): 6/6 OK.

The MISMATCH lines are the entire proof. A sequential run passes either way,
so a serial test can NEVER catch this -- it has to be concurrent.

## Related trap

`run(code, size, memory_pointer)`: `popen()` runs a shell, so it SUCCEEDS even
when the executable is missing. Only the absence of a numeric stdout line
reveals the failure. Treat a failed `fscanf` as -1, never as result 0.