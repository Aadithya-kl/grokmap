"""Build quiz briefs for coding agents and record the results in the ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from grokmap import gitutil
from grokmap.config import Config
from grokmap.ledger import Record, append_records, load_ledger
from grokmap.scan import Scan, is_meaningful, line_hash, normalize
from grokmap.score import UNDERSTOOD, _record_state, ranges

LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".sh": "bash",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".vue": "vue",
    ".svelte": "svelte",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".md": "markdown",
    ".lua": "lua",
    ".dart": "dart",
    ".scala": "scala",
    ".ex": "elixir",
    ".exs": "elixir",
    ".zig": "zig",
}


@dataclass
class Target:
    path: str
    ranges: list[tuple[int, int]]
    tools: list[str]
    lines: dict[int, str]  # lineno -> text (only lines inside ranges)


def parse_ranges(spec: str) -> list[tuple[int, int]]:
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a), int(b)
        else:
            lo = hi = int(part)
        if lo < 1 or hi < lo:
            raise ValueError(f"bad line range: {part}")
        out.append((lo, hi))
    return out


def format_ranges(rs: list[tuple[int, int]]) -> str:
    return ",".join(f"{a}-{b}" if a != b else str(a) for a, b in rs)


def inside_repo(root: Path, path: str) -> Path | None:
    """The file at a repository-relative path, or None if it is a symlink or resolves outside the repository."""
    full = root / path
    try:
        if full.is_symlink() or not full.resolve().is_relative_to(root.resolve()):
            return None
    except OSError:
        return None
    return full


def read_lines(root: Path, path: str) -> list[str]:
    # never follow a symlink: a branch could add one pointing at ~/.ssh or ~/.aws and the quiz
    # would hand that file's content to the coding agent
    full = inside_repo(root, path)
    if full is None:
        return []
    try:
        return full.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def known_hashes(records: list[Record], who: str, path: str, cfg: Config) -> set[str]:
    now = datetime.now(UTC)
    known: set[str] = set()
    for rec in records:
        if rec.path == path and rec.who == who and _record_state(rec, cfg, now) == UNDERSTOOD:
            known |= rec.hashes
    return known


def build_targets(
    root: Path,
    cfg: Config,
    who: str,
    scan: Scan | None,
    paths: list[str],
    diff_base: str | None,
    staged: bool,
    diff_mode: bool,
    include_human: bool = False,
) -> list[Target]:
    records = load_ledger(root)
    targets: list[Target] = []

    if diff_mode:
        for path in gitutil.diff_files(root, diff_base, staged):
            if not cfg.is_included(path) or (paths and not any(path == p or path.startswith(p.rstrip("/") + "/") for p in paths)):
                continue
            text = read_lines(root, path)
            if not text:
                continue
            added = gitutil.diff_added_lines(root, path, diff_base, staged)
            if added is None:
                added = [(1, len(text))]
            known = known_hashes(records, who, path, cfg)
            picked = []
            for lo, hi in added:
                for n in range(lo, min(hi, len(text)) + 1):
                    norm = normalize(text[n - 1])
                    if is_meaningful(norm) and line_hash(norm) not in known:
                        picked.append(n)
            if picked:
                rs = ranges(picked)
                targets.append(Target(path, rs, [], _slice(text, rs)))
        return targets

    if scan is None:
        return targets
    wanted = list(scan.files)
    if paths:
        norm_paths = [p.rstrip("/") for p in paths]
        wanted = [f for f in wanted if any(f == p or f.startswith(p + "/") or p in ("", ".") for p in norm_paths)]
    for path in sorted(wanted):
        fs = scan.files[path]
        known = known_hashes(records, who, path, cfg)
        picked, tools = [], set()
        for ln in fs.lines:
            meta = scan.commits.get(ln.sha)
            tool = meta.tool if meta else None
            if (tool or include_human) and ln.h not in known:
                picked.append(ln.lineno)
                if tool:
                    tools.add(tool)
        if picked:
            text = read_lines(root, path)
            rs = ranges(picked)
            targets.append(Target(path, rs, sorted(tools) or ["human"], _slice(text, rs)))
    return targets


def _slice(text: list[str], rs: list[tuple[int, int]]) -> dict[int, str]:
    out = {}
    for lo, hi in rs:
        for n in range(lo, min(hi, len(text)) + 1):
            out[n] = text[n - 1]
    return out


def truncate(targets: list[Target], max_lines: int) -> tuple[list[Target], bool]:
    """Keep the brief small enough for one quiz: biggest chunks first, up to max_lines lines."""
    if max_lines <= 0:
        return targets, False
    budget = max_lines
    kept: list[Target] = []
    cut = False
    for t in sorted(targets, key=lambda t: -len(t.lines)):
        if budget <= 0:
            cut = True
            break
        rs_kept, lines_kept = [], {}
        for lo, hi in t.ranges:
            if budget <= 0:
                cut = True
                break
            span = [n for n in range(lo, hi + 1) if n in t.lines]
            if not span:
                continue
            if len(span) > budget:
                span = span[:budget]
                cut = True
            rs_kept.append((span[0], span[-1]))
            for n in span:
                lines_kept[n] = t.lines[n]
            budget -= len(span)
        if rs_kept:
            kept.append(Target(t.path, rs_kept, t.tools, lines_kept))
    kept.sort(key=lambda t: t.path)
    return kept, cut


QUIZ_RULES = """\
## How to run this quiz

You are checking that **{who}** understands this code well enough to debug it at 2am without an AI.

1. Read the code below yourself first. Find the parts that matter: the core logic, edge cases, error paths, and anything surprising.
2. Ask **{n_questions} questions, one at a time**, and wait for each answer before asking the next. Do not show the code again in the question and do not hint at the answer.
3. Good questions ask *why* and *what if*, not trivia:
   - "What happens if `X` is empty / null / huge?"
   - "Why is this done before that?"
   - "A user reports <symptom>. Where would you look first?"
   - "What would break if we removed this line?"
   Avoid questions answerable by re-reading a name (for example "what does `get_user` return?").
4. Grade each answer: **1** = correct and explains why, **0.5** = partly right or vague, **0** = wrong or "I don't know". Explain the right answer after each one, briefly.
5. Score = average of the grades. Then record it (this command covers exactly the lines shown below):

```
{mark_cmd}
```

If the person does not want a quiz, offer the lighter options instead: ask them to explain the change back in their own words (`--method explain`, you grade it), or record that they only skimmed it (`--method review`, counts as half-understood).
"""


def render_markdown(targets: list[Target], who: str, truncated: bool, n_questions: int = 3) -> str:
    total = sum(len(t.lines) for t in targets)
    if not targets:
        return f"# grokmap quiz brief\n\nNothing to quiz: **{who}** already understands every AI-written line in scope.\n"
    if len(targets) == 1:
        mark_cmd = f"grokmap mark {targets[0].path} --lines {format_ranges(targets[0].ranges)} --score <0..1> --method quiz"
    else:
        mark_cmd = (
            "grokmap mark " + " ".join(f"{t.path}:{format_ranges(t.ranges)}" for t in targets) + " --score <0..1> --method quiz"
        )
    n_q = max(n_questions, min(6, 2 + total // 80))
    head = [
        "# grokmap quiz brief",
        "",
        f"Person: **{who}** · {total} lines in {len(targets)} file(s) they have not yet shown they understand.",
    ]
    if truncated:
        head.append("_The brief was cut to keep the quiz short. Run it again afterwards to cover the rest._")
    head += ["", QUIZ_RULES.format(who=who, n_questions=n_q, mark_cmd=mark_cmd), "## Code to quiz on", ""]
    body = []
    for t in targets:
        lang = LANG.get(Path(t.path).suffix.lower(), "")
        span = format_ranges(t.ranges)
        word = "line" if len(t.ranges) == 1 and t.ranges[0][0] == t.ranges[0][1] else "lines"
        origin = f"written by {', '.join(t.tools)}" if t.tools else "new or changed, not committed yet"
        body.append(f"### `{t.path}` — {word} {span} · {origin}")
        body.append("")
        for lo, hi in t.ranges:
            body.append(f"```{lang}")
            width = len(str(hi))
            for n in range(lo, hi + 1):
                if n in t.lines:
                    body.append(f"{str(n).rjust(width)} | {t.lines[n]}")
            body.append("```")
        body.append("")
    return "\n".join(head + body)


def render_json(targets: list[Target], who: str, truncated: bool) -> str:
    return json.dumps(
        {
            "who": who,
            "truncated": truncated,
            "targets": [
                {"path": t.path, "ranges": t.ranges, "tools": t.tools, "lines": {str(k): v for k, v in t.lines.items()}}
                for t in targets
            ],
        },
        indent=2,
    )


def mark(
    root: Path,
    cfg: Config,
    specs: list[str],
    score: float,
    method: str,
    who: str,
    line_spec: str | None,
    note: str = "",
) -> list[Record]:
    """Record understanding for files (optionally only some lines). Directories expand to their files."""
    if score > 1.0:
        score = score / 100.0  # accept 85 as well as 0.85
    if not 0.0 <= score <= 1.0:
        raise ValueError("score must be between 0 and 1 (or 0 and 100)")
    if method == "wrote" and score < cfg.pass_score:
        score = 1.0

    jobs: list[tuple[str, list[tuple[int, int]] | None]] = []
    for spec in specs:
        path, rs = spec, None
        if ":" in spec and spec.rsplit(":", 1)[1].replace("-", "").replace(",", "").isdigit():
            path, r = spec.rsplit(":", 1)
            rs = parse_ranges(r)
        path = path.replace("\\", "/").rstrip("/")
        if path.startswith("./"):
            path = path[2:]
        full = root / path
        if inside_repo(root, path) is None:
            raise FileNotFoundError(f"not a file inside the repository: {path}")
        if full.is_dir():
            for f in sorted(full.rglob("*")):
                rel = f.relative_to(root).as_posix()
                if f.is_file() and cfg.is_included(rel) and "/.git/" not in f"/{rel}/":
                    jobs.append((rel, None))
        elif full.is_file():
            jobs.append((path, rs))
        else:
            raise FileNotFoundError(f"no such file or directory: {path}")
    if line_spec:
        if len(jobs) != 1:
            raise ValueError("--lines only works with a single file (use path:10-40 for several)")
        jobs[0] = (jobs[0][0], parse_ranges(line_spec))

    now = datetime.now(UTC)
    records = []
    for path, rs in jobs:
        text = read_lines(root, path)
        wanted = set()
        for n, raw in enumerate(text, start=1):
            if rs and not any(lo <= n <= hi for lo, hi in rs):
                continue
            norm = normalize(raw)
            if is_meaningful(norm):
                wanted.add(line_hash(norm))
        if wanted:
            records.append(Record(path, who, score, method, now, frozenset(wanted), note))
    if records:
        append_records(root, records)
    return records
