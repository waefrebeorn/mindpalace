---
name: wubu-vault
description: Manage API keys securely — vault inventory, verify, rotate, never leak.
tags: [keys, secrets, vault, nvidia, openrouter, huggingface, github]
category: devops
version: 1.0.0
author: WaefreBeorn
license: WaefreBeorn-Umbrella-1.0
related_skills: [wubu-keys-and-oracles, free-api-inference, wubuos-github-push]
---

# WuBu Vault — Key Management Skill

The vault is the single source of truth for every API key WuBu uses.
This skill drives the vault system without ever exposing key values.

## Vault layout

```
~/.hermes/profiles/mind-palace/
├── secrets/
│   ├── hf.env          (0600) — HF read/write + NVIDIA + OpenRouter
│   └── github.env      (0600) — GitHub classic PAT
└── vault/
    ├── VAULT.md        ← inventory, rules, rotation schedule
    ├── scripts/
    │   └── vault.py    ← verify, status commands (never prints values)
    └── logs/
        └── verify.log  ← timestamped verification log (no key values)
```

## Commands

### Verify all keys live
```bash
python3 ~/.hermes/profiles/mind-palace/vault/scripts/vault.py verify
# Probes every key against its provider API.
# Exit 0 = all green. Exit 1 = one or more failed.
# Output: KEY_NAME STATUS provider-safe detail (never the key value).
```

### Check vault inventory
```bash
python3 ~/.hermes/profiles/mind-palace/vault/scripts/vault.py status
# Prints file existence, permissions, size — no key values.
```

### Rotate a key
1. Generate the new key at the provider dashboard.
2. Edit the appropriate `secrets/*.env` file (0600).
3. Run `vault.py verify` to confirm the new key works.
4. Update `vault/VAULT.md` rotation date for that key.
5. **Never commit the old key value** — the env file is gitignored.

## How skills reference keys (never hardcode)

Every skill that needs a key reads it from the env file:

```python
import os
key = os.environ.get("NVIDIA_API_KEY", "")
# or parse the env file directly:
for line in open(os.path.expanduser("~/.hermes/profiles/mind-palace/secrets/hf.env")):
    ...
```

The `wubu-keys-and-oracles` skill documents which env vars to use.
The `free-api-inference` skill documents the RLHF oracle pattern.
The `wubuos-github-push` skill uses `GITHUB_TOKEN` from `github.env`.

## Rules

1. **Never echo a key** into commits, docs, or paste.
2. **Never `git add -A`** after touching env files — stage explicit paths.
3. **The vault file is OUTSIDE both repos** — it survives prestige handoffs.
4. **GitHub push protection** blocks commits with secret literals. If it fires,
   find the literal in tree AND history (`git-filter-repo --replace-text`)
   then force-push. See `git-secret-scrub` skill.
5. **Push protection bypass** — `wubu_push.sh` uses `~/.git-credentials`
   (x-access-token form), not env vars in argv.
6. **Rotation** — NVIDIA keys every 90 days, HF/OpenRouter/GitHub every 180
   days, or immediately on any compromise signal.

## Verification

```bash
# All keys live-verified (exit 0 = green):
python3 ~/.hermes/profiles/mind-palace/vault/scripts/vault.py verify

# Vault inventory check:
python3 ~/.hermes/profiles/mind-palace/vault/scripts/vault.py status

# Check for leaked literals in working trees:
grep -rn "sk-or-v1-\|hf_SnPL\|hf_SUmX\|nvapi-\|ghp_" \
  /home/wubu/wubuwizard /home/wubu/wubuos \
  /home/wubu/.hermes/profiles/mind-palace/skills/ \
  2>/dev/null | grep -v "^Binary\|\.\.\." | grep -v "^#" | grep -v "hf_SnPLzxl\.\.\."
# (the last grep allows truncated prefixes in docs — full literals are leaks)
```

## Pitfalls

- The `vault.py` script uses `urllib` (no pip dependency) — it works in
  any Python 3 environment without network packages.
- `vault.py verify` appends to `vault/logs/verify.log` — the log has
  timestamps and status but never key values.
- If a key is 429 (rate-limited), it's still VALID — the probe returns
  HTTP 200 with usage data. A 401 means the key is revoked or malformed.
- The `wubu-keys-and-oracles` skill stores truncated prefixes (`hf_SnPLzxl...`)
  in its SKILL.md — this is safe because the full values are never written.
- The `wubuos-github-push/scripts/wubu_push.sh` has a comment `ghp_xxx`
  which is a placeholder pattern, not a real token. This is safe.
