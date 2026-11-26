"""Decide whether a commit was written (or co-written) by an AI coding agent.

Detection is evidence-based: we only flag a commit when its metadata carries a
marker the tools themselves leave behind (co-author trailers, bot authors,
"Generated with" footers). Teams can add their own patterns in config.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from grokmap.gitutil import CommitInfo

# (tool, where, pattern). where: "message" | "author"
BUILTIN_SIGNATURES: list[tuple[str, str, str]] = [
    # Anthropic Claude / Claude Code
    ("claude", "message", r"^co-authored-by:.*\b(claude|anthropic)\b"),
    ("claude", "message", r"generated with \[?claude code"),
    ("claude", "message", r"^claude-session:"),
    ("claude", "message", r"^assisted-by:.*\bclaude\b"),
    ("claude", "author", r"\bclaude\[bot\]|noreply@anthropic\.com"),
    # GitHub Copilot (agent mode, coding agent, co-author trailer)
    ("copilot", "message", r"^co-authored-by:.*\b(copilot|github copilot)\b"),
    ("copilot", "author", r"copilot-swe-agent|^copilot\b|copilot@github\.com|\bcopilot\[bot\]"),
    ("copilot", "message", r"^\(written by copilot\)|^assisted-by:.*\bcopilot\b"),
    # Cursor
    ("cursor", "message", r"^co-authored-by:.*\bcursor(agent)?\b"),
    ("cursor", "author", r"cursoragent@cursor\.com|\bcursor agent\b"),
    # OpenAI Codex / ChatGPT
    ("codex", "message", r"^co-authored-by:.*\b(codex|chatgpt|openai)\b"),
    ("codex", "author", r"\bchatgpt-codex|codex\[bot\]"),
    ("codex", "message", r"^assisted-by:.*\b(codex|gpt-\d)"),
    # Charm Crush
    ("crush", "message", r"^co-authored-by:.*<crush@charm\.land>"),
    ("crush", "author", r"crush@charm\.land"),
    # Aider
    ("aider", "message", r"^aider:"),
    ("aider", "message", r"^co-authored-by:.*\baider\b"),
    ("aider", "author", r"\(aider\)"),
    # Devin
    ("devin", "author", r"devin-ai-integration|\bdevin\b.*\[bot\]"),
    ("devin", "message", r"^co-authored-by:.*\bdevin\b"),
    # Google Gemini / Jules
    ("gemini", "message", r"^co-authored-by:.*\b(gemini|jules)\b"),
    ("gemini", "author", r"gemini-code-assist|google-labs-jules|\bjules\[bot\]"),
    # Amazon Q / Kiro
    ("amazon-q", "message", r"^co-authored-by:.*\b(amazon q|kiro)\b"),
    # Windsurf / Codeium
    ("windsurf", "message", r"^co-authored-by:.*\b(windsurf|codeium|cascade)\b"),
    # Generic marker many teams adopt
    ("ai", "message", r"^(ai-assisted|ai-generated):"),
    ("ai", "message", r"^assisted-by:.*\b(ai|llm|gpt|gemini|agent|model)\b"),
]


@dataclass
class Detector:
    signatures: list[tuple[str, str, re.Pattern[str]]]
    forced: dict[str, str]  # sha prefix -> tool, from config

    @classmethod
    def build(cls, extra: dict[str, str] | None = None, forced: dict[str, str] | None = None) -> Detector:
        sigs = [(tool, where, re.compile(pat, re.IGNORECASE | re.MULTILINE)) for tool, where, pat in BUILTIN_SIGNATURES]
        for tool, pat in (extra or {}).items():
            where = "message"
            if pat.startswith("author:"):
                where, pat = "author", pat[len("author:") :]
            sigs.append((tool, where, re.compile(pat, re.IGNORECASE | re.MULTILINE)))
        return cls(sigs, {k.lower(): v for k, v in (forced or {}).items()})

    def tool_for(self, info: CommitInfo) -> str | None:
        for prefix, tool in self.forced.items():
            if info.sha.lower().startswith(prefix):
                return tool or None
        author = f"{info.author_name} <{info.author_email}>"
        for tool, where, rx in self.signatures:
            text = info.message if where == "message" else author
            if rx.search(text):
                return tool
        return None
