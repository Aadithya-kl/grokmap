"""`grokmap hook`: a git pre-push hook that reminds you about AI-written code nobody has checked.

The hook only reads: it never changes the ledger or blocks a push unless you install it with --block.
`git push --no-verify` skips it, like any pre-push hook.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from grokmap import gitutil, prdiff
from grokmap.config import Config

MARKER = "# grokmap pre-push hook"
ZERO = "0" * 40


def hooks_dir(root: Path) -> Path:
    configured = gitutil.run_git(["config", "--get", "core.hooksPath"], root, check=False).strip()
    if configured:
        p = Path(configured)
        return p if p.is_absolute() else root / p
    p = Path(gitutil.run_git(["rev-parse", "--git-path", "hooks"], root).strip())
    return p if p.is_absolute() else root / p  # git answers relative to the repository root


def _python() -> str:
    # forward slashes so the path also works in the sh that Git for Windows runs hooks with
    return Path(sys.executable).as_posix()


def script(block: bool) -> str:
    mode = "--block" if block else ""
    return (
        "#!/bin/sh\n"
        f"{MARKER} (installed by `grokmap hook install`; remove with `grokmap hook uninstall`)\n"
        f'exec "{_python()}" -m grokmap hook run {mode} "$@"\n'.replace("  ", " ")
    )


def install(root: Path, block: bool = False, force: bool = False) -> tuple[bool, str]:
    d = hooks_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "pre-push"
    if path.exists() and MARKER not in path.read_text(encoding="utf-8", errors="replace") and not force:
        return False, f"{path} already exists and was not written by grokmap. Re-run with --force to replace it."
    path.write_text(script(block), encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    how = "blocks the push" if block else "prints a reminder (the push still goes through)"
    return True, f"Installed {path}. Before each push it {how} when you push AI-written lines nobody has checked."


def uninstall(root: Path) -> tuple[bool, str]:
    path = hooks_dir(root) / "pre-push"
    if not path.exists():
        return False, "No pre-push hook installed."
    if MARKER not in path.read_text(encoding="utf-8", errors="replace"):
        return False, f"{path} was not written by grokmap; leaving it alone."
    path.unlink()
    return True, f"Removed {path}."


def _resolves(root: Path, ref: str) -> bool:
    return bool(gitutil.run_git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], root, check=False).strip())


def pick_base(root: Path, remote: str | None, remote_sha: str) -> str | None:
    """What the push is compared with: the remote's current tip, or for a new branch, its likely parent."""
    if remote_sha and remote_sha != ZERO and _resolves(root, remote_sha):
        return remote_sha
    candidates = ["@{upstream}"]
    if remote:
        candidates += [f"{remote}/HEAD", f"{remote}/main", f"{remote}/master"]
    candidates += ["main", "master"]
    head = gitutil.run_git(["rev-parse", "HEAD"], root).strip()
    for ref in candidates:
        if _resolves(root, ref):
            sha = gitutil.run_git(["rev-parse", f"{ref}^{{commit}}"], root).strip()
            if sha != head:
                return ref
    return None


def check_push(root: Path, cfg: Config, remote: str | None, updates: list[tuple[str, str, str, str]]) -> tuple[int, list[str]]:
    """Return (unread AI lines in the push, message lines). Only the branch checked out (HEAD) is examined."""
    head = gitutil.run_git(["rev-parse", "HEAD"], root).strip()
    for local_ref, local_sha, _remote_ref, remote_sha in updates:
        if local_sha == ZERO or local_sha != head:
            continue  # deleting a branch, or pushing something other than the checked-out branch
        base = pick_base(root, remote, remote_sha)
        if base is None:
            return 0, []
        delta = prdiff.compute(root, cfg, base)
        if delta.unread == 0:
            return 0, []
        lines = [
            f"grokmap: you're pushing {delta.unread} AI-written line{prdiff._s(delta.unread)} that nobody has shown they understand"
            f" ({local_ref.removeprefix('refs/heads/')}):"
        ]
        for f in sorted(delta.files, key=lambda f: -f.unread)[:5]:
            if f.unread:
                lines.append(f"  {f.path}: {f.unread} unread")
        lines.append(f"Ask your coding agent to run `grokmap quiz --diff {base}` and quiz you, or push with --no-verify.")
        return delta.unread, lines
    return 0, []


def run(root: Path, cfg: Config, remote: str | None, stdin_text: str, block: bool) -> int:
    updates = []
    for raw in stdin_text.splitlines():
        parts = raw.split()
        if len(parts) == 4:
            updates.append((parts[0], parts[1], parts[2], parts[3]))
    try:
        unread, lines = check_push(root, cfg, remote, updates)
    except gitutil.GitError as exc:  # never break a push because of grokmap itself
        print(f"grokmap hook: skipped ({exc})", file=sys.stderr)
        return 0
    for line in lines:
        print(line, file=sys.stderr)
    if unread and block and not os.environ.get("GROKMAP_HOOK_ALLOW"):
        print(
            "grokmap: push blocked (installed with --block). Set GROKMAP_HOOK_ALLOW=1 or use --no-verify to push anyway.",
            file=sys.stderr,
        )
        return 1
    return 0
