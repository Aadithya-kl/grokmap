"""Typed results for the MCP tools, so clients get an outputSchema and structuredContent.

Field descriptions are what an agent reads to interpret a result, so keep them short and exact.
Models allow extra keys: a newer grokmap can add a field without breaking an older client.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Risk = Literal["none", "low", "medium", "high", "very high"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class LineStats(_Model):
    lines: int = Field(description="Meaningful lines scanned.")
    human: int = Field(description="Lines written by people.")
    ai: int = Field(description="Lines written by AI coding agents.")
    understood: int = Field(description="AI-written lines someone has shown they understand.")
    fading: int = Field(description="AI-written lines understood more than 180 days ago.")
    skimmed: int = Field(description="AI-written lines only reviewed, or quizzed with a low score.")
    unread: int = Field(description="AI-written lines nobody has checked.")
    debt_lines: float = Field(description="unread + half of skimmed and fading.")
    debt_pct: float = Field(description="Comprehension debt: debt_lines as a percentage of all lines.")
    ai_pct: float = Field(description="Share of lines written by AI, in percent.")
    understood_by: dict[str, int] = Field(description="Person (git email) -> AI-written lines they understand.")
    agents: dict[str, int] = Field(description="AI agent -> lines it wrote.")


class RiskyFile(_Model):
    path: str
    lines: int
    ai_lines: int
    unread: int
    debt_pct: float
    critical: bool = Field(description="Matches a critical path in .grokmap.toml.")


class RepoStatus(_Model):
    repo: str = Field(description="Repository folder name.")
    head: str = Field(description="Commit scanned (short SHA).")
    risk: Risk = Field(description="Overall risk level for the repository.")
    total: LineStats
    critical_paths: LineStats | None = Field(description="Same numbers for critical paths only; null if none are configured.")
    riskiest_files: list[RiskyFile] = Field(description="Files with the most comprehension debt, worst first.")


class UnreadFile(_Model):
    path: str
    unread: int


class PathRisk(_Model):
    path: str = Field(description="The path as you passed it.")
    found: bool = Field(description="False if the path is not a tracked file or folder; then only note is set.")
    note: str | None = None
    files: int | None = Field(default=None, description="Tracked files under the path.")
    risk: Risk | None = None
    critical_path: bool | None = Field(default=None, description="Any file under the path is on a critical path.")
    lines: int | None = None
    ai: int | None = None
    understood: int | None = None
    skimmed: int | None = None
    fading: int | None = None
    unread: int | None = None
    debt_pct: float | None = None
    ai_pct: float | None = None
    agents: dict[str, int] | None = None
    understood_by: dict[str, int] | None = None
    advice: str | None = Field(default=None, description="How carefully to change this code. Follow it.")
    most_unread_files: list[UnreadFile] | None = Field(default=None, description="For folders: files with the most unread lines.")


class ComprehensionRisk(_Model):
    repo: str
    results: list[PathRisk] = Field(description="One entry per path, in the order given.")


class Committer(_Model):
    name: str
    commits: int


class WhoUnderstands(_Model):
    path: str
    understood_by: dict[str, int] = Field(description="Person -> AI-written lines they passed a quiz, explanation or review on.")
    ai_lines: int
    unread: int = Field(description="AI-written lines nobody has checked.")
    recent_committers: list[Committer] = Field(description="Most frequent recent committers. Committing is not understanding.")
    note: str


class RecordWith(_Model):
    tool: str
    paths: list[str] = Field(description="Pass these unchanged to record_understanding.")
    method: str
    score: str


class QuizBrief(_Model):
    who: str = Field(description="Person being quizzed.")
    nothing_to_quiz: bool = Field(description="True if they already understand all of it, or there is no AI-written code.")
    truncated: bool = Field(description="True if the brief was cut at max_lines.")
    line_count: int
    record_with: RecordWith = Field(description="How to record the result once the quiz is done.")
    brief_markdown: str = Field(description="The code to quiz on, and the rules for running the quiz.")


class RecordResult(_Model):
    recorded: int = Field(description="Files recorded.")
    who: str
    score: float | None
    counts_as: str | None = Field(description="understood, or skimmed for low scores and reviews.")
    lines: int
    files: list[str]
    ledger: str = Field(description="Ledger file that was appended to.")
    reminder: str


class PrFile(_Model):
    path: str
    ai: int
    human: int
    understood: int
    unread: int
    partial: bool = Field(description="Only part of the file's AI-written lines are understood.")


class PrComprehension(_Model):
    base: str
    merge_base: str
    commits: int
    ai: int = Field(description="AI-written lines the branch adds.")
    human: int
    understood: int
    unread: int
    tools: dict[str, int] = Field(description="AI agent -> lines it added on this branch.")
    files: list[PrFile]
    markdown: str = Field(description="Ready-to-post pull request comment.")


class TrendSummary(_Model):
    human: int
    ai: int
    ai_pct: float
    tools: dict[str, int] = Field(description="AI agent -> lines added over the whole range.")


class TrendPeriod(_Model):
    start: str = Field(description="First day of the week or month (ISO date).")
    human: int
    tools: dict[str, int] = Field(description="AI agent -> lines added in this period.")


class AiTrend(_Model):
    by: str = Field(description="week or month.")
    summary: TrendSummary
    periods: list[TrendPeriod] = Field(description="Oldest first.")
