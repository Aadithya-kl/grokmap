import json

from grokmap.cli import main
from grokmap.config import load_config
from grokmap.lines import file_lines


def _states(data):
    return {ln["line"]: ln["state"] for ln in data["lines"]}


def test_lines_match_blame_and_ledger(mixed_repo):
    root = mixed_repo.root
    cfg = load_config(root)
    data = file_lines(root, cfg, "src/ai.py")
    assert data["tracked"] and data["summary"]["ai"] == data["summary"]["lines"] > 0
    assert set(_states(data).values()) == {"unread"}
    assert all(ln["agent"] == "claude" for ln in data["lines"])

    assert main(["--repo", str(root), "mark", "src/ai.py:1-4", "--who", "ana@example.com", "--score", "1"]) == 0
    data = file_lines(root, cfg, str(root / "src" / "ai.py"))  # absolute path works too
    understood = [ln for ln in data["lines"] if ln["state"] == "understood"]
    assert understood and all(ln["line"] <= 4 for ln in understood)
    assert understood[0]["understood_by"] == ["ana@example.com"]

    human = file_lines(root, cfg, "src/human.py")
    assert set(_states(human).values()) == {"human"}


def test_unsaved_buffer_shows_uncommitted_lines(mixed_repo):
    root = mixed_repo.root
    text = (root / "src" / "ai.py").read_text(encoding="utf-8")
    buffer = "def brand_new():\n    return 1\n\n" + text
    data = file_lines(root, load_config(root), "src/ai.py", contents=buffer)
    states = _states(data)
    assert states[1] == states[2] == "uncommitted"
    # the committed lines moved down by three, and keep their state
    assert {s for n, s in states.items() if n > 3} == {"unread"}


def test_lines_cli_json_and_untracked(mixed_repo, capsys):
    root = mixed_repo.root
    assert main(["--repo", str(root), "lines", "src/ai.py", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["path"] == "src/ai.py" and data["commits"]
    (root / "new.py").write_text("x = 1\n")
    assert main(["--repo", str(root), "lines", "new.py", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["tracked"] is False
