"""The understanding ledger: an append-only record of who has shown they understand which code.

Each record stores short hashes of the meaningful lines the person was checked on.
A line counts as understood only while its content is unchanged, so edits made
after the quiz automatically show up as new, not-yet-understood code.

The ledger lives in `.grokmap/ledger.jsonl` and is meant to be committed, so the
whole team shares it. One JSON object per line keeps git merges painless
(grokmap init adds `merge=union` for it in .gitattributes).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from grokmap.scan import STATE_DIR

LEDGER_NAME = "ledger.jsonl"
METHODS = ("quiz", "explain", "review", "wrote", "pair")


@dataclass
class Record:
    path: str
    who: str
    score: float
    method: str
    at: datetime
    hashes: frozenset[str]
    note: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "v": 1,
                "path": self.path,
                "who": self.who,
                "score": round(self.score, 3),
                "method": self.method,
                "at": self.at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "lines": "".join(sorted(self.hashes)),
                **({"note": self.note} if self.note else {}),
            },
            ensure_ascii=False,
        )


def ledger_path(root: Path) -> Path:
    return root / STATE_DIR / LEDGER_NAME


def parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.fromtimestamp(0, UTC)


def load_ledger(root: Path) -> list[Record]:
    p = ledger_path(root)
    if not p.exists():
        return []
    records: list[Record] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        try:
            d = json.loads(raw)
            lines = d.get("lines", "")
            hashes = frozenset(lines[i : i + 8] for i in range(0, len(lines), 8))
            records.append(
                Record(
                    path=d["path"],
                    who=d.get("who", "unknown"),
                    score=float(d.get("score", 0)),
                    method=d.get("method", "quiz"),
                    at=parse_time(d.get("at", "")),
                    hashes=hashes,
                    note=d.get("note", ""),
                )
            )
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            continue  # tolerate hand edits and merge debris
    return records


def append_records(root: Path, records: list[Record]) -> Path:
    p = ledger_path(root)
    p.parent.mkdir(exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(rec.to_json() + "\n")
    return p
