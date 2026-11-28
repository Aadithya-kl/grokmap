"""Configuration: `.grokmap.toml` at the repo root, or `[tool.grokmap]` in pyproject.toml."""

from __future__ import annotations

import functools
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_EXCLUDE = [
    # dependencies and build output
    "node_modules/**",
    "vendor/**",
    "third_party/**",
    "dist/**",
    "build/**",
    "out/**",
    ".venv/**",
    "venv/**",
    "__pycache__/**",
    "target/**",
    ".next/**",
    "coverage/**",
    # generated and lock files
    "*.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "uv.lock",
    "Cargo.lock",
    "go.sum",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.snap",
    "*.pb.go",
    "*_pb2.py",
    # data, media and binaries
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.webp",
    "*.pdf",
    "*.zip",
    "*.gz",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "*.mp4",
    "*.mp3",
    "*.wav",
    "*.csv",
    "*.tsv",
    "*.parquet",
    "*.ipynb",
    # grokmap's own state
    ".grokmap/**",
    ".grokmap.toml",
    "grokmap-report.html",
    "grokmap-badge.svg",
]


@dataclass
class Config:
    pass_score: float = 0.7
    decay_days: int = 180
    max_debt: float = 40.0
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    critical: list[str] = field(default_factory=list)
    ai_patterns: dict[str, str] = field(default_factory=dict)
    ai_commits: dict[str, str] = field(default_factory=dict)
    max_file_lines: int = 20000

    def is_included(self, path: str) -> bool:
        if self.include and not any(match(path, g) for g in self.include):
            return False
        return not any(match(path, g) for g in DEFAULT_EXCLUDE + self.exclude)

    def is_critical(self, path: str) -> bool:
        return any(match(path, g) for g in self.critical)


def match(path: str, pattern: str) -> bool:
    """Glob match where `dir/**` matches anything below dir and a bare name matches at any depth."""
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/") or ("/" + prefix + "/") in ("/" + path)
    if "/" not in pattern:
        return _glob(pattern).fullmatch(path.rsplit("/", 1)[-1]) is not None
    return _glob(pattern).fullmatch(path) is not None


@functools.lru_cache(maxsize=512)
def _glob(pattern: str) -> re.Pattern[str]:
    """Translate a glob: `**` crosses folders, `*` and `?` stay within one path segment."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        out.append("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c))
        i += 1
    return re.compile("".join(out))


def load_config(root: Path) -> Config:
    data: dict = {}
    toml_path = root / ".grokmap.toml"
    pyproject = root / "pyproject.toml"
    if toml_path.exists():
        raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        data = raw.get("grokmap", raw)
    elif pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}).get("grokmap", {})
        except tomllib.TOMLDecodeError:
            data = {}
    cfg = Config()
    for key in ("pass_score", "decay_days", "max_debt", "max_file_lines"):
        if key in data:
            setattr(cfg, key, type(getattr(cfg, key))(data[key]))
    for key in ("include", "exclude", "critical"):
        if key in data:
            setattr(cfg, key, [str(x) for x in data[key]])
    if "ai_patterns" in data:
        cfg.ai_patterns = {str(k): str(v) for k, v in data["ai_patterns"].items()}
    if "ai_commits" in data:
        cfg.ai_commits = {str(k): str(v) for k, v in data["ai_commits"].items()}
    return cfg


DEFAULT_TOML = """\
# grokmap configuration — https://github.com/Aadithya-kl/grokmap
[grokmap]
# A quiz score at or above this counts as "understood" (0.0 - 1.0).
pass_score = 0.7
# Understanding older than this many days counts as "fading" (0 = never fades).
decay_days = 180
# `grokmap check` fails when comprehension debt (%) is above this.
max_debt = 40
# Extra globs to skip, on top of the built-in list (lock files, build output, media...).
exclude = []
# Paths where debt matters most; `grokmap check --critical` only looks at these.
critical = []

# Extra AI signatures: tool = "regex on the commit message", or "author:regex".
[grokmap.ai_patterns]
# internal-bot = "^co-authored-by:.*internal-bot"

# Mark specific commits as AI-written (sha prefix = tool), e.g. before trailers were used.
[grokmap.ai_commits]
# "3f2a9c1" = "claude"
"""


def add_excludes(root: Path, globs: list[str], remove: bool = False) -> tuple[Path, list[str]]:
    """Add (or remove) globs in the `exclude` list of `.grokmap.toml`, creating the file if needed.

    Returns the config path and the resulting list. Raises ValueError when the configuration
    lives in pyproject.toml, which we don't rewrite.
    """
    import json
    import re

    path = root / ".grokmap.toml"
    if not path.exists():
        pyproject = root / "pyproject.toml"
        if pyproject.exists() and "grokmap" in tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}):
            raise ValueError(
                "this repository keeps its Grok-map settings in pyproject.toml; add the paths to [tool.grokmap] exclude there"
            )
        path.write_text(DEFAULT_TOML, encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    current = [str(g) for g in tomllib.loads(text).get("grokmap", {}).get("exclude", [])]
    if remove:
        updated = [g for g in current if g not in globs]
    else:
        updated = current + [g for g in globs if g not in current]
    rendered = "exclude = [" + ", ".join(json.dumps(g) for g in updated) + "]"
    section = re.search(r"(?m)^\[grokmap\]\s*$", text)
    key = re.compile(r"(?ms)^exclude\s*=\s*\[.*?\]")
    found = key.search(text, section.end() if section else 0)
    if found:
        text = text[: found.start()] + rendered + text[found.end() :]
    elif section:
        text = text[: section.end()] + "\n" + rendered + text[section.end() :]
    else:
        text = text.rstrip("\n") + "\n\n[grokmap]\n" + rendered + "\n"
    tomllib.loads(text)  # never write a file we can't read back
    path.write_text(text, encoding="utf-8")
    return path, updated
