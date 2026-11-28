# grokmap for VS Code

**See which AI-written code nobody on your team understands, right in the gutter.**

grokmap traces every line to the commit that wrote it, recognises commits made by AI coding agents (Claude Code, Copilot, Cursor, Codex, Aider, Devin, Gemini…), and checks them against a ledger, kept in git, of who has *shown* they understand that code. This extension paints the result next to your code:

| Gutter | Meaning |
|---|---|
| 🟥 red | AI-written, and nobody has checked it |
| 🟧 orange | Only skimmed: reviewed, or quizzed with a low score |
| 🟨 yellow | Understood, but more than 180 days ago |
| 🟩 green | Someone passed a quiz, explained it or paired on it |
| none | Written by a person, or not committed yet |

- **Hover** a coloured block to see which agent wrote it, in which commit, and who understands it.
- **Status bar** shows the file's comprehension debt. Click it for who understands what.
- **Quiz me on this file** (command palette, or the link in the hover) copies a short quiz brief for your coding agent. Paste it into Copilot Chat, Claude Code or Cursor: the agent asks you 2 to 6 questions and records the result, and the gutter turns green.

It follows your edits as you type, and updates when anyone records a quiz (the ledger is just a file in the repo).

## Requirements

The `grokmap` command-line tool, version 0.5 or later:

```bash
pip install grokmap        # or: pipx install grokmap
```

No install? Set **grokmap.command** to `uvx grokmap`. Everything runs locally on your git history: no network calls, no account, no API keys.

## Settings

| Setting | Default | |
|---|---|---|
| `grokmap.enabled` | `true` | Show the gutter colours (also: **grokmap: Toggle gutter colours**). |
| `grokmap.command` | `grokmap` | How to run grokmap, e.g. `uvx grokmap` or a full path. |
| `grokmap.tintLines` | `false` | Also tint the background of AI-written lines. |
| `grokmap.statusBar` | `true` | Show the file's debt in the status bar. |

## More

grokmap also has a CLI with an HTML heatmap, a GitHub Action that comments on pull requests, and an MCP server so your coding agent checks who understands a file before it edits it. See the [project README](https://github.com/Aadithya-kl/grokmap).
