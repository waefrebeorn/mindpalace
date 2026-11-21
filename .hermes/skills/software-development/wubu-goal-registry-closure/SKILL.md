---
name: wubu-goal-registry-closure
description: Close a GOALS-1000 goal with a tested C11 module.
category: software-development
---

# Closing a GOALS-1000 registry goal

**Use when** running the standing "complete all goals" directive: pick the next
open entry in `wubuwizard/docs/GOALS-1000.json`, ship a real C11 module behind a
test, mark it DONE, push. Also use when resuming a prior registry session and the
next open goal list must be re-derived from the registry.

The standing autonomous goal closes each remaining registry entry the same way: a
real, self-contained C11 module behind an assertion test, gate green, registry
marked DONE, pushed to `wubu-integration`. This is the procedure; `wubuos-test-suite`
covers the shared Makefile recipe traps and `wubu-session-workflow-agro` the
status-reporting style. Compiler Makefile gate recipes (header-deps `-MMD`,
zero-warning locked baseline, compile-flag parity):
`references/compiler-makefile-gates.md`.

## Procedure (in order)

1. **Read the goal**: python-json the registry for `n`, `title`, `module`,
   `criterion`, `domain`, `tier`. Skip BRAIN hyperbolic/MLA Lean goals — that is
   the other agent's wubumath domain.
2. **Check the CONCEPT is free, not just the name**:
   `ls include/ src/ | grep -i <name>` catches the same word; it does not catch
   the same idea under a different one. Before writing a module, grep the
   concept's own nouns across both trees (a "solar system of experts" is not
   named `orbit` — it may already live in `wubu_gravity.h` with cells carrying
   mass, radius and angle). Read the matching header's API and decide
   explicitly: extend it, or state in your own header that your module is a
   complement and why. Two routers over the same field is the failure; a
   header that names the existing owner is the fix.
   `write_file` REFUSING to overwrite an existing `.h` you never read IS the
   collision alarm — honor it, rename, move on.

**When the goal's `module` path does not exist as a file, grep the capability's
action-verbs, not the goal's module name.** A "Build wubu_seccomp_gen.c" goal is
nominal the moment `filter_build_allowlist`/the BPF byte-emitter already lives in
a differently-named module (`ct_iso_seccomp.c`): the registry `module` field is
only a label, the exported verb is the capability. Search `src/` in every repo for
the generator/builder/transform verb (the title words: build, emit, gen, filter);
only a truly absent verb makes a clean build that unblocks the cluster. Closing
on a capability that already exists under another file is a duplicate, not a
closure.

### Crypto / numeric-constant modules (subclass of steps 2-3)

When the goal is a self-contained algorithm with magic constants (SHA-2, GCM, CRC, etc.):

1. **Derive the constants from their first-principles source, never from memory.** For FIPS 180-4: `K[i] = floor(2^64 · frac(cube_root(p_i)))` (cube root of the first primes) and `H[i] = floor(2^64 · frac(sqrt(p_i)))` (square root of the first primes). Compute with exact integer arithmetic (`math.isqrt` for square roots; integer Newton for cube roots — floating point cannot hold 64 bits of mantissa for `p·2^192`). Prove exactness in the generator with the floor identity: `F**3 <= p*(2**192) < (F+1)**3` for every K, and `s*s <= p*(2**128) < (s+1)**2` for every H — if it fails for a prime, the arithmetic lost a bit and the constant is wrong.
2. **Cross-validate against an independent oracle before hardcoding.** For hash constants that is the NIST FIPS 180-4 PDF (§5.3) verified word-for-word (K0, K79, every H); for KAT expected digests it is stdlib `hashlib` run on the EXACT test input bytes. Memory is not an oracle: a remembered constant (e.g. H1 = ...a742 vs NIST ...a73b) or a 52-byte string typed where a 56-byte one was intended is exactly the bug this step exists to catch.
3. **Mirror the proven-green sibling in the target language, not a draft.** A Python reference that fails its own empty-message test has a transcription or logic bug; a C module that mirrors `wubu_sha256.c` (opaque ctx, 64-bit bitlen, 0x80 pad, `rotr64`, identical control flow) is green on first compile because it inherits a vetted shape. Translate the proven structure, then let the KATs catch drift — do not hand-port a scratch draft.

### Numeric / geometric modules (rotation, interpolation, manifolds - no stdlib oracle)

When the module has no magic constants and no stdlib reference (quaternions,
matrices, slerp/squad, manifolds), the independent-oracle step has nothing to
lean on but first principles. Build the oracle in a *different language* from the
C under test, reuse no code, and anchor every formula with a hand-checkable
identity before trusting any computed value:

- 180 degree rotation x2 -> (-1,0,0,0)  [double cover of identity, NOT (1,0,0,0)]
- two 90 degree quaternions multiply to the 180 degree quaternion
- slerp(a,b,0)=a, slerp(a,b,1)=b; slerp(a,b,0.5) at the acos(dot) midpoint
- slerp(a,-a,0.5)=identity  (exercises the dot<0 hemisphere flip)
- normalize(0,0,0,0) = identity  (never NaN)
- a full 2pi rotation -> -identity  (double cover, not identity)
- axis-angle(A,theta) and axis-angle(A,-theta) are conjugates

Print oracle values at full precision (repr/str, never rounded) and use them
directly as the C test expected literals; compare with a tolerance that exceeds
float-vs-double rounding (>=1e-5 absolute for 32-bit float, ~7 sig figs) but
 sits far below any geometric threshold the library promises. Assert both the
happy path and the fail-closed path (zero input -> identity, not NaN). NOTE:
quaternion orientation is a *value type* returned by value, NOT the
opaque-ctx byte-buffer pattern -- that applies to context objects (hash/seccomp
state), not to small plain-old-data math structs.

3. **Author the module**: `include/<name>.h` (opaque struct + decls only),
   `src/<name>.c` (real work — no stubs, per the standing directive),
   `tools/test_<name>.c` (`static int fails` + `CHECK(cond)` macro printing
   `FAIL: <cond> (line N)`). Assert the happy path AND the fail-closed paths:
   bad args, duplicates, full/exhausted tables.
4. **Wire the Makefile** (recipe lines need real TABs — splice with python; the
   `patch` tool mangles recipe TABs and backslash continuations, see
   `wubuos-test-suite` "Makefile edit pitfall"): a `.o` rule after a neighbor's,
   then a test target:
   ```
   test_<name>: tools/test_<name>.c src/<name>.o
   	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) -lm
   	./$@
   ```
   Run `make test_<name>` and read the tail — target ALL PASSED.
5. **Mark DONE**: run `make test_<name>` once more just before writing, and put
   that run's EXACT count into ` [verified: ...]` -- never a figure from a debug,
   pre-fix, or draft run. python-json appends ` (DONE)` to `title` and
   ` [verified: <what the assertions prove>]` to `criterion`. A stale count
   (e.g. quoted before the fixture was corrected) makes the DONE row
   unverifiable, so it must match the final re-run line-for-line. Print the new
   done/total and remaining-open list as a plain data point.
6. **Commit in two steps**: code commit, then a small registry commit. They may
   be in **different git repos** -- `GOALS-1000.json` lives in `wubuwizard/docs`
   but a module's `module` field can point at `wubunos/...` or `wubuos/...`;
   commit each in its own repo and push each before reporting. Code commit
   (`git add -f include/<name>.h src/<name>.c tools/test_<name>.c Makefile`):
   the `-f` is required because `src/*/test_*` in `.gitignore` ignores test
   sources -- a plain `git add` silently drops the test while the recipe still
   references it. Then a small registry commit (`git add docs/GOALS-1000.json`).
   Push to `wubu-integration`. **Verify the commit actually landed** -- `git log
   --oneline -1` plus `git show HEAD:src/<name>.c | head -2`. A terminal heredoc
   commit can stage nothing and only report "nothing added to commit but
   untracked files present"; if the code files aren't in HEAD, redo the
   add+commit before reporting.

## Aligning the whole registry to an external policy corpus

A different operation from closing one goal: map an external corpus (a
government strategy, a standards body, a funder's objectives) onto GOALS-1000
and produce a gap matrix. **Do not mutate the 1000-goal / 16-domain layout** —
that invariant is load-bearing. Write a separate document.

1. **Fetch primaries, never summaries.** The authoritative text (executive
   order, plan PDF, standard) — record section numbers so a claim can be
   checked. Search snippets paraphrase and go stale.
2. **Map by keyword, label as candidates.** Search each objective's keywords
   over `title + criterion + module`, count hits, and list representative `n`
   IDs. Report them as *candidates*, not compliance: "standard" matches protocol
   work, not standards policy; a goal can mention "eval" and still be a stub.
   Spot-read a few matches before quoting a count.
3. **Use a fixed matrix shape** in `docs/<POLICY>-ALIGNMENT-MATRIX.md`:
   objective | source (§) | our goal IDs | armor/governance invariant | status |
   gap / next action. One row per objective, no prose padding.
4. **Name the gaps with numbers.** A theme with 2 matching goals out of 1000 is
   a gap, not a rounding error. List the unaddressed objectives explicitly
   instead of stretching a weak match to cover them.
5. **Record prohibitions too.** A policy corpus usually says what not to do
   (e.g. no mandatory licensing/preclearance, no censorship, no unlawful
   surveillance). Put those in their own section — they constrain future
   designs more than the positive asks.
6. **No endorsement claim.** The matrix is an engineering crosswalk, not legal
   advice or a claim that the body endorses the work. Say so in the document.

## Regenerating the whole registry from evidence (explicit instruction only)

A whole-file retool is a different operation from closing goals. Default is
still "do not rewrite content"; this section applies only when the user asks
for the backlog to be regenerated.

1. **Freeze the baseline and make the generator read it.**
   `cp docs/GOALS-1000.json docs/GOALS-1000.baseline.json`, then have the script
   read the baseline and never the file it writes. Without this the second run
   consumes its own output — open entries become "nominal" rows, counts drift
   (observed: 403 nominal → 652, 235 missing → 251) and the backlog degrades
   while looking plausible.
2. **Keep the invariant:** exactly 1000 goals, exactly 16 domains, `n`
   contiguous 1..1000, every criterion >= 25 chars and decidable by a command
   or a named record. Per-domain counts become a consequence of the evidence;
   do not force them back to the old quotas.
3. **Derive every row from a measured evidence class and put the class in the
   title** so the backlog is self-describing:
   - module absent (resolver returns None) → `Build <file>: <capability>`;
     criterion: file exists, `test_<stem>` target exists and prints ALL PASSED
   - module present, capability unverified → `Verify <capability>`; criterion:
     evidence recorded in `docs/PORTFOLIO-REALITY-CHECK.md` with file:line and
     the owning test green
   - module with no `test_<stem>` target anywhere → `Test coverage: <stem> has
     no test target`
   - gauntlet failures **bucketed into diagnostic classes** (~550 raw tests →
     ~70 classes) plus one row per runtime-wrong suite. Per-test rows are a
     work queue, not a backlog; 500 of them drown the domain.
   - hand-written feature gaps that were measured this session
4. **Write the RESOLVED path into every nominal row.** The resolver matches by
   basename across four repos, so keeping the original string yields "Verify"
   entries pointing at files that do not exist — the same nominal trap the
   section above warns about. Store repo-relative (`wubunos/wubu_preproc.c`).
5. **Filter coverage candidates:** skip `test_*`, `bench*`, `main`, `util`,
   `demo` and files under ~1.2 KB, or the backlog fills with generic stems.
6. **Verify before committing:** 1000 rows, 16 domains, 0 duplicate titles, 0
   criteria under 25 chars, `n` contiguous, sampled `Build` modules absent and
   sampled `Verify` modules present, and a second run producing a
   byte-identical file (idempotent).
7. **Report what the retool exposed, not the row count.** "235 entries the old
   registry called active name modules that do not exist, and 265 modules have
   no regression test" is the finding; "1000 goals regenerated" is bookkeeping.

Keep the generator in `tools/` (`tools/retool_registry.py`) with a `--dry-run`
that prints the class and domain counts, and leave a `docs/GOALS-RETOOL.md`
recording the evidence sources and the exact regeneration command.

## Continuity goals (the standing loop)

A goal whose purpose is to keep FUTURE sessions working is a different artifact
from a registry entry. Keep it outside `GOALS-1000.json` (for example
`docs/GOAL-CONTINUITY.json`, `n >= 1001`) so the exactly-1000 / 16-domain
invariant survives; paste-ready JSON is the deliverable.

Write the criterion as a checklist over **sources of truth**, not over a
feature:

1. re-read the policy primaries and the current registry;
2. run the honest gate and record binaries / ALL-PASSED / failures;
3. advance at least one open matrix or manifold item;
4. consult the accumulated research waves and the math repo's linkage map
   before inventing anything;
5. leave a pushed commit and an honest gap list.

Pair the standing loop with ONE concrete milestone goal, or it has a mandate
without a target. Keep the criterion checkable after the fact by reading the
repo (counts, file, commit), never by trusting the session's own summary.

The user's standing correction: the broad continuity goal must be **agnostic
and non-myopic**. A criterion tied to one feature or one subsystem is rejected
as myopic even when it is checkable — the portfolio-level shape below is the
accepted form.

### Portfolio-level continuity (anti-myopia)

A standing loop that always works on the same subsystem is myopia with a
schedule. When the ask is "do all goals, not just the current one", make the
selection rule and the coverage floor explicit and machine-checkable. The goal
is a **controller over the portfolio**, not a feature goal:

- **Triage every open goal each cycle**: active, blocked (reason), or deferred
  (dated expiry). No silent drops; a deferral without an expiry is a drop.
- **Closure has one definition**: the module exists, a test runs inside the
  aggregate gate, and the criterion evidence is recorded in the registry.
- **Pick by cluster, not by domain.** The registry is file-anchored: ~500 open
  goals name ~500 modules, and a module that holds N goals closes N at once
  (one 9-goal file, one 6-goal file, and so on). Rank candidates with
  `python3 tools/goal_leverage.py --min 3`, which groups open goals by target
  module and marks whether the file exists yet. Working domain-round-robin
  reopens a 9-goal file nine times and is the reason breadth-first cycles
  produce one closure each; cluster-first produces the whole cluster or
  nothing. Domain spread becomes a consequence, not a target.
- **A MISSING module is a build, not a goal.** Goals whose file does not exist
  unblock together: five absent namespace files held ~20 goals, and one core
  build landed them. Read the cluster before scheduling singles.
- **Keep a ledger** (`docs/portfolio-cycles.jsonl`: cycle, domains, closed ids,
  gate counts, deferrals) and validate it with a script wired into `test_all`
  (`make test_portfolio`). A scheduling rule outside the gate is prose.
- **Report the grounded count**: goals whose named module resolves to a file.
  A large ungrounded remainder is the honest size of the prospective backlog,
  not a build failure — and never something to "close" in prose.

Module-path resolution is the trap in that count. Registry entries mix
`foo.c`, `src/foo.c`, and `wubuos/src/kernel/foo.c`. Strip a leading repo name
before joining the path to that repo's root, then fall back to a basename
search in `src/ include/ apps/ tools/` across brain, body, compiler and math.
Joining a prefixed path to its own root doubles the directory and reports
hundreds of false "missing" modules.

Build that basename index ONCE with a single `os.walk` per repo (pruning
`.git`, `build`, `node_modules`, `__pycache__`, `models`, `research`) and look
names up in a dict. Resolving each of 638 goals with its own recursive glob over
these trees does not finish inside a five-minute tool timeout.

### A module that resolves is not a capability that exists

Many "active" goals resolve to a real file that does not implement the named
capability. Before selecting a goal, grep the module for the capability's own
symbols, not its filename:

- page-table walker → `grep -n 'PML4\|PDPT\|PTE' src/kernel/wubu_vmm.c`
  (the module was a physical-frame bitmap allocator; no walker at all)
- resumable `readdir` → `grep -n readdir src/kernel/fat32_dir.c` (absent)
- PCG-XSH-RR world RNG → the module used xorshift64
- suspend counts → `grep -n resume_thread` (no handler, no count, no status)

Such a goal is **nominal**: module present, capability absent. Keep it OPEN,
record the evidence as a table in `docs/PORTFOLIO-REALITY-CHECK.md` with
`file:line`, and never close it on a test that asserts something adjacent.

Splitting `active` into `active` + `nominal` is the honest fix; until then say
in the triage doc that "active" only means the path resolved.

**Batch-verify a whole cluster in one pass.** When `goal_leverage --min 3` surfaces a
cluster of N goals on one module, do not triage them one at a time. Run one grep per
*capability symbol* (the title words: complex, span, expected, undeclared, overflow,
LICM, unroll, ...) against the single file, collect present/absent per goal, then write
ONE evidence table covering the whole cluster. One grep pass per symbol beats N file
reads, and the table is the artifact the next cycle needs. Mark only the goals whose
criterion is a pure capability check ("module implements X") as candidates; goals whose
criterion names a gauntlet class ("all N captured tests in this class build") are a
separate lane — see the gauntlet-class note below, do not attempt them here.

**Multi-module sweeps cross repos.** A single capability-verify session usually spans
wubunos (compiler), wubuos (kernel/drivers/GUI), and wubuwizard (brain). Each module's
file lives in a different repo root, so anchor every grep with `cd <repo> &&` — the
tool runner does not honor a separate working-directory argument. Record each cluster as
its own `## <DOMAIN> <file> cluster (date)` section in `docs/PORTFOLIO-REALITY-CHECK.md`
with a consistent table (goal | capability | evidence file:line | verdict), so the next
cycle can resume without re-deriving. When a cluster is entirely nominal (all capabilities
absent), one section still counts as real progress — it shrinks the prospective backlog
honestly.

When the user chooses to build one of these properly, build it in a module that
fits the capability rather than bolting it onto the file the registry happens to
name (a page-table walker does not belong inside a physical-frame bitmap
allocator). Then update the entry's `module` field to the new file in the same
commit — a DONE entry still pointing at the old module is unverifiable, and the
next cycle will "discover" the capability missing again.

### Running a cycle — the mechanics that bite

- **Pick a goal whose criterion names an existing test target.** Extending
  `tools/test_<existing>.c` and its Makefile rule is the cheapest honest
  closure; a brand-new test file only makes sense when the criterion names no
  target at all. Read the criterion before choosing, not after implementing — and grep the
  criterion for the target's EXACT name to confirm it is this goal's test. One
  test family can serve several goals, so fixing the wrong one produces a green
  suite with the criterion still unmet.
  Then RUN that target and count its PASS/FAIL before committing to the goal:
  a target that builds and exits 0 is not a target that passes. A suite can
  report `4/15` while `make` prints only the compile line — run the binary
  directly or grep for `Results:`/`FAIL` in the log.
- **When an extended test starts calling a new module, add that module's `.o`
  to the target's prerequisites.** The symptom is an undefined reference at
  link, not a failing assertion, and `make` deletes the binary on failure — so
  it looks like the test "vanished". Check the recipe's prerequisite list
  before debugging the test body.
- **Before implementing, grep the test tree for the criterion's own words.** A goal can
  already be satisfied and merely unmarked: the cap-narrowing criterion ("requested mask
  must be subset of token rights") was already proven by `test_vsl_nt`, which asserts the
  ceiling refuses the right AND reports a granted mask of 0. Writing a second module for it
  would have duplicated a proven behaviour. Read the existing assertion first — confirm it
  asserts the refusal and the zero grant, not just that the call returns — run the target,
  record the count, and close it as **verified rather than written**. Say so in the commit
  and the ledger note; a verification closure is honest when it names its evidence.
  If the existing test is weaker than the criterion — it claims four aliases but builds
  one, or asserts one refusal where the criterion names five handles — extend the test to
  the criterion's number BEFORE closing. A green assertion on a smaller case is not
  evidence for the larger claim; record the new check count either way.
  "Weaker" can also mean the **wrong oracle**, which no check count reveals: a
  criterion requiring finite differences at 1e-4 is not satisfied by assertions
  that gradients are merely non-zero and finite. Grade the test's assertions
  against the criterion's own words (FD, tolerance, threshold, exact count) and
  add the missing oracle; a substitute oracle that passes is the same failure as
  a green test that never ran. When the analytic gradients are also implausible
  (e.g. ~1e9 with uniform forward weights), the missing oracle is hiding a real
  defect — record the magnitude and keep the goal OPEN.

Crypto KAT failures are fixture drift, not core bugs: when the AAD-dependent field (the GCM tag, GHASH over AAD+C+len) is wrong on some vectors while the AAD-independent ciphertext and the no-AAD vectors are all correct, the failure is almost always stale expected values in the fixture rather than the gfmul/GHASH core -- gfmul is already exercised by the length-block multiplication of the passing no-AAD cases. Diagnostic gate: (1) confirm the failure is isolated to the AAD-dependent output of an otherwise-correct module; (2) localize with a focused scratch that calls the public wrapper versus the bare static core on one vector -- if the wrapper reproduces the trusted tag and only the test harness disagrees, the harness/fixture is the suspect. (3) Re-derive the expected tag from a deterministic Python cryptography AESGCM run using the fixture's exact bytes, never a prior run whose printed label disagreed with its actual AAD argument. A shared KAT header (WUBU_GCM_TEST_BODY) keeps the kernel and runtime facades in lockstep, so fixing the fixture once repairs both targets.
- **Never wire a red measurement into `test_all`.** An audit that fails on
  known debt gets switched off within one session, and then it protects
  nothing. Ship it as a standalone tool plus a documented before/after count,
  keep the goal OPEN, and add the gate only once the count reaches zero.
- **Measure a whole-build criterion before promising it.** "Compile every
  source under `-std=c11 -pedantic`" is a project, not a cycle. Run the
  measurement first (recipe in `wubunos-runtime-integrity`), fix one error
  class, and leave the goal OPEN while the diagnostic file is non-empty. The
  ledger note carries the before/after counts; that is an advance, not a
  closure.
- **The ledger is JSONL, one object per line.** A last line without a trailing
  newline makes the next append concatenate two objects; the checker then
  reports `Extra data: line 1 column N` and the whole ledger is unreadable.
  Write the newline, and `json.loads` every line before running `--check-cycle`.
- **Triage with the controller's resolver, never by hand.** Active = open +
  module resolves + P0/P1; blocked = open + module missing (reason "not
  written"); deferred = open + module present + P2/P3 with a dated expiry.
  Publish the per-domain table once per cycle and point at `--json` for the
  per-goal detail; do not paste 700 rows into chat.
- **Record both gate numbers.** A new test that passes by exit code but does
  not print the aggregate `ALL TESTS PASSED` line raises the binary count
  without raising the ALL-PASSED count. Report binaries, ALL-PASSED lines and
  failures as three separate facts; never claim the line count is the number
  of tests.
- **A goal in another repo is evidenced by THAT repo's gate.** Closing a body
  (`wubuos`) or compiler (`wubunos`) goal means running `make test` there and
  recording its suite/check counts in the ledger's `gate` object with a `repo`
  field; the brain gate proves nothing about the body. The checker only reads
  `binaries`, `passed` and `fail`, so extra keys cost nothing and keep the
  evidence honest.
- **Write the criterion's assertion before changing the implementation.** The
  test is the spec: on a search/state-machine goal it surfaced an uninitialized
  string terminator, a self-aliasing copy, and a mode flag that Esc never
  reset — none of which implementation-first work would have found. When it
  fails, decide whether the TEST or the MODULE is wrong (a defensible behaviour
  change belongs in the test), then fix one side deliberately.
- **Make a failing probe print the value it computed before diagnosing it.**
  A harness that only prints `(expect N)` cannot distinguish "wrong by one"
  from "returns exactly 0" / "returns a reinterpreted bit pattern", and those
  three point at completely different code. Store the child's result and print
  `expect N, got M`; that single change turned two vague failure families into
  one root cause plus one unrelated lexer defect in a single run.
- **Several probes failing with the SAME exact value are one defect.** Seven
  struct-return cases all returning exactly `0` (never garbage) means the value
  never reached the caller at all — look for one mechanism (a restore that
  wipes the buffer) instead of seven bugs. Fix the shared cause and re-count;
  six flipped together, which is the cluster-first rule paying off.
- **Prove a failure pre-existed before owning it.** After touching a shared
  file, revert ONLY that file (`git checkout <first-bad-commit>^ -- path`),
  rebuild, and re-run the same probe list. If the same probes fail with the same
  values, the defect is pre-existing and your change is merely net-positive —
  state that with both counts (`PASS 114` without the change, `115` with it)
  instead of guessing whether you regressed something.
- **If a probe's value changes when you add a debug print, stop reasoning
  about the algorithm — that is undefined behaviour.** One shadowing probe
  evaluated to 2 normally and 0 with an `fprintf` enabled, reproducibly. No
  amount of scope-table reading explains it; the variable is reading
  uninitialised or clobbered memory. Reclassify the probe as a memory bug and
  run it under ASan/valgrind before touching the logic it appears to exercise.
- **Give the probe runner a name filter while you instrument it.**
  `main(int argc, char **argv)` + `if (filter && !strstr(name, filter)) continue;`
  turns a 120-case battery into a one-case reproduction that rebuilds in
  seconds, and pairs with env-gated traces (`if (getenv("MIRDBG")) fprintf(...)`) so
  the diagnostic never pollutes a normal run.
- **The ledger checker (`tools/goal_portfolio.py --check-cycle`, wired as `make test_portfolio`) is the arbiter of cycle shape — do not append a cycle line until it passes.** Its three rules, learned by failing them: (1) `min_domains=2` — every cycle line must list >= 2 distinct domains (real work domains; advance-notes on goals in a second domain legitimately count, precedent: cycles 15/19); (2) `max_consecutive=2` — no domain in 3 ADJACENT cycles; (3) the anti-myopia floor — the last 8 cycles must span >= 8 DISTINCT domains, so a domain-cluster streak (e.g. four styx cycles touching only 5 domains) fails at the end and the fix is closing one more goal in an untouched domain, NOT relabeling. When the checker rejects an unpushed line, edit that line freely (renumber, move goal ids between unpushed lines, insert a cycle); once pushed, the ledger is append-only history. Pillar reading (GEO → BODY → KVFS → ROUTE → REV → MANIFOLD in `docs/GOAL-PILLARS.md`) still governs WHAT to work on; the checker governs how the work is SLICED into ledger lines. The claim that the rotation rule was 'retired' is stale — the checker enforces it; if the two ever disagree, the gate wins and the skill follows the gate.
- **Membership is fixed by default; precedence and tier always are not.**
  "Reorganise the 1,000 goals" means reorder the reading plan and correct tiers,
  never edit the 1,000-goal / 16-domain invariant. The one exception is an
  explicit instruction to regenerate the backlog (`retool the 1000 goals`,
  `regenerate from scratch`): then content may be replaced wholesale, but the
  1000/16 invariant and the frozen-baseline rule in the retool section still
  apply. Record the mapping in a doc
  (`docs/GOAL-PILLARS.md`) and keep the archetype: a pillar may contain goals
  from several domains (`wubu_kvfs` sits in KVFS and REV), and a goal can serve
  more than one pillar.
- **A continuity goal can carry a cycle but does not move the registry count.**
  Closing `n >= 1001` entries (`GOAL-CONTINUITY.json`) is legitimate domain
  work; record those ids in the ledger's `closed` array, and report the
  registry's done count as UNCHANGED rather than adding them to it. Two kinds of
  numbering in one total is how a ledger starts lying.
- **Report the seven required steps by name every cycle.** Counts from
  `--json`, domains touched, each closure with its evidence, gate numbers,
  SI-matrix refresh, the ledger append, and `--check-cycle`. A summary that
  drops two of them reads as an unfinished cycle even when they ran — the
  reader cannot tell omission from failure.
- **Advance is not close.** A goal whose first leg is proven and whose second
  leg is measured-and-still-failing stays OPEN with the numbers in the ledger
  note. Marking it DONE is the one dishonest move available in this loop.
- **The criterion names a target; another target's green does not close it.**
  "make test_tasking: …" is satisfied by `test_tasking`, not by a `test_<module>`
  binary that measures the same code. Ship the module, keep the goal OPEN, and
  write a short `docs/<TOPIC>-STATUS.md` with one row per goal: closed / what
  the test proves, then a "not closed — still needs …" list. That file is what
  lets the next session resume without re-deriving why a working module did not
  close its goal.
- **A criterion that needs the kernel to execute on a task's own stack is
  BLOCKED in the hosted build — record it, do not fake it.** Hosted switching is
  `setjmp`/`longjmp` on the host thread's stack, so `CTask.stack_base` is
  allocated and canary-checked but never executed on. A stack high-water
  watermark would scan an untouched fill pattern and report zero for every task;
  TLS FS/GS bases do not exist per task; an idle-HLT goal wants a boot log.
  Implement nothing, write `docs/<BATCH>-REMAINING-BLOCKED.md` with the one
  shared cause and what would unblock it, and keep the goals OPEN. A pattern-scan
  test that measures the wrong stack converts "blocked" into a false green,
  which is strictly worse than an honest gap.
- **Gauntlet-class goals ("all N captured tests in this class build, class count
  drops to 0") are BLOCKED on the gauntlet infra (n832/n833), not on
  capability.** A module can fully implement the capability and the goal still
  cannot close until the gauntlet runtime + 14 ISAs (incl. PTX/Vulkan) are stood
  up. Treat them as a separate lane; do not attempt them under
  capability-verify. Record the cluster's evidence (which capabilities exist vs.
  are nominal) in `docs/PORTFOLIO-REALITY-CHECK.md` and move on.
- **Wire-format criteria: prove the record encoder before the pager.** A goal
  about directory batching, packet framing or message layout is really two
  problems — encoding one record correctly, and slicing N records at an offset.
  Write the encoder as its own function and assert its exact byte length, its
  size field and the offset of its name field BEFORE wiring any paging. Doing
  paging first produced two failed rewrites (duplicates at one `count`, drops at
  another) that were all encoder/parser disagreement, not paging logic.
- **Read the put/get helpers before parsing wire bytes.** This tree's
  `styx_put16` is little-endian; a test that parsed the size field big-endian
  reported `size=15872` for a correct 62 and sent the debugging at the encoder.
  Open the helper, note the byte order, then write the parser.
- **Prove a large-N loop actually ran by printing the iteration count.** A
  sleep test over a 2^32-tick span printed "err 0" for every case, which could
  equally mean "exact" or "the loop never executed". Printing the counter
  (4,294,967,296 iterations) is what made the result evidence. Any test whose
  body is an unbounded-looking loop should report how many times it ran.
- **When the named test cannot drive the code, split the halves — do not
  re-derive them in the test.** `test_tasking` could not sleep a task because
  the timer tick returns early with no current task, so `task_sleep` was split
  into `task_arm_sleep` (set state + file the timer) and `task_wake_expired`
  (advance + wake). The tick calls the same two functions and the test calls
  them directly — the criterion is met through the named target with no
  duplicated logic. A test that re-implements the accounting it is measuring
  proves nothing about the implementation.

## Pitfalls

- **Stage `HEAD` + only your hunk into a dirty shared file (e.g. mk/tests.mk), never `git add <file>`.** Other agents' uncommitted recipes live in the same Makefile; `git add` stages them all and commits them under your hash, breaking precise scope. Reconstruct the tree you want to commit (`git show HEAD:mk/tests.mk` -> splice in ONLY your new target, anchored on a neighbor recipe line -> `git hash-object -w` -> `git update-index --cacheinfo 100644,<hash>,mk/tests.mk`); new source files stage with `git add -f`. Verify with `git diff --cached --name-only`; if anything extra appears, `git reset HEAD` and redo. The working tree keeps everyone's uncommitted dirt; only your hunk lands.
- **Kernel-module selftests compile `src/<mod>.c` + `test/<mod>_selftest.c` directly** (mirror `test_txfs`/`test_fat32`), not via a `.o` prerequisite — no `objects.mk` edit, no `-DWUBU_HOSTED`, pure `-std=c11`, and the run line must execute the binary the recipe built (read the run line before adopting a recipe). A new orphan target must be appended to `mk/test_wiring_baseline.txt` or `make test`'s `check_test_wiring` step fails; never run `--write-baseline` on a dirty tree (it absorbs other orphans — add only your target by name).

- **Patch a registry goal by `n`, never by string match on `criterion`.** `criterion` fields are templated and reused verbatim across sibling goals in the same domain cluster (a scalar implementation and its accelerated/NI-dispatch sibling share one criterion string; an AEAD scalar goal and its nonce-misuse variant share theirs). Matching the `criterion` text to close a goal therefore cannot distinguish the siblings and can flip the *wrong* goal's state — leaving the real one open while a sibling the criterion does not actually cover gets marked CLOSED. Use `n` (the integer primary key) as the sole patch target and treat the `title` as authoritative for intent; the `criterion` is the gate, not the identity. Verify with python-json by selecting on `n` before writing, and re-read the record after to confirm the right `title` changed.
- **Never run a Python edit script through `python3 -c "..."` when the payload contains `$(...)`, backticks, or `$@`.** The shell command-substitutes those inside the double-quoted argument before Python sees them — backticks in a doc string actually executed `make <target>` mid-script, and a `$(wildcard …)` was eaten to empty. Write the script to a file (`write_file`) and run `python3 /path/script.py`; file contents are never shell-interpolated. Related: `subprocess.check_output(..., text=True)` already returns `str`, so calling `.decode()` on it raises AttributeError.
- **Edit registry JSON by splicing the `"n": N` block, not `json.load` + `json.dump`.** A load/dump round-trip reformats the whole ~8k-line file (whole-file diff) and can reorder keys. Locate the block with `re.search(r'\{\s*"n":\s*N\b[^{}]*\}', s, re.S)`, find its `"title"`/`"criterion"` line, scan to the closing quote skipping `\"` escapes, insert the suffix before it, then `json.loads` the whole text BEFORE writing. Formatting of every untouched goal survives.
- **A regenerate-and-diff gate is tautological unless you assert the manifest has real content.** If the gate writes the baseline and then diffs the regenerated output against that same just-written baseline, it passes on an empty or mis-classified manifest (0 == 0). After authoring such a gate, print the row count and the deviation set and check every entry is a genuine deviation — source filenames, stray parentheses and `$^` expansions leaking into an "explicit flag override" list mean the classifier is too broad and the green is fake.
- **`goal_leverage --min 3` clusters carry a `grounded` flag; only `grounded:false` clusters are closure picks.** A `grounded:true` cluster (real file exists) is capability-verify work, not the controller's pick. Each closure can drop a cluster below `--min 3` (5→4→…→2), at which point it leaves the pick set — re-run the controller after each closure instead of assuming the same cluster stays selected.
- **Anchor an insertion on the whole line you intend to keep.** A `patch` whose
  `old_string` includes a function signature must repeat that signature in
  `new_string`; a "comment-only" replacement silently deletes the signature and
  the file still looks plausible until the next compile. When adding a block,
  append at end-of-file (`cat >> file <<'EOF'`) or anchor on a complete,
  unique section and restate every line you are not deliberately removing.
- **Guard `!ptr` at the TOP of every public function before calling a static
  helper.** A static `find(s, name)` dereferences `s` on its first line, so a
  public function that reaches it with a NULL `s` segfaults inside the helper
  far from the obvious call site. The public entry point is the only NULL
  contract boundary; the helper is allowed to assume non-NULL. Guard the
  caller (`if (!c) return -1;`) AND/OR the helper (`if (!s || !name) return -1;`)
  — doing it in the helper covers every caller at once.
- **Define a static helper BEFORE the public function that calls it, or
  forward-declare it.** An `init()` that calls a `compute_*` helper defined
  further down the file gives "static declaration follows non-static
  declaration" — add a `static ...;` forward decl after the includes.
- **A Makefile insert can steal the previous target's `./$@` line** — run BOTH
  targets after adding one and confirm each prints its own results. Full
  mechanics: `wubuwizard-c11-correctness` P76.
- **`make test_<name>` deleting the binary means the test FAILED** and its
  stdout was swallowed by the output pipe. Recompile the test directly
  (`gcc -O2 -I include -o /tmp/t tools/test_x.c src/x.o -lm && /tmp/t`) to read
  the FAIL lines, then run it once under ASAN (`-fsanitize=address`) before
  re-running the Makefile target.
- **Trace the index arithmetic of every navigation assertion** before writing
  its expected value. A delta-reorder that swaps (not shifts) positions, and a
  keyboard grid whose row 0 is digits (not letters), both silently break the
  "obvious" expectation — assert the full resulting order/position, not one slot.
- **Any tests.mk edit must be continuation-aware.** Prereq lines can be backslash-continued: a script that appends text after the FIRST physical segment lands it after a `\` and corrupts the logical line (`missing separator`). Walk the continuation (`while line.rstrip().endswith('\\'): end += 1`) and append at the END segment (which has no trailing backslash). Also: a target's recipe scan must start at `i+1`, not `i` (the target line itself is not a recipe line). Verify with `make -n <target>` on several targets including `make -n test` before running anything.
- **Recipes that link pre-built `$(RT)/*.o` without carrying it as a make prerequisite break on the next header change.** Symptom: undefined-reference cascades in consumers of an embedded struct (a stale `styxfs_host.o` built pre-header-change made two green suites fail 15/3 and 16/7; stash-proof showed both rc=0 pre-change; rebuilding the objects restored 23/0 and 18/0 with the new code in place). Audit script: for each recipe, add every command-line `$(RT)/*.o` to the target's prerequisites (39 targets in one pass).
- **When a new function moves into module X, every recipe linking the callers needs X too.** Adding `styx_errno_ename` to styx_names.c broke `test_styx_socket` (linked styx_serve.c but not styx_names.c) at LINK time, not test time. Grep all recipes for the caller module and check the provider is present in the same recipe (multi-line recipes: scan the whole block, not one line).
- **A recipe whose run line executes a DIFFERENT binary than it builds proves nothing** — `test_styxfs` built `styxfs_test` but ran `styxfs_callbacks_test`; the green-looking output belonged to another suite. Always read the run line when adopting a recipe.
- **Normalize shared numeric helpers to ONE scale and prove them directly
  first.** A contrast helper returning num/den scaled x10 while the threshold
  was an unscaled ratio made low-contrast inputs silently pass. Assert the
  helper with a known pair (black-vs-white) before building assertions on it.
- **Trace every counter increment before writing its expected value.** Admission
  counters increment in several branches (answer-YES, immediate admit,
  fallback); an off-by-one assertion fails an otherwise-correct module.
- **A preview predicate and the work path may legitimately differ.** When
  `decide()` returns the effective source but `generate()` still walks the
  try-then-fallback path (so its counters move), document the split and assert
  the effective result plus the counter delta separately — don't "fix" the
  module to match a test that assumed one unified path.
- **Duplicates and exhaustion are first-class tests** for any registry/bind/
  prompt table — the reject path is the interesting half of the contract.
- **Report shipped artifacts in neutral present/past facts** (no "N DONE,
  pushed") — `wubu-session-workflow-agro` carries the completion-detector rule.
- When a goal's named module (`wine_backend.c`) turns out to already exist under
  another shape (an exec-dispatch pipeline + env module with its own passing
  test targets), run the existing gates and mark DONE from real output — do not
  rebuild a parallel implementation.
- **Opaque contexts cannot be instantiated across translation units.** A
  `typedef struct foo_ctx foo_ctx;` declared in the header is an INCOMPLETE type
  to every other TU, so `struct foo_ctx c;` in a test is a `variable has
  incomplete type` error. Hold the context in an aligned byte buffer sized by
  the static-asserted context size and pass a typed pointer:
  `union { uint64_t a; uint8_t bytes[FOO_CTX_SZ]; } buf; foo_ctx *c =
  (foo_ctx*)buf.bytes;` — the union forces 8-byte alignment for 64-bit fields, and
  casting to the incomplete struct type is well-defined.
- **Hex-encode / compare truncated digests at the digest length, not the buffer
  width.** A SHA-384 fixture writes 48 bytes into a 64-byte buffer; encoding
  all 64 compares 16 bytes of uninitialised stack and fails the KAT even when
  the 48 real bytes are correct. Pass the algorithm's digest size (`WUBU_SHA384_SZ`, not `sizeof(got)`) to the hex/encode/compare helper.
- **C11 portability traps when building new modules by hand.** `-std=c11` hides POSIX extensions: `strdup` is an implicit declaration (returns int, corrupts the pointer) — use `malloc`+`strcpy` or `#define _GNU_SOURCE` before includes. `FILE *` in a header needs `#include <stdio.h>` in that header, not just in the .c. Headers live at the repo root in wubunos (not `include/`), so `#include "foo.h"` with `-I.` (not `-Iinclude`). Compile the scratch build with `gcc -std=c11 -I. -o /tmp/t tools/test_x.c x.c` and run it before wiring the Makefile.
- **Test placement and `.gitignore` scope differ by repo -- confirm the path is tracked before commit.**
   `wubunos` tests live under `src/runtime/tests/` and are caught by `src/*/test_*` in `.gitignore`;
  `wubuwizard` tests live under `tools/` with a different ignore scope. Before any test
  commit run `git check-ignore -v <chosen path>`: if it is ignored, move the test to a
  tracked subdir or use `git add -f`. The recipe references the file by its chosen path, so
  an untracked-but-referenced test breaks `make` on a clean checkout even when the binary
  built locally. The two-commit convention commits the test file together with the module code
  (commit 1), then the registry (commit 2).
- **Prefix every shell command with `cd <repo> &&`; anchor to the repo root, not the tool's working-directory argument.**
  The runner does not always honor a separate working-directory argument, so commands that
  rely on it execute in the scratch/TMPDIR tree and every git-free invocation touches the
  wrong repo. `cd <repo> &&` in the command string is honored everywhere and needs no
  parameter; verify once with `pwd`.
- **C11 portability traps when building new modules by hand.** `-std=c11` hides POSIX
  extensions: `strdup` is an implicit declaration (returns int, corrupts the pointer) — use
  `malloc`+`strcpy` or `#define _GNU_SOURCE` before includes. `FILE *` in a header needs
  `#include <stdio.h>` in that header, not just in the .c. Headers live at the repo root in
  wubunos (not `include/`), so `#include "foo.h"` with `-I.` (not `-Iinclude`). Compile the
  scratch build with `gcc -std=c11 -I. -o /tmp/t tools/test_x.c x.c` and run it before
  wiring the Makefile.
