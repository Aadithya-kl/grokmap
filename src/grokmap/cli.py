"""grokmap command line."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from grokmap import __version__, gitutil, prdiff, trend
from grokmap.badge import render_badge
from grokmap.config import DEFAULT_TOML, load_config
from grokmap.ledger import METHODS, ledger_path, load_ledger
from grokmap.quiz import build_targets, mark, render_json, render_markdown, truncate
from grokmap.report import render_report, write_report
from grokmap.scan import scan_repo
from grokmap.score import evaluate

ROW = "{:<52} {:>7} {:>7} {:>7} {:>7}"


def _use_color() -> bool:
    return sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _use_color() else text


def _progress(done: int, total: int) -> None:
    if sys.stderr.isatty() and total > 50:
        sys.stderr.write(f"\rgrokmap: blaming files {done}/{total}")
        if done == total:
            sys.stderr.write("\r" + " " * 40 + "\r")
        sys.stderr.flush()


def _context(args):
    root = gitutil.repo_root(Path(args.repo).resolve())
    cfg = load_config(root)
    return root, cfg


def _analyze(root, cfg, no_cache=False):
    scan = scan_repo(root, cfg, use_cache=not no_cache, progress=_progress)
    result = evaluate(scan, load_ledger(root), cfg)
    return scan, result


def _debt_label(pct: float, ai: int) -> str:
    if ai == 0:
        return _c("no AI code", "2")
    code = "32" if pct < 10 else "33" if pct < 35 else "31"
    return _c(f"{pct:.1f}%", code)


def cmd_status(args) -> int:
    root, cfg = _context(args)
    scan, res = _analyze(root, cfg, args.no_cache)
    if args.json:
        out = {
            "repo": root.name,
            "head": scan.head,
            "total": res.total.to_dict(),
            "critical": res.critical.to_dict() if res.critical_files else None,
            "files": {p: s.to_dict() for p, s in sorted(res.files.items())},
        }
        print(json.dumps(out, indent=2))
        return 0
    if args.markdown:
        print(_markdown_summary(root.name, scan.head, res, args.top))
        return 0
    t = res.total
    if scan.head is None:
        print("grokmap: this repository has no commits yet.")
        return 0
    print(f"{_c('grokmap', '1')} · {root.name} @ {scan.head[:10]}")
    print()
    print(f"  Comprehension debt   {_debt_label(t.debt_pct, t.ai)}")
    print(f"  Lines scanned        {t.lines:,} in {len(res.files):,} files")
    print(
        f"  Written by AI        {t.ai:,} lines ({t.ai_pct:.1f}%)"
        + (f"  — {', '.join(f'{k} {v:,}' for k, v in t.tools.most_common())}" if t.tools else "")
    )
    if t.ai:
        print(f"    understood         {t.understood:,}  ({100 * t.understood / t.ai:.0f}%)")
        print(f"    fading             {t.fading:,}")
        print(f"    skimmed            {t.skimmed:,}")
        print(f"    nobody checked     {t.unread:,}")
    if res.critical_files:
        c = res.critical
        print(f"  Critical paths       {_debt_label(c.debt_pct, c.ai)} debt over {c.lines:,} lines")
    if t.people:
        print(f"  Understood by        {', '.join(f'{p} ({n:,})' for p, n in t.people.most_common(5))}")
    risky = sorted(((p, s) for p, s in res.files.items() if s.debt > 0), key=lambda x: -x[1].debt)[: args.top]
    if risky:
        print()
        print(_c(ROW.format("Riskiest files", "lines", "AI", "unread", "debt"), "1"))
        for p, s in risky:
            name = p if len(p) <= 52 else "…" + p[-51:]
            print(ROW.format(name, s.lines, s.ai, s.unread, f"{s.debt_pct:.0f}%"))
        print()
        print("Pay it down: ask your coding agent to run `grokmap quiz <file>` and quiz you.")
    elif t.ai:
        print()
        print("Every AI-written line has been understood by someone. Nice.")
    return 0


def _markdown_summary(name, head, res, top: int) -> str:
    t = res.total
    lines = [f"### grokmap · {name} @ `{(head or '')[:10]}`", ""]
    if not t.ai:
        lines.append("No AI-written code detected. Comprehension debt: **0%**.")
        return "\n".join(lines)
    lines += [
        "| | |",
        "|---|---|",
        f"| Comprehension debt | **{t.debt_pct:.1f}%** |",
        f"| Written by AI | {t.ai:,} of {t.lines:,} lines ({t.ai_pct:.1f}%) |",
        f"| AI code understood | {t.understood:,} lines ({t.understood_pct_of_ai:.0f}%) |",
        f"| Nobody has checked | {t.unread:,} lines |",
    ]
    if res.critical_files:
        lines.append(f"| Debt on critical paths | {res.critical.debt_pct:.1f}% |")
    if t.tools:
        lines.append(f"| Agents | {', '.join(f'{k} ({v:,})' for k, v in t.tools.most_common())} |")
    risky = sorted(((p, s) for p, s in res.files.items() if s.debt > 0), key=lambda x: -x[1].debt)[:top]
    if risky:
        lines += ["", "**Riskiest files**", "", "| File | AI lines | Unread | Debt |", "|---|---:|---:|---:|"]
        lines += [f"| `{p}` | {s.ai:,} | {s.unread:,} | {s.debt_pct:.0f}% |" for p, s in risky]
    return "\n".join(lines)


def cmd_report(args) -> int:
    root, cfg = _context(args)
    scan, res = _analyze(root, cfg, args.no_cache)
    out = Path(args.output) if args.output else root / "grokmap-report.html"
    by, buckets = trend.collect(root, cfg)
    write_report(out, render_report(scan, res, args.name or root.name, trend.to_json(by, buckets), args.note))
    print(f"grokmap: wrote {out}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_trend(args) -> int:
    root, cfg = _context(args)
    by, buckets = trend.collect(root, cfg, args.by, args.since)
    if args.json:
        print(json.dumps(trend.to_json(by, buckets), indent=2))
    else:
        print(trend.render_text(by, buckets))
    return 0


def cmd_diff(args) -> int:
    root, cfg = _context(args)
    try:
        delta = prdiff.compute(root, cfg, args.base)
    except gitutil.GitError:
        print(f"grokmap diff: can't compare with '{args.base}'. Fetch it first (e.g. git fetch origin main).", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(prdiff.to_json(delta), indent=2))
    elif args.markdown:
        print(prdiff.render_markdown(delta))
    else:
        if not delta.ai:
            print(f"grokmap diff vs {args.base}: {delta.human:,} lines added, none by AI.")
        else:
            print(
                f"grokmap diff vs {args.base}: {delta.ai:,} AI-written lines added "
                f"({', '.join(f'{k} {v:,}' for k, v in delta.tools.most_common())}), "
                f"{delta.understood:,} understood, {delta.unread:,} nobody has checked."
            )
            for f in sorted(delta.files, key=lambda f: -f.unread):
                if f.ai:
                    print(f"  {f.path}: {f.ai} AI lines, {f.unread} unchecked")
            if delta.unread:
                print(f"Quiz yourself: grokmap quiz --diff {args.base}")
    if args.max_unread is not None and delta.unread > args.max_unread:
        return 1
    return 0


def cmd_badge(args) -> int:
    root, cfg = _context(args)
    _, res = _analyze(root, cfg, args.no_cache)
    svg = render_badge(res.total.debt_pct, res.total.ai, args.label)
    out = Path(args.output) if args.output else root / "grokmap-badge.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"grokmap: wrote {out} ({res.total.debt_pct:.0f}% comprehension debt)")
    return 0


def cmd_check(args) -> int:
    root, cfg = _context(args)
    _, res = _analyze(root, cfg, args.no_cache)
    limit = args.max_debt if args.max_debt is not None else cfg.max_debt
    stats = res.critical if args.critical else res.total
    scope = "critical paths" if args.critical else "repository"
    if args.critical and not res.critical_files:
        print("grokmap check: no critical paths configured (set `critical = [...]` in .grokmap.toml); skipping.")
        return 0
    ok = stats.debt_pct <= limit
    verdict = _c("PASS", "32") if ok else _c("FAIL", "31")
    print(f"grokmap check {verdict}: {scope} comprehension debt {stats.debt_pct:.1f}% (limit {limit:.0f}%)")
    if not ok:
        files = res.critical_files if args.critical else list(res.files)
        worst = sorted(files, key=lambda p: -res.files[p].debt)[:5]
        print("Biggest contributors:")
        for p in worst:
            s = res.files[p]
            if s.debt > 0:
                print(f"  {p}: {s.unread} unread AI lines, {s.debt_pct:.0f}% debt")
        print("Run `grokmap quiz <file>` with your coding agent to bring it down.")
    return 0 if ok else 1


def cmd_quiz(args) -> int:
    root, cfg = _context(args)
    who = args.who or gitutil.current_user(root)
    diff_mode = bool(args.diff or args.staged or args.uncommitted)
    scan = None if diff_mode else scan_repo(root, cfg, progress=_progress)
    base = args.diff if args.diff and args.diff != "WORKTREE" else None
    paths = [p.replace("\\", "/").removeprefix("./") for p in args.paths]
    targets = build_targets(root, cfg, who, scan, paths, base, args.staged, diff_mode, include_human=args.include_human)
    targets, cut = truncate(targets, args.max_lines)
    print(render_json(targets, who, cut) if args.format == "json" else render_markdown(targets, who, cut, args.questions))
    return 0


def cmd_mark(args) -> int:
    root, cfg = _context(args)
    who = args.who or gitutil.current_user(root)
    try:
        recs = mark(root, cfg, args.paths, args.score, args.method, who, args.lines, args.note or "")
    except (ValueError, FileNotFoundError) as exc:
        print(f"grokmap mark: {exc}", file=sys.stderr)
        return 2
    if not recs:
        print("grokmap mark: nothing to record (no meaningful lines in those files).")
        return 1
    n = sum(len(r.hashes) for r in recs)
    state = "understood" if args.method != "review" and recs[0].score >= cfg.pass_score else "skimmed"
    print(f"grokmap: recorded {who} — {args.method}, score {recs[0].score:.2f} ({state}) — {n} lines in {len(recs)} file(s)")
    print(f"         ledger: {ledger_path(root).relative_to(root)} (commit it so your team shares it)")
    return 0


def cmd_who(args) -> int:
    root, cfg = _context(args)
    scan, res = _analyze(root, cfg)
    path = args.path.replace("\\", "/").removeprefix("./").rstrip("/")
    matches = [p for p in res.files if p == path or p.startswith(path + "/")]
    if not matches:
        print(f"grokmap who: no scanned files under {path}")
        return 1
    from grokmap.score import Stats

    agg = Stats()
    for p in matches:
        agg.add(res.files[p])
    print(f"{path}: {agg.lines:,} lines, {agg.ai:,} written by AI, debt {agg.debt_pct:.1f}%")
    if agg.people:
        for person, n in agg.people.most_common():
            print(f"  {person}: understands {n:,} of {agg.ai:,} AI lines ({100 * n / max(agg.ai, 1):.0f}%)")
    else:
        print("  Nobody has shown they understand the AI-written code here yet.")
    return 0


def cmd_init(args) -> int:
    root = gitutil.repo_root(Path(args.repo).resolve())
    cfg_path = root / ".grokmap.toml"
    if not cfg_path.exists():
        cfg_path.write_text(DEFAULT_TOML, encoding="utf-8")
        print(f"grokmap: wrote {cfg_path.name}")
    else:
        print(f"grokmap: {cfg_path.name} already exists, left it alone")
    state = root / ".grokmap"
    state.mkdir(exist_ok=True)
    (state / ".gitignore").write_text("# local cache, safe to delete\ncache.json\n", encoding="utf-8")
    ledger = ledger_path(root)
    if not ledger.exists():
        ledger.write_text("", encoding="utf-8")
    ga = root / ".gitattributes"
    line = ".grokmap/ledger.jsonl merge=union"
    existing = ga.read_text(encoding="utf-8") if ga.exists() else ""
    if line not in existing:
        ga.write_text(existing + ("" if existing.endswith("\n") or not existing else "\n") + line + "\n", encoding="utf-8")
        print("grokmap: added union merge for the ledger to .gitattributes")
    print("grokmap: ready. Next: `grokmap status`, then install the agent skill (see README).")
    return 0


def cmd_mcp(args) -> int:
    try:
        from grokmap.mcp_server import main as serve
    except ImportError as exc:
        print(f"grokmap mcp: {exc}", file=sys.stderr)
        return 2
    import os

    if args.repo and args.repo != ".":
        os.chdir(args.repo)
    serve()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="grokmap",
        description="Measure comprehension debt: AI-written code that nobody on the team has shown they understand.",
    )
    p.add_argument("--version", action="version", version=f"grokmap {__version__}")
    p.add_argument("-C", "--repo", default=".", help="path inside the git repository (default: .)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="summary of comprehension debt and the riskiest files")
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--json", action="store_true", help="machine-readable output")
    s.add_argument("--markdown", action="store_true", help="markdown summary (for PR comments and CI job summaries)")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("report", help="write the interactive HTML heatmap")
    s.add_argument("-o", "--output")
    s.add_argument("--name", help="project name shown in the report")
    s.add_argument("--open", action="store_true", help="open it in a browser")
    s.add_argument("--note", help="a line of text shown under the title (e.g. 'Demo data')")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("trend", help="AI-written vs human-written lines added over time")
    s.add_argument("--by", choices=("auto", "week", "month"), default="auto")
    s.add_argument("--since", help="only commits after this date, e.g. 2026-01-01 or '6 months ago'")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_trend)

    s = sub.add_parser("diff", help="AI-written lines a branch adds, and how many are understood (for PRs)")
    s.add_argument("--base", default="origin/main", help="branch to compare with (default: origin/main)")
    s.add_argument("--markdown", action="store_true", help="markdown for a PR comment")
    s.add_argument("--json", action="store_true")
    s.add_argument("--max-unread", type=int, help="exit 1 when more AI lines than this are unchecked")
    s.set_defaults(func=cmd_diff)

    s = sub.add_parser("badge", help="write an SVG README badge")
    s.add_argument("-o", "--output")
    s.add_argument("--label", default="comprehension debt")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_badge)

    s = sub.add_parser("check", help="exit 1 when debt is above the limit (for CI)")
    s.add_argument("--max-debt", type=float, help="limit in percent (default: max_debt from config, 40)")
    s.add_argument("--critical", action="store_true", help="only check paths listed as critical in config")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("quiz", help="print a quiz brief for your coding agent")
    s.add_argument("paths", nargs="*", help="files or folders (default: whole repo)")
    s.add_argument("--uncommitted", action="store_true", help="quiz on changes not yet committed (incl. new files)")
    s.add_argument("--staged", action="store_true", help="quiz on staged changes")
    s.add_argument("--diff", metavar="REV", help="quiz on what changed since REV (e.g. main, HEAD~3)")
    s.add_argument("--max-lines", type=int, default=200, help="cap the brief at this many lines (0 = no cap)")
    s.add_argument("--questions", type=int, default=3, help="minimum number of questions")
    s.add_argument("--include-human", action="store_true", help="also quiz on human-written code")
    s.add_argument("--who", help="person being quizzed (default: git user.email)")
    s.add_argument("--format", choices=("md", "json"), default="md")
    s.set_defaults(func=cmd_quiz)

    s = sub.add_parser("mark", help="record that someone understands files or lines")
    s.add_argument("paths", nargs="+", help="files or folders; use path:10-40,55-60 for line ranges")
    s.add_argument("--score", type=float, required=True, help="quiz score 0..1 (or 0..100)")
    s.add_argument("--method", choices=METHODS, default="quiz")
    s.add_argument("--lines", help="line ranges for a single file, e.g. 10-40,55-60")
    s.add_argument("--who", help="person (default: git user.email)")
    s.add_argument("--note", help="optional note stored with the record")
    s.set_defaults(func=cmd_mark)

    s = sub.add_parser("who", help="who understands the AI-written code in a file or folder")
    s.add_argument("path")
    s.set_defaults(func=cmd_who)

    s = sub.add_parser("mcp", help='run the MCP server over stdio for coding agents (needs: pip install "grokmap[mcp]")')
    s.set_defaults(func=cmd_mcp)

    s = sub.add_parser("init", help="add config, ledger and .gitattributes to this repo")
    s.set_defaults(func=cmd_init)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except gitutil.GitError as exc:
        print(f"grokmap: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # output piped into `head` or similar: stop quietly
        import os

        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
