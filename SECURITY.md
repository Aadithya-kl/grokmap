# Security

## What Grok-map can touch

- **No network.** Grok-map and grokmap-mcp make no network calls and need no API keys or accounts.
- **The MCP server is read-only, except the ledger.** Every tool is marked read-only except `record_understanding`, which appends lines to `.grokmap/ledger.jsonl` in the repository you point it at. The server writes nothing else, apart from a blame cache in `.grokmap/cache.json`. (The CLI also writes the files you ask for: a report, a badge, `grokmap init`'s config.)
- **Runs git, nothing else.** The only external program Grok-map starts is `git` (`blame`, `log`, `diff`, `rev-parse`), with arguments passed as a list, never through a shell. (`grokmap report --open` also opens the report in your web browser.)
- **Dependencies.** The core package has none. The MCP server adds only the official `mcp` Python SDK.

## Reporting a vulnerability

Please report it privately through [GitHub security advisories](https://github.com/Aadithya-kl/grokmap/security/advisories/new) rather than a public issue. You'll get a reply within 7 days, and a fix or a plan within 30.

## Supported versions

Only the latest release gets security fixes.
