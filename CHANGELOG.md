# Changelog

## Unreleased

## 0.7.0

- **A Grok-map panel in VS Code.** Click the Grok-map icon in the sidebar (or open it as an editor tab, like a chat):
  - **No folder to open first.** Pick any git repository from the panel; it remembers your recent ones.
  - **Dashboard:** how much of the AI-written code anyone understands, the files that need attention (click to open, one click to quiz), who understands what, and which agents wrote it. It follows the file you have open.
  - **Quizzes right in the panel.** One question at a time, then a score, per-question feedback and a good answer for each. The result is saved to the ledger for exactly the quizzed lines, and the gutter updates. Questions are written and graded by the AI model you already have in VS Code (for example GitHub Copilot), with no API keys. A score of 0 isn't recorded, so failed code stays unchecked rather than counting as skimmed.
  - **A start screen before every quiz** shows exactly which files and lines it covers, with **Quick** (3 questions) or **Thorough** (4 to 6), and **Pick another file**. Nothing is sent to a model until you press Start.
  - **Finish now** grades what you've answered; unanswered questions count as "I don't know". **Retake with new questions** from the result.
  - **Explain it instead**: describe the code in a paragraph and get it graded, recorded as `--method explain`.
  - **Commit to git** on the result commits only `.grokmap/ledger.jsonl` (never your other changes, and never pushes), so your team sees it.
  - **New code by week**: a small chart of lines added by AI and by people, from `grokmap trend`.
  - **Install for me**: no `grokmap` command yet? One click installs it with uv or pip and finds a command that runs it.
  - **A welcome guide** (VS Code's Get started page) walks new users through install, picking a repository, a first quiz and sharing the result.
  - **This branch**: the AI-written lines your branch adds compared with `main` (or, on `main`, what you haven't pushed), how many you've checked, and **Quiz me before I push**.
  - **Code only**, on by default: tests, test data, docs, config and generated files are left out of the numbers and the lists. One switch turns it off.
  - **Files or Folders**: "Needs attention" groups by folder at a depth that splits the repository usefully, so a large codebase shows which areas nobody understands. Quiz a whole folder.
  - **Mark as reviewed** (counts as skimmed, never as understood) and **Ignore** on every row, both with a confirmation first.
  - **Switch or close the repository** from the repository chip (recent ones, another folder, or back to the start screen).
  - **No model? One-click hand-off** to Claude Code, Copilot Chat, Kilo Code, Cline, Roo Code or Cursor's chat: the quiz is copied (or filled in) and the assistant records your score through the MCP server.
  - Follows your light or dark theme, keyboard friendly, respects reduced motion.
- **`grokmap ignore PATH…`**: leave files or folders out of Grok-map. Adds them to `exclude` in `.grokmap.toml` (creating it if needed) without touching the rest of the file; `--remove` undoes it. Refuses to rewrite settings kept in `pyproject.toml`.
- "Quiz me" in hovers and menus now opens the panel quiz. The old copy-a-brief command is still there as **Grok-map: Copy a quiz brief for my AI assistant**.

## 0.6.2

- **The project is now called Grok-map** everywhere people read the name: README, website, VS Code extension, MCP server title, HTML report and PR comments. Install names and commands don't change: `pip install grokmap`, `uvx grokmap-mcp`, the `grokmap` command and the `aadithya-kl.grokmap` extension ID all stay the same, so nothing breaks.

## 0.6.1

- **New logo**: the orbit-ring G and M, in silver and mint. It is the VS Code extension's icon and appears in the README, on the website (with a favicon), and on the social preview card. Source files are in `docs/` (`logo.svg`, `logo-mark.svg`, and `logo-mark-light.svg` for light backgrounds).

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
