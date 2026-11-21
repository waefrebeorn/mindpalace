# Float Test Fix (2026-09-01)

## Problem

Float arithmetic tests were failing because the MIR generator and JIT backend were using f64 semantics for float operations, while the interpreter expected f32 semantics.

Example:
```c
float a=1.5; float b=2.5; a+b;
```
Expected (f32 bits): 1082130432 (0x40800000 = 4.0f)
Got (f64 bits): Different bit pattern

## Root Cause

1. **Float literals**: Stored as 64-bit double bits in the MIR
2. **Arithmetic ops**: Used `MIR_DADD`, `MIR_DSUB`, `MIR_DMUL`, `MIR_DDIV` (f64) instead of f32 ops
3. **float-to-int cast**: Used `MIR_DTOI` instead of `MIR_FTOI`
4. **int-to-float cast**: Used `MIR_DITOF` instead of `MIR_ITOF`

## Fix

### 1. Float literal storage (holyd_mir_eval.c)

Changed from:
```c
union { double d; uint64_t u; } u;
u.d = n->float_val;
wubu_mir_const(g->prog, u.u);  // stores 64-bit bits
```

Changed to:
```c
union { float f; uint32_t u; } u;
u.f = (float)n->float_val;
wubu_mir_const(g->prog, (int64_t)u.u);  // store f32 bits in 64-bit VR
```

### 2. Float arithmetic opcodes (holyd_mir_eval.c)

In `HD_AST_ADD`, `HD_AST_SUB`, `HD_AST_MUL`, `HD_AST_DIV` handlers:

Changed from:
```c
if (is_float) r = wubu_mir_binop(g->prog, MIR_DADD, ...);
```

Changed to:
```c
if (is_float) r = wubu_mir_binop(g->prog, MIR_FADD, ...);
```

### 3. Float negation (holyd_mir_eval.c)

Changed `MIR_DNEG` to `MIR_FNEG` using `mir_is_float_node()` helper.

### 4. Casts (holyd_mir_eval.c HD_AST_CAST handler)

Changed from `MIR_DTOI`/`MIR_DITOF` to `MIR_FTOI`/`MIR_ITOF` when source is float.

### 5. x86-64 JIT backend (wubu_isa_x86_64.c)

For `MIR_FTOI` operation:
```c
case MIR_FTOI:
    // cvttss2si converts f32->i32 and truncates
    // But result is in eax, need to sign-extend to rax
    emit_byte(0x48);  // REX.W prefix
    emit_byte(0x98);  // cdqe: sign-extend eax to rax
```

## Test Expectations

Float operations return raw IEEE-754 bits, not the float value:

| Expression | Expected (f32 bits) | Decimal |
|------------|---------------------|---------|
| 1.5 | 1065353216 | 0x3FC00000 |
| 2.5 | 1069547520 | 0x3FE00000 |
| 1.5+2.5=4.0 | 1082130432 | 0x40800000 |

## Verification

```sh
make test_mir_battery
# All 69 tests should PASS

./gauntlet_runner --dump-asm x86-64 "1.5+2.5"
# result=1082130432
```