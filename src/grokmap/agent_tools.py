"""The logic behind grokmap's MCP tools, as plain functions that return JSON-ready dicts.

Kept free of any MCP dependency so it can be tested directly and reused by other integrations.
Every function takes `repo`, a path anywhere inside a git repository (default: current directory).
"""

from __future__ import annotations

import json
from pathlib import Path

from grokmap import gitutil, prdiff, trend
from grokmap.config import Config, load_config
from grokmap.ledger import METHODS, load_ledger
from grokmap.quiz import build_targets, format_ranges, mark, render_markdown, truncate
from grokmap.scan import scan_repo
from grokmap.score import Stats, evaluate

RISK_LEVELS = ("none", "low", "medium", "high", "very high")

ADVICE = {
    "none": "Written by people (or no AI-agent commits detected). Edit normally.",
    "low": "Most AI-written code here has been understood by someone. Edit normally, and mention what you changed.",
    "medium": "Some AI-written code here has not been checked by anyone. Keep changes focused and explain them clearly.",
    "high": (
        "Much of this is AI-written code nobody on the team has shown they understand. Prefer small, reviewable "
        "changes, explain the existing behavior before changing it, and offer the user a short grokmap quiz afterwards."
    ),
    "very high": (
        "Almost nobody understands this AI-written code. Before changing it, summarize how it works for the user and "
        "confirm the plan. Avoid broad refactors. Afterwards, offer a short grokmap quiz so the change does not add more debt."
    ),
}


def _root(repo: str | None) -> tuple[Path, Config]:
    root = gitutil.repo_root(Path(repo or ".").resolve())
    return root, load_config(root)


def _norm(path: str, root: Path) -> str:
    p = path.replace("\\", "/").strip()
    full = Path(p)
    if full.is_absolute():
        try:
            p = full.resolve().relative_to(root).as_posix()
        except ValueError:
            pass
    return p.removeprefix("./").rstrip("/")


def risk_level(st: Stats, critical: bool = False) -> str:
    if st.ai == 0:
        return "none"
    pct = st.debt_pct
    level = 1 if pct < 10 else 2 if pct < 35 else 3 if pct < 60 else 4
    if critical and level >= 2:
        level = min(level + 1, 4)
    return RISK_LEVELS[level]


def _stats_dict(st: Stats) -> dict:
    d = st.to_dict()
    d["understood_by"] = d.pop("people")
    d["agents"] = d.pop("tools")
    return d


def repo_status(repo: str | None = None, top: int = 10) -> dict:
    """Whole-repository summary: debt, AI share, who understands what, riskiest files."""
    root, cfg = _root(repo)
    scan = scan_repo(root, cfg)
    res = evaluate(scan, load_ledger(root), cfg)
    risky = sorted(((p, s) for p, s in res.files.items() if s.debt > 0), key=lambda x: -x[1].debt)[:top]
    return {
        "repo": root.name,
        "head": (scan.head or "")[:12],
        "total": _stats_dict(res.total),
        "risk": risk_level(res.total),
        "critical_paths": _stats_dict(res.critical) if res.critical_files else None,
        "riskiest_files": [
            {
                "path": p,
                "lines": s.lines,
                "ai_lines": s.ai,
                "unread": s.unread,
                "debt_pct": round(s.debt_pct, 1),
                "critical": p in res.critical_files,
            }
            for p, s in risky
        ],
    }


def comprehension_risk(paths: list[str], repo: str | None = None) -> dict:
    """Per-path risk before an edit: how much is AI-written, how much nobody has checked, and what to do about it."""
    root, cfg = _root(repo)
    tracked = [tf.path for tf in gitutil.tracked_files(root)]
    wanted: dict[str, list[str]] = {}
    for raw in paths:
        p = _norm(raw, root)
        if p in ("", "."):
            wanted[raw] = [t for t in tracked if cfg.is_included(t)]
        else:
            wanted[raw] = [t for t in tracked if (t == p or t.startswith(p + "/")) and cfg.is_included(t)]
    every = {f for files in wanted.values() for f in files}
    scan = scan_repo(root, cfg, only=every)
    res = evaluate(scan, load_ledger(root), cfg)

    results = []
    for raw, files in wanted.items():
        if not files:
            results.append({"path": raw, "found": False, "note": "Not a tracked file or folder (new files have no history yet)."})
            continue
        agg = Stats()
        crit = False
        for f in files:
            if f in res.files:
                agg.add(res.files[f])
                crit = crit or f in res.critical_files
        level = risk_level(agg, crit)
        entry = {
            "path": raw,
            "found": True,
            "files": len(files),
            "risk": level,
            "critical_path": crit,
            **{
                k: v
                for k, v in _stats_dict(agg).items()
                if k
                in ("lines", "ai", "understood", "skimmed", "fading", "unread", "debt_pct", "ai_pct", "agents", "understood_by")
            },
            "advice": ADVICE[level],
        }
        if len(files) > 1:
            worst = sorted((f for f in files if f in res.files and res.files[f].unread), key=lambda f: -res.files[f].unread)[:5]
            entry["most_unread_files"] = [{"path": f, "unread": res.files[f].unread} for f in worst]
        results.append(entry)
    return {"repo": root.name, "results": results}


def who_understands(path: str, repo: str | None = None) -> dict:
    """Who has shown they understand the AI-written code at a path, plus who has been changing it lately."""
    root, cfg = _root(repo)
    p = _norm(path, root)
    risk = comprehension_risk([p], str(root))["results"][0]
    recent = gitutil.run_git(["log", "-n", "200", "--format=%an <%ae>", "--", p or "."], root, check=False).splitlines()
    authors: dict[str, int] = {}
    for a in recent:
        authors[a] = authors.get(a, 0) + 1
    top_authors = sorted(authors.items(), key=lambda kv: -kv[1])[:5]
    return {
        "path": p or ".",
        "understood_by": risk.get("understood_by", {}),
        "ai_lines": risk.get("ai", 0),
        "unread": risk.get("unread", 0),
        "recent_committers": [{"name": a, "commits": n} for a, n in top_authors],
        "note": (
            "understood_by counts AI-written lines each person passed a grokmap quiz on. "
            "recent_committers is plain git history: committing code is not evidence of understanding it, "
            "especially when an agent wrote the change."
        ),
    }


def quiz_brief(
    paths: list[str] | None = None,
    uncommitted: bool = False,
    diff_base: str | None = None,
    who: str | None = None,
    max_lines: int = 200,
    repo: str | None = None,
) -> dict:
    """The lines a person has not yet shown they understand, plus the rules for running the quiz."""
    root, cfg = _root(repo)
    who = who or gitutil.current_user(root)
    diff_mode = bool(uncommitted or diff_base)
    scan = None if diff_mode else scan_repo(root, cfg)
    norm_paths = [_norm(p, root) for p in (paths or [])]
    targets = build_targets(root, cfg, who, scan, norm_paths, diff_base, False, diff_mode)
    targets, cut = truncate(targets, max_lines)
    specs = [f"{t.path}:{format_ranges(t.ranges)}" for t in targets]
    return {
        "who": who,
        "nothing_to_quiz": not targets,
        "truncated": cut,
        "line_count": sum(len(t.lines) for t in targets),
        "record_with": {"tool": "record_understanding", "paths": specs, "method": "quiz", "score": "<mean of grades, 0..1>"},
        "brief_markdown": render_markdown(targets, who, cut),
    }


def record_understanding(
    paths: list[str],
    score: float,
    method: str = "quiz",
    who: str | None = None,
    note: str = "",
    repo: str | None = None,
) -> dict:
    """Record that a person showed they understand files or line ranges (path or path:10-40,55-60)."""
    if method not in METHODS:
        raise ValueError(f"method must be one of {', '.join(METHODS)}")
    root, cfg = _root(repo)
    who = who or gitutil.current_user(root)
    specs = []
    for raw in paths:
        if ":" in raw and raw.rsplit(":", 1)[1].replace("-", "").replace(",", "").isdigit():
            p, r = raw.rsplit(":", 1)
            specs.append(f"{_norm(p, root)}:{r}")
        else:
            specs.append(_norm(raw, root))
    recs = mark(root, cfg, specs, score, method, who, None, note)
    state = "skimmed" if (method == "review" or (recs and recs[0].score < cfg.pass_score)) else "understood"
    return {
        "recorded": len(recs),
        "who": who,
        "score": round(recs[0].score, 3) if recs else None,
        "counts_as": state if recs else None,
        "lines": sum(len(r.hashes) for r in recs),
        "files": [r.path for r in recs],
        "ledger": ".grokmap/ledger.jsonl",
        "reminder": "Ask the user to commit .grokmap/ledger.jsonl with their change so the team shares it.",
    }


def pr_comprehension(base: str = "origin/main", repo: str | None = None) -> dict:
    """AI-written lines the current branch adds compared with `base`, and how many anyone understands."""
    root, cfg = _root(repo)
    try:
        delta = prdiff.compute(root, cfg, base)
    except gitutil.GitError as exc:
        raise ValueError(f"cannot compare with '{base}': fetch it first (git fetch origin) or pass another base") from exc
    data = prdiff.to_json(delta)
    data["markdown"] = prdiff.render_markdown(delta)
    return data


def ai_trend(by: str = "auto", since: str | None = None, repo: str | None = None) -> dict:
    """AI-written vs human-written lines added per week or month, by agent."""
    root, cfg = _root(repo)
    b, buckets = trend.collect(root, cfg, by, since)
    return trend.to_json(b, buckets)


def dumps(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)
