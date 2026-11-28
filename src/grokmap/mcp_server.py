"""grokmap as an MCP server: coding agents can see which code nobody understands, and pay it down.

Run with `grokmap mcp` (stdio). Needs the optional dependency: pip install "grokmap[mcp]".
"""

from __future__ import annotations

import functools
from typing import Annotated, Literal

from grokmap import __version__, agent_tools, gitutil

try:
    import mcp_types
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from pydantic import Field
except ImportError as exc:  # pragma: no cover - exercised by the CLI message test
    raise ImportError('grokmap\'s MCP server needs the "mcp" package: pip install "grokmap[mcp]"') from exc

INSTRUCTIONS = """\
grokmap tracks comprehension debt: code written by AI coding agents that no person on the team has shown they understand.

How to use these tools well:
- Before you change existing code in a non-trivial way, call comprehension_risk on the files or folders involved. \
Follow its "advice": the higher the risk, the smaller and better-explained your change should be.
- When the user asks who knows a part of the code or who should review it, call who_understands.
- After you finish a substantial change the user will commit, offer once (one line, never forced) to quiz them. \
If they agree: call quiz_brief with uncommitted=true, ask the questions one at a time as the brief describes, grade honestly, \
then call record_understanding with the paths the brief gives you.
- Never call record_understanding without real answers from the person, never round scores up, and never record \
understanding for code because you wrote it. The ledger is about people.
- For a branch or pull request, pr_comprehension summarizes the AI-written lines it adds and how many anyone understands.
All tools are local: they read git history and the repository's .grokmap/ledger.jsonl, and make no network calls.
"""

READ = mcp_types.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = mcp_types.ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


def friendly(fn):
    """Turn expected failures (bad path, unknown branch, not a repo) into a clear message for the agent."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, FileNotFoundError, gitutil.GitError) as exc:
            raise ToolError(str(exc)) from None

    return wrapper


RepoArg = Annotated[str | None, Field(description="Path inside the git repository. Defaults to the server's working directory.")]

server = MCPServer(
    "grokmap",
    title="grokmap: comprehension debt",
    description="See which AI-written code nobody on the team understands, and pay it down with quizzes.",
    instructions=INSTRUCTIONS,
    website_url="https://aadithya-kl.github.io/grokmap/",
    version=__version__,
)


@server.tool(annotations=READ)
@friendly
def comprehension_risk(
    paths: Annotated[
        list[str],
        Field(description="Files or folders you are about to change, relative to the repo root. '.' means the whole repo."),
    ],
    repo: RepoArg = None,
) -> dict:
    """Rate how risky it is to change specific files or folders, based on how much of their AI-written code anyone
    on the team has shown they understand.

    When to use: before editing existing code in a non-trivial way. Follow the returned advice: at high or very high,
    keep the diff small, explain the change, and offer a quiz afterwards. For the whole repository use repo_status;
    to find a reviewer use who_understands.

    Returns {"repo", "results": [...]}, one entry per path with: risk (none, low, medium, high, very high),
    lines, ai, understood, skimmed, fading, unread, debt_pct, ai_pct, agents (lines per AI agent), understood_by
    (person -> lines), critical_path, advice, and most_unread_files. A path that does not exist has found=false.
    Lines count as AI-written when the commit that last changed them carries an AI agent's marker
    (e.g. a Co-Authored-By: Claude trailer)."""
    return agent_tools.comprehension_risk(paths, repo)


@server.tool(annotations=READ)
@friendly
def repo_status(
    top: Annotated[int, Field(description="How many of the riskiest files to list.", ge=1, le=50)] = 10,
    repo: RepoArg = None,
) -> dict:
    """Summarize comprehension debt for the whole repository: how much code is AI-written, how much of that anyone
    understands, and which files are riskiest.

    When to use: the user asks how much of the code is AI-written, where the risk is, or for an overview. For
    specific files you are about to change, use comprehension_risk instead; for change over time, use ai_trend.

    Returns {"repo", "head", "risk", "total", "critical_paths", "riskiest_files"}. total and critical_paths hold
    lines, human, ai, understood, skimmed, fading, unread, debt_pct, ai_pct, agents and understood_by.
    riskiest_files lists up to `top` files with lines, ai_lines, unread, debt_pct and critical. Debt counts unread
    AI-written lines in full and skimmed or fading ones (understood over 180 days ago) as half."""
    return agent_tools.repo_status(repo, top)


@server.tool(annotations=READ)
@friendly
def who_understands(
    path: Annotated[str, Field(description="File or folder, relative to the repo root.")],
    repo: RepoArg = None,
) -> dict:
    """List the people who have shown they understand the AI-written code at a path, and who committed to it lately.

    When to use: the user asks who knows this code, who should review a change, or whom to ask. For a risk rating
    use comprehension_risk.

    Returns {"path", "understood_by" (person -> lines they passed a quiz, explanation or review on), "ai_lines",
    "unread" (AI-written lines nobody has checked), "recent_committers": [{"name", "commits"}], "note"}.
    Committing code is not counted as understanding it: only recorded quizzes, explanations and reviews are."""
    return agent_tools.who_understands(path, repo)


@server.tool(annotations=READ)
@friendly
def quiz_brief(
    paths: Annotated[
        list[str] | None,
        Field(description="Files or folders to quiz on. Leave empty with uncommitted=true for the change just made."),
    ] = None,
    uncommitted: Annotated[bool, Field(description="Quiz on uncommitted changes and new files (what you just wrote).")] = False,
    diff_base: Annotated[
        str | None, Field(description="Quiz on everything changed since this git ref, e.g. 'main' for a branch.")
    ] = None,
    who: Annotated[str | None, Field(description="Person being quizzed. Defaults to git user.email.")] = None,
    max_lines: Annotated[int, Field(description="Cap on lines in the brief, to keep the quiz short.", ge=20, le=1000)] = 200,
    repo: RepoArg = None,
) -> dict:
    """Build a quiz brief: the exact AI-written lines a person has not yet shown they understand, with rules for
    quizzing them.

    When to use: the user asks to be quizzed, or agrees to a quiz after you finished a change (uncommitted=true for
    that change, diff_base='main' for a whole branch, paths for specific code). Ask 2 to 6 questions one at a time,
    grade each 0, 0.5 or 1, then call record_understanding with record_with.paths and the mean grade.

    Returns {"who", "nothing_to_quiz", "line_count", "truncated", "brief_markdown" (the code and quiz rules),
    "record_with": {"tool", "paths", "method", "score"}}. If nothing_to_quiz is true, tell the person there is
    nothing new for them to check. Read-only: nothing is recorded until you call record_understanding."""
    return agent_tools.quiz_brief(paths, uncommitted, diff_base, who, max_lines, repo)


@server.tool(annotations=WRITE)
@friendly
def record_understanding(
    paths: Annotated[list[str], Field(description="Paths exactly as quiz_brief returned them, e.g. 'src/a.py:10-40,55-60'.")],
    score: Annotated[float, Field(description="Mean of the grades, 0 to 1.", ge=0, le=1)],
    method: Annotated[
        Literal["quiz", "explain", "review", "pair"],
        Field(description="quiz: answered questions. explain: explained the change back. review: only skimmed (counts as half)."),
    ] = "quiz",
    who: Annotated[
        str | None,
        Field(description="Person who answered. Defaults to git user.email. Only set it when the user says who is answering."),
    ] = None,
    note: Annotated[str, Field(description="Optional short note stored with the record.")] = "",
    repo: RepoArg = None,
) -> dict:
    """Record in the shared ledger (.grokmap/ledger.jsonl) that a person showed they understand these lines.

    When to use: only after the person actually answered a quiz from quiz_brief, explained the change back to you,
    reviewed it, or paired on it, with the score they earned. Never record understanding because you or they wrote
    the code, and never round scores up. This is the only tool that writes: it appends to the ledger and changes
    nothing else. Lines edited later count as not understood again.

    Returns {"recorded", "who", "score", "counts_as" (understood, or skimmed for low scores and reviews),
    "files", "lines", "ledger" (its path), "reminder"}."""
    return agent_tools.record_understanding(paths, score, method, who, note, repo)


@server.tool(annotations=READ)
@friendly
def pr_comprehension(
    base: Annotated[str, Field(description="Branch to compare with, e.g. 'origin/main' or 'main'.")] = "origin/main",
    repo: RepoArg = None,
) -> dict:
    """Summarize a branch or pull request: the AI-written lines it adds compared with base and how many of them
    anyone understands.

    When to use: before opening or merging a pull request, or when asked how much of a branch is AI-written. For
    the whole repository use repo_status. The base ref must exist locally (run git fetch if it is missing).

    Returns {"base", "merge_base", "commits", "ai", "human", "understood", "unread", "tools" (AI lines per agent),
    "files": [{"path", "ai", "human", "understood", "unread", "partial"}], "markdown" (a ready-to-post PR comment)}."""
    return agent_tools.pr_comprehension(base, repo)


@server.tool(annotations=READ)
@friendly
def ai_trend(
    by: Annotated[Literal["auto", "week", "month"], Field(description="Bucket size.")] = "auto",
    since: Annotated[str | None, Field(description="Only commits after this date, e.g. '2026-01-01' or '6 months ago'.")] = None,
    repo: RepoArg = None,
) -> dict:
    """Show how much of the code added over time was written by each AI agent versus people, per week or month.

    When to use: the user asks how AI use has changed, which agents write the most code, or since when. For
    today's totals use repo_status. Counts lines added in commits (from git log), attributed to an AI agent when
    the commit carries its marker, e.g. a Co-Authored-By: Claude trailer or a Copilot bot author.

    Returns {"by", "summary": {"human", "ai", "ai_pct", "tools" (lines per agent)},
    "periods": [{"start", "human", "tools"}]}, oldest period first."""
    return agent_tools.ai_trend(by, since, repo)


@server.prompt(title="Quiz me on what you just wrote")
def quiz_me() -> str:
    """Start a short grokmap quiz on the uncommitted changes."""
    return (
        "Call grokmap's quiz_brief tool with uncommitted=true. Then quiz me on that code exactly as the brief says: "
        "one question at a time, wait for my answer, grade it honestly, explain the right answer briefly. At the end, "
        "call record_understanding with the paths from the brief and my average score, and tell me my score."
    )


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
