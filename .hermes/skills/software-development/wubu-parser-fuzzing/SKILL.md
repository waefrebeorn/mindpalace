---
name: wubu-parser-fuzzing
description: Use when fuzzing a WuBuOS parser against untrusted bytes.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [fuzzing, sanitizers, wubuos, verification]
    related_skills: [wubuos-build-integrity, wubuos-test-suite, test-driven-development]
---

# WuBuOS parser fuzzing

## When to Use

- Hardening a parser that consumes untrusted bytes: image and FS-image formats,
  config files, `.desktop`/MIME entries, `.spell` module containers, wire formats, EDID.
- Before claiming a parser is safe, or when a hostile-input sweep already exists but
  nothing checks memory behaviour.
- Adding a new `test_*_fuzz` target, or wiring one into `mk/sanitize.mk`.

A hostile sweep that forks with `alarm(1)` proves "did not crash". A sanitizer
proves "did not read or write out of bounds, did not overflow, did not execute
undefined behaviour". Different claims -- build both.

## Procedure

1. **Find the entry point and its documented failure policy.** Read the header: most
   parsers here say explicitly what they refuse. That sentence IS your invariant list.
   If it is vague, the parser needs a contract before it needs a fuzzer.
2. **Build a valid seed** and mutate it. Noise-only mutation dies on the first line and
   never reaches deep parser states; start from a real, well-formed input.
3. **Choose mutations deliberately**: bit flips, truncation, single-byte insert/delete,
   run deletion, and above all *hostile values for every length/count field* the format
   has. Length fields are where memory-safety lives.
4. **Assert properties, not survival.** Four worth writing every time:
   - refusal is always reported as a bounded value (never a wild count a caller trusts);
   - a documented invariant holds for EVERY accepted parse (e.g. "no Name means not a
     valid entry");
   - derived counts stay within the array caps the caller allocates;
   - identical input parses identically twice (global-state dependence is a bug).
5. **Wire into both gates**: a plain `make test_<x>_fuzz` target, and a sanitized build
   under `mk/sanitize.mk`. Exact flags and env: `references/sanitizer-gate-recipe.md`.
6. **Prove the gate actually runs the binary**: delete the `.san` artifact and rerun.
   A prerequisite spelled through a variable defined below the rule is silently
   dropped -- see `wubuos-build-integrity`. Verify with `make -qp | grep '^test_x:'`.
7. **When a fuzzer finds a bug**, fix it, then REVERT-VERIFY the new assertion: undo the
   fix temporarily and confirm the new check FAILS. An assertion that passes either way
   proves nothing; record the revert result in the commit message.

## Rules

- **Never assert only that the process survived.** Survival is the sanitizer's job.
- **Enforce the contract at the BOUNDARY the caller passes through, not only on a
  later accessor.** A validator that lives inside one getter can be bypassed entirely
  by input the PARSE step accepts: a `.spell` module checked every export's bounds but
  only under `if (code_len > 0)` admitted every image declaring no code, so over a
  thousand malformed modules parsed cleanly and would only fail when someone happened
  to resolve a symbol. Mutation fuzzers find this class precisely because they flip the
  guard away. Fix by moving the check into open/parse so a lying image is refused at
  ADMISSION, then extend the unit test to pin the previously-bypassed input -- the old
  assertion encoded the weaker contract and had to change with it.
- **Share the PRNG.** One header-only splitmix64, seeded from argv. Copies drift the
  moment someone improves one of them, and a finding you cannot reproduce is not a
  finding. `rand()` has unspecified sequencing and global state.
- **`-Werror=implicit-function-declaration` belongs in the SANITIZED build.** It catches
  calling an undeclared function -- UB whose return value comes from garbage -- before
  any input runs. This repeatedly finds real defects that a clean plain build allows.
- **Fuzzers never touch user state.** Point stores at scratch paths through an env
  override (`WUBU_FS_STORE`, `WUBU_DRM_SYSFS` pattern) and unlink fixtures afterwards.
  A test that writes into the user's real data file is worse than no test.
- **Hardware-dependent checks must degrade honestly.** When no device is reachable,
  assert the fail-closed path (`-1`, empty output) instead of skipping: a skipped test
  looks like a pass.

## Pitfalls that cost real time

- **A fixture that passes both ways is worthless.** Before trusting a regression test,
  run it against a reverted fix. If it passes there too, the fixture never exercised
  the defect (typical when debris is placed at a path the old code did not use).
- **`*/` inside a comment ends it.** A path like `/sys/class/drm/*/edid` written in a
  `/* ... */` block silently terminates the comment and everything after it compiles
  as code. Scan comments for glob characters.
- **Structured formats pack fields two-per-byte or store IDs, not values.** Reading a
  mode-id array as pixel widths, or treating shared high/low nibble bytes as separate
  fields, produces plausible-looking nonsense that still passes a `> 0` check. Validate
  against REAL captured data, and make the oracle independent (parse `xrandr` TEXT, do
  not call the same library twice).
- **Integer truncation leaves dead strips.** `(int)(fraction * width)` summed across
  zones rarely reaches the screen edge; clamp edge-touching regions exactly.
- **Pin wire formats with `_Static_assert`** so extending the shared struct without
  updating the decoder fails the build instead of misreading firmware data.
