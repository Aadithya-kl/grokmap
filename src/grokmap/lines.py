"""Per-line comprehension states for one file, for editor integrations.

Unlike a repository scan, this blames the file as it is now: the working tree, or text passed in
(an editor's unsaved buffer, via `git blame --contents`). Line numbers therefore match what the
editor shows, and lines not committed yet come back as "uncommitted".
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from grokmap import gitutil
from grokmap.config import Config
from grokmap.detect import Detector
from grokmap.ledger import load_ledger
from grokmap.scan import is_meaningful, line_hash, normalize, parse_blame
from grokmap.score import _RANK, DEBT_WEIGHT, FADING, HUMAN, UNDERSTOOD, UNREAD, Stats, _record_state

UNCOMMITTED = "uncommitted"
_ZERO = "0" * 40


def relative_path(root: Path, path: str) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"{path} is not inside the repository at {root}") from exc
    return p.as_posix().removeprefix("./")


def file_lines(root: Path, cfg: Config, path: str, contents: str | None = None) -> dict:
    rel = relative_path(root, path)
    if not cfg.is_included(rel):
        return {"path": rel, "tracked": False, "note": "This file is excluded by .grokmap.toml.", "lines": []}
    args = ["blame", "--no-textconv", "--line-porcelain", "-w"]
    if contents is not None:
        args += ["--contents", "-"]
    try:
        porcelain = gitutil.run_git([*args, "--", rel], root, input_text=contents)
    except gitutil.GitError:
        return {"path": rel, "tracked": False, "note": "This file is not committed to git yet.", "lines": []}

    rows = parse_blame(porcelain)
    shas = sorted({sha for _, sha, _ in rows if sha != _ZERO})
    infos = gitutil.commit_infos(root, shas)
    detector = Detector.build(cfg.ai_patterns, cfg.ai_commits)
    agents = {sha: detector.tool_for(info) for sha, info in infos.items()}

    now = datetime.now(UTC)
    recs = [(_record_state(r, cfg, now), r) for r in load_ledger(root) if r.path == rel]

    stats = Stats()
    out_lines = []
    used: set[str] = set()
    for lineno, sha, content in rows:
        norm = normalize(content)
        if not is_meaningful(norm):
            continue
        h = line_hash(norm)
        entry: dict = {"line": lineno}
        if sha == _ZERO:
            entry["state"] = UNCOMMITTED
            out_lines.append(entry)
            continue
        agent = agents.get(sha)
        stats.lines += 1
        entry["sha"] = sha[:10]
        used.add(sha)
        if agent is None:
            entry["state"] = HUMAN
            stats.human += 1
        else:
            state, best, knowers = UNREAD, -1, set()
            for rstate, rec in recs:
                if h in rec.hashes:
                    if rstate in (UNDERSTOOD, FADING):
                        knowers.add(rec.who)
                    if _RANK[rstate] > best:
                        best, state = _RANK[rstate], rstate
            entry.update(state=state, agent=agent)
            if knowers:
                entry["understood_by"] = sorted(knowers)
            stats.tools[agent] += 1
            stats.people.update(knowers)
            setattr(stats, state, getattr(stats, state) + 1)
        stats.debt += DEBT_WEIGHT[entry["state"]]
        out_lines.append(entry)

    commits = {}
    for sha in sorted(used):
        info = infos.get(sha)
        if info is None:
            continue
        summary = info.message.strip().splitlines()[0] if info.message.strip() else ""
        commits[sha[:10]] = {
            "author": info.author_name,
            "date": datetime.fromtimestamp(info.time, UTC).strftime("%Y-%m-%d"),
            "summary": summary[:120],
            "agent": agents.get(sha),
        }
    return {
        "path": rel,
        "tracked": True,
        "critical": cfg.is_critical(rel),
        "summary": stats.to_dict(),
        "commits": commits,
        "lines": out_lines,
    }
