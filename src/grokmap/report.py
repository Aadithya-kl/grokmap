"""Render the self-contained HTML comprehension map."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from grokmap import __version__
from grokmap.scan import Scan
from grokmap.score import Result


def build_payload(scan: Scan, result: Result, repo_name: str, trend: dict | None = None, note: str | None = None) -> dict:
    files = []
    for path, st in sorted(result.files.items()):
        files.append(
            {
                "p": path,
                "n": st.lines,
                "h": st.human,
                "u": st.understood,
                "f": st.fading,
                "s": st.skimmed,
                "x": st.unread,
                "d": round(st.debt, 1),
                "t": dict(st.tools.most_common()),
                "k": dict(st.people.most_common()),
                "c": path in result.critical_files,
            }
        )
    total = result.total
    return {
        "repo": repo_name,
        "head": (scan.head or "")[:10],
        "generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "version": __version__,
        "total": total.to_dict(),
        "critical": result.critical.to_dict() if result.critical_files else None,
        "files": files,
        "trend": trend,
        "note": note,
    }


def render_report(scan: Scan, result: Result, repo_name: str, trend: dict | None = None, note: str | None = None) -> str:
    template = resources.files("grokmap").joinpath("report_template.html").read_text(encoding="utf-8")
    data = json.dumps(build_payload(scan, result, repo_name, trend, note), separators=(",", ":"))
    data = data.replace("</", "<\\/")
    return template.replace("/*__GROKMAP_DATA__*/null", data).replace("__GROKMAP_TITLE__", _html_escape(repo_name))


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def write_report(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
