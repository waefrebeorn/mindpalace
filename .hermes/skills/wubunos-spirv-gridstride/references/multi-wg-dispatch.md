# Multi-WG dispatch reference

## Kernel constants to bake

```c
/* In wubu_isa_spirv.c -> emit_tgemm_spirv() */
unsigned gx = 1;
{ const char *ge = getenv("WUBU_VK_GROUPS"); if (ge) gx=(unsigned)atoi(ge); if (gx<1) gx=1; }
uint32_t total_lanes = gx * 64;
uint32_t cSTRIDE = spirv_find_const(cmts, ncm, total_lanes);
uint32_t cPASS = spirv_find_const(cmts, ncm, (M*Nn + total_lanes - 1)/total_lanes);
```

## Pass loop stride change

```c
/* Line ~217: pass*stride instead of pass*64 */
{ uint32_t o[]={s->t_u64,p64,w,cSTRIDE}; spv_ins(&s->bin,OPCODE_IMUL,o,4);}
```

## Buffer sizing (wubu_isa_vulkan.c -> vulkan_compile())

```c
g_cells = (uint32_t)((p->total_mem > 0 ? p->total_mem : 1) + 1 + (has_tg?gx*64*4+1:0));
// NOT: 64*4+1 (single-WG only)
```

## Return slot race

When gx>1, all lanes write to cell 0 at merge block. Fix:
- Option A: Guard with `if (wg_id==0 && lane_id==0)` via structured-if
- Option B: Read result from last C cell (total_mem) instead of cell 0

Option A requires:
```c
/* Before the return-store block */
OpIEqual %is_zero %id_gid %zero_u64
OpSelectionMerge %merge %control
OpBranchConditional %is_zero %then %merge
%then = OpLabel
... store to cell 0 ...
OpBranch %merge
%merge = OpLabel
```

NOTES:
- %id_gid = GlobalInvocationId.x (u64)
- %zero_u64 must be a u64 zero constant (use s->c_zero64)
- OpIEqual = opcode 59