"""How much of the code added over time was written by AI agents (from `git log --numstat`)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from grokmap import gitutil
from grokmap.config import Config
from grokmap.detect import Detector

_BRACE_RENAME = re.compile(r"\{([^{}]*) => ([^{}]*)\}")


def renamed_path(path: str) -> str:
    """numstat shows renames as `src/{old => new}/f.py` or `old.py => new.py`; keep the new path."""
    if "=>" not in path:
        return path
    if "{" in path:
        return re.sub(r"//+", "/", _BRACE_RENAME.sub(lambda m: m.group(2), path))
    return path.split(" => ", 1)[1]


@dataclass
class Bucket:
    start: date
    human: int = 0
    tools: Counter = field(default_factory=Counter)

    @property
    def ai(self) -> int:
        return sum(self.tools.values())

    @property
    def total(self) -> int:
        return self.human + self.ai


def bucket_start(d: date, by: str) -> date:
    if by == "month":
        return d.replace(day=1)
    return d - timedelta(days=d.weekday())  # Monday


def _next(d: date, by: str) -> date:
    if by == "month":
        return date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return d + timedelta(days=7)


def collect(root: Path, cfg: Config, by: str = "auto", since: str | None = None) -> tuple[str, list[Bucket]]:
    """Lines added per period, split into human and per-agent. Merge commits are skipped."""
    fmt = "%x1e%H%x00%an%x00%ae%x00%ct%x00%B%x1f"
    args = ["log", "--no-merges", "--numstat", "-M", f"--format={fmt}", "HEAD"]
    if since:
        args.append(f"--since={since}")
    if gitutil.head_sha(root) is None:
        return "week", []
    out = gitutil.run_git(args, root)
    detector = Detector.build(cfg.ai_patterns, cfg.ai_commits)

    rows: list[tuple[date, str | None, int]] = []
    for record in out.split("\x1e"):
        if not record.strip():
            continue
        head, _, stats = record.partition("\x1f")
        parts = head.split("\x00")
        if len(parts) < 5:
            continue
        sha, name, email, ts, message = parts[0], parts[1], parts[2], parts[3], "\x00".join(parts[4:])
        try:
            when = datetime.fromtimestamp(int(ts), UTC).date()
        except ValueError:
            continue
        tool = detector.tool_for(gitutil.CommitInfo(sha, name, email, int(ts), message))
        added = 0
        for line in stats.strip().splitlines():
            cols = line.split("\t")
            if len(cols) != 3 or cols[0] == "-":
                continue  # binary files
            if cfg.is_included(renamed_path(cols[2])):
                added += int(cols[0])
        if added:
            rows.append((when, tool, added))

    if not rows:
        return ("week" if by == "auto" else by), []
    first, last = min(r[0] for r in rows), max(r[0] for r in rows)
    if by == "auto":
        by = "week" if (last - first).days <= 26 * 7 else "month"

    buckets: dict[date, Bucket] = {}
    cur = bucket_start(first, by)
    while cur <= last:
        buckets[cur] = Bucket(cur)
        cur = _next(cur, by)
    for when, tool, added in rows:
        b = buckets[bucket_start(when, by)]
        if tool:
            b.tools[tool] += added
        else:
            b.human += added
    return by, [buckets[k] for k in sorted(buckets)]


def summarize(buckets: list[Bucket]) -> dict:
    tools: Counter = Counter()
    human = 0
    for b in buckets:
        tools.update(b.tools)
        human += b.human
    ai = sum(tools.values())
    return {
        "human": human,
        "ai": ai,
        "tools": dict(tools.most_common()),
        "ai_pct": round(100 * ai / (ai + human), 1) if ai + human else 0.0,
    }


def to_json(by: str, buckets: list[Bucket]) -> dict:
    return {
        "by": by,
        "summary": summarize(buckets),
        "periods": [{"start": b.start.isoformat(), "human": b.human, "tools": dict(b.tools)} for b in buckets],
    }


def render_text(by: str, buckets: list[Bucket], width: int = 40) -> str:
    if not buckets:
        return "grokmap trend: no commits with added lines in range."
    s = summarize(buckets)
    peak = max(b.total for b in buckets) or 1
    label = "Week of" if by == "week" else "Month"
    lines = [
        f"Lines added per {by}: {s['ai']:,} by AI ({s['ai_pct']:.0f}%), {s['human']:,} by people",
        "",
        f"{label:<11} {'AI %':>5}  {'added':>7}  █ AI  ░ people",
    ]
    for b in buckets:
        n_ai = round(width * b.ai / peak)
        n_h = round(width * b.human / peak)
        pct = f"{100 * b.ai / b.total:.0f}%" if b.total else "–"
        stamp = b.start.isoformat() if by == "week" else b.start.strftime("%Y-%m")
        lines.append(f"{stamp:<11} {pct:>5}  {b.total:>7,}  {'█' * n_ai}{'░' * n_h}")
    if s["tools"]:
        lines += ["", "By agent: " + ", ".join(f"{k} {v:,}" for k, v in s["tools"].items())]
    return "\n".join(lines)
