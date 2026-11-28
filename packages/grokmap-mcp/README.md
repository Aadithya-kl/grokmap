# grokmap-mcp

<!-- mcp-name: io.github.Aadithya-kl/grokmap -->

The MCP server for [grokmap](https://github.com/Aadithya-kl/grokmap): it lets coding agents (Claude Code, Codex, Cursor, Gemini CLI, VS Code…) see which AI-written code **nobody on your team has shown they understand**, adjust how carefully they change it, and quiz you on it.

```json
{
  "mcpServers": {
    "grokmap": { "command": "uvx", "args": ["grokmap-mcp"] }
  }
}
```

Tools: `comprehension_risk`, `repo_status`, `who_understands`, `quiz_brief`, `record_understanding`, `pr_comprehension`, `ai_trend`, plus a `quiz_me` prompt. Everything runs locally on git history; no network calls, no API keys.

This package only installs `grokmap[mcp]` and the `grokmap-mcp` command. Docs, the CLI and the GitHub Action are in the [main repository](https://github.com/Aadithya-kl/grokmap).
