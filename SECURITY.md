# Security

## What Grok-map can touch

- **No network.** Grok-map and grokmap-mcp make no network calls and need no API keys or accounts.
- **The MCP server is read-only, except the ledger.** Every tool is marked read-only except `record_understanding`, which appends lines to `.grokmap/ledger.jsonl` in the repository you point it at. The server writes nothing else, apart from a blame cache in `.grokmap/cache.json`. (The CLI also writes the files you ask for: a report, a badge, `grokmap init`'s config, and `grokmap ignore`'s changes to `.grokmap.toml`.)
- **Runs git, nothing else.** The only external program Grok-map starts is `git` (`blame`, `log`, `diff`, `rev-parse`), with arguments passed as a list, never through a shell. (`grokmap report --open` also opens the report in your web browser.)
- **Dependencies.** The core package has none. The MCP server adds only the official `mcp` Python SDK. The VS Code extension has no runtime dependencies.
- **The VS Code extension** runs only in folders you trust (VS Code's Workspace Trust). The command it runs, `grokmap.command`, can only be set in your user settings, never by a repository's `.vscode/settings.json`. A quiz taken in its panel sends the lines being quizzed, and your answers, to the AI model you picked in VS Code; nothing else leaves your machine.

## Hardening against hostile repositories and agents

Grok-map is meant to be pointed at code you didn't write, and its MCP server takes arguments from an AI agent that may have read untrusted text. So:

- **Revisions are never passed to git as given.** A base branch from the CLI or an agent (`--base`, `--diff`, `pr_comprehension`) is resolved to a commit hash first, and one that starts with `-` is refused. Otherwise a value such as `--output=FILE` would make `git diff` overwrite a file.
- **Git can't run programs named in the repository's config.** Every git call turns off the fsmonitor hook and external diff tools (`-c core.fsmonitor=false -c diff.external=`, `--no-ext-diff`, `--no-textconv`), so a planted `.git/config` doesn't get code execution through Grok-map.
- **Symlinks are never followed.** Quizzes and `grokmap mark` only read regular files inside the repository. A branch that adds a symlink to `~/.ssh` or `~/.aws` can't get those files into a quiz brief.
- **Output is escaped where it lands.** File names, author names and commit messages are escaped in the HTML report (data is embedded with `<`, `>` and `&` encoded), in the pull request comment (names are put in code spans they can't break out of, so no injected links or @mentions), in VS Code hovers, and in the extension's panel.
- **The GitHub Action** passes inputs to shell steps through environment variables, posts its comment from a file, and only updates a previous comment written by a bot.

## Trust model

- **The ledger is a shared record, not proof.** Anyone who can commit, and any coding agent you allow to call `record_understanding`, can add a line to `.grokmap/ledger.jsonl`, including in someone else's name. Review changes to the ledger in pull requests the way you review code: git shows who committed each line.
- **The Docker image** turns off git's folder-ownership check (`safe.directory '*'`), because a mounted repository is owned by a different user than the container's. That check exists to stop config-driven code execution, which the hardening above blocks independently. Only mount repositories you mean to inspect.

## Reporting a vulnerability

Please report it privately through [GitHub security advisories](https://github.com/Aadithya-kl/grokmap/security/advisories/new) rather than a public issue. You'll get a reply within 7 days, and a fix or a plan within 30.

## Supported versions

Only the latest release gets security fixes.
