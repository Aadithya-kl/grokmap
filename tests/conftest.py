import os
import subprocess
import textwrap
from pathlib import Path

import pytest

CLAUDE_TRAILER = "\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"


class Repo:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.day = 0
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "dev@example.com")
        self.git("config", "user.name", "Dev")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args, env=None):
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True, env={**os.environ, **(env or {})}
        ).stdout

    def write(self, path: str, body: str) -> None:
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")

    def commit(self, message: str, author=("Dev", "dev@example.com")) -> str:
        self.day += 1
        date = f"2026-01-{self.day:02d}T12:00:00"
        env = {
            "GIT_AUTHOR_NAME": author[0],
            "GIT_AUTHOR_EMAIL": author[1],
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": author[0],
            "GIT_COMMITTER_EMAIL": author[1],
            "GIT_COMMITTER_DATE": date,
        }
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, env=env)
        return self.git("rev-parse", "HEAD").strip()


@pytest.fixture
def repo(tmp_path) -> Repo:
    return Repo(tmp_path / "repo")


@pytest.fixture
def mixed_repo(repo: Repo) -> Repo:
    """human.py by a person, ai.py by Claude, bot.py by the Copilot agent, plus files that must be skipped."""
    repo.write(
        "src/human.py",
        """
        def add(a, b):
            return a + b


        def sub(a, b):
            return a - b
        """,
    )
    repo.write("package-lock.json", '{"lockfileVersion": 3}\n')
    (repo.root / "logo.bin").parent.mkdir(parents=True, exist_ok=True)
    (repo.root / "logo.bin").write_bytes(b"\x89PNG\x00\x01\x02binary")
    repo.commit("human work")
    repo.write(
        "src/ai.py",
        """
        import math


        def area(r):
            if r < 0:
                raise ValueError("negative radius")
            return math.pi * r * r


        def circumference(r):
            return 2 * math.pi * r
        """,
    )
    repo.commit("Add geometry helpers" + CLAUDE_TRAILER)
    repo.write(
        "src/bot.py",
        """
        def greet(name):
            name = name.strip()
            if not name:
                return "hello, stranger"
            return f"hello, {name}"
        """,
    )
    repo.commit("Add greeting", author=("Copilot", "198982749+Copilot@users.noreply.github.com"))
    return repo
