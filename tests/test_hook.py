import subprocess

from conftest import CLAUDE_TRAILER

from grokmap.cli import main


def _push_input(repo, base):
    head = repo.git("rev-parse", "HEAD").strip()
    return f"refs/heads/feature {head} refs/heads/feature {base}\n"


def test_install_writes_hook_and_respects_foreign_hooks(repo, capsys):
    repo.write("a.py", "x = 1\n")
    repo.commit("init")
    root = str(repo.root)
    hook = repo.root / ".git" / "hooks" / "pre-push"
    hook.write_text("#!/bin/sh\necho mine\n")
    assert main(["-C", root, "hook", "install"]) == 1
    assert "not written by grokmap" in capsys.readouterr().err
    assert main(["-C", root, "hook", "install", "--force"]) == 0
    text = hook.read_text()
    assert "grokmap pre-push hook" in text and "-m grokmap hook run" in text.replace("--block ", "")
    assert main(["-C", root, "hook", "uninstall"]) == 0
    assert not hook.exists()


def test_run_reminds_then_blocks(repo, capsys, monkeypatch):
    repo.write("a.py", "x = 1\n")
    base = repo.commit("init")
    repo.git("checkout", "-q", "-b", "feature")
    repo.write("b.py", "def f(a):\n    return a * 2\n\n\ndef g(b):\n    return b + 1\n")
    repo.commit("feat: helpers" + CLAUDE_TRAILER)
    root = str(repo.root)

    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(_push_input(repo, base)))
    assert main(["-C", root, "hook", "run", "origin", "url"]) == 0
    err = capsys.readouterr().err
    assert "AI-written line" in err and "b.py" in err and f"--diff {base}" in err

    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(_push_input(repo, base)))
    assert main(["-C", root, "hook", "--block", "run", "origin", "url"]) == 1

    # once the lines are understood, the push is quiet
    assert main(["-C", root, "mark", "b.py", "--who", "dev@example.com", "--score", "1"]) == 0
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(_push_input(repo, base)))
    assert main(["-C", root, "hook", "--block", "run", "origin", "url"]) == 0
    assert capsys.readouterr().err == ""


def test_real_git_push_runs_the_hook(repo, tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    repo.write("a.py", "x = 1\n")
    repo.commit("init")
    repo.git("remote", "add", "origin", str(remote))
    repo.git("push", "-q", "origin", "main")
    assert main(["-C", str(repo.root), "hook", "install", "--block"]) == 0
    repo.git("checkout", "-q", "-b", "feature")
    repo.write("b.py", "def f(a):\n    return a * 2\n")
    repo.commit("feat" + CLAUDE_TRAILER)
    pushed = subprocess.run(["git", "push", "-q", "origin", "feature"], cwd=repo.root, capture_output=True, text=True)
    assert pushed.returncode != 0 and "push blocked" in pushed.stderr
    ok = subprocess.run(["git", "push", "-q", "--no-verify", "origin", "feature"], cwd=repo.root, capture_output=True, text=True)
    assert ok.returncode == 0
