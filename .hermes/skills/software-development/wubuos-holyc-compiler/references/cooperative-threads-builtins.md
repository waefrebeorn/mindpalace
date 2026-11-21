# C11 threads as cooperative builtins (thrd_create / thrd_join / thrd_detach)

Expanded at compile time in a single-threaded-codegen (cooperative) model.
Builds on the cross-function func-ptr param propagation in SKILL.md -- the
callee identity is a compile-time constant at each `thrd_create` site.

## thrd_create(&t, fn, arg)
1. Resolve `fn` (arg 1, a bare function IDENT) to a `func_id`.
2. Allocate a memory cell (`prog->total_mem`) holding `arg` (arg 2); store arg there.
3. Map the handle VARIABLE name -> thread-id: arg 0 is `&t` = an ADDR node whose
   `child->ident` is the var name. Record `handle_name[i] -> tid`.
4. Write the tid into `*t`, return 0 (thrd_success).

## thrd_join(t, &res)
- Resolve the handle's tid AT COMPILE TIME when `t` is a known handle var (arg 0
  is a bare IDENT, NOT `&t` -- join reads the value, create takes its address).
  Then emit a DIRECT call: load stored arg from the cell -> `mov_to(prog,1,arg)`
  -> `wubu_mir_call(prog, func_id)` -> capture return -> store into `*res`.
- Fallback (handle not a known var): runtime `tid==i` dispatch -- for each
  created thread, `cond=EQ(tid_vr,i)`, `jz(cond,end)`, call, `place_label(end)`.

## Pitfalls (each cost a debug cycle)
- **Resolve the handle->tid at compile time.** A runtime-dispatch-only
  `thrd_join` mis-dispatches multi-thread joins (two threads returned the wrong
  function's result). The handle-name->tid map is what makes `join(t1)`/`join(t2)`
  each call the right function.
- **Read the callee return from vr0 correctly**: `rv = mir_new_vr(g);
  wubu_mir_mov_to(prog, rv, 0);`. Do NOT use `wubu_mir_load(const(0))` -- vr0 is
  a register, not a memory address; loading address 0 silently returns 0.
- **Clear func_id state per param**: when seeding `fn_ptr_func_id` from the map,
  set it to -1 for params with no map entry, or a stale func_id from another
  function's same-named variable leaks in and the wrong function gets called.
- The correct branch helpers are `wubu_mir_jz(prog, cond_vr, label)` (jump if
  zero) and `wubu_mir_place_label(prog, label)` -- there is no `wubu_mir_jcc` /
  `wubu_mir_label`. AST branch fields are `then_branch`/`else_branch`, not
  `then_br`/`else_br`.

## Verify
`./gauntlet_runner --dump-asm x86-64 '<src>'` -> `result=<N>`. Single join=42,
two threads (w1=11,w2=99) sum=110, arg-deref=7. Gate: `--core x86-64` stays
247/247 (the call path is hot -- always re-run the core gate after touching it).
