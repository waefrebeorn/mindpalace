# Stale build artifacts will silently invalidate a whole debug cycle

## The trap

A one-command gcc of N sources into /tmp/probe is not incremental, so you
assume each build picks up your edit. It does — UNLESS the build FAILED. Then
the old binary stays, keeps running, and every measurement you take describes
code that no longer exists.

I lost several iterations this way: a heredoc turned `\n` in a C string literal
into a real newline, the compile failed, and the old /tmp binary kept
producing plausible output. It looked like my fix "didn't work" when in fact
nothing had been rebuilt.

## The rule

After EVERY rebuild, assert BOTH:

    errors == 0                    # the build actually succeeded
    binary_mtime > source_mtime    # the binary is newer than the source you edited

Do not chain the build with output redirection without checking. Do not treat
"the test still prints the old numbers" as evidence the fix had no effect.

## Also

- grep the build log for `error:` AND check the exit status; a pipeline through
  `tail` or `grep` masks the compiler's status.
- When a debug `fprintf` I expected to see produces nothing, suspect the build
  before suspecting the code path.
- Edit via a Python/structural script and VERIFY the anchor matched (assert).
  A silent no-op replace leaves you debugging code that was never changed.