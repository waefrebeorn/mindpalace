# Verify a push landed (one repo)

```bash
lb=$(git -C <repo> branch --show-current)
sha=$(git -C <repo> rev-parse HEAD)
# commit + push first, then:
rs=$(git -C <repo> ls-remote origin refs/heads/$lb | cut -f1)
# OK only when sha == rs
```

`git push origin HEAD` pushes the LOCAL branch name, so verify against the
local-branch ref. When the branch is nonstandard (`wubu-integration`, `root`,
`master`), `ls-remote refs/heads/main` returns empty and looks like a failure
that never happened.

## Resolve the default branch via the API (authoritative)

```python
import json, urllib.request
req=urllib.request.Request("https://api.github.com/repos/waefrebeorn/NAME",
  headers={"Authorization":f"Bearer {token}"})
d=json.load(urllib.request.urlopen(req))
print(d["default_branch"])   # e.g. wubu-integration
```

The local clone checks out the default branch, so `git -C repo branch
--show-current` usually equals it.

## Token from the credential store (never echo it)

```bash
token=$(grep github.com ~/.git-credentials | head -1 \
  | sed 's|^https://||; s|@github.com.*||' | sed 's|^[^:]*:||')
```
