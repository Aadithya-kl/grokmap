"""Regression tests for the security checkup: option injection, repo-configured programs, symlinks."""

import json
import os
from pathlib import Path

import pytest
from conftest import CLAUDE_TRAILER

from grokmap import gitutil
from grokmap.cli import main


@pytest.fixture
def branch_repo(mixed_repo):
    mixed_repo.git("switch", "-q", "-c", "feature")
    mixed_repo.write("src/extra.py", "def extra(x):\n    if x < 0:\n        raise ValueError(x)\n    return x * 2\n")
    mixed_repo.commit("extra" + CLAUDE_TRAILER)
    return mixed_repo


@pytest.mark.parametrize("bad", ["--output=pwned.txt", "-p", "", "main\n--output=x", "no-such-branch"])
def test_revisions_that_look_like_options_are_refused(branch_repo, bad, capsys):
    root = branch_repo.root
    assert main(["-C", str(root), "diff", f"--base={bad}", "--json"]) != 0
    assert main(["-C", str(root), "quiz", f"--diff={bad}"]) != 0 or not bad.strip()
    assert not (root / "pwned.txt").exists()
    assert not (root / "x").exists()


def test_resolve_commit_returns_a_sha(branch_repo):
    sha = gitutil.resolve_commit(branch_repo.root, "main")
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)


def test_mcp_pr_comprehension_refuses_option_injection(branch_repo):
    from grokmap import agent_tools

    root = branch_repo.root
    with pytest.raises((gitutil.GitError, ValueError)):
        agent_tools.pr_comprehension(base="--output=pwned.txt", repo=str(root))
    assert not (root / "pwned.txt").exists()


def test_repo_configured_external_diff_and_fsmonitor_never_run(branch_repo, tmp_path, capsys):
    root = branch_repo.root
    marker = tmp_path / "ran"
    script = tmp_path / "evil.sh"
    script.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n")
    script.chmod(0o755)
    branch_repo.git("config", "diff.external", str(script))
    branch_repo.git("config", "core.fsmonitor", str(script))
    branch_repo.git("config", "diff.evil.textconv", str(script))
    (root / ".gitattributes").write_text("*.py diff=evil\n")
    (root / "src" / "extra.py").write_text("changed in the working tree\n")  # so worktree diffs have work to do

    assert main(["-C", str(root), "diff", "--base", "main", "--json"]) == 0
    main(["-C", str(root), "quiz", "--uncommitted"])
    main(["-C", str(root), "quiz", "--diff", "main"])
    main(["-C", str(root), "lines", "src/extra.py", "--json"])
    main(["-C", str(root), "trend", "--json"])
    main(["-C", str(root), "status", "--json"])
    capsys.readouterr()
    assert not marker.exists(), "git ran a program named in the repository's config"


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_quiz_never_follows_symlinks_out_of_the_repo(branch_repo, tmp_path, capsys):
    root = branch_repo.root
    secret = tmp_path / "credentials"
    secret.write_text("aws_secret_access_key = SUPERSECRET\n")
    (root / "notes.py").symlink_to(secret)
    branch_repo.commit("notes" + CLAUDE_TRAILER)

    main(["-C", str(root), "quiz", "--diff", "main", "--format", "json"])
    main(["-C", str(root), "quiz", "--uncommitted", "--format", "json"])
    out = capsys.readouterr().out
    assert "SUPERSECRET" not in out

    assert main(["-C", str(root), "mark", "notes.py", "--score", "1"]) != 0
    assert main(["-C", str(root), "mark", "../credentials", "--score", "1"]) != 0
    ledger = Path(root, ".grokmap", "ledger.jsonl")
    assert not ledger.exists() or "credentials" not in ledger.read_text()
    json.dumps({})  # keep json import used


def test_pr_comment_cannot_be_broken_out_of():
    from grokmap.prdiff import md_code

    evil = "a` @org/everyone [click](https://evil.example) |x|\n## injected"
    out = md_code(evil)
    assert out.startswith("``") and out.endswith("``")
    inner = out[2:-2]
    assert "``" not in inner  # the fence can't be closed from inside
    assert "\n" not in out and "\\|" in out and "|x" not in out.replace("\\|", "")
    assert md_code("plain.py") == "`plain.py`"
    assert md_code("`tick.py") == "`` `tick.py ``"
