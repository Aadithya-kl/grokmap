# Changelog

## Unreleased

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
