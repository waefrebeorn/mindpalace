---
name: wubuos-submodule-without-token
description: Use when adding a GitHub submodule; avoid token URLs.
---

# Adding a submodule without leaking the token

## The trap

`git submodule add https://x-access-token:$TOKEN@github.com/org/repo.git path`
works -- and writes the token into `.gitmodules`. It then sits in the commit
waiting to be pushed.

GitHub push protection usually rejects it (`GH013: Push cannot contain
secrets`), which is the good case: nothing leaks, you just cannot push. If the
repo has no protection, the token is published.

## The right order

1. Add with the **clean** URL:

   ```
   git submodule add https://github.com/org/repo.git path/to/submodule
   ```

2. Let the credential helper / `.git-credentials` authenticate. No token in
   any file.

3. If the path already holds a tracked file, `git rm --cached` it first --
   `git submodule add` refuses a non-empty path.

## If it already leaked

Scrub every copy, then amend:

```python
import re
for p in (".gitmodules", ".git/config"):
    s = open(p).read()
    s = re.sub(r'https://x-access-token:[^\s@]+@github\.com/',
               'https://github.com/', s)
    open(p, "w").write(s)
```

Then `git add .gitmodules && git commit --amend --no-edit` and push.

## Verify the remote, not just the push

A successful push does not prove the secret is absent -- check the file on the
remote:

```
gh api repos/ORG/REPO/contents/.gitmodules?ref=main
```

decode the base64 and assert the token prefix is not present.

## Related lesson

A committed **prebuilt binary** (`src/tools/wubugrep`, mode 100755) was the
reason the submodule existed at all: the tree shipped an artifact with no
relationship to any source. When you find a committed binary, ask which repo
owns those sources and link it instead.
