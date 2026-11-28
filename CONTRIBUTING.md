# Contributing to grokmap

Thanks for helping. grokmap is small on purpose: one Python package with no dependencies, a single-file HTML report, and an agent skill. Contributions that keep it that way are the easiest to merge.

## Set up

```bash
git clone https://github.com/Aadithya-kl/grokmap && cd grokmap
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Try your change on the demo repository:

```bash
python scripts/make_demo.py /tmp/grokmap-demo --with-ledger
grokmap -C /tmp/grokmap-demo status
grokmap -C /tmp/grokmap-demo report --open
```

## Where things live

| Path | What it does |
|---|---|
| `src/grokmap/scan.py` | blames every file at HEAD, keeps a per-blob cache |
| `src/grokmap/detect.py` | decides whether a commit was written by an AI agent |
| `src/grokmap/ledger.py` | the append-only understanding ledger |
| `src/grokmap/score.py` | combines blame and ledger into per-line states and debt |
| `src/grokmap/quiz.py` | quiz briefs and `grokmap mark` |
| `src/grokmap/prdiff.py`, `trend.py` | PR summaries and history over time |
| `src/grokmap/report_template.html` | the whole HTML report (plain JS, no build step) |
| `skills/grokmap/SKILL.md` | instructions coding agents follow to run quizzes |
| `src/grokmap/lines.py` | per-line states for one file, for editors (`grokmap lines`) |
| `src/grokmap/agent_tools.py`, `mcp_server.py`, `mcp_models.py` | the MCP server: plain functions, the tool wrappers, typed results |
| `editors/vscode/` | the VS Code extension (TypeScript; `npm test` there) |
| `action.yml` | the GitHub Action |

## Good first issues: where to start

Each of these is a few hours of work, has a clear "done", and touches one or two files. Comment on the issue to claim it, and ask anything there: you'll get an answer within a day.

| Issue | Start here | Done when |
|---|---|---|
| [#1 Detect Cline, Roo Code and Zed's agent](https://github.com/Aadithya-kl/grokmap/issues/1) | `BUILTIN_SIGNATURES` in `src/grokmap/detect.py`; follow "Adding detection" below | a test in `tests/test_detect_config.py` per agent, with a link to a real commit in the PR |
| [#2 Detect Amp and OpenHands](https://github.com/Aadithya-kl/grokmap/issues/2) | same as #1 | same as #1 |
| [#6 Skip comment-only and import lines](https://github.com/Aadithya-kl/grokmap/issues/6) | `is_meaningful()` in `src/grokmap/scan.py`, plus a `skip_comments` option in `src/grokmap/config.py` | off by default; a test in `tests/test_scan_score.py` shows the counts change only when it's on |
| [#9 Keyboard and screen-reader support for the treemap](https://github.com/Aadithya-kl/grokmap/issues/9) | the `#treemap` code in `src/grokmap/report_template.html` (plain JS, no build) | Tab moves between files, Enter opens one, each tile has an `aria-label`; attach light and dark screenshots |
| [#10 Example quiz sessions with Codex, Cursor and Gemini CLI](https://github.com/Aadithya-kl/grokmap/issues/10) | run a quiz on the demo repo (see "Set up") with your agent | a short transcript per agent in `docs/`, linked from the README |

## Adding detection for another coding agent

This is the most useful kind of first contribution.

1. Find a **real** commit made by the agent (a public repo is fine) and note what marks it: a co-author trailer, a bot author, a message prefix.
2. Add a signature to `BUILTIN_SIGNATURES` in `src/grokmap/detect.py`. Prefer trailers and bot accounts over words in the message. A pattern must never match normal human commits (see `test_human_commits_stay_human`).
3. Add a case to `test_builtin_signatures` in `tests/test_detect_config.py`, and a negative case if the name could appear in ordinary commit messages.
4. Add the agent to the table in the README and link the example commit in your PR.

## Before you open a pull request

```bash
ruff check src tests scripts
ruff format src tests scripts
pytest
```

- Keep the runtime dependency list empty. Development tools are fine.
- If you touch the report, open it in light and dark mode and attach a screenshot to the PR.
- Detection must stay conservative: a false "AI-written" label is worse than a missed one.
- Update `CHANGELOG.md` under "Unreleased".

## Reporting bugs

Open an issue with your grokmap version (`grokmap --version`), the command you ran and what you expected. For detection problems, include the commit message and author line (anonymize them if you need to).
