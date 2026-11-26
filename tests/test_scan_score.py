from datetime import UTC, datetime, timedelta

from grokmap.config import Config
from grokmap.ledger import Record, append_records, load_ledger
from grokmap.quiz import mark
from grokmap.scan import is_meaningful, normalize, parse_blame, scan_repo
from grokmap.score import evaluate, ranges


def test_parse_blame_handles_repeated_commits():
    sha = "1" * 40
    porcelain = (
        f"{sha} 1 1 2\nauthor A\nsummary s\nfilename f.py\n\tdef a():\n"
        f"{sha} 2 2\nauthor A\nsummary s\nfilename f.py\n\t    return 1\n"
    )
    assert parse_blame(porcelain) == [(1, sha, "def a():"), (2, sha, "    return 1")]


def test_meaningful_lines():
    assert not is_meaningful(normalize("   "))
    assert not is_meaningful(normalize("});"))
    assert is_meaningful(normalize("return x"))
    assert normalize("  a   =  1 ") == "a = 1"


def test_ranges_bridge_small_gaps():
    assert ranges([1, 2, 3, 5, 6, 20]) == [(1, 6), (20, 20)]


def test_scan_attributes_lines_and_skips_noise(mixed_repo):
    scan = scan_repo(mixed_repo.root, Config())
    assert set(scan.files) == {"src/human.py", "src/ai.py", "src/bot.py"}
    res = evaluate(scan, [], Config())
    assert res.files["src/human.py"].human == 4 and res.files["src/human.py"].ai == 0
    assert res.files["src/ai.py"].tools == {"claude": 7}
    assert res.files["src/bot.py"].tools == {"copilot": 5}
    assert res.total.unread == 12 and res.total.debt_pct == 100 * 12 / 16
    assert res.by_dir["src"].lines == 16


def test_cache_round_trip(mixed_repo):
    first = scan_repo(mixed_repo.root, Config())
    assert (mixed_repo.root / ".grokmap" / "cache.json").exists()
    assert (mixed_repo.root / ".grokmap" / ".gitignore").read_text().strip().endswith("cache.json")
    second = scan_repo(mixed_repo.root, Config())
    assert {p: [(ln.lineno, ln.sha, ln.h) for ln in f.lines] for p, f in first.files.items()} == {
        p: [(ln.lineno, ln.sha, ln.h) for ln in f.lines] for p, f in second.files.items()
    }


def test_quiz_marks_understanding_and_edits_reset_it(mixed_repo):
    root, cfg = mixed_repo.root, Config()
    mark(root, cfg, ["src/ai.py"], 0.9, "quiz", "dev@example.com", None)
    res = evaluate(scan_repo(root, cfg), load_ledger(root), cfg)
    ai = res.files["src/ai.py"]
    assert ai.understood == 7 and ai.unread == 0 and ai.debt == 0
    assert ai.people == {"dev@example.com": 7}

    # the agent rewrites one line: that line is new code nobody has understood
    p = root / "src/ai.py"
    p.write_text(p.read_text().replace('raise ValueError("negative radius")', 'raise ValueError(f"bad radius {r}")'))
    mixed_repo.commit("Better error" + "\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    res = evaluate(scan_repo(root, cfg), load_ledger(root), cfg)
    assert res.files["src/ai.py"].understood == 6 and res.files["src/ai.py"].unread == 1


def test_review_low_scores_and_decay(mixed_repo):
    root, cfg = mixed_repo.root, Config()
    mark(root, cfg, ["src/bot.py"], 1.0, "review", "a@x.io", None)
    mark(root, cfg, ["src/ai.py"], 0.4, "quiz", "b@x.io", None)
    res = evaluate(scan_repo(root, cfg), load_ledger(root), cfg)
    assert res.files["src/bot.py"].skimmed == 5 and res.files["src/bot.py"].debt == 2.5
    assert res.files["src/ai.py"].skimmed == 7 and not res.files["src/ai.py"].people

    old = datetime.now(UTC) - timedelta(days=400)
    rec = load_ledger(root)[1]
    append_records(root, [Record(rec.path, "c@x.io", 1.0, "quiz", old, rec.hashes)])
    res = evaluate(scan_repo(root, cfg), load_ledger(root), cfg)
    assert res.files["src/ai.py"].fading == 7 and res.files["src/ai.py"].people == {"c@x.io": 7}
    cfg.decay_days = 0
    res = evaluate(scan_repo(root, cfg), load_ledger(root), cfg)
    assert res.files["src/ai.py"].understood == 7


def test_mark_line_ranges_and_percent_scores(mixed_repo):
    root, cfg = mixed_repo.root, Config()
    recs = mark(root, cfg, ["src/ai.py:1-6"], 85, "quiz", "dev@example.com", None)
    assert recs[0].score == 0.85 and len(recs[0].hashes) == 4
    res = evaluate(scan_repo(root, cfg), load_ledger(root), cfg)
    assert res.files["src/ai.py"].understood == 4 and res.files["src/ai.py"].unread == 3


def test_directory_mark_and_critical_paths(mixed_repo):
    root = mixed_repo.root
    cfg = Config(critical=["src/ai.py"])
    recs = mark(root, cfg, ["src"], 1, "explain", "dev@example.com", None)
    assert {r.path for r in recs} == {"src/human.py", "src/ai.py", "src/bot.py"}
    res = evaluate(scan_repo(root, cfg), load_ledger(root), cfg)
    assert res.total.debt == 0 and res.critical_files == ["src/ai.py"] and res.critical.lines == 7


def test_ledger_tolerates_garbage(mixed_repo):
    root = mixed_repo.root
    (root / ".grokmap").mkdir(exist_ok=True)
    (root / ".grokmap" / "ledger.jsonl").write_text(
        '# comment\nnot json\n{"path": "a.py", "score": 1, "lines": "abcdef12"}\n<<<<<<< HEAD\n'
    )
    recs = load_ledger(root)
    assert len(recs) == 1 and recs[0].hashes == frozenset({"abcdef12"})


def test_empty_repo(repo):
    scan = scan_repo(repo.root, Config())
    assert scan.head is None and not scan.files


def test_crlf_and_lf_lines_hash_the_same():
    from grokmap.scan import line_hash

    assert line_hash(normalize("return x\r")) == line_hash(normalize("return x"))


def test_own_config_is_not_counted(repo):
    repo.write(".grokmap.toml", "[grokmap]\nmax_debt = 10\n")
    repo.write("app.py", "print('hi')\n")
    repo.commit("setup")
    assert set(scan_repo(repo.root, Config()).files) == {"app.py"}
