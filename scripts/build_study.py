"""Render site/study/index.html from site/study/data.json (static SVG charts, no JavaScript).

python scripts/build_study.py
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "site/study/data.json").read_text(encoding="utf-8"))
REPOS = DATA["repos"]
TOOL_ORDER = ["claude", "copilot", "codex", "cursor", "crush"]  # fixed color slots c1..c5, rest -> c6


def tool_class(tool: str) -> str:
    return f"c{TOOL_ORDER.index(tool) + 1}" if tool in TOOL_ORDER else "c6"


def gh(repo: str) -> str:
    return f'<a href="https://github.com/{escape(repo)}">{escape(repo)}</a>'


def dumbbell() -> str:
    rows = sorted((r for r in REPOS if r["share_recent"] is not None), key=lambda r: -(r["share_recent"] or 0))
    W, L, R, row_h, top = 900, 270, 60, 30, 34
    H = top + row_h * len(rows) + 30
    x = lambda v: L + (W - L - R) * (v or 0) / 100  # noqa: E731
    out = [
        f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Share of commits marked as AI co-authored, 2025 versus August to October 2026, per repository">'
    ]
    for t in (0, 25, 50, 75, 100):
        out.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top - 12}" y2="{H - 26}"/>')
        out.append(f'<text x="{x(t):.1f}" y="{top - 18}" text-anchor="middle">{t}%</text>')
    for i, r in enumerate(rows):
        y = top + i * row_h + row_h / 2
        a, b = r["share_2025"] or 0, r["share_recent"] or 0
        out.append(f'<text class="lbl" x="{L - 12}" y="{y + 4:.1f}" text-anchor="end">{escape(r["repo"])}</text>')
        out.append(f'<line class="link" x1="{x(a):.1f}" x2="{x(b):.1f}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(
            f'<circle class="c0" cx="{x(a):.1f}" cy="{y:.1f}" r="5"><title>{escape(r["repo"])}, 2025: {a}%</title></circle>'
        )
        out.append(
            f'<circle class="c1" cx="{x(b):.1f}" cy="{y:.1f}" r="6"><title>{escape(r["repo"])}, Aug to Oct 2026: {b}%</title></circle>'
        )
        out.append(f'<text class="val" x="{min(x(max(a, b)) + 12, W - 4):.1f}" y="{y + 4:.1f}">{b:g}%</text>')
    out.append("</svg>")
    legend = '<div class="legend"><span><i class="c0"></i>2025</span><span><i class="c1"></i>Aug to Oct 2026 (label shows this value)</span></div>'
    return "".join(out) + legend


def line_bars() -> str:
    rows = sorted((r for r in REPOS if "lines" in r), key=lambda r: -r["lines"]["ai_pct"])
    W, L, R, row_h, top = 900, 270, 70, 34, 30
    H = top + row_h * len(rows) + 20
    span = W - L - R
    tools_seen: list[str] = []
    out = [
        f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Share of current lines last changed by an AI co-authored commit, by agent">'
    ]
    for t in (0, 25, 50, 75, 100):
        xx = L + span * t / 100
        out.append(f'<line class="grid" x1="{xx:.1f}" x2="{xx:.1f}" y1="{top - 8}" y2="{H - 14}"/>')
        out.append(f'<text x="{xx:.1f}" y="{top - 14}" text-anchor="middle">{t}%</text>')
    for i, r in enumerate(rows):
        y = top + i * row_h + 6
        total = r["lines"]["total"]
        out.append(f'<text class="lbl" x="{L - 12}" y="{y + 15}" text-anchor="end">{escape(r["repo"])}</text>')
        cx = L
        grouped: dict[str, int] = {}
        for tool, n in r["lines"]["tools"].items():
            key = tool if tool in TOOL_ORDER else "other"
            grouped[key] = grouped.get(key, 0) + n
        for tool, n in sorted(grouped.items(), key=lambda kv: TOOL_ORDER.index(kv[0]) if kv[0] in TOOL_ORDER else 99):
            w = span * n / total
            if tool not in tools_seen:
                tools_seen.append(tool)
            if w >= 0.5:
                out.append(
                    f'<rect class="{tool_class(tool)}" x="{cx:.1f}" y="{y}" width="{max(w - 2, 0.5):.1f}" height="20" rx="3"><title>{escape(r["repo"])}: {tool}, {n:,} of {total:,} lines</title></rect>'
                )
            cx += w
        out.append(f'<text class="val" x="{cx + 8:.1f}" y="{y + 15}">{r["lines"]["ai_pct"]:g}%</text>')
    out.append("</svg>")
    legend = (
        '<div class="legend">'
        + "".join(
            f'<span><i class="{tool_class(t)}"></i>{escape(t)}</span>'
            for t in sorted(tools_seen, key=lambda t: TOOL_ORDER.index(t) if t in TOOL_ORDER else 99)
        )
        + "</div>"
    )
    return "".join(out) + legend


def table() -> str:
    rows = sorted(REPOS, key=lambda r: -(r["share_recent"] or 0))
    out = [
        '<p>Commits: non-merge commits since January 2025. AI columns: share of commits co-authored by an AI agent. AI lines now: share of current lines last changed by such a commit (only measured for seven repositories).</p><div style="overflow-x:auto"><table><thead><tr><th>Repository</th><th class="num">Commits</th><th class="num">AI, 2025</th><th class="num">AI, Aug–Oct 26</th><th class="num">AI lines now</th><th>Main agents</th></tr></thead><tbody>'
    ]
    for r in rows:
        top = sorted(r["tools"].items(), key=lambda kv: -kv[1])
        tools = ", ".join(t for t, _ in top[:3]) + (f" +{len(top) - 3}" if len(top) > 3 else "")
        lines = f"{r['lines']['ai_pct']:g}%" if "lines" in r else "–"
        out.append(
            f'<tr><td>{gh(r["repo"])}</td><td class="num">{r["commits"]:,}</td><td class="num">{r["share_2025"] if r["share_2025"] is not None else "–"}%</td><td class="num"><b>{r["share_recent"]}%</b></td><td class="num">{lines}</td><td class="agents">{escape(tools) or "–"}</td></tr>'
        )
    out.append("</tbody></table></div>")
    return "".join(out)


def main() -> None:
    n = len(REPOS)
    rising = sum(1 for r in REPOS if (r["share_recent"] or 0) > (r["share_2025"] or 0))
    majority = [r for r in REPOS if (r["share_recent"] or 0) >= 50]
    total_commits = sum(r["commits"] for r in REPOS)
    trailer = DATA["claude_trailer_commits_on_github"]
    html = (ROOT / "site/study/template.html").read_text(encoding="utf-8")
    html = html.replace("{{N}}", str(n)).replace("{{RISING}}", str(rising)).replace("{{MAJORITY}}", str(len(majority)))
    html = html.replace(
        "{{MAJORITY_LIST}}",
        ", ".join(f"{gh(r['repo'])} ({r['share_recent']:g}%)" for r in sorted(majority, key=lambda r: -r["share_recent"])),
    )
    html = html.replace("{{TOTAL_COMMITS}}", f"{total_commits:,}").replace("{{TRAILER}}", f"{trailer / 1e6:.1f} million")
    html = html.replace("{{DUMBBELL}}", dumbbell()).replace("{{LINEBARS}}", line_bars()).replace("{{TABLE}}", table())
    html = html.replace("{{GENERATED}}", DATA["generated"]).replace("{{VERSION}}", DATA["grokmap"])
    (ROOT / "site/study/index.html").write_text(html, encoding="utf-8")
    print("wrote site/study/index.html")


if __name__ == "__main__":
    main()
