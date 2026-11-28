import tomllib

import pytest
from conftest import CLAUDE_TRAILER

from grokmap.cli import main


@pytest.fixture
def demo_repo(mixed_repo):
    mixed_repo.write("tests/test_ai.py", "def test_area():\n    assert round(1.0, 1) == 1.0\n")
    mixed_repo.write("README.md", "# demo\n\nSome words.\n")
    mixed_repo.commit("tests and readme" + CLAUDE_TRAILER)
    return mixed_repo.root


def test_ignore_creates_config_and_skips_folder(demo_repo, capsys):
    root = demo_repo
    assert main(["-C", str(root), "ignore", "tests", "README.md"]) == 0
    data = tomllib.loads((root / ".grokmap.toml").read_text(encoding="utf-8"))
    assert data["grokmap"]["exclude"] == ["tests/**", "README.md"]
    assert "commit .grokmap.toml" in capsys.readouterr().out

    # idempotent, and --remove takes one back out
    assert main(["-C", str(root), "ignore", "tests"]) == 0
    assert main(["-C", str(root), "ignore", "--remove", "README.md"]) == 0
    data = tomllib.loads((root / ".grokmap.toml").read_text(encoding="utf-8"))
    assert data["grokmap"]["exclude"] == ["tests/**"]
    # the rest of the default config survives
    assert data["grokmap"]["pass_score"] == 0.7


def test_ignore_applies_to_status(demo_repo, capsys):
    import json

    root = demo_repo
    main(["-C", str(root), "status", "--json"])
    before = json.loads(capsys.readouterr().out)
    assert any(p.startswith("tests/") for p in before["files"])
    main(["-C", str(root), "ignore", "tests"])
    capsys.readouterr()
    main(["-C", str(root), "status", "--json"])
    after = json.loads(capsys.readouterr().out)
    assert not any(p.startswith("tests/") for p in after["files"])


def test_ignore_refuses_to_rewrite_pyproject(demo_repo, capsys):
    root = demo_repo
    (root / "pyproject.toml").write_text("[tool.grokmap]\npass_score = 0.8\n", encoding="utf-8")
    assert main(["-C", str(root), "ignore", "tests"]) == 2
    assert "pyproject.toml" in capsys.readouterr().err
    assert not (root / ".grokmap.toml").exists()
