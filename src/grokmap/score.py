"""Combine the blame scan with the ledger into per-line states and debt scores."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from grokmap.config import Config
from grokmap.ledger import Record
from grokmap.scan import Scan

HUMAN, UNDERSTOOD, FADING, SKIMMED, UNREAD = "human", "understood", "fading", "skimmed", "unread"
AI_STATES = (UNDERSTOOD, FADING, SKIMMED, UNREAD)
# how much each state of AI-written code counts toward comprehension debt
DEBT_WEIGHT = {HUMAN: 0.0, UNDERSTOOD: 0.0, FADING: 0.5, SKIMMED: 0.5, UNREAD: 1.0}
_RANK = {UNREAD: 0, SKIMMED: 1, FADING: 2, UNDERSTOOD: 3}


@dataclass
class Stats:
    lines: int = 0
    human: int = 0
    understood: int = 0
    fading: int = 0
    skimmed: int = 0
    unread: int = 0
    debt: float = 0.0
    tools: Counter = field(default_factory=Counter)
    people: Counter = field(default_factory=Counter)

    @property
    def ai(self) -> int:
        return self.understood + self.fading + self.skimmed + self.unread

    @property
    def debt_pct(self) -> float:
        return 100.0 * self.debt / self.lines if self.lines else 0.0

    @property
    def ai_pct(self) -> float:
        return 100.0 * self.ai / self.lines if self.lines else 0.0

    @property
    def understood_pct_of_ai(self) -> float:
        return 100.0 * self.understood / self.ai if self.ai else 100.0

    def add(self, other: Stats) -> None:
        for k in ("lines", "human", "understood", "fading", "skimmed", "unread"):
            setattr(self, k, getattr(self, k) + getattr(other, k))
        self.debt += other.debt
        self.tools.update(other.tools)
        self.people.update(other.people)

    def to_dict(self) -> dict:
        return {
            "lines": self.lines,
            "human": self.human,
            "ai": self.ai,
            "understood": self.understood,
            "fading": self.fading,
            "skimmed": self.skimmed,
            "unread": self.unread,
            "debt_lines": round(self.debt, 1),
            "debt_pct": round(self.debt_pct, 1),
            "ai_pct": round(self.ai_pct, 1),
            "tools": dict(self.tools.most_common()),
            "people": dict(self.people.most_common()),
        }


@dataclass
class LineState:
    lineno: int
    state: str
    tool: str | None
    sha: str


@dataclass
class Result:
    files: dict[str, Stats]
    line_states: dict[str, list[LineState]]
    total: Stats
    by_dir: dict[str, Stats]
    critical: Stats
    critical_files: list[str]


def _record_state(rec: Record, cfg: Config, now: datetime) -> str:
    if rec.method == "review" or rec.score < cfg.pass_score:
        return SKIMMED
    if cfg.decay_days > 0 and now - rec.at > timedelta(days=cfg.decay_days):
        return FADING
    return UNDERSTOOD


def evaluate(scan: Scan, records: list[Record], cfg: Config, now: datetime | None = None) -> Result:
    now = now or datetime.now(UTC)
    by_path: dict[str, list[tuple[str, Record]]] = defaultdict(list)
    for rec in records:
        by_path[rec.path].append((_record_state(rec, cfg, now), rec))

    files: dict[str, Stats] = {}
    line_states: dict[str, list[LineState]] = {}
    for path, fs in scan.files.items():
        st = Stats()
        states: list[LineState] = []
        recs = by_path.get(path, [])
        for ln in fs.lines:
            meta = scan.commits.get(ln.sha)
            tool = meta.tool if meta else None
            st.lines += 1
            if tool is None:
                state = HUMAN
                st.human += 1
            else:
                st.tools[tool] += 1
                state = UNREAD
                best = -1
                knowers: set[str] = set()
                for rstate, rec in recs:
                    if ln.h in rec.hashes:
                        if rstate in (UNDERSTOOD, FADING):
                            knowers.add(rec.who)
                        if _RANK[rstate] > best:
                            best, state = _RANK[rstate], rstate
                st.people.update(knowers)
                setattr(st, state, getattr(st, state) + 1)
            st.debt += DEBT_WEIGHT[state]
            states.append(LineState(ln.lineno, state, tool, ln.sha))
        files[path] = st
        line_states[path] = states

    total = Stats()
    by_dir: dict[str, Stats] = defaultdict(Stats)
    critical = Stats()
    critical_files = []
    for path, st in files.items():
        total.add(st)
        parts = path.split("/")
        for i in range(1, len(parts)):
            by_dir["/".join(parts[:i])].add(st)
        if cfg.is_critical(path):
            critical.add(st)
            critical_files.append(path)
    return Result(files, line_states, total, dict(by_dir), critical, sorted(critical_files))


def ranges(numbers: list[int]) -> list[tuple[int, int]]:
    """Collapse sorted line numbers into inclusive ranges, bridging gaps of up to 2 lines."""
    out: list[tuple[int, int]] = []
    for n in sorted(numbers):
        if out and n - out[-1][1] <= 3:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out
