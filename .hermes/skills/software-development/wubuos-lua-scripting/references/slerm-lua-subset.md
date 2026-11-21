# Wua / slerm-Lua: language surface, host API, known gaps

Depth note for embedding slerm-Lua in a C11 host. Load when writing a host,
debugging a script that "does nothing", or deciding whether a construct is
supported.

## Where it lives

slerm-Lua was rewritten to the full Lua 5.4 surface and moved to its own
repository, **Wua**. WWW pulls it in as a NESTED submodule, so the path is:

```
src/lua/www/~WuBu~/src/lv/src/wb_lv.h            public API
src/lua/www/~WuBu~/src/lv/src/wb_lv_arena.c      allocator
src/lua/www/~WuBu~/src/lv/src/wb_lv_coro.c       coroutines (builds on non-Windows as of bf39a26)
src/lua/www/~WuBu~/src/lv/src/wb_lv_eval.c       evaluator + tables + globals
src/lua/www/~WuBu~/src/lv/src/wb_lv_host.c       state, register_global, call, builtins, openlibs
src/lua/www/~WuBu~/src/lv/src/wb_lv_lex.c        lexer
src/lua/www/~WuBu~/src/lv/src/wb_lv_parse.c      parser
src/lua/www/~WuBu~/src/lv/src/wb_lv_stdlib.c     base + table + math + os + io registration
src/lua/www/~WuBu~/src/lv/src/wb_lv_string.c     string library + Lua-pattern matcher
src/lua/www/~WuBu~/src/lv/src/wb_lv_value.c      values, interning, equality
```

Build against it with `LUAWWW := $(LUA)/www/~WuBu~/src/lv/src` (set in
`mk/tests.mk`) and link **all** of the `.c` files above -- `wb_lv_openlibs`
lives in `wb_lv_host.c` and calls registration functions defined in
`wb_lv_stdlib.c` / `wb_lv_string.c`, so omitting those two is a link error.

## Supported surface (Lua 5.4)

Values: `nil`, `bool`, **integer and float** (5.3+ numeric model), `string`,
`table`, `function`, C function.

Statements: `local`, assignment, `if`/`elseif`/`else`, `while`, numeric and
generic `for` (`ipairs`/`pairs`), `do`/`end`, `break`, `repeat`/`until`,
`goto` + labels, `function` declarations (incl. `function t.f()` and
`function t:f()`), `return`.

Expressions: full operator set `# ^ // & | ~ << >> + - * / % ..`, comparisons,
`and`/`or`/`not`, table literals, `t[k]`/`t.k`, method calls, varargs, multiple
returns, metamethods (`__index`/`__newindex`/`__add` family, `__eq`/`__lt`/
`__le`/`__concat`/`__call`/`__tostring`/`__len`).

Literals: decimal, **hex**, string escapes, long strings `[[ ]]` and long
comments `--[[ ]]`.

Error handling: `pcall`/`xpcall` with real unwinding; runtime errors carry a
**line number**, e.g. `attempt to index a nil value (line 2)`.

Libraries (`wb_lv_openlibs`): base, string (with a Lua-pattern matcher),
table, math, os, io.

A construct outside the surface is still a **parse error**, reported by
`wb_lv_run()` as a string -- not a runtime error. When a binding appears to do
nothing, run the script alone through `wb_lv_run` first; if it parses, the
problem is in the host.

## Host API (wb_lv.h)

```c
wb_lv *wb_lv_new(void);          /* state + ALL libraries (alloc + openlibs) */
wb_lv *wb_lv_alloc(void);        /* state only, nothing registered */
void   wb_lv_free(wb_lv *L);

const char *wb_lv_run(wb_lv *L, const char *src, const char *chunkname);
              /* NULL on success, error text on failure */

void   wb_lv_register_global(wb_lv *L, const char *name, wb_lv_cfn fn, void *ud);
wb_lv_value wb_lv_get_global(wb_lv *L, const char *name);
void   wb_lv_set_global(wb_lv *L, const char *name, wb_lv_value v);
wb_lv_value wb_lv_call(wb_lv *L, wb_lv_value fn, wb_lv_value *args, int nargs);
int    wb_lv_pcall(wb_lv *L, wb_lv_value fn, wb_lv_value *args, int nargs,
                   wb_lv_value *out, int *nout);
              /* 0 = ok (out/nout hold the returns); 1 = raised.
                 On error nout is 0 and out[] is NOT written: the message is
                 stashed in the global __lv_last_error. */
int    wb_lv_call_multi(wb_lv *L, wb_lv_value fn, wb_lv_value *args, int nargs,
                        wb_lv_value **out);
              /* returns the result COUNT and sets *out to the result array
                 (NULL if the call raised) -- every result, not just the first */

wb_lv_table *wb_lv_table_new(wb_lv *L, int narr, int nrec);
void         wb_lv_table_set(wb_lv *L, wb_lv_table *t, wb_lv_value k, wb_lv_value v);
wb_lv_value  wb_lv_table_get(wb_lv *L, const wb_lv_table *t, wb_lv_value k);
size_t       wb_lv_table_len(const wb_lv_table *t);

wb_lv_table *wb_lv_getmetatable(wb_lv *L, wb_lv_value v);
void         wb_lv_setmetatable(wb_lv *L, wb_lv_table *t, wb_lv_table *meta);
              /* takes a table POINTER, not a value */
int          wb_lv_has_meta(wb_lv *L, wb_lv_value v, const char *event);

const char *wb_lv_intern(wb_lv *L, const char *bytes, size_t len);
double      wb_lv_tonumber(wb_lv_value v, int *ok);   /* BY VALUE */
int64_t     wb_lv_tointeger(wb_lv_value v, int *ok); /* BY VALUE */
const char *wb_lv_tostring(wb_lv_value v);           /* BY VALUE, shared buffer */
const char *wb_lv_tostring_intern(wb_lv *L, wb_lv_value v);
int         wb_lv_truthy(wb_lv_value v);
int         wb_lv_equal(wb_lv *L, wb_lv_value a, wb_lv_value b);  /* takes L */
int         wb_lv_rawequal(wb_lv_value a, wb_lv_value b);

void wb_lv_register_builtins(wb_lv *L);   /* base library (now in the header) */
void wb_lv_openlibs(wb_lv *L);            /* base + string + table + math + io */
const char *wb_lv_version(void);
```

Value constructors: `wb_lv_nil()`, `wb_lv_bool(b)`, `wb_lv_number(n)`,
`wb_lv_str(s)`. To wrap a C function or a table you must build the value by
hand:

```c
wb_lv_value fv = wb_lv_nil();
fv.t = WB_LV_CFUNCTION; fv.as.cf.f = my_fn; fv.as.cf.ud = my_ctx;

wb_lv_value tv = wb_lv_nil();
tv.t = WB_LV_TABLE; tv.as.tab = my_table;
```

## Gaps (upstream, in Wua)

Report these to the Wua owner; work around them in host code and test scripts.

**Status 2026-11-09 (Wua bf39a26).** Fixed and verified since cf995cb:
`wb_lv_coro.c` now builds on non-Windows hosts, the table constructor no
longer drops the array part when a keyed field comes first, and
`__lv_last_error` carries the caught message. Also new: `wb_lv_call_multi`
returns every result (see the API block).

Still open:

1. **`string.gsub` with a table replacement drops unmatched characters.** The
   string and function paths are correct; the table path emits only the
   replacements.
   ```lua
   string.gsub('abc','%a',{a='X'})     --> "X"   (want "Xbc")
   string.gsub('abc','%a',{a='X',b='Y'}) --> "XY" (want "XYc")
   string.gsub('abc','%a',{})          --> ""    (want "abc")
   string.gsub('aXb','%a',{a='Z'})     --> "Z"   (want "ZXb")
   string.gsub('ab','(%a)',{a='X'})    --> "X"   (want "Xb")
   ```
2. **Table keys are hashed by string identity**, so a key must be interned
   via `wb_lv_intern` to match a script literal. `wb_lv_equal` compares strings
   by content, but the table lookup never reaches it for an uninterned key.
   This is a design constraint of the interpreter, not a defect -- intern every
   key you set from a host.

Retired (were open at cf995cb, fixed in bf39a26):

- ~~`wb_lv_coro.c` does not compile on non-Windows hosts.~~ FIXED. Link the real
  file; the old weak `wb_lv_register_coro` shim is gone.
- ~~A table literal with a hash-part key before its array items loses the
  array part.~~ FIXED. `{spacing=6, 'a','b','c'}` has length 3; numeric
  children in a literal are reliable again.
- ~~`wb_lv_pcall` stashes an EMPTY `__lv_last_error`.~~ FIXED. The C-API path
  now carries the message; a host may report the text.

Two expectations that look like bugs and are not:

- `print(4/2)` -> `2.0`, not `2`. Lua 5.4 `/` always yields a float.
- `string.gsub('aaa','a','b',2)` -> `bba, 2`: the count limits replacements
  from the left, so the FIRST two change.

## Debugging recipe

A binding that reads as nil in a script:

1. Confirm the table exists: `wb_lv_get_global(L, "gui").t == WB_LV_TABLE`.
2. Confirm the field exists on the table:
   `wb_lv_table_get(L, t, wb_lv_str("text")).t == WB_LV_CFUNCTION`.
   If it is `WB_LV_NIL`, the key was not interned (gap 7).
3. Confirm the script parsed: `wb_lv_run` returned NULL. A parse error looks
   exactly like a missing binding.
4. Confirm the host called the hook: check `fn.t` before `wb_lv_call`.
5. Confirm the library was opened. `wb_lv_new()` already opens everything;
   only `wb_lv_alloc()` leaves the state bare.
6. Confirm the host interned the key: `wb_lv_table_get(L, t,
   wb_lv_str(wb_lv_intern(L, "text", 4)))` matches; a plain `wb_lv_str("text")`
   does not.
7. If you are reading a host-side global in a TEST, remember
   `wb_lv_get_global` is flat: `"wet.clicks"` is not a field lookup. Get the
   table, then index it.
