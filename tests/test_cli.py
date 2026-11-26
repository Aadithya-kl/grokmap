import json
import re

from grokmap.cli import main


def run(capsys, *args):
    code = main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_status_and_json(mixed_repo, capsys):
    code, out, _ = run(capsys, "-C", str(mixed_repo.root), "status")
    assert code == 0 and "Comprehension debt" in out and "src/ai.py" in out and "claude 7" in out
    code, out, _ = run(capsys, "-C", str(mixed_repo.root), "status", "--json")
    data = json.loads(out)
    assert data["total"]["ai"] == 12 and data["files"]["src/bot.py"]["tools"] == {"copilot": 5}


def test_check_exit_codes(mixed_repo, capsys):
    root = str(mixed_repo.root)
    assert run(capsys, "-C", root, "check")[0] == 1
    assert run(capsys, "-C", root, "check", "--max-debt", "80")[0] == 0
    code, out, _ = run(capsys, "-C", root, "check", "--critical")
    assert code == 0 and "no critical paths" in out


def test_quiz_then_mark_round_trip(mixed_repo, capsys):
    root = str(mixed_repo.root)
    code, out, _ = run(capsys, "-C", root, "quiz", "src/ai.py")
    assert code == 0 and "## Code to quiz on" in out and "negative radius" in out
    cmd = re.search(r"grokmap mark (\S+) --lines (\S+)", out)
    assert cmd and cmd.group(1) == "src/ai.py"
    code, out, _ = run(capsys, "-C", root, "mark", "src/ai.py", "--lines", cmd.group(2), "--score", "1")
    assert code == 0 and "understood" in out
    code, out, _ = run(capsys, "-C", root, "quiz", "src/ai.py")
    assert "Nothing to quiz" in out
    code, out, _ = run(capsys, "-C", root, "who", "src")
    assert "dev@example.com: understands 7 of 12" in out


def test_quiz_uncommitted_includes_new_files(mixed_repo, capsys):
    (mixed_repo.root / "src" / "new.py").write_text("def fresh():\n    return 42\n")
    code, out, _ = run(capsys, "-C", str(mixed_repo.root), "quiz", "--uncommitted")
    assert "src/new.py" in out and "return 42" in out and "not committed yet" in out
    code, out, _ = run(capsys, "-C", str(mixed_repo.root), "quiz", "--uncommitted", "--format", "json")
    assert json.loads(out)["targets"][0]["path"] == "src/new.py"


def test_quiz_brief_is_capped(mixed_repo, capsys):
    code, out, _ = run(capsys, "-C", str(mixed_repo.root), "quiz", "--max-lines", "3", "--format", "json")
    data = json.loads(out)
    assert data["truncated"] and sum(len(t["lines"]) for t in data["targets"]) == 3


def test_mark_errors(mixed_repo, capsys):
    root = str(mixed_repo.root)
    assert run(capsys, "-C", root, "mark", "nope.py", "--score", "1")[0] == 2
    assert run(capsys, "-C", root, "mark", "src/ai.py", "--score", "-1")[0] == 2
    assert run(capsys, "-C", root, "mark", "src/ai.py", "src/bot.py", "--lines", "1-2", "--score", "1")[0] == 2


def test_report_and_badge(mixed_repo, capsys, tmp_path):
    root = str(mixed_repo.root)
    (mixed_repo.root / "src" / "evil.py").write_text('X = "</script><script>alert(1)</script>"\n')
    mixed_repo.commit("tricky file" + "\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    report = tmp_path / "r.html"
    assert run(capsys, "-C", root, "report", "-o", str(report), "--name", "<demo>")[0] == 0
    html = report.read_text()
    assert "/*__GROKMAP_DATA__*/" not in html and '"src/ai.py"' in html
    assert html.count("</script>") == 1 + html.count("<script") - 1  # no injected closing tag
    assert "&lt;demo&gt;" in html
    badge = tmp_path / "b.svg"
    assert run(capsys, "-C", root, "badge", "-o", str(badge))[0] == 0
    assert "comprehension debt" in badge.read_text() and "%" in badge.read_text()


def test_init(repo, capsys):
    repo.write("a.py", "x = 1\n")
    repo.commit("init")
    assert run(capsys, "-C", str(repo.root), "init")[0] == 0
    assert (repo.root / ".grokmap.toml").exists()
    assert "merge=union" in (repo.root / ".gitattributes").read_text()
    assert run(capsys, "-C", str(repo.root), "init")[0] == 0
    assert (repo.root / ".gitattributes").read_text().count("merge=union") == 1


def test_not_a_repo(tmp_path, capsys):
    code, _, err = run(capsys, "-C", str(tmp_path), "status")
    assert code == 2 and "not inside a git repository" in err
