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
| `action.yml` | the GitHub Action |

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
