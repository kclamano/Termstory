## 10. Privacy Sanitizer

All data passes through `sanitizer.py` **locally** before any AI call. Nothing sensitive ever leaves your machine.

### Session Blacklist

If any command in a session matches these patterns, the entire session is short-circuited to return `"Security/Authentication Operations"` — no commands are sent to the LLM at all:

```python
BLACKLIST_PATTERNS = [
    r'\bvault\b',
    r'\baws\s+configure\b',
    r'\bgh\s+auth\b',
    r'\bkubectl\s+.*?\bcreate\s+secret\b',
]
```

### Redaction Rules

| Type | Pattern | Replacement |
|---|---|---|
| Private keys | `-----BEGIN ... PRIVATE KEY-----` | `[REDACTED_PRIVATE_KEY]` |
| AWS keys | `AKIA[A-Z0-9]{16}` | `[REDACTED_AWS_KEY]` |
| Bearer tokens | `bearer <token>` | `Bearer [REDACTED_TOKEN]` |
| Flag values | `--password`, `--token`, `--api-key`, `-p` | `--password=[REDACTED]` |
| IPv4/IPv6 | standard address patterns | `[REDACTED_IP]` |
| Hostnames/FQDNs | `host.domain.tld` | `[REDACTED_HOST]` |
| Exports | `export KEY=value` | `export KEY=[REDACTED]` |

**File extension whitelist:** Paths ending in `.py`, `.json`, `.sh`, `.yml`, `.ts`, `.go`, etc. are never redacted even if they look like FQDNs — preserving filenames like `config.json` and `api.ts`.

---
