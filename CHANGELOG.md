# Changelog

## Unreleased

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
