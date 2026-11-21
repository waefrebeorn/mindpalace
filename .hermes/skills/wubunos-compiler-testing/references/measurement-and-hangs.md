# Honest measurement and hang localisation

## The gauntlet number is a band, not a point

Six runs of the SAME binary (semantic pass toggled only at runtime) produced
1519, 1523, 1548, 1551, 1559, 1561, 1581 valid passes — a **~62-pass band**. Six
workers compete, and under load a test moves between PASS and ERROR without any
code change.

Rules:

1. Never compare two configurations by single runs. Run each side 3+ times on an
   otherwise idle machine and compare **medians** against the observed band.
2. `tools/gauntlet_noise.sh [runs] [binary]` does this and prints min/median/max
   plus the band. Any claimed improvement must exceed the band.
3. Quote the range (e.g. "1519–1581, median ~1559"), never one number as "the"
   score. `valid_pass_rate` alone hides whether tests moved between fail and
   error.
4. Make a feature runtime-switchable (env var) so both sides come from one
   build — switching source and rebuilding adds a second variable.
5. `make test_*` exits nonzero when the battery reports its known deferred case,
   so `make` failure is not a build failure; read the log before believing it.

## Localising a parser/lexer hang

Order matters — each step eliminates a layer before the next:

1. **Reproduce from the harness's own text**, not a hand-typed approximation:
   extract the test source byte-for-byte from the suite array and feed it to
   `tools/compile_diag` under `timeout`.
2. **Separate lexer from parser.** A 30-line lexer-only probe (loop `hd_lex_next`
   to EOF with an iteration cap) proves whether the lexer terminates. If the
   lexer reaches EOF cleanly, the hang is in the parser.
3. **Distinguish recursion from a loop**: rerun with `ulimit -s 256`. Unbounded
   recursion segfaults fast; a non-advancing loop keeps timing out.
4. **Count `peek()` calls** and abort after ~20M, printing pos, token value, token
   text and `__builtin_return_address(0)`. Build with `-O0 -g -no-pie` and resolve
   the address with `addr2line -f -e <binary> <addr>` — that names the frame
   instead of guessing which loop spins.
5. **Map token values numerically**, not by enum line number: print
   `(int)HD_TOK_RBRACE` etc. from a 5-line program. Enum line numbers and values
   differ as soon as the enum has gaps or comments.
6. Guards worth keeping permanently: `advance()` forces `HD_TOK_EOF` when the
   lexer position does not move, and the compilation-unit loop reports and
   advances when a declaration returns a node consuming nothing. A guard that
   does NOT fire is itself a diagnostic — it exonerates that layer.

Write the ruled-out list into a doc in the repo (`docs/PARSER-HANG.md`) so the
next session does not restart the bisection.
