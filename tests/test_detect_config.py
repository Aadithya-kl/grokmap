import pytest

from grokmap.config import Config, load_config, match
from grokmap.detect import Detector
from grokmap.gitutil import CommitInfo


def info(message="fix", name="Dev", email="dev@example.com", sha="a" * 40):
    return CommitInfo(sha, name, email, 0, message)


@pytest.mark.parametrize(
    "message,name,email,tool",
    [
        ("feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>", "Dev", "d@x.io", "claude"),
        ("feat: x\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)", "Dev", "d@x.io", "claude"),
        ("feat: x\n\nClaude-Session: https://claude.ai/code/session_1", "Dev", "d@x.io", "claude"),
        ("feat: x", "claude[bot]", "209825114+claude[bot]@users.noreply.github.com", "claude"),
        ("fix", "Copilot", "198982749+Copilot@users.noreply.github.com", "copilot"),
        ("fix\n\nCo-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>", "Dev", "d@x.io", "copilot"),
        ("fix\n\nCo-authored-by: Cursor Agent <cursoragent@cursor.com>", "Dev", "d@x.io", "cursor"),
        ("aider: add retry to client", "Dev", "d@x.io", "aider"),
        ("fix", "Dev (aider)", "d@x.io", "aider"),
        ("fix", "devin-ai-integration[bot]", "158243242+devin-ai-integration[bot]@users.noreply.github.com", "devin"),
        ("fix\n\nCo-authored-by: Gemini <gemini@google.com>", "Dev", "d@x.io", "gemini"),
        ("fix\n\nCo-authored-by: Codex <codex@openai.com>", "Dev", "d@x.io", "codex"),
        ("fix\n\nAI-Assisted: yes", "Dev", "d@x.io", "ai"),
    ],
)
def test_builtin_signatures(message, name, email, tool):
    assert Detector.build().tool_for(info(message, name, email)) == tool


@pytest.mark.parametrize(
    "message,name,email",
    [
        ("Refactor claude integration module", "Dev", "d@x.io"),  # mentions claude, but not as co-author
        ("fix copilot settings page", "Dev", "d@x.io"),
        ("normal commit\n\nCo-authored-by: Jane Doe <jane@example.com>", "Dev", "d@x.io"),
        ("fix", "Sam", "sam@openai.com"),  # people who work at AI labs are not bots
        ("fix", "Sam", "sam@anthropic.com"),
    ],
)
def test_human_commits_stay_human(message, name, email):
    assert Detector.build().tool_for(info(message, name, email)) is None


def test_custom_patterns_and_forced_commits():
    d = Detector.build({"internal": "^co-authored-by:.*helperbot", "farm": "author:render-farm"}, {"abc123": "claude"})
    assert d.tool_for(info("x\n\nCo-authored-by: HelperBot <b@x.io>")) == "internal"
    assert d.tool_for(info("x", name="render-farm")) == "farm"
    assert d.tool_for(info("plain", sha="abc123" + "0" * 34)) == "claude"


@pytest.mark.parametrize(
    "path,pattern,expected",
    [
        ("node_modules/a/b.js", "node_modules/**", True),
        ("web/node_modules/a/b.js", "node_modules/**", True),
        ("src/app.min.js", "*.min.js", True),
        ("src/app.js", "*.min.js", False),
        ("docs/guide.md", "docs/*.md", True),
        ("docs/deep/guide.md", "docs/*.md", False),
        ("src/core/x.py", "src/core/**", True),
        ("src/corex/x.py", "src/core/**", False),
    ],
)
def test_glob_matching(path, pattern, expected):
    assert match(path, pattern) is expected


def test_default_excludes_and_include_list():
    cfg = Config()
    assert not cfg.is_included("package-lock.json")
    assert not cfg.is_included("dist/bundle.js")
    assert cfg.is_included("src/main.py")
    cfg.include = ["src/**"]
    assert not cfg.is_included("scripts/x.py")


def test_load_config_from_toml_and_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.grokmap]\nmax_debt = 12\ncritical = ["src/pay/**"]\n')
    cfg = load_config(tmp_path)
    assert cfg.max_debt == 12 and cfg.is_critical("src/pay/a.py")
    (tmp_path / ".grokmap.toml").write_text('[grokmap]\npass_score = 0.9\n[grokmap.ai_patterns]\nbot = "x"\n')
    cfg = load_config(tmp_path)
    assert cfg.pass_score == 0.9 and cfg.max_debt == 40 and cfg.ai_patterns == {"bot": "x"}
