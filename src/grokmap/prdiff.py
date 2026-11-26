"""Summarize the AI-written code a branch or pull request adds, and how much of it is understood."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from grokmap import gitutil
from grokmap.config import Config
from grokmap.ledger import load_ledger
from grokmap.scan import scan_repo
from grokmap.score import HUMAN, UNDERSTOOD, UNREAD, evaluate

MARKER = "<!-- grokmap:pr-summary -->"


@dataclass
class FileDelta:
    path: str
    ai: int = 0
    human: int = 0
    understood: int = 0
    unread: int = 0
    partial: int = 0  # skimmed or fading
    tools: Counter = field(default_factory=Counter)


@dataclass
class PrDelta:
    base: str
    merge_base: str
    commits: int
    files: list[FileDelta]

    @property
    def ai(self) -> int:
        return sum(f.ai for f in self.files)

    @property
    def human(self) -> int:
        return sum(f.human for f in self.files)

    @property
    def understood(self) -> int:
        return sum(f.understood for f in self.files)

    @property
    def unread(self) -> int:
        return sum(f.unread for f in self.files)

    @property
    def tools(self) -> Counter:
        c: Counter = Counter()
        for f in self.files:
            c.update(f.tools)
        return c


def compute(root: Path, cfg: Config, base: str) -> PrDelta:
    merge_base = gitutil.run_git(["merge-base", base, "HEAD"], root).strip()
    branch_commits = set(gitutil.run_git(["rev-list", f"{merge_base}..HEAD"], root).split())
    changed = set(
        gitutil.run_git(["diff", "--name-only", "--diff-filter=AMR", "-z", f"{merge_base}..HEAD"], root).split("\0")
    ) - {""}
    changed = {p for p in changed if cfg.is_included(p)}
    scan = scan_repo(root, cfg, only=changed)
    result = evaluate(scan, load_ledger(root), cfg)
    files = []
    for path in sorted(changed):
        fd = FileDelta(path)
        for ls in result.line_states.get(path, []):
            if ls.sha not in branch_commits:
                continue  # line predates the branch
            if ls.state == HUMAN:
                fd.human += 1
                continue
            fd.ai += 1
            fd.tools[ls.tool] += 1
            if ls.state == UNDERSTOOD:
                fd.understood += 1
            elif ls.state == UNREAD:
                fd.unread += 1
            else:
                fd.partial += 1
        if fd.ai or fd.human:
            files.append(fd)
    return PrDelta(base, merge_base, len(branch_commits), files)


def _s(n: int) -> str:
    return "" if n == 1 else "s"


def render_markdown(d: PrDelta, top: int = 15) -> str:
    out = [MARKER, "### grokmap: comprehension check", ""]
    if not d.files:
        out.append("This change adds no code lines that grokmap tracks.")
        return "\n".join(out)
    if not d.ai:
        out.append(f"This change adds **{d.human:,}** line{_s(d.human)}, all written by people. No new comprehension debt.")
        return "\n".join(out)
    pct = 100 * d.understood / d.ai
    tools = ", ".join(f"{k} {v:,}" for k, v in d.tools.most_common())
    out.append(
        f"This change adds **{d.ai:,} AI-written line{_s(d.ai)}** ({tools}) and {d.human:,} human-written line{_s(d.human)}. "
        f"**{d.understood:,} of the AI lines ({pct:.0f}%)** have been understood by someone on the team."
    )
    out += ["", "| File | AI lines | Understood | Not checked |", "|---|---:|---:|---:|"]
    ranked = sorted((f for f in d.files if f.ai), key=lambda f: (-f.unread, -f.ai))
    for f in ranked[:top]:
        out.append(f"| `{f.path}` | {f.ai:,} | {f.understood:,} | {f.unread:,} |")
    if len(ranked) > top:
        out.append(f"| _…and {len(ranked) - top} more files_ | | | |")
    out += [""]
    if d.unread:
        out.append(
            f"Before merging, the author can ask their coding agent to run `grokmap quiz --diff {d.base}` "
            "for a 2-minute quiz on the unchecked lines."
        )
    else:
        out.append("Every AI-written line in this change has been understood by someone. 🎉")
    out.append("")
    out.append(
        "<sub>Measured by [grokmap](https://github.com/Aadithya-kl/grokmap) from commit trailers and the team's understanding ledger.</sub>"
    )
    return "\n".join(out)


def to_json(d: PrDelta) -> dict:
    return {
        "base": d.base,
        "merge_base": d.merge_base,
        "commits": d.commits,
        "ai": d.ai,
        "human": d.human,
        "understood": d.understood,
        "unread": d.unread,
        "tools": dict(d.tools.most_common()),
        "files": [
            {"path": f.path, "ai": f.ai, "human": f.human, "understood": f.understood, "unread": f.unread, "partial": f.partial}
            for f in d.files
        ],
    }
