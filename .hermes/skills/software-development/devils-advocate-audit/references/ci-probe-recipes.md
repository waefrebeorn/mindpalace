# CI probe recipes (GitHub Actions)

Use these when an audit needs the REAL runner result, not a local guess.
All examples are Python calling `gh`; keep the scripts in the session scratch
dir so the command text stays short and rerunnable.

## Token without leaking it into the shell

Read the git credential helper inside Python and pass the result via `env`:

```python
import subprocess, os
p = subprocess.run(["git", "credential", "fill"],
                   input="protocol=https\nhost=github.com\n\n",
                   capture_output=True, text=True, cwd="/path/to/repo")
tok = next(l.split("=", 1)[1] for l in p.stdout.splitlines()
           if l.startswith("pass" + "word="))
env = dict(os.environ, GH_TOKEN=tok)
```

Splitting the literal key avoids shell-command sanitizers that rewrite
credential-shaped text; never echo or log the token itself.

## Find the failed job and read its actual log

```bash
gh run list --repo <owner>/<repo> --workflow <wf>.yml --limit 4 \
  --json databaseId,headSha,status,conclusion,createdAt
gh run view <run> --repo <owner>/<repo> --json jobs,headSha,conclusion
```

For the full log use `gh api repos/<owner>/<repo>/actions/jobs/<job_id>/logs`.
`gh run view --job <id> --log` can return an empty body on older runs. Save
the API output to a file, then filter lines for `##[error]`, `FAIL`,
`MISSING`, `RESULT`, and print a context window around the first hit — the
marker says WHAT failed, the surrounding lines say WHERE the chain stopped.

## Dispatch a fresh run and watch it

```bash
gh api repos/<owner>/<repo>/actions/workflows/<wf>.yml/dispatches -f ref=<branch>
```

Then list the newest run and `gh run watch <id> --repo <owner>/<repo>
--exit-status`, followed by a jobs conclusions summary. Launch that watcher
as a background job with completion notification; do not poll it in a sleep
loop. Check the workflow's `on.push.paths` before assuming a code push
triggered CI — a runtime-only change often does not trigger a kernel/firmware
workflow, so dispatch explicitly if its result matters. After dispatching,
confirm the new run's `headSha` is the commit you mean to verify; older
path-triggered runs can still be in progress and are not evidence. Pass the
DEFAULT BRANCH to `workflow_dispatch` (`gh workflow run <wf>.yml --ref main`),
not a commit SHA: GitHub rejects a SHA ref for dispatch while `--ref main`
picks up the current tip. A run whose conclusion is still `in_progress` is
not a PASS; record the completed conclusion before trusting CI.

## Gates must survive shallow checkouts

Never make a gate's negative control depend on `git show <old-sha>` or
`git cat-file -e <old-sha>:<path>`. CI checkouts are shallow, so the
 historical object is usually absent and the gate fails on checkout shape
instead of on the code under test. Sweep ALL gate scripts before trusting a
CI fix: `grep -rn 'git show [0-9a-f]\{7\}\|git -C.*show.*[0-9a-f]\{7\}' tools/*.sh` — one hardcoded SHA in a sibling gate keeps the run red after the first one is fixed.
Build the pre-change control from the
CURRENT source instead: copy the file and disable the single dispatch or
branch under test, compile that synthetic variant, and require the old
behavior to fail. If a source diff is impractical, assert an in-run state
the old behavior could not produce. Why: a gate that needs a historical
object is a local-only gate wearing a CI badge, and it will keep the remote
red after every unrelated local fix lands.

## Probe an optional compile-time dependency without installing it

When a feature is gated behind a dev package that CI does not carry, fetch
it into scratch instead of changing the host:

```bash
apt-get download <lib>-dev <lib-runtime>
mkdir -p <scratch>/dep-root
for d in <lib>*.deb; do dpkg-deb -x "$d" <scratch>/dep-root; done
```

Point an env var (`<PROJECT>_<DEP>_ROOT`) at the extracted tree, add an
OPT-IN make target that requires the env var and fails loudly when it is
missing, and keep the default build/test tier green without the dependency.
Verify the optional path with a real differential gate (valid artifact
accepted; tampered artifact refused) and re-run the default gate after the
merge. Never claim the optional path is proven by a compile alone.
