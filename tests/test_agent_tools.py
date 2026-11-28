import asyncio
import json

import pytest
from conftest import CLAUDE_TRAILER

from grokmap import agent_tools


def test_comprehension_risk_levels_and_advice(mixed_repo):
    root = str(mixed_repo.root)
    out = agent_tools.comprehension_risk(["src/human.py", "src/ai.py", "src", "missing.py"], root)
    by = {r["path"]: r for r in out["results"]}
    assert by["src/human.py"]["risk"] == "none" and by["src/human.py"]["ai"] == 0
    assert by["src/ai.py"]["risk"] == "very high" and by["src/ai.py"]["unread"] == 7
    assert "summarize how it works" in by["src/ai.py"]["advice"]
    assert by["src"]["files"] == 3 and by["src"]["most_unread_files"][0]["path"] == "src/ai.py"
    assert by["missing.py"]["found"] is False


def test_risk_drops_after_quiz_and_rises_for_critical(mixed_repo):
    root = str(mixed_repo.root)
    brief = agent_tools.quiz_brief(["src/ai.py"], repo=root)
    assert not brief["nothing_to_quiz"] and brief["record_with"]["paths"][0].startswith("src/ai.py:")
    assert "## Code to quiz on" in brief["brief_markdown"]
    rec = agent_tools.record_understanding(brief["record_with"]["paths"], 0.9, repo=root)
    assert rec["counts_as"] == "understood" and rec["files"] == ["src/ai.py"]
    after = agent_tools.comprehension_risk(["src/ai.py"], root)["results"][0]
    assert after["risk"] == "low" and after["understood_by"] == {"dev@example.com": 7}
    assert agent_tools.quiz_brief(["src/ai.py"], repo=root)["nothing_to_quiz"]

    (mixed_repo.root / ".grokmap.toml").write_text('[grokmap]\ncritical = ["src/bot.py"]\n')
    agent_tools.record_understanding(["src/bot.py:1-4"], 1.0, repo=root)  # 4 of 5 lines understood -> 20% debt
    bot = agent_tools.comprehension_risk(["src/bot.py"], root)["results"][0]
    assert bot["critical_path"] and bot["risk"] == "high"  # medium, bumped one level for a critical path


def test_record_review_counts_as_skimmed_and_rejects_bad_method(mixed_repo):
    root = str(mixed_repo.root)
    assert agent_tools.record_understanding(["src/bot.py"], 1.0, method="review", repo=root)["counts_as"] == "skimmed"
    with pytest.raises(ValueError):
        agent_tools.record_understanding(["src/bot.py"], 1.0, method="vibes", repo=root)


def test_absolute_paths_are_accepted(mixed_repo):
    full = str(mixed_repo.root / "src" / "ai.py")
    out = agent_tools.comprehension_risk([full], str(mixed_repo.root))
    assert out["results"][0]["found"] and out["results"][0]["ai"] == 7


def test_who_understands_and_status_and_trend(mixed_repo):
    root = str(mixed_repo.root)
    who = agent_tools.who_understands("src/bot.py", root)
    assert who["understood_by"] == {} and who["recent_committers"][0]["name"].startswith("Copilot")
    status = agent_tools.repo_status(root, top=2)
    assert status["total"]["ai"] == 12 and len(status["riskiest_files"]) == 2
    assert agent_tools.ai_trend("month", repo=root)["summary"]["tools"] == {"claude": 11, "copilot": 5}


def test_pr_comprehension_and_bad_base(mixed_repo):
    repo = mixed_repo
    repo.git("checkout", "-q", "-b", "feature")
    repo.write("src/new.py", "def f():\n    return 1\n")
    repo.commit("feat" + CLAUDE_TRAILER)
    out = agent_tools.pr_comprehension("main", str(repo.root))
    assert out["ai"] == 2 and out["markdown"].startswith("<!-- grokmap:pr-summary -->")
    with pytest.raises(ValueError, match="cannot compare"):
        agent_tools.pr_comprehension("does-not-exist", str(repo.root))


def test_mcp_server_lists_and_calls_tools(mixed_repo):
    pytest.importorskip("mcp")
    from grokmap.mcp_server import server

    async def run():
        tools = {t.name: t for t in await server.list_tools()}
        assert set(tools) == {
            "comprehension_risk",
            "repo_status",
            "who_understands",
            "quiz_brief",
            "record_understanding",
            "pr_comprehension",
            "ai_trend",
        }
        assert tools["comprehension_risk"].annotations.read_only_hint is True
        assert tools["record_understanding"].annotations.read_only_hint is False
        res = await server.call_tool("comprehension_risk", {"paths": ["src/ai.py"], "repo": str(mixed_repo.root)})
        data = json.loads(res.content[0].text)
        assert data["results"][0]["risk"] == "very high"
        from mcp.server.mcpserver.exceptions import ToolError

        # a clear message, not a crash (over stdio the client receives it as an error result)
        with pytest.raises(ToolError, match="cannot compare with 'nope'"):
            await server.call_tool("pr_comprehension", {"base": "nope", "repo": str(mixed_repo.root)})
        prompts = await server.list_prompts()
        assert [p.name for p in prompts] == ["quiz_me"]

    asyncio.run(run())


def test_all_version_numbers_agree():
    import re
    import tomllib
    from pathlib import Path

    import grokmap

    root = Path(__file__).resolve().parent.parent
    server = json.loads((root / "server.json").read_text())
    mcp_pkg = tomllib.loads((root / "packages/grokmap-mcp/pyproject.toml").read_text())["project"]
    versions = {
        tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"],
        mcp_pkg["version"],
        server["version"],
        server["packages"][0]["version"],
        json.loads((root / ".claude-plugin/plugin.json").read_text())["version"],
        json.loads((root / "editors/vscode/package.json").read_text())["version"],
        grokmap.__version__,
    }
    assert len(versions) == 1, versions
    assert mcp_pkg["dependencies"] == [f"grokmap[mcp]=={grokmap.__version__}"]
    readme = (root / "packages/grokmap-mcp/README.md").read_text()
    assert re.search(rf"mcp-name: {re.escape(server['name'])}\s", readme)


def test_every_mcp_tool_declares_an_output_schema():
    import asyncio

    from grokmap.mcp_server import server

    tools = asyncio.run(server.list_tools())
    assert len(tools) == 7
    for t in tools:
        assert t.output_schema, t.name
        assert t.annotations is not None, t.name
