import json

from conftest import CLAUDE_TRAILER

from grokmap.cli import main
from grokmap.config import Config
from grokmap.prdiff import MARKER, compute, render_markdown
from grokmap.quiz import mark
from grokmap.trend import collect, renamed_path, render_text, to_json


def test_renamed_paths():
    assert renamed_path("src/a.py") == "src/a.py"
    assert renamed_path("old.py => new.py") == "new.py"
    assert renamed_path("src/{core => engine}/x.py") == "src/engine/x.py"
    assert renamed_path("src/{ => sub}/x.py") == "src/sub/x.py"


def test_trend_counts_lines_by_agent(mixed_repo):
    by, buckets = collect(mixed_repo.root, Config(), by="week")
    data = to_json(by, buckets)
    # numstat counts blank lines too; package-lock.json and the binary are excluded
    assert data["summary"]["tools"] == {"claude": 11, "copilot": 5}
    assert data["summary"]["human"] == 6
    assert all(p["start"] <= q["start"] for p, q in zip(data["periods"], data["periods"][1:], strict=False))
    text = render_text(by, buckets)
    assert "By agent: claude 11, copilot 5" in text


def test_trend_by_month_and_empty_repo(mixed_repo, tmp_path):
    from conftest import Repo

    by, buckets = collect(mixed_repo.root, Config(), by="month")
    assert by == "month" and len(buckets) == 1 and buckets[0].start.day == 1
    assert collect(Repo(tmp_path / "empty").root, Config()) == ("week", [])


def test_pr_diff_only_counts_branch_lines(mixed_repo):
    repo = mixed_repo
    repo.git("checkout", "-q", "-b", "feature")
    repo.write("src/new.py", "def f():\n    return 1\n")
    p = repo.root / "src" / "ai.py"
    p.write_text(p.read_text() + "\n\ndef diameter(r):\n    return 2 * r\n")
    repo.commit("feature" + CLAUDE_TRAILER)
    repo.write("src/human.py", (repo.root / "src/human.py").read_text() + "\n\ndef mul(a, b):\n    return a * b\n")
    repo.commit("human change")

    d = compute(repo.root, Config(), "main")
    by_path = {f.path: f for f in d.files}
    assert by_path["src/new.py"].ai == 2
    assert by_path["src/ai.py"].ai == 2  # the 7 older Claude lines predate the branch
    assert by_path["src/human.py"].human == 2 and by_path["src/human.py"].ai == 0
    assert d.ai == 4 and d.unread == 4 and d.commits == 2

    mark(repo.root, Config(), ["src/new.py"], 1.0, "quiz", "dev@example.com", None)
    d = compute(repo.root, Config(), "main")
    assert d.understood == 2 and d.unread == 2
    md = render_markdown(d)
    assert md.startswith(MARKER) and "**4 AI-written lines**" in md and "grokmap quiz --diff main" in md


def test_pr_diff_cli(mixed_repo, capsys):
    repo = mixed_repo
    repo.git("checkout", "-q", "-b", "feature")
    repo.write("src/x.py", "VALUE = 1\n")
    repo.commit("x" + CLAUDE_TRAILER)
    root = str(repo.root)
    assert main(["-C", root, "diff", "--base", "main", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ai"] == 1
    assert main(["-C", root, "diff", "--base", "main", "--max-unread", "0"]) == 1
    capsys.readouterr()
    assert main(["-C", root, "diff", "--base", "no-such-branch"]) == 2


def test_report_contains_trend_and_note(mixed_repo, capsys, tmp_path):
    out = tmp_path / "r.html"
    assert main(["-C", str(mixed_repo.root), "report", "-o", str(out), "--note", "hello <world>"]) == 0
    html = out.read_text()
    assert '"trend":{"by":' in html and '"note":"hello \\u003cworld\\u003e"' in html
    assert main(["-C", str(mixed_repo.root), "trend", "--json"]) == 0
