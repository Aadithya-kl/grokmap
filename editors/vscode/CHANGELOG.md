# Changelog

## 0.7.1

- Security: `grokmap.command` can only be set in user settings, never by a repository's `.vscode/settings.json`, and the extension runs only in trusted workspaces. Commit authors in hovers are escaped; the panel opens only `https://` links.
- Needs grokmap 0.7.1 for the command-line fixes (validated revisions, no repo-configured git programs, no symlinks followed).

## 0.7.0

- **Grok-map panel**: click the Grok-map icon in the activity bar (or open it in an editor tab). Pick any git repository without opening it as a folder, see how much AI-written code anyone understands, which files need attention and who understands what.
- **Quizzes in the panel**, written and graded by the AI model you already have in VS Code (such as GitHub Copilot). Results are saved to the ledger and the gutter updates.
- **Start screen** with the exact files and lines, **Quick** or **Thorough**, and **Pick another file**. **Finish now**, **Retake**, and **Explain it instead**.
- **Commit to git** on the result commits only the ledger, never pushes.
- **This branch** card with **Quiz me before I push**; **Code only** switch (on by default); **Files / Folders** views; **Mark as reviewed** and **Ignore** on every row; switch or close the repository from the chip.
- **New code by week** chart, **Install for me** for the command-line tool, and a **Get started** guide.
- **No model?** One click hands the quiz to Claude Code, Copilot Chat, Kilo Code, Cline, Roo Code or Cursor's chat.

## 0.6.2

- Renamed to Grok-map. The extension ID stays `aadithya-kl.grokmap`, so updates arrive as usual.

## 0.6.1

- New icon.

## 0.6.0

- Published on the VS Code Marketplace. No changes to the extension itself; it ships with each grokmap release so versions stay in step.

## 0.5.0

- First release: gutter colours by comprehension state, hovers with the writing agent, commit and who understands it, status bar debt, and a "Quiz me on this file" command.
