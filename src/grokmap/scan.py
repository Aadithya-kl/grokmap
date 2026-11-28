"""Walk the repository at HEAD and attribute every meaningful line to the commit that wrote it."""

from __future__ import annotations

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from grokmap import gitutil
from grokmap.config import Config
from grokmap.detect import Detector

CACHE_VERSION = 2
STATE_DIR = ".grokmap"
_TRIVIAL = re.compile(r"^[\W_]{0,3}$")
_WS = re.compile(r"\s+")


def normalize(line: str) -> str:
    return _WS.sub(" ", line.strip())


def is_meaningful(norm: str) -> bool:
    """Skip blank lines and lone punctuation such as `}` or `});` — nothing to understand there."""
    return bool(norm) and not _TRIVIAL.match(norm)


def line_hash(norm: str) -> str:
    # a short fingerprint to match lines across edits, not a security measure
    return hashlib.sha1(norm.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:8]


@dataclass
class Line:
    lineno: int
    sha: str
    h: str


@dataclass
class FileScan:
    path: str
    lines: list[Line]


@dataclass
class CommitMeta:
    sha: str
    tool: str | None
    author: str
    email: str
    time: int
    summary: str


@dataclass
class Scan:
    root: Path
    head: str | None
    files: dict[str, FileScan] = field(default_factory=dict)
    commits: dict[str, CommitMeta] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)


def parse_blame(porcelain: str) -> list[tuple[int, str, str]]:
    """Return (final_lineno, sha, content) for each line of `git blame --line-porcelain` output."""
    out: list[tuple[int, str, str]] = []
    sha = ""
    lineno = 0
    expect_header = True
    for raw in porcelain.split("\n"):
        if raw.startswith("\t"):
            out.append((lineno, sha, raw[1:]))
            expect_header = True
            continue
        if expect_header and raw:
            parts = raw.split(" ")
            if len(parts) >= 3 and len(parts[0]) >= 40:
                sha = parts[0]
                try:
                    lineno = int(parts[2])
                except ValueError:
                    lineno = 0
                expect_header = False
    return out


def _cache_path(root: Path) -> Path:
    return root / STATE_DIR / "cache.json"


def _load_cache(root: Path) -> dict:
    p = _cache_path(root)
    if not p.exists():
        return {"version": CACHE_VERSION, "blame": {}, "commits": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("version") == CACHE_VERSION:
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": CACHE_VERSION, "blame": {}, "commits": {}}


def _save_cache(root: Path, data: dict) -> None:
    state = root / STATE_DIR
    try:
        state.mkdir(exist_ok=True)
        gi = state / ".gitignore"
        if not gi.exists():
            gi.write_text("# local cache, safe to delete\ncache.json\n", encoding="utf-8")
        tmp = _cache_path(root).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, _cache_path(root))
    except OSError:
        pass  # read-only checkout: caching is best-effort


def text_files_at_head(root: Path) -> set[str]:
    out = gitutil.run_git(["grep", "--no-textconv", "-I", "-l", "-z", "-e", "", "HEAD", "--"], root, check=False)
    files = set()
    for item in out.split("\0"):
        if item.startswith("HEAD:"):
            files.add(item[5:])
    return files


def scan_repo(root: Path, cfg: Config, use_cache: bool = True, progress=None, only: set[str] | None = None) -> Scan:
    """Blame every included text file at HEAD (or just the paths in `only`)."""
    head = gitutil.head_sha(root)
    scan = Scan(root=root, head=head)
    if head is None:
        return scan

    cache = _load_cache(root) if use_cache else {"version": CACHE_VERSION, "blame": {}, "commits": {}}
    blame_cache: dict = cache["blame"]
    text_files = text_files_at_head(root)

    todo = []
    for tf in gitutil.tracked_files(root):
        if not cfg.is_included(tf.path) or (only is not None and tf.path not in only):
            continue
        if tf.path not in text_files:
            scan.skipped.append(tf.path)
            continue
        todo.append(tf)

    def work(tf: gitutil.TrackedFile):
        cached = blame_cache.get(tf.path)
        if cached and cached.get("blob") == tf.blob:
            return tf, cached["lines"], True
        try:
            porcelain = gitutil.blame_porcelain(root, tf.path)
        except gitutil.GitError:
            return tf, None, False
        rows = parse_blame(porcelain)
        if len(rows) > cfg.max_file_lines:
            return tf, None, False
        lines = []
        for lineno, sha, content in rows:
            norm = normalize(content)
            if is_meaningful(norm):
                lines.append([lineno, sha, line_hash(norm)])
        return tf, lines, False

    workers = max(2, min(8, (os.cpu_count() or 4)))
    new_blame: dict = {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for tf, lines, _hit in pool.map(work, todo):
            done += 1
            if progress:
                progress(done, len(todo))
            if lines is None:
                scan.skipped.append(tf.path)
                continue
            new_blame[tf.path] = {"blob": tf.blob, "lines": lines}
            if lines:
                scan.files[tf.path] = FileScan(tf.path, [Line(row[0], row[1], row[2]) for row in lines])

    # commit metadata (cached raw, AI detection re-run every time so config changes apply)
    shas = sorted({ln.sha for f in scan.files.values() for ln in f.lines})
    commit_cache: dict = cache["commits"]
    missing = [s for s in shas if s not in commit_cache]
    for i in range(0, len(missing), 500):
        infos = gitutil.commit_infos(root, missing[i : i + 500])
        for sha, info in infos.items():
            commit_cache[sha] = [info.author_name, info.author_email, info.time, info.message[:6000]]
    detector = Detector.build(cfg.ai_patterns, cfg.ai_commits)
    for sha in shas:
        raw = commit_cache.get(sha)
        if raw is None:
            # uncommitted or unknown: treat as human so we never over-claim AI authorship
            scan.commits[sha] = CommitMeta(sha, None, "unknown", "", 0, "")
            continue
        info = gitutil.CommitInfo(sha, raw[0], raw[1], raw[2], raw[3])
        summary = raw[3].strip().splitlines()[0] if raw[3].strip() else ""
        scan.commits[sha] = CommitMeta(sha, detector.tool_for(info), raw[0], raw[1], raw[2], summary[:120])

    if use_cache:
        keep_commits = {s: commit_cache[s] for s in shas if s in commit_cache}
        if only is not None:
            # partial scan: keep everything else we already knew
            blame = {**blame_cache, **new_blame}
            keep_commits = {**cache["commits"], **keep_commits}
        else:
            blame = new_blame
        _save_cache(root, {"version": CACHE_VERSION, "blame": blame, "commits": keep_commits})
    return scan
