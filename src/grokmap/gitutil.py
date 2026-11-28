"""Thin wrappers around the git CLI. grokmap shells out to git and has no other dependencies."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


# Grok-map only reads repositories. These keep git from running programs that a repository's own
# config can name (an fsmonitor hook, an external diff tool), however git is invoked below.
SAFE_CONFIG = ["-c", "core.fsmonitor=false", "-c", "diff.external="]


def run_git(args: list[str], cwd: Path, input_text: str | None = None, check: bool = True, safe: bool = True) -> str:
    env = dict(os.environ)
    env.setdefault("LC_ALL", "C")
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env.pop("GIT_EXTERNAL_DIFF", None)
    proc = subprocess.run(
        ["git", *(SAFE_CONFIG if safe else []), *args],
        cwd=str(cwd),
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def resolve_commit(root: Path, rev: str) -> str:
    """The commit a user- or agent-supplied revision names, as a full sha.

    Never pass such a revision to git directly: one that starts with "-" would be read as an
    option (for example `--output=FILE`, which makes `git diff` overwrite FILE).
    """
    rev = (rev or "").strip()
    if not rev or rev.startswith("-") or any(c in rev for c in "\0\n\r"):
        raise GitError(f"not a valid revision: {rev!r}")
    sha = run_git(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}"], root, check=False).strip()
    if not sha:
        raise GitError(f"unknown revision: {rev}")
    return sha


def repo_root(start: Path) -> Path:
    try:
        out = run_git(["rev-parse", "--show-toplevel"], start).strip()
    except (GitError, FileNotFoundError) as exc:
        raise GitError(f"{start} is not inside a git repository") from exc
    return Path(out)


def head_sha(root: Path) -> str | None:
    out = run_git(["rev-parse", "--verify", "-q", "HEAD"], root, check=False).strip()
    return out or None


def current_user(root: Path) -> str:
    for key in ("user.email", "user.name"):
        out = run_git(["config", key], root, check=False).strip()
        if out:
            return out
    return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


@dataclass(frozen=True)
class TrackedFile:
    path: str  # repo-relative, forward slashes
    blob: str  # blob sha at HEAD


def tracked_files(root: Path) -> list[TrackedFile]:
    """Files tracked at HEAD with their blob ids (regular files only, no submodules)."""
    out = run_git(["ls-tree", "-r", "-z", "--full-tree", "HEAD"], root, check=False)
    files: list[TrackedFile] = []
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) != 3 or parts[1] != "blob" or parts[0] == "120000":
            continue
        files.append(TrackedFile(path=path, blob=parts[2]))
    return files


@dataclass
class CommitInfo:
    sha: str
    author_name: str
    author_email: str
    time: int
    message: str


def commit_infos(root: Path, shas: list[str]) -> dict[str, CommitInfo]:
    """Fetch author and full message for many commits in one git call."""
    result: dict[str, CommitInfo] = {}
    if not shas:
        return result
    fmt = "%H%x00%an%x00%ae%x00%ct%x00%B%x1e"
    out = run_git(
        ["log", "--no-walk=unsorted", "--stdin", f"--format={fmt}"],
        root,
        input_text="\n".join(shas) + "\n",
    )
    for record in out.split("\x1e"):
        record = record.lstrip("\n")
        if not record:
            continue
        parts = record.split("\x00")
        if len(parts) < 5:
            continue
        sha, name, email, ts, message = parts[0], parts[1], parts[2], parts[3], "\x00".join(parts[4:])
        try:
            t = int(ts)
        except ValueError:
            t = 0
        result[sha] = CommitInfo(sha, name, email, t, message)
    return result


def blame_porcelain(root: Path, path: str, rev: str = "HEAD") -> str:
    return run_git(["blame", "--no-textconv", "--line-porcelain", "-w", rev, "--", path], root)


def diff_files(root: Path, base: str | None, staged: bool) -> list[str]:
    """Paths changed relative to base (or the working tree vs HEAD)."""
    args = ["diff", "--no-ext-diff", "--no-textconv", "--name-only", "--diff-filter=AMR", "-z"]
    if staged:
        args.append("--cached")
    if base:
        args.append(resolve_commit(root, base))
    out = run_git(args, root)
    paths = [p for p in out.split("\0") if p]
    if not staged and not base:
        # include untracked files too: an agent often writes brand-new files
        extra = run_git(["ls-files", "--others", "--exclude-standard", "-z"], root)
        paths += [p for p in extra.split("\0") if p]
    return sorted(set(paths))


def diff_added_lines(root: Path, path: str, base: str | None, staged: bool) -> list[tuple[int, int]] | None:
    """Line ranges (1-based, inclusive) added in the working copy of path. None = whole file is new."""
    args = ["diff", "--no-ext-diff", "--no-textconv", "-U0", "--no-color"]
    if staged:
        args.append("--cached")
    if base:
        args.append(resolve_commit(root, base))
    args += ["--", path]
    out = run_git(args, root, check=False)
    if not out.strip():
        tracked = run_git(["ls-files", "--error-unmatch", "--", path], root, check=False).strip()
        return None if not tracked else []
    ranges: list[tuple[int, int]] = []
    for line in out.splitlines():
        if line.startswith("@@"):
            try:
                plus = line.split("+", 1)[1].split(" ", 1)[0]
            except IndexError:
                continue
            if "," in plus:
                start_s, count_s = plus.split(",", 1)
                start, count = int(start_s), int(count_s)
            else:
                start, count = int(plus), 1
            if count > 0:
                ranges.append((start, start + count - 1))
    return ranges
