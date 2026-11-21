# Float Literal Parsing in HolyD Lexer

## Forms Supported

HolyD recognizes these float literal forms:

| Form | Example | Notes |
|------|---------|-------|
| Standard | `1.0`, `3.14` | Digits, dot, digits |
| Trailing dot | `1.`, `2.` | Digits followed by dot (no trailing digits) |
| Leading dot | `.5`, `.125` | Dot followed by digits — requires special handling |
| Exponent | `1e10`, `2.5E-3` | Standard exponent notation |
| Integer exponent | `1E0`, `2e+3` | No decimal point — parsed as integer then converted to float |
| Leading dot + exponent | `.01e+2`, `.5E-3` | Combined form |
| Suffixes | `1.5f`, `2.0L` | f/F (float), l/L (long double) |

## Lexer Implementation

### The Dot Dispatch Problem

The main lexer loop (`hd_lex_next`) calls `hd_advance(lex)` BEFORE the `switch (c)`:

```c
char c = hd_advance(lex);  // consumes the character
switch (c) {
    case '.':  // lex->pos now points to the NEXT character
```

This means by the time `case '.'` is reached, the dot is ALREADY consumed and
`lex->pos` points to the first digit after the dot.

### Leading Dot Floats (.5, .01e+2)

In `case '.'`, check if the next character is a digit:

```c
case '.': {
    if (lex->src[lex->pos] == '.' && lex->src[lex->pos + 1] == '.') {
        lex->pos += 2;
        return hd_make_token(lex, HD_TOK_ELLIPSIS);
    }
    if (isdigit((unsigned char)lex->src[lex->pos])) {
        // Parse float inline — dot already consumed
        return parse_float_leading_dot(lex);
    }
    return hd_make_token(lex, HD_TOK_DOT);
}
```

**CRITICAL**: Do NOT call `hd_scan_number` from the `.` case — it expects to start
at a digit but the dot is already gone. The `hd_scan_number` function's first
check `hd_peek(lex) == '0'` will see the first digit (not the dot), and the
function will miss the leading dot entirely, producing wrong values.

Instead, parse inline: prepend '.' to buf, consume digits, handle exponent.

### Integer Exponent Floats (1E0, 2e+3)

After parsing an integer and its suffixes (L, U, LL, etc.), check for `e`/`E`:

```c
// After integer suffix scanning
if (!hd_is_at_end(lex)) {
    char c = hd_peek(lex);
    if (c == 'e' || c == 'E') {
        // Consume exponent and convert to float
        buf[i++] = hd_advance(lex);  // e/E
        if (hd_peek(lex) == '+' || hd_peek(lex) == '-')
            buf[i++] = hd_advance(lex);
        while (isdigit(hd_peek(lex)))
            buf[i++] = hd_advance(lex);
        buf[i] = '\0';
        lex->tok.float_val = strtod(buf, NULL);
        return hd_make_token(lex, HD_TOK_FLOAT);
    }
}
```

Without this, `1E0` is parsed as integer `1` followed by identifier `E0`.

**Implementation note (2026-09-21)**: The exponent check is in `hd_scan_number`, AFTER the `is_float` block and AFTER integer suffix scanning. The `is_float` flag is only set when a `.` is encountered, so the exponent check must be OUTSIDE the `if (is_float)` block — it should run for both float-with-dot and integer-with-exponent cases. The check scans `e`/`E`, optional sign, digits, then calls `strtod(buf, NULL)` and returns `HD_TOK_FLOAT`.

## Storage

Float literals are stored as 64-bit double bits:

```c
case HD_AST_FLOAT_LIT: {
    union { double d; uint64_t u; } u;
    u.d = n->float_val;
    return wubu_mir_const(g->prog, (int64_t)u.u);
}
```

## Pitfalls

1. **Dot already consumed**: The main lexer loop consumes the dot before `case '.'` runs.
   Always check `lex->src[lex->pos]` for the first digit, never `lex->src[lex->pos + 1]`.

2. **Don't delegate to hd_scan_number**: `hd_scan_number` expects to start at a digit.
   The dot is already consumed, so it would miss the leading dot. Parse inline.

3. **Exponent after integer suffixes**: The exponent check must come AFTER the L/U/LL
   suffix scanning. Otherwise `1ULL` would be misinterpreted as having an exponent.

4. **strtod handles all forms**: `strtod("1")` = 1.0, `strtod(".5")` = 0.5,
   `strtod("1e10")` = 10000000000.0, `strtod("125.E-3")` = 0.125. All forms work.
