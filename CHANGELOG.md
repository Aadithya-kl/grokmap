# Changelog

## Unreleased

## 0.6.0

- **`grokmap hook install`**: a git pre-push hook that tells you when you're pushing AI-written lines nobody has shown they understand, and how to fix it (`grokmap quiz --diff <base>`). Reminds by default; `--block` stops the push (`--no-verify` still skips it). Leaves existing hooks alone unless you pass `--force`. Closes #5.
- The VS Code extension is on the Marketplace: search **grokmap** in Extensions. The README links it.
- The VS Code extension ships from its own workflow (`extension.yml`): it is attached to each release, published to the VS Code Marketplace with Trusted Publishing (no token), and to Open VSX (token for the first versions, then Trusted Publishing).

## 0.5.0

- **VS Code extension** (`editors/vscode`): colours AI-written lines in the gutter by whether anyone understands them, with hovers naming the agent, commit and who understands it, the file's debt in the status bar, and a "Quiz me on this file" command. Follows unsaved edits. Works in VS Code, Cursor, Windsurf and VSCodium; the `.vsix` is attached to each GitHub release.
- **`grokmap lines FILE`**: per-line states for one file as an editor sees it (`--json`; `--stdin` blames unsaved text), with uncommitted lines marked as such.
- An animated demo at the top of the README and on the website.
- CONTRIBUTING: where to start on each good first issue.

## 0.4.0

- **Structured output.** Every MCP tool declares an output schema and returns `structuredContent`, with a description on each field, so agents can read results without parsing text. The JSON text is still sent for older clients.
- CI builds both packages, hands them to a second job and installs them there, the same way the release does.
- GitHub Actions updated to their latest majors, pinned to commit SHAs.

## 0.3.1

- Clearer MCP tool descriptions: when to use each tool, which sibling to use instead, and what it returns.
- Listed on Glama and cursor.directory; OpenSSF Scorecard, CodeQL and a SECURITY.md describing what grokmap can touch.

## 0.3.0

- **MCP server.** `uvx grokmap-mcp` (or `grokmap mcp` with `pip install "grokmap[mcp]"`) gives coding agents seven tools: `comprehension_risk`, `repo_status`, `who_understands`, `quiz_brief`, `record_understanding`, `pr_comprehension` and `ai_trend`, plus a `quiz_me` prompt. Agents can check how well a file is understood before they change it.
- Published to the official MCP Registry as `io.github.Aadithya-kl/grokmap`; the Claude Code plugin now wires up the server too.
- The core package still has zero dependencies; the MCP SDK is only pulled in by the `mcp` extra.

## 0.2.1

- Detect Charm Crush commits, `Assisted-by: Claude` / Copilot / Codex trailers, Copilot Autofix and "(Written by Copilot)".
- A generic `Assisted-by:` trailer only counts as AI when it names an AI (it can name a person).
- New website: landing page, "What is comprehension debt?" explainer and a study of 18 open-source repositories; the demo moved to `/demo/`.

## 0.2.0

- `grokmap diff`: the AI-written lines a branch adds and how many are understood, as text, JSON or a PR comment. `--max-unread` gates merges.
- GitHub Action posts one PR comment and keeps it updated; new `comment`, `max-unread` and `github-token` inputs.
- `grokmap trend`: AI-written vs human-written lines added per week or month, by agent; also a chart in the report.
- `grokmap report --note` adds a line under the title.
- Live demo on GitHub Pages, built from `scripts/make_demo.py --with-ledger`.
- Partial scans keep the rest of the blame cache.
- Fixed the release workflow's YAML.

## 0.1.0

- First release: blame-based attribution, AI-agent detection, understanding ledger, quiz briefs, HTML heatmap, badge, `check`, GitHub Action and agent skill.
